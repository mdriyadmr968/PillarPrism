import subprocess
from pathlib import Path
import pytest
from backend.app.modules.ingestion.job_store import JobStore, JobStatus
from backend.app.modules.ingestion.extractor import extract_metadata, extract_audio
from backend.app.modules.ingestion.downloader import is_url, ingest_media


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory) -> Path:
    """Generate a valid 2-second 1280x720 MP4 test video with an audio stream."""
    temp_dir = tmp_path_factory.mktemp("media_fixtures")
    video_path = temp_dir / "sample.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(video_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg synthetic video creation failed: {res.stderr}"
    assert video_path.exists() and video_path.stat().st_size > 0
    return video_path


def test_is_url():
    assert is_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_url("http://example.com/video.mp4") is True
    assert is_url("C:/Videos/my_video.mp4") is False
    assert is_url("sample.mp4") is False


def test_extract_metadata(synthetic_video: Path):
    meta = extract_metadata(synthetic_video)
    assert meta.width == 1280
    assert meta.height == 720
    assert meta.aspect_ratio == "16:9"
    assert round(meta.fps) == 30
    assert 1.8 <= meta.duration <= 2.2


def test_extract_audio(synthetic_video: Path, tmp_path: Path):
    out_wav = tmp_path / "audio.wav"
    extracted = extract_audio(synthetic_video, out_wav, sample_rate=16000)
    assert extracted.exists()
    assert extracted.stat().st_size > 0
    
    # Verify audio properties using ffprobe
    meta = extract_metadata(extracted)
    assert meta.audio_sample_rate == 16000
    assert meta.audio_channels == 1


def test_job_store(tmp_path: Path):
    store = JobStore(tmp_path)
    manifest = store.create_job("https://youtube.com/test", source_type="url")
    assert manifest.status == JobStatus.CREATED
    assert manifest.job_id is not None

    # Retrieve
    loaded = store.get_job(manifest.job_id)
    assert loaded.job_id == manifest.job_id
    assert loaded.source_input == "https://youtube.com/test"

    # Update
    updated = store.update_job(
        manifest.job_id,
        status=JobStatus.INGESTING,
        progress=0.25,
        current_step="Downloading video..."
    )
    assert updated.status == JobStatus.INGESTING
    assert updated.progress == 0.25

    # List
    all_jobs = store.list_jobs()
    assert len(all_jobs) == 1
    assert all_jobs[0].job_id == manifest.job_id


def test_ingest_local_media(synthetic_video: Path, tmp_path: Path):
    job_dir = tmp_path / "job_local"
    dest = ingest_media(str(synthetic_video), job_dir)
    assert dest.exists()
    assert dest.name == "source.mp4"
    assert dest.stat().st_size == synthetic_video.stat().st_size
