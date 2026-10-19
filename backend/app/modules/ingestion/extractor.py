import json
import subprocess
from pathlib import Path
from typing import Optional
from backend.app.modules.ingestion.job_store import VideoMetadata


def _parse_fps(fps_str: Optional[str]) -> float:
    if not fps_str or fps_str == "0/0":
        return 30.0
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/")
            return round(float(num) / float(den), 3) if float(den) != 0 else 30.0
        return round(float(fps_str), 3)
    except Exception:
        return 30.0


def extract_metadata(video_path: Path) -> VideoMetadata:
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate",
        "-show_entries", "format=duration,bit_rate",
        "-of", "json",
        str(video_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed to probe video: {e.stderr}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe JSON output: {e}")

    # Extract audio stream info
    audio_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels",
        "-of", "json",
        str(video_path)
    ]
    audio_sample_rate = 16000
    audio_channels = 1
    try:
        audio_result = subprocess.run(audio_cmd, capture_output=True, text=True, check=False)
        if audio_result.returncode == 0:
            audio_data = json.loads(audio_result.stdout)
            a_streams = audio_data.get("streams", [])
            if a_streams:
                audio_sample_rate = int(a_streams[0].get("sample_rate", 16000))
                audio_channels = int(a_streams[0].get("channels", 1))
    except Exception:
        pass

    streams = data.get("streams", [])
    format_info = data.get("format", {})

    width = 0
    height = 0
    fps = 30.0

    if streams:
        v_stream = streams[0]
        width = int(v_stream.get("width", 0))
        height = int(v_stream.get("height", 0))
        fps_str = v_stream.get("r_frame_rate") or v_stream.get("avg_frame_rate")
        fps = _parse_fps(fps_str)

    duration = float(format_info.get("duration", 0.0))
    bitrate = int(format_info.get("bit_rate", 0)) if format_info.get("bit_rate") else 0

    aspect_ratio = f"{width}:{height}"
    if width > 0 and height > 0:
        ratio = width / height
        if abs(ratio - 16 / 9) < 0.05:
            aspect_ratio = "16:9"
        elif abs(ratio - 9 / 16) < 0.05:
            aspect_ratio = "9:16"
        elif abs(ratio - 4 / 3) < 0.05:
            aspect_ratio = "4:3"
        elif abs(ratio - 1.0) < 0.05:
            aspect_ratio = "1:1"

    return VideoMetadata(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        aspect_ratio=aspect_ratio,
        bitrate=bitrate,
        audio_sample_rate=audio_sample_rate,
        audio_channels=audio_channels
    )


def extract_audio(video_path: Path, output_wav_path: Path, sample_rate: int = 16000) -> Path:
    video_path = Path(video_path).resolve()
    output_wav_path = Path(output_wav_path).resolve()
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Source video not found: {video_path}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        str(output_wav_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")

    if not output_wav_path.exists() or output_wav_path.stat().st_size == 0:
        raise RuntimeError(f"Extracted audio file is missing or empty: {output_wav_path}")

    return output_wav_path
