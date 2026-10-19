from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app, job_store
from backend.app.modules.ingestion.job_store import JobStatus
from backend.app.pipeline import PipelineOrchestrator


@pytest.fixture
def api_client():
    return TestClient(app)


def test_api_config(api_client: TestClient):
    res = api_client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "has_gemini_key" in data
    assert "whisper_model" in data


def test_api_gemini_key_update(api_client: TestClient):
    res = api_client.post("/api/config/gemini-key", json={"api_key": "test_key_123"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Missing key error
    res_err = api_client.post("/api/config/gemini-key", json={"api_key": "   "})
    assert res_err.status_code == 400


def test_api_jobs_flow(api_client: TestClient, tmp_path: Path):
    # Create URL Job
    res = api_client.post("/api/jobs", json={"source_url": "https://example.com/test_video.mp4"})
    assert res.status_code == 200
    job = res.json()
    job_id = job["job_id"]
    assert job["status"] in ["CREATED", "INGESTING"]

    # List Jobs
    list_res = api_client.get("/api/jobs")
    assert list_res.status_code == 200
    assert any(j["job_id"] == job_id for j in list_res.json())

    # Get Job Status
    status_res = api_client.get(f"/api/jobs/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["job_id"] == job_id


def test_pipeline_orchestrator_end_to_end(synthetic_video: Path, tmp_path: Path):
    from backend.app.modules.ingestion.job_store import JobStore
    store = JobStore(tmp_path / "workspace_test")
    manifest = store.create_job(source_input=str(synthetic_video), source_type="local")

    orchestrator = PipelineOrchestrator(job_store=store)
    final_manifest = orchestrator.run_pipeline(manifest.job_id)

    assert final_manifest.status == JobStatus.COMPLETED
    assert final_manifest.progress == 1.0
    assert final_manifest.metadata is not None
    assert final_manifest.audio_wav_path is not None
    assert Path(final_manifest.audio_wav_path).exists()
    assert final_manifest.transcript_path is not None
    assert Path(final_manifest.transcript_path).exists()
    assert len(final_manifest.clips) >= 1

    # Check rendered clip
    first_clip = final_manifest.clips[0]
    assert first_clip.rendered_video_path is not None
    assert Path(first_clip.rendered_video_path).exists()
    assert Path(first_clip.ass_subtitle_path).exists()

    # Check written assets
    assert "linkedin" in final_manifest.written_assets
    assert "twitter_thread" in final_manifest.written_assets
    assert "newsletter" in final_manifest.written_assets


def test_api_retry_job(api_client: TestClient):
    # Setup a failed job directly in job_store
    failed_manifest = job_store.create_job(source_input="https://example.com/failed.mp4", source_type="url")
    failed_manifest.status = JobStatus.FAILED
    failed_manifest.error = "Simulated download error"
    failed_manifest.current_step = "Failed: Simulated download error"
    job_store.save_manifest(failed_manifest)

    # 404 on non-existent job
    res_404 = api_client.post("/api/jobs/nonexistent_id_999/retry")
    assert res_404.status_code == 404

    # Retry the failed job
    res = api_client.post(f"/api/jobs/{failed_manifest.job_id}/retry")
    assert res.status_code == 200
    retried_data = res.json()
    assert retried_data["status"] == "INGESTING"
    assert retried_data["error"] is None
    assert retried_data["current_step"] == "Retrying pipeline..."


def test_api_stream_media_security(api_client: TestClient):
    job = job_store.create_job(source_input="https://example.com/media_test.mp4", source_type="url")
    
    # Path traversal attempt should return 403 Forbidden
    res_forbidden = api_client.get(f"/api/jobs/{job.job_id}/media/../../main.py")
    assert res_forbidden.status_code in [403, 404]

    # Non-existent file inside valid folder should return 404
    res_not_found = api_client.get(f"/api/jobs/{job.job_id}/media/nonexistent_clip.mp4")
    assert res_not_found.status_code == 404

