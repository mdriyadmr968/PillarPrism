import subprocess
from pathlib import Path
import pytest


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
