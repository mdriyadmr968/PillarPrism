# PillarPrism — API Reference

The PillarPrism REST API is built with FastAPI. It handles copyright-free content discovery, video ingestion, pipeline execution, job state polling, review/approval gating, social publishing, and media streaming.

Base URL: `http://localhost:8000`  
Interactive OpenAPI Documentation: `http://localhost:8000/docs`

---

## 1. System Configuration

### `GET /api/config`
Returns system status, active Whisper model, execution device, and whether a Gemini API key is configured.

* **Response (200 OK):**
```json
{
  "has_gemini_key": true,
  "whisper_model": "base",
  "whisper_device": "cpu",
  "workspace_dir": "c:\\Projects\\PillarPrism\\workspace"
}
```

---

### `POST /api/config/gemini-key`
Dynamically sets or updates the Google Gemini API key at runtime and persists it into the local `.env` file.

* **Request Body:**
```json
{
  "api_key": "AIzaSy..."
}
```
* **Response (200 OK):**
```json
{
  "status": "success",
  "has_gemini_key": true
}
```

---

## 2. Content Discovery

### `POST /api/discovery/search`
Searches for copyright-free / Creative Commons videos on YouTube and the Internet Archive.

* **Request Body:**
```json
{
  "query": "Artificial Intelligence Lecture",
  "max_results": 6,
  "platform": "all"
}
```
* **Parameters:**
  * `query` *(string, required)*: Keyword or niche topic.
  * `max_results` *(int, default: 6)*: Number of candidates to return.
  * `platform` *(string, default: "all")*: `"youtube"`, `"archive"`, or `"all"`.
* **Response (200 OK):**
```json
[
  {
    "id": "yt_dQw4w9WgXcQ",
    "title": "Intro to Deep Learning (MIT OpenCourseWare)",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "duration_seconds": 3600.0,
    "duration_formatted": "1:00:00",
    "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    "source_platform": "YouTube (CC-BY)",
    "license_type": "Creative Commons Attribution license (reuse allowed)",
    "author": "MIT OpenCourseWare",
    "attribution_text": "Original video 'Intro to Deep Learning' by MIT OpenCourseWare under Creative Commons Attribution (reuse allowed)."
  }
]
```

---

## 3. Job Lifecycle & Ingestion

### `POST /api/jobs`
Creates a new repurposing job from a web video URL (YouTube, Vimeo, direct MP4/MKV).

* **Request Body:**
```json
{
  "source_url": "https://www.youtube.com/watch?v=example",
  "target_clip_count": 3,
  "attribution_text": "Original video by MIT OpenCourseWare under CC-BY."
}
```
* **Parameters:**
  * `source_url` *(string, required)*: Public URL to download and process.
  * `target_clip_count` *(int, default: 3, range: 1–10)*: How many vertical clips to synthesize.
  * `attribution_text` *(string, optional)*: Attribution text to append to generated social posts.
* **Response (200 OK):** Returns [`JobManifest`](#the-jobmanifest-schema) with status `CREATED`.

---

### `POST /api/jobs/upload`
Uploads a local video file from the browser and starts the repurposing pipeline.

* **Content-Type:** `multipart/form-data`
* **Form Parameters:**
  * `file` *(binary file, required)*: Video file (`.mp4`, `.mov`, `.mkv`, `.webm`).
  * `target_clip_count` *(int, default: 3, range: 1–10)*: Number of vertical shorts to generate.
  * `attribution_text` *(string, optional)*: Optional attribution note.
* **Response (200 OK):** Returns [`JobManifest`](#the-jobmanifest-schema) with status `INGESTING`.

---

### `GET /api/jobs`
Lists all repurposing jobs in the workspace.

* **Response (200 OK):**
```json
[
  {
    "job_id": "a1b2c3d4e5f6",
    "status": "COMPLETED",
    "approval_status": "PENDING_APPROVAL",
    "progress": 1.0,
    "current_step": "Successfully repurposed video into 3 vertical clips...",
    "source_input": "https://example.com/video.mp4",
    "target_clip_count": 3,
    "clips": [...]
  }
]
```

---

### `GET /api/jobs/{job_id}`
Returns the complete manifest and real-time progress for a specific job.

* **Response (200 OK):** Returns [`JobManifest`](#the-jobmanifest-schema).
* **Response (404 Not Found):** If `job_id` does not exist.

---

### `POST /api/jobs/{job_id}/retry`
Resets a failed job and re-triggers the processing pipeline worker.

* **Response (200 OK):** Updated manifest with status reset to `INGESTING`.

---

## 4. Review, Approval & Social Publishing

### `POST /api/jobs/{job_id}/approve`
Records creator edits and marks selected clips as approved for publishing.

* **Request Body:**
```json
{
  "approved_clip_ids": ["clip_01", "clip_03"],
  "custom_linkedin_text": "Edited summary with key insights...",
  "custom_twitter_tweets": [
    "Tweet 1: Key hook from our latest breakdown 🧵👇",
    "Tweet 2: Why this changes the industry..."
  ],
  "custom_titles": {
    "clip_01": "The #1 Secret to Scaling AI Agents"
  }
}
```
* **Response (200 OK):** Updated manifest with `approval_status = "APPROVED"`.

---

### `POST /api/jobs/{job_id}/publish`
Dispatches approved clips and social copy to selected platforms.

* **Request Body:**
```json
{
  "clip_ids": ["clip_01"],
  "platforms": ["youtube_shorts", "twitter", "linkedin"],
  "simulate": false
}
```
* **Parameters:**
  * `clip_ids` *(list[string], optional)*: Clip IDs to publish. If empty, all approved clips are published.
  * `platforms` *(list[string])*: Supported options: `"youtube_shorts"`, `"twitter"`, `"linkedin"`, `"webhook"`.
  * `simulate` *(bool, default: false)*: When `true`, validates payload and generates mock receipts without posting live.
* **Response (200 OK):**
```json
[
  {
    "platform": "youtube_shorts",
    "clip_id": "clip_01",
    "status": "PUBLISHED",
    "post_id": "yt_short_12345",
    "post_url": "https://youtube.com/shorts/yt_short_12345",
    "message": "Successfully dispatched 'The #1 Secret...' to YouTube Shorts."
  },
  {
    "platform": "twitter",
    "clip_id": "clip_01",
    "status": "PUBLISHED",
    "post_id": "tweet_67890",
    "post_url": "https://x.com/creator/status/tweet_67890",
    "message": "Dispatched 2 tweets in thread with video attachment to X/Twitter."
  }
]
```

---

## 5. Media Streaming

### `GET /api/jobs/{job_id}/media/{file_path:path}`
Safely streams rendered video clips, audio tracks, or subtitle files for in-browser playback.

* **Security:** Enforces path traversal sandboxing using `Path.relative_to()`. Any attempt to traverse outside `workspace/{job_id}/` returns `403 Forbidden`.
* **Example:** `GET /api/jobs/a1b2c3d4e5f6/media/clips/clip_01.mp4`

---

## 6. The `JobManifest` Schema

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "COMPLETED",
  "progress": 1.0,
  "current_step": "Pipeline finished",
  "source_input": "https://example.com/video.mp4",
  "source_type": "url",
  "target_clip_count": 3,
  "attribution_text": "Original video by Open Edu under CC-BY 4.0.",
  "approval_status": "PENDING_APPROVAL",
  "error": null,
  "metadata": {
    "duration": 600.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "aspect_ratio": "16:9"
  },
  "clips": [
    {
      "id": "clip_01",
      "title": "The Power of Prompt Caching",
      "start_time": 45.2,
      "end_time": 98.4,
      "duration": 53.2,
      "hook_score": 92,
      "hook_summary": "Reveals 80% latency reduction in LLM inference",
      "virality_reason": "High curiosity gap and immediate practical takeaway",
      "is_approved": false,
      "rendered_video_path": "workspace/a1b2c3d4e5f6/clips/clip_01.mp4",
      "ass_subtitle_path": "workspace/a1b2c3d4e5f6/clips/clip_01.ass"
    }
  ],
  "written_assets": {
    "linkedin": { "full_text": "..." },
    "twitter_thread": { "tweets": ["...", "..."] },
    "newsletter": { "subject": "...", "body": "..." }
  },
  "published_records": []
}
```
