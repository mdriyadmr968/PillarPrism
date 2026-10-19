import logging
import traceback
from pathlib import Path
from typing import Callable, Optional
from backend.app.config import settings
from backend.app.modules.ingestion.job_store import (
    JobStore,
    JobManifest,
    JobStatus,
    ClipInfo,
)
from backend.app.modules.ingestion.downloader import ingest_media
from backend.app.modules.ingestion.extractor import extract_metadata, extract_audio
from backend.app.modules.transcription.transcriber import WhisperTranscriber
from backend.app.modules.intelligence.gemini_client import GeminiSynthesizer
from backend.app.modules.video_processing.face_tracker import FaceTracker
from backend.app.modules.video_processing.stabilizer import CameraStabilizer
from backend.app.modules.video_processing.cropper import VideoCropper
from backend.app.modules.video_processing.renderer import render_vertical_short
from backend.app.modules.subtitles.ass_generator import generate_ass_subtitle

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(
        self,
        job_store: Optional[JobStore] = None,
        transcriber: Optional[WhisperTranscriber] = None,
        synthesizer: Optional[GeminiSynthesizer] = None,
    ):
        self.job_store = job_store or JobStore(settings.WORKSPACE_DIR)
        self.transcriber = transcriber or WhisperTranscriber(
            model_size=settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
        )
        self.synthesizer = synthesizer or GeminiSynthesizer(api_key=settings.GEMINI_API_KEY)
        self.face_tracker = FaceTracker(sample_fps=6.0)
        self.cropper = VideoCropper(target_aspect_ratio=9.0 / 16.0)

    def run_pipeline(
        self,
        job_id: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> JobManifest:
        manifest = self.job_store.get_job(job_id)
        job_dir = self.job_store.get_job_dir(job_id)
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        def _update(status: JobStatus, progress: float, step: str):
            manifest.status = status
            manifest.progress = progress
            manifest.current_step = step
            self.job_store.save_manifest(manifest)
            if progress_callback:
                progress_callback(progress, step)
            logger.info(f"[{job_id}] ({progress*100:.0f}%) {step}")

        try:
            # 1. INGESTION
            _update(JobStatus.INGESTING, 0.05, f"Ingesting media from {manifest.source_type}: {manifest.source_input}")
            video_path = ingest_media(manifest.source_input, job_dir)
            manifest.source_video_path = str(video_path)

            _update(JobStatus.INGESTING, 0.15, "Extracting video metadata and audio track...")
            meta = extract_metadata(video_path)
            manifest.metadata = meta

            audio_path = job_dir / "audio.wav"
            extract_audio(video_path, audio_path, sample_rate=16000)
            manifest.audio_wav_path = str(audio_path)

            # 2. TRANSCRIPTION
            _update(JobStatus.TRANSCRIBING, 0.25, f"Transcribing audio with Whisper ({settings.WHISPER_MODEL})...")
            transcript_json = job_dir / "transcript.json"
            transcript_output = self.transcriber.transcribe(
                audio_path=audio_path,
                output_json_path=transcript_json,
                vad_filter=True
            )
            manifest.transcript_path = str(transcript_json)

            # 3. INTELLIGENCE & BOUNDARY SNAPPING
            _update(JobStatus.ANALYZING, 0.50, f"Evaluating viral hooks & synthesizing {manifest.target_clip_count} clips with Gemini...")
            analysis_json = job_dir / "analysis.json"
            synthesis, snapped_candidates = self.synthesizer.find_and_snap_clips(
                segments=transcript_output.segments,
                metadata=meta,
                cached_json_path=analysis_json,
                target_clip_count=manifest.target_clip_count
            )

            # Inject attribution if Creative Commons source
            li_dict = synthesis.linkedin.model_dump()
            tw_dict = synthesis.twitter_thread.model_dump()
            nl_dict = synthesis.newsletter.model_dump()
            if manifest.attribution_text:
                attr_note = f"\n\nSource Attribution: {manifest.attribution_text}"
                li_dict["full_text"] += attr_note
                if tw_dict.get("tweets"):
                    tw_dict["tweets"][-1] += f" ({manifest.attribution_text})"
                nl_dict["full_markdown"] += f"\n\n---\n**Source License & Attribution:** {manifest.attribution_text}"

            manifest.written_assets = {
                "linkedin": li_dict,
                "twitter_thread": tw_dict,
                "newsletter": nl_dict,
            }

            # 4. REFRAMING & SINGLE-PASS RENDERING FOR EACH CLIP
            total_clips = len(snapped_candidates)
            rendered_clips: list[ClipInfo] = []

            for idx, (candidate, snapped) in enumerate(snapped_candidates):
                clip_num = idx + 1
                clip_id = f"clip_{clip_num:02d}"
                clip_progress_base = 0.60 + (0.35 * (idx / max(1, total_clips)))

                _update(
                    JobStatus.CROPPING,
                    clip_progress_base,
                    f"Tracking speaker & reframing clip {clip_num}/{total_clips}: '{candidate.title}'"
                )

                # Computer vision tracking on clip window
                tracks = self.face_tracker.track_clip(
                    video_path=video_path,
                    start_sec=snapped.snapped_start,
                    end_sec=snapped.snapped_end
                )

                crop_w, crop_h = self.cropper.calculate_crop_dimensions(meta.width, meta.height)
                stabilizer = CameraStabilizer(
                    frame_width=meta.width,
                    frame_height=meta.height,
                    crop_width=crop_w,
                    deadband_ratio=0.20,
                    ema_alpha=0.10
                )
                stabilized_tracks = stabilizer.stabilize(tracks)
                crop_plan = self.cropper.build_crop_plan(
                    width=meta.width,
                    height=meta.height,
                    tracks=stabilized_tracks,
                    output_dir=clips_dir,
                    clip_id=clip_id
                )

                # Generate dynamic ASS karaoke subtitle
                ass_file = clips_dir / f"{clip_id}.ass"
                generate_ass_subtitle(
                    words=snapped.relative_words,
                    output_path=ass_file,
                    font_size=58
                )

                # Single-pass FFmpeg rendering
                _update(
                    JobStatus.RENDERING,
                    clip_progress_base + (0.15 / max(1, total_clips)),
                    f"Rendering 9:16 vertical short {clip_num}/{total_clips}..."
                )
                rendered_mp4 = clips_dir / f"{clip_id}.mp4"
                render_vertical_short(
                    source_video_path=video_path,
                    output_clip_path=rendered_mp4,
                    start_sec=snapped.snapped_start,
                    end_sec=snapped.snapped_end,
                    crop_filter=crop_plan.filter_string,
                    ass_subtitle_path=ass_file,
                    normalize_audio=True,
                    target_width=1080,
                    target_height=1920
                )

                rendered_clips.append(ClipInfo(
                    id=clip_id,
                    title=candidate.title,
                    start_time=snapped.snapped_start,
                    end_time=snapped.snapped_end,
                    duration=snapped.duration,
                    hook_score=candidate.hook_score,
                    hook_summary=candidate.hook_summary,
                    virality_reason=candidate.virality_reason,
                    relative_words_count=len(snapped.relative_words),
                    is_approved=False,
                    rendered_video_path=str(rendered_mp4),
                    ass_subtitle_path=str(ass_file)
                ))

            manifest.clips = rendered_clips
            manifest.approval_status = "PENDING_APPROVAL"
            _update(JobStatus.COMPLETED, 1.0, f"Successfully repurposed video into {len(rendered_clips)} vertical clips and 3 social assets ready for review and approval!")
            return manifest

        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Pipeline failed for job {job_id}: {err_msg}\n{traceback.format_exc()}")
            manifest.status = JobStatus.FAILED
            manifest.error = err_msg
            manifest.current_step = f"Failed: {err_msg}"
            self.job_store.save_manifest(manifest)
            raise
