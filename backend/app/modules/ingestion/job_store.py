import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    CREATED = "CREATED"
    INGESTING = "INGESTING"
    TRANSCRIBING = "TRANSCRIBING"
    ANALYZING = "ANALYZING"
    CROPPING = "CROPPING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VideoMetadata(BaseModel):
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    aspect_ratio: str = "16:9"
    bitrate: int = 0
    audio_sample_rate: int = 16000
    audio_channels: int = 1


class ClipInfo(BaseModel):
    id: str
    title: str = ""
    start_time: float
    end_time: float
    duration: float = 0.0
    hook_score: int = 0
    hook_summary: str = ""
    virality_reason: str = ""
    relative_words_count: int = 0
    is_approved: bool = False
    custom_title: Optional[str] = None
    custom_caption: Optional[str] = None
    cropped_video_path: Optional[str] = None
    rendered_video_path: Optional[str] = None
    ass_subtitle_path: Optional[str] = None


class JobManifest(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.CREATED
    progress: float = 0.0
    current_step: str = "Initialized"
    source_type: str = "url"  # "url" or "local"
    source_input: str = ""
    target_clip_count: int = 3
    approval_status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, APPROVED, REJECTED, PUBLISHED
    attribution_text: Optional[str] = None
    source_video_path: Optional[str] = None
    audio_wav_path: Optional[str] = None
    transcript_path: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None
    metadata: Optional[VideoMetadata] = None
    clips: List[ClipInfo] = Field(default_factory=list)
    written_assets: Dict[str, Any] = Field(default_factory=dict)
    published_records: List[Dict[str, Any]] = Field(default_factory=list)


class JobStore:
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def get_job_dir(self, job_id: str) -> Path:
        job_dir = self.workspace_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def _get_manifest_path(self, job_id: str) -> Path:
        return self.get_job_dir(job_id) / "job_state.json"

    def create_job(
        self,
        source_input: str,
        source_type: str = "url",
        target_clip_count: int = 3,
        attribution_text: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> JobManifest:
        if not job_id:
            job_id = uuid.uuid4().hex[:12]
        manifest = JobManifest(
            job_id=job_id,
            source_input=source_input,
            source_type=source_type,
            target_clip_count=max(1, min(10, target_clip_count)),
            attribution_text=attribution_text,
            status=JobStatus.CREATED,
            current_step="Job created"
        )
        self.save_manifest(manifest)
        return manifest

    def get_job(self, job_id: str) -> JobManifest:
        manifest_path = self._get_manifest_path(job_id)
        if not manifest_path.exists():
            raise FileNotFoundError(f"Job manifest not found for job_id: {job_id}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JobManifest.model_validate(data)

    def save_manifest(self, manifest: JobManifest) -> None:
        manifest.updated_at = datetime.now(timezone.utc).isoformat()
        manifest_path = self._get_manifest_path(manifest.job_id)
        temp_path = manifest_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))
        temp_path.replace(manifest_path)

    def update_job(self, job_id: str, **kwargs) -> JobManifest:
        manifest = self.get_job(job_id)
        for key, value in kwargs.items():
            if hasattr(manifest, key):
                setattr(manifest, key, value)
        self.save_manifest(manifest)
        return manifest

    def list_jobs(self) -> List[JobManifest]:
        jobs = []
        if not self.workspace_dir.exists():
            return jobs
        for path in self.workspace_dir.iterdir():
            if path.is_dir():
                manifest_file = path / "job_state.json"
                if manifest_file.exists():
                    try:
                        jobs.append(self.get_job(path.name))
                    except Exception:
                        pass
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs
