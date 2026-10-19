# PillarPrism — Implementation Plan & Technical Architecture

This document outlines the detailed modular engineering roadmap for **PillarPrism**. Each module is designed to be decoupled, resumable, testable, and incrementally buildable.

---

## Module 1: Ingestion & Media Pipeline

### Objective
Accept either a local video file (`.mp4`, `.mov`, `.mkv`) or a streaming link (YouTube/Vimeo) and produce normalized video and audio streams inside an isolated workspace job directory.

### Key Components
* **`yt-dlp` Integration:** Robust fetching of videos with automated format selection (`bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]`).
* **FFmpeg Audio Extraction:** Slicing high-fidelity 16kHz mono `.wav` audio (`pcm_s16le`) optimized for `faster-whisper`.
* **Metadata Extraction:** Extracting duration, resolution, aspect ratio, frame rate (`fps`), and audio bitrate via `ffprobe`.
* **Storage, Caching & Job Manifest:**
  * Organizing files under `workspace/<job_id>/` (`source.mp4`, `audio.wav`, `transcript.json`, `analysis.json`, `clips/`).
  * Maintaining a persistent `job_state.json` (or SQLite record) tracking pipeline stages (`INGESTING` $\to$ `TRANSCRIBING` $\to$ `ANALYZING` $\to$ `RENDERING` $\to$ `COMPLETED` / `FAILED`) so jobs survive server restarts and skip already-completed stages.

### Deliverables
* `backend/app/modules/ingestion/downloader.py`
* `backend/app/modules/ingestion/extractor.py`
* `backend/app/modules/ingestion/job_store.py`
* Unit tests for local and URL-based imports.

---

## Module 2: Transcription & Word-Level Alignment

### Objective
Generate full-text transcriptions with word-level millisecond timestamps to enable precise video slicing and dynamic karaoke subtitle rendering.

### Key Components
* **Engine:** `faster-whisper` (CTranslate2 backend) supporting CPU (`int8`) and CUDA GPU (`float16`) acceleration with VAD (`vad_filter=True`) to prevent hallucinated timestamps during silence.
* **Model Size Selection:** Configurable model tier (`base.en` / `small.en` for fast local CPU execution, or `medium` / `large-v3-turbo` for GPU accuracy).
* **Structured Data Representation:**
  ```python
  class WordTimestamp(BaseModel):
      word: str
      start: float  # seconds
      end: float    # seconds
      probability: float

  class TranscriptSegment(BaseModel):
      id: int
      start: float
      end: float
      text: str
      words: list[WordTimestamp]
  ```

### Deliverables
* `backend/app/modules/transcription/transcriber.py`
* JSON serialization and caching (`transcript.json`) to prevent re-running Whisper on retry.

---

## Module 3: Gemini Multimodal Intelligence & Boundary Snapping

### Objective
Leverage Google **Gemini 2.5 Flash** (`gemini-2.5-flash` via free API tier) to evaluate content, pinpoint viral clip moments, snap clip boundaries to exact spoken words, and draft publication-ready written assets.

### Key Components
* **Google GenAI SDK Integration:** Utilizing `google-genai` with strict Pydantic structured output schemas (`types.GenerateContentConfig(response_mime_type="application/json", response_schema=...)`).
* **Input Mode Strategy:**
  * **Default (Transcript-First):** Feeds compact timestamped transcript segments to `gemini-2.5-flash` for near-instant, low-token analysis.
  * **Optional Multimodal Mode:** Uploads extracted `.wav` audio or low-res video via the Gemini File API to factor vocal tone and visual energy into hook scoring.
* **Viral Clip Scoring:**
  * Analyzes transcript timecodes and semantic hooks.
  * Filters for standalone 30–75 second segments with a strong opening hook ($0\text{–}3\text{s}$), sustained body, and clean resolution.
* **Deterministic Boundary Snapper:**
  * Post-processes Gemini's suggested `[start_time, end_time]` by snapping them to the exact nearest `WordTimestamp` boundaries from Module 2.
  * Appends a configurable tail padding ($+150\text{–}250\text{ms}$) so final syllables are never clipped abruptly.
  * Produces clip-relative word timestamps (`word.start - clip.start`) for downstream subtitle generation.
* **Repurposed Written Assets Engine:**
  * **LinkedIn Post:** Hook $\to$ Context $\to$ 3 Key Takeaways $\to$ Discussion prompt.
  * **X / Twitter Thread:** 5–7 tweet sequence with engagement hooks.
  * **Newsletter / Blog Summary:** Comprehensive markdown document with chapter timestamps.

### Deliverables
* `backend/app/modules/intelligence/gemini_client.py`
* `backend/app/modules/intelligence/boundary_snapper.py`
* `backend/app/modules/intelligence/prompts.py`
* `backend/app/modules/intelligence/schemas.py`

---

## Module 4: Computer Vision & Smart Re-framing (16:9 to 9:16)

### Objective
Dynamically convert widescreen horizontal footage into vertical 9:16 format (`1080x1920`) while keeping the active speaker centered without camera jitter.

### Key Components
* **Clip-Scoped Processing:** Runs CV analysis *only* on the selected `[start, end]` clip windows (seeking directly via OpenCV/FFmpeg) rather than scanning the entire long-form source video.
* **Face & Active Speaker Detection:**
  * Uses Google `MediaPipe Face Landmarker` (or Face Detection + Mouth Aspect Ratio heuristics) sampled at 5–10 fps.
  * When multiple faces are present, prioritizes the active speaker via lip-movement variance, or falls back to a centered/split crop for two-shots.
* **Deadband + Scene-Cut Stabilization:**
  * **Safe-Zone Deadband:** Keeps the 9:16 crop window completely locked when the speaker remains within the central 30% safe zone, preventing "seasick" micro-drifting from minor head nods.
  * **Smooth Panning:** Applies Exponential Moving Average (EMA) interpolation only when the speaker moves outside the deadband.
  * **Scene-Cut Reset:** Detects hard camera cuts (via frame histogram delta) and snaps the crop window immediately to the new speaker position without panning across the cut.
* **Crop Trajectory Output:** Generates piecewise crop coordinates (`sendcmd` keyframe script or segment filter expressions) consumed by the final single-pass renderer.

### Deliverables
* `backend/app/modules/video_processing/face_tracker.py`
* `backend/app/modules/video_processing/stabilizer.py`
* `backend/app/modules/video_processing/cropper.py`

---

## Module 5: Dynamic Karaoke Subtitle & Single-Pass Render Engine

### Objective
Generate viral, social-media-style animated captions where the active spoken word pops in real time, and render the final vertical short in a single lossless-pipeline FFmpeg pass.

### Key Components
* **Format:** Advanced SubStation Alpha (`.ass`) using phrase-chunked word-state override events.
* **Karaoke Phrase Highlighting:**
  * Groups clip-relative `WordTimestamp` entries into readable 2–4 word display chunks (breaking naturally on punctuation or pauses $>0.4\text{s}$).
  * Keeps all words in the current chunk visible simultaneously while applying active inline overrides (highlight color `#FFFF00` / `#00E5FF` + subtle scale pop `\fscx108\fscy108`) to the currently spoken word.
* **Bundled Typography & Cross-Platform Paths:**
  * Bundles open-source display fonts (e.g., *Montserrat Black*, *Inter ExtraBold*) in `backend/assets/fonts/`.
  * Normalizes Windows drive paths (`C\:/...`) and passes `fontsdir` to FFmpeg `ass` filter so rendering is identical across Windows, macOS, and Linux.
* **Single-Pass FFmpeg Render Pipeline (`renderer.py`):**
  * Combines clip trimming (`-ss` / `-to`), 9:16 dynamic crop + scale (`1080x1920`), `.ass` subtitle burn-in (`libass`), H.264/AAC encoding (`libx264 -preset fast -crf 20`), and EBU R128 audio loudness normalization (`loudnorm`) in **one FFmpeg pass** to maximize speed and avoid double-compression artifacts.

### Deliverables
* `backend/app/modules/subtitles/ass_generator.py`
* `backend/app/modules/video_processing/renderer.py`
* `backend/assets/fonts/` (Bundled `.ttf` font files)

---

## Module 6: Web Dashboard & CLI Interface

### Objective
Provide a unified, user-friendly interface and headless CLI to manage the repurposing pipeline.

### Key Components
* **Backend:** FastAPI service orchestrating the pipeline worker queue with persistent job status polling (`GET /api/jobs/{job_id}`) and static media serving.
* **Frontend (React + Vite + Tailwind CSS):**
  * URL input & drag-and-drop local video upload widget.
  * Step-by-step episode processing progress bar (`Ingesting` $\to$ `Transcribing` $\to$ `Finding Hooks` $\to$ `Reframing & Subtitling`).
  * Clip selection cards with inline 9:16 video player, hook scores, and transcript preview.
  * Tabbed viewer for LinkedIn, X thread, and Newsletter markdown copy with one-click copy.
  * Download buttons for rendered vertical clips (`.mp4`) and subtitle files (`.ass` / `.srt`).

### Deliverables
* `backend/app/main.py`
* `frontend/` (React + Vite + Tailwind CSS Web Dashboard)
* `cli.py` (Command-line interface for headless batch automation)

---

## Implementation Roadmap & Milestones

| Milestone | Target Scope | Output |
| :--- | :--- | :--- |
| **Phase 1** | Media Ingestion + Job Store + Whisper Transcription | Resumable pipeline from video URL/file to cached word-level `transcript.json`. |
| **Phase 2** | Gemini 2.5 Flash + Word Boundary Snapper | Automated clip discovery, exact word-snapped timestamps, & social copy JSON. |
| **Phase 3** | Clip-Scoped Face Tracking & Deadband Stabilizer | 9:16 crop coordinate generator with active-speaker detection and cut resets. |
| **Phase 4** | `.ass` Word-Pop Subtitles & Single-Pass Renderer | End-to-end 1080x1920 vertical clip rendering with burned captions and normalized audio. |
| **Phase 5** | FastAPI Backend + React/Tailwind Dashboard & CLI | Interactive web UI and CLI for end-to-end operation. |
