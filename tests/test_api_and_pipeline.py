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
