# PillarPrism — User Guide & Tutorials

Welcome to PillarPrism! This guide walks you through using both the **Interactive Web Dashboard** and the **Headless CLI** to turn long-form content into high-performing short-form video assets and social copy.

---

## 1. Getting Started & Setup

### Prerequisites
* **Python 3.10+**
* **FFmpeg** installed and accessible in your system `PATH` (verify by running `ffmpeg -version`).
* **Google Gemini API Key** (Free tier from [Google AI Studio](https://aistudio.google.com/)).

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/mdriyadmr968/PillarPrism.git
cd PillarPrism

# 2. Create and activate a Python virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux / macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Environment Configuration
Copy the template `.env.example` to `.env`:
```bash
cp .env.example .env
```
Add your credentials:
```env
GEMINI_API_KEY=your_gemini_api_key_here
WHISPER_MODEL=base
WHISPER_DEVICE=cpu

# Optional: Social Publishing API Keys
YOUTUBE_API_KEY=
TWITTER_BEARER_TOKEN=
LINKEDIN_ACCESS_TOKEN=
WEBHOOK_URL=
```
*(Note: You can also set your Gemini API key directly from the Web Dashboard without editing the file manually).*

---

## 2. Web Dashboard Workflow

To start the local web application:
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser and navigate to **`http://localhost:8000`**.

### Step 1: Configure Gemini API Key
If this is your first run, enter your Gemini API key in the top settings bar and click **Save**. The dashboard will display a green badge `Gemini: Connected`.

### Step 2: Discover Copyright-Free Content or Ingest Pillar Videos
You have three flexible input methods:
1. **🔍 CC Discovery Tab:** Enter a topic (e.g. *"Quantum Computing"*, *"Productivity Advice"*, *"AI Ethics"*). Browse returned Creative Commons and Public Domain videos with preview thumbnails and CC license tags. Click **Select for Repurposing** on any video.
2. **🌐 Direct URL Tab:** Paste a YouTube video URL, Vimeo link, or direct `.mp4` web URL.
3. **📁 Local Upload Button:** Click **Upload Local File** to choose a `.mp4`, `.mov`, or `.mkv` from your computer.

### Step 3: Choose Target Clip Count
Use the **Target Clips (1–10)** slider or input field to select how many vertical shorts you want Gemini to extract (e.g., 3 clips for a 30-minute podcast, 5 clips for an hour-long lecture).

### Step 4: Monitor Pipeline Progress
Click **Start Repurposing**. The live progress monitor displays:
* Real-time progress bar ($0\%\dots100\%$).
* Active processing stage:
  * `[15%] Ingesting media & extracting 16kHz audio...`
  * `[25%] Transcribing audio with Whisper & VAD...`
  * `[50%] Evaluating viral hooks with Gemini 2.5 Flash...`
  * `[70%] Tracking face & stabilizing 9:16 crop window...`
  * `[85%] Rendering single-pass vertical short with karaoke subtitles...`
  * `[100%] Ready for Review & Approval!`

### Step 5: Review, Edit & Approve
Once processing completes, the job switches to **`PENDING APPROVAL`**:
* **Watch Rendered Shorts:** Click play on the embedded 9:16 vertical video player to verify frame composition, face tracking, and animated word-pop karaoke subtitles.
* **Inspect Hook Scores:** Review Gemini's viral hook score ($0\text{–}100$) and virality reasoning for each clip.
* **Edit Copy:** Modify clip titles, edit the generated LinkedIn post, or tweak individual tweets in the X/Twitter thread.
* **Select Approved Clips:** Check the checkbox for each clip you wish to publish.
* **Approve & Publish:** Select your target destinations (YouTube Shorts, X/Twitter, LinkedIn, Webhook) and click **Approve & Publish**.

---

## 3. Headless CLI Workflow

For server automation, cron jobs, and background workers, PillarPrism provides a full CLI:

### 1. Discover Copyright-Free Videos
```bash
python cli.py discover "Machine Learning Lecture" --max 5
```
Output:
```text
ID              PLATFORM         DURATION   TITLE
--------------------------------------------------------------------------------
yt_abc123       YouTube (CC-BY)  45:12      Deep Learning Basics - Stanford
  URL: https://www.youtube.com/watch?v=abc123
  License: Creative Commons Attribution license (reuse allowed)
```

### 2. Repurpose Video
Process a URL or local file, specifying how many shorts to generate:
```bash
python cli.py process "https://www.youtube.com/watch?v=abc123" --clips 3
```
Or with a local file:
```bash
python cli.py process "C:/Videos/my_podcast.mp4" --clips 4
```

### 3. Check Workspace Job Status
```bash
python cli.py list
```
View detailed status for a specific job:
```bash
python cli.py status <job_id>
```

### 4. Publish Approved Content
Publish to all supported platforms:
```bash
python cli.py publish <job_id> --platforms youtube_shorts,twitter,linkedin
```
Run in simulation mode (dry run without consuming API quotas):
```bash
python cli.py publish <job_id> --platforms youtube_shorts,twitter,linkedin --simulate
```

---

## 4. Tips & Best Practices

1. **GPU Acceleration:** If an NVIDIA GPU is available with CUDA, install PyTorch with CUDA and set `WHISPER_DEVICE=cuda` in `.env` for $5\times$ faster transcription.
2. **Audio Quality:** PillarPrism automatically applies audio normalization (`loudnorm` to $-16\text{ LUFS}$), ensuring voice tracks meet social platform broadcast standards.
3. **Attribution:** When using CC-BY content, PillarPrism automatically prepends or appends attribution notices with the original author's name and license to respect copyright compliance.
