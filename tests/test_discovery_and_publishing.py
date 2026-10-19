from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app, job_store
from backend.app.modules.discovery.finder import discover_copyright_free_videos
from backend.app.modules.publishing.dispatcher import SocialDispatcher
from backend.app.modules.publishing.schemas import PublishRequest
from backend.app.modules.ingestion.job_store import JobStore


@pytest.fixture
def client():
    return TestClient(app)


def test_cc_video_discovery():
    results = discover_copyright_free_videos("Artificial Intelligence", max_results=3)
    assert len(results) >= 1
    first = results[0]
    assert first.title
    assert first.url
    assert first.license_type
    assert first.attribution_text
    assert "Creative Commons" in first.license_type or "Public Domain" in first.license_type


def test_api_discovery_search(client: TestClient):
    res = client.post("/api/discovery/search", json={"query": "Quantum Computing", "max_results": 2})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "attribution_text" in data[0]


def test_job_with_clip_count_and_approval_flow(client: TestClient, tmp_path: Path):
    # 1. Create job with 4 clips requested and attribution
    res = client.post("/api/jobs", json={
        "source_url": "https://example.com/lecture.mp4",
        "target_clip_count": 4,
        "attribution_text": "Original video by Open Edu under CC-BY 4.0."
    })
    assert res.status_code == 200
    job = res.json()
    job_id = job["job_id"]
    assert job["target_clip_count"] == 4
    assert job["attribution_text"] == "Original video by Open Edu under CC-BY 4.0."
    assert job["approval_status"] == "PENDING_APPROVAL"

    # 2. Approve job with edited LinkedIn text
    approve_res = client.post(f"/api/jobs/{job_id}/approve", json={
        "approved_clip_ids": ["clip_01", "clip_02"],
        "custom_linkedin_text": "My custom edited LinkedIn hook."
    })
    assert approve_res.status_code == 200
    appr_job = approve_res.json()
    assert appr_job["approval_status"] == "APPROVED"

    # 3. Publish approved job to multiple channels
    pub_res = client.post(f"/api/jobs/{job_id}/publish", json={
        "platforms": ["youtube_shorts", "twitter", "linkedin"],
        "simulate": True
    })
    assert pub_res.status_code == 200
    receipts = pub_res.json()
    assert len(receipts) >= 1
    platforms = [r["platform"] for r in receipts]
    assert "youtube_shorts" in platforms
    assert "twitter" in platforms
    assert "linkedin" in platforms


def test_social_dispatcher_unit(tmp_path: Path):
    store = JobStore(tmp_path / "ws")
    manifest = store.create_job("https://example.com/test.mp4")
    # Attach dummy clip
    from backend.app.modules.ingestion.job_store import ClipInfo
    manifest.clips = [
        ClipInfo(id="clip_01", title="Test Clip 1", start_time=0.0, end_time=10.0, is_approved=True)
    ]
    manifest.written_assets = {
        "linkedin": {"full_text": "Insights here."},
        "twitter_thread": {"tweets": ["Tweet 1", "Tweet 2"]}
    }
    store.save_manifest(manifest)

    dispatcher = SocialDispatcher()
    req = PublishRequest(platforms=["youtube_shorts", "twitter", "linkedin", "webhook"], simulate=True)
    results = dispatcher.dispatch(manifest, req)

    assert len(results) == 4
    for r in results:
        assert r.status in ["PUBLISHED", "SIMULATED"]
        assert r.post_url is not None
    assert manifest.approval_status == "PUBLISHED"
