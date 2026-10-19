import os
import shutil
from pathlib import Path
from typing import Callable, Optional
import yt_dlp


def is_url(source: str) -> bool:
    source_lower = source.strip().lower()
    return source_lower.startswith("http://") or source_lower.startswith("https://")


def ingest_media(
    source: str,
    output_dir: Path,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Path:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_video_path = output_dir / "source.mp4"

    source = source.strip()

    if not is_url(source):
        local_path = Path(source).resolve()
        if not local_path.exists():
            raise FileNotFoundError(f"Local video file does not exist: {source}")
        
        if progress_callback:
            progress_callback(0.2, f"Copying local video {local_path.name}...")

        if local_path != target_video_path:
            shutil.copy2(local_path, target_video_path)

        if progress_callback:
            progress_callback(1.0, "Local video imported successfully.")
        return target_video_path

    # URL Ingestion via yt-dlp
    if progress_callback:
        progress_callback(0.1, "Initializing yt-dlp download...")

    def _yt_dlp_hook(d: dict):
        if d.get("status") == "downloading" and progress_callback:
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total and total > 0:
                fraction = min(0.9, 0.1 + 0.8 * (downloaded / total))
                progress_callback(fraction, f"Downloading: {downloaded // 1024} KB / {total // 1024} KB")

    outtmpl_pattern = str(output_dir / "source.%(ext)s")
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best",
        "outtmpl": outtmpl_pattern,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "progress_hooks": [_yt_dlp_hook],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([source])

    # Find the resulting file
    if target_video_path.exists():
        if progress_callback:
            progress_callback(1.0, "Video download completed.")
        return target_video_path

    # Check if downloaded with different extension and convert or rename
    for candidate in output_dir.glob("source.*"):
        if candidate.suffix.lower() in [".mp4", ".mkv", ".webm", ".mov"]:
            if progress_callback:
                progress_callback(1.0, "Video download completed.")
            return candidate

    raise RuntimeError(f"Download finished but no source video was found in {output_dir}")
