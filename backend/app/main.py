import asyncio
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.modules.ingestion.job_store import JobStore, JobManifest
from backend.app.pipeline import PipelineOrchestrator
from backend.app.modules.discovery.schemas import CCVideoCandidate
from backend.app.modules.discovery.finder import discover_copyright_free_videos
from backend.app.modules.publishing.schemas import PublishRequest, PublishResult
from backend.app.modules.publishing.dispatcher import SocialDispatcher

app = FastAPI(
    title="PillarPrism API",
    description="Autonomous pillar content repurposing engine powered by Gemini, CC Discovery, and Social Dispatcher",
    version="1.1.0"
)

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

job_store = JobStore(settings.WORKSPACE_DIR)
orchestrator = PipelineOrchestrator(job_store=job_store)
social_dispatcher = SocialDispatcher()


class CreateJobRequest(BaseModel):
    source_url: str
    target_clip_count: int = 3
    attribution_text: Optional[str] = None


class GeminiKeyRequest(BaseModel):
    api_key: str


class DiscoverySearchRequest(BaseModel):
    query: str
    max_results: int = 6
    platform: str = "all"


class ApproveJobRequest(BaseModel):
    approved_clip_ids: List[str] = []
    custom_linkedin_text: Optional[str] = None
    custom_twitter_tweets: Optional[List[str]] = None
    custom_titles: Optional[Dict[str, str]] = None


def _run_job_worker(job_id: str):
    try:
        orchestrator.run_pipeline(job_id)
    except Exception as e:
        # State is already recorded in manifest by orchestrator
        pass


@app.get("/api/config")
def get_config():
    return {
        "has_gemini_key": settings.has_gemini_key,
        "whisper_model": settings.WHISPER_MODEL,
        "whisper_device": settings.WHISPER_DEVICE,
        "workspace_dir": str(settings.WORKSPACE_DIR),
    }


@app.post("/api/config/gemini-key")
def update_gemini_key(req: GeminiKeyRequest):
    key = req.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    settings.GEMINI_API_KEY = key
    orchestrator.synthesizer.api_key = key
    # Persist to .env
    env_file = Path(".env")
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
        updated = False
        for i, l in enumerate(lines):
            if l.startswith("GEMINI_API_KEY="):
                lines[i] = f"GEMINI_API_KEY={key}"
                updated = True
                break
        if not updated:
            lines.append(f"GEMINI_API_KEY={key}")
    else:
        lines = [f"GEMINI_API_KEY={key}"]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "success", "has_gemini_key": True}


# --- COPYRIGHT-FREE DISCOVERY ENDPOINTS ---

@app.post("/api/discovery/search", response_model=List[CCVideoCandidate])
def search_cc_videos(req: DiscoverySearchRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    return discover_copyright_free_videos(
        query=query,
        max_results=req.max_results,
        platform=req.platform
    )


# --- JOB LIFECYCLE ENDPOINTS ---

@app.post("/api/jobs", response_model=JobManifest)
def create_url_job(req: CreateJobRequest, background_tasks: BackgroundTasks):
    url = req.source_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Source URL is required")

    clip_count = max(1, min(10, req.target_clip_count))
    manifest = job_store.create_job(
        source_input=url,
        source_type="url",
        target_clip_count=clip_count,
        attribution_text=req.attribution_text
    )
    background_tasks.add_task(_run_job_worker, manifest.job_id)
    return manifest


@app.post("/api/jobs/upload", response_model=JobManifest)
async def upload_local_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_clip_count: int = Form(3),
    attribution_text: Optional[str] = Form(None)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name cannot be empty")

    clip_count = max(1, min(10, target_clip_count))
    manifest = job_store.create_job(
        source_input=file.filename,
        source_type="local",
        target_clip_count=clip_count,
        attribution_text=attribution_text
    )
    job_dir = job_store.get_job_dir(manifest.job_id)
    dest_path = job_dir / "source.mp4"

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job_store.update_job(manifest.job_id, source_input=str(dest_path))
    background_tasks.add_task(_run_job_worker, manifest.job_id)
    return job_store.get_job(manifest.job_id)


@app.get("/api/jobs", response_model=List[JobManifest])
def list_jobs():
    return job_store.list_jobs()


@app.get("/api/jobs/{job_id}", response_model=JobManifest)
def get_job_status(job_id: str):
    try:
        return job_store.get_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


# --- APPROVAL & PUBLISHING ENDPOINTS ---

@app.post("/api/jobs/{job_id}/approve", response_model=JobManifest)
def approve_job_content(job_id: str, req: ApproveJobRequest):
    try:
        manifest = job_store.get_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update approval flags on clips
    for clip in manifest.clips:
        if req.approved_clip_ids:
            clip.is_approved = clip.id in req.approved_clip_ids
        else:
            clip.is_approved = True

        if req.custom_titles and clip.id in req.custom_titles:
            clip.custom_title = req.custom_titles[clip.id]

    # Update custom written text if provided
    if req.custom_linkedin_text and "linkedin" in manifest.written_assets:
        manifest.written_assets["linkedin"]["full_text"] = req.custom_linkedin_text

    if req.custom_twitter_tweets and "twitter_thread" in manifest.written_assets:
        manifest.written_assets["twitter_thread"]["tweets"] = req.custom_twitter_tweets

    manifest.approval_status = "APPROVED"
    job_store.save_manifest(manifest)
    return manifest


@app.post("/api/jobs/{job_id}/publish", response_model=List[PublishResult])
def publish_approved_job(job_id: str, req: PublishRequest):
    try:
        manifest = job_store.get_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")

    results = social_dispatcher.dispatch(manifest, req)
    job_store.save_manifest(manifest)
    return results


@app.get("/api/jobs/{job_id}/media/{file_path:path}")
def stream_media(job_id: str, file_path: str):
    job_dir = job_store.get_job_dir(job_id)
    target = (job_dir / file_path).resolve()

    # Security check: ensure path is within job_dir
    if not str(target).startswith(str(job_dir.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/octet-stream"
    if target.suffix == ".mp4":
        media_type = "video/mp4"
    elif target.suffix == ".wav":
        media_type = "audio/wav"
    elif target.suffix in [".ass", ".srt"]:
        media_type = "text/plain"
    elif target.suffix == ".json":
        media_type = "application/json"

    return FileResponse(target, media_type=media_type)


# Mount frontend dist if it exists
frontend_dist = Path("frontend/dist")
if frontend_dist.exists() and frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
