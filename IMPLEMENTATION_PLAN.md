# PillarPrism — Implementation Plan & Technical Architecture

This document outlines the detailed modular engineering roadmap for **PillarPrism**. Each module is designed to be decoupled, testable, and incrementally buildable.

---

## Module 1: Ingestion & Media Pipeline

### Objective
Accept either a local video file (`.mp4`, `.mov`, `.mkv`) or a streaming link (YouTube/Vimeo) and produce normalized video and audio streams.

### Key Components
* **`yt-dlp` integration:** Robust fetching of videos with automated format selection (best video + best audio).
* **FFmpeg Audio Extraction:** Slicing high-fidelity 16kHz mono `.wav` audio for speech recognition.
* **Metadata Extraction:** Extracting duration, resolution, aspect ratio, frame rate, and audio bitrate via `ffprobe`.
* **Storage & Caching:** Organizing temporary and processed files under a workspace cache directory.

### Deliverables
* `backend/app/modules/ingestion/downloader.py`
* `backend/app/modules/ingestion/extractor.py`
* Unit tests for local and URL-based imports.

---

## Module 2: Transcription & Word-Level Alignment

### Objective
Generate full-text transcriptions with word-level millisecond timestamps to enable precise video slicing and dynamic karaoke subtitle rendering.

### Key Components
* **Engine:** `faster-whisper` (CTranslate2 backend) supporting CPU and CUDA GPU acceleration.
* **Model Size Selection:** Default to `base.en` / `small.en` for instant local execution or `medium` for maximum accuracy.
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
* JSON serialization and caching of transcription outputs to prevent re-running Whisper.

---

## Module 3: Gemini Multimodal Intelligence & Content Synthesis

### Objective
Leverage Google Gemini 1.5/2.0 Flash (via free API tier) to evaluate content, pinpoint viral clip moments, and draft publication-ready written assets.

### Key Components
* **Google GenAI SDK Integration:** Utilizing `google-genai` with structured output schemas (`types.GenerateContentConfig(response_mime_type="application/json")`).
* **Viral Clip Scoring:**
  * Analyzes transcript timecodes and semantic hooks.
  * Filters for standalone 30–75 second segments with a strong opening hook ($0\text{–}3$s), sustained body, and clean resolution.
* **Repurposed Written Assets Engine:**
  * **LinkedIn Post:** Hook $\to$ Context $\to$ 3 Key Takeaways $\to$ Discussion prompt.
  * **X / Twitter Thread:** 5–7 tweet sequence with engagement hooks.
  * **Newsletter / Blog Summary:** Comprehensive markdown document with timestamps.

### Deliverables
* `backend/app/modules/intelligence/gemini_client.py`
* `backend/app/modules/intelligence/prompts.py`
* `backend/app/modules/intelligence/schemas.py`

---

## Module 4: Computer Vision & Smart Re-framing (16:9 to 9:16)

### Objective
Dynamically convert widescreen horizontal footage into vertical 9:16 format while keeping the active speaker centered in the frame.

### Key Components
* **Face Detection:** Google `MediaPipe` Face Detection (or OpenCV Haar/DNN) running on sample frames (e.g., 5–10 fps).
* **Speaker Centering & Box Tracking:** Calculates speaker face midpoint $(x, y)$.
* **Smoothing Algorithm:** Exponential Moving Average (EMA) applied to camera panning coordinates to eliminate visual jitter.
* **FFmpeg Dynamic Crop Execution:**
  * Applies FFmpeg crop filter calculated from smoothed coordinate sequences.
  * Fallback to centered crop if no faces are detected.

### Deliverables
* `backend/app/modules/video_processing/face_tracker.py`
* `backend/app/modules/video_processing/cropper.py`

---

## Module 5: Dynamic Karaoke Subtitle Engine

### Objective
Generate viral, social-media-style animated captions where the active spoken word is highlighted in real time.

### Key Components
* **Format:** Advanced SubStation Alpha (`.ass`) with karaoke timing tags `\k`.
* **Styling Customization:**
  * Modern fonts (e.g., *Montserrat Black*, *The Bold Font*, *Inter*).
  * Color schemes (Primary: White, Active Highlight: Yellow `#FFFF00` / Cyan `#00E5FF`, Stroke: Black outline + drop shadow).
  * 2–3 words per subtitle block for high mobile readability.
* **FFmpeg Subtitle Burner:** Hardcoding `.ass` captions into the vertical `.mp4` clip via `libass`.

### Deliverables
* `backend/app/modules/subtitles/ass_generator.py`
* `backend/app/modules/subtitles/burner.py`

---

## Module 6: Web Dashboard & CLI Interface

### Objective
Provide a unified, user-friendly interface to manage the repurposing pipeline.

### Key Components
* **Backend:** FastAPI service orchestrating the processing queue with background task workers.
* **Frontend:** Modern interactive dashboard:
  * URL / File upload widget.
  * Episode processing status with progress indicators.
  * Clip selection cards with inline video player and hook scores.
  * Tabbed viewer for LinkedIn, X thread, and Newsletter markdown copy with one-click copy.
  * Download buttons for rendered vertical clips (`.mp4`) and subtitle files (`.srt`/`.ass`).

### Deliverables
* `backend/app/main.py`
* `frontend/` (Modern Web Dashboard)
* `cli.py` (Command-line interface for headless automation)

---

## Implementation Roadmap & Milestones

| Milestone | Target Scope | Output |
| :--- | :--- | :--- |
| **Phase 1** | Media Ingestion + Whisper Transcription | Working pipeline from video URL to timestamped transcript JSON. |
| **Phase 2** | Gemini API Integration | Automated clip discovery & social copy generation via Gemini Flash. |
| **Phase 3** | Face Tracking & 9:16 Cropping | Vertical video generator with smooth speaker centering. |
| **Phase 4** | Subtitle Styling & Karaoke Burning | End-to-end clip rendering with animated captions. |
| **Phase 5** | Web UI & Preview Dashboard | Interactive dashboard for end-to-end operation. |
