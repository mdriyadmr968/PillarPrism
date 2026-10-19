import subprocess
from pathlib import Path
from typing import Optional, Tuple


def escape_ffmpeg_path(path: Path) -> str:
    """Escape Windows drive colons and backslashes for FFmpeg filter arguments."""
    p_str = str(path.resolve()).replace("\\", "/")
    # Escape colon (e.g. C: -> C\:)
    return p_str.replace(":", "\\:")


def render_vertical_short(
    source_video_path: Path,
    output_clip_path: Path,
    start_sec: float,
    end_sec: float,
    crop_filter: str,
    ass_subtitle_path: Optional[Path] = None,
    normalize_audio: bool = True,
    target_width: int = 1080,
    target_height: int = 1920,
) -> Path:
    source_video_path = Path(source_video_path).resolve()
    output_clip_path = Path(output_clip_path).resolve()
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_video_path.exists():
        raise FileNotFoundError(f"Source video not found: {source_video_path}")

    # Build video filter chain
    vf_components = [
        crop_filter,
        f"scale={target_width}:{target_height}:flags=lanczos"
    ]

    if ass_subtitle_path:
        ass_path = Path(ass_subtitle_path).resolve()
        if ass_path.exists():
            escaped_ass = escape_ffmpeg_path(ass_path)
            vf_components.append(f"ass='{escaped_ass}'")

    vf_string = ",".join(vf_components)

    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{start_sec:.3f}",
        "-to", f"{end_sec:.3f}",
        "-i", str(source_video_path),
        "-vf", vf_string,
    ]

    if normalize_audio:
        cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])

    cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        str(output_clip_path)
    ])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg render failed: {result.stderr}")

    if not output_clip_path.exists() or output_clip_path.stat().st_size == 0:
        raise RuntimeError(f"Rendered clip file is missing or empty: {output_clip_path}")

    return output_clip_path
