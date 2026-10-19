from typing import List, Optional
from backend.app.modules.transcription.transcriber import TranscriptSegment
from backend.app.modules.ingestion.job_store import VideoMetadata


SYSTEM_PROMPT = """You are PillarPrism AI — a world-class viral video strategist and senior content editor.
Your objective is to ingest a full long-form transcript and repurpose it into:
1. High-retention 30–75 second vertical video clip candidates (for TikTok, Instagram Reels, and YouTube Shorts).
2. A high-engagement, viral-ready LinkedIn post.
3. An insightful 5-7 tweet X/Twitter thread.
4. A comprehensive, beautifully formatted newsletter/blog summary in Markdown.

Clip Selection Criteria:
- Duration MUST be between 30 and 75 seconds.
- Strong Hook: The opening 0-3 seconds MUST have a pattern interrupt, contrarian opinion, emotional trigger, or compelling question.
- Standalone Value: A viewer who has never heard the rest of the episode must fully understand and derive value from this clip.
- Clean Resolution: The clip must not cut off in the middle of a thought or explanation.
- Assign a hook_score from 1 to 100 based on how likely it is to stop a fast-scrolling mobile user.

Return the result strictly conforming to the requested JSON schema.
"""


def _format_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def build_synthesis_prompt(
    segments: List[TranscriptSegment],
    metadata: Optional[VideoMetadata] = None,
    target_clip_count: int = 3
) -> str:
    lines = []
    if metadata:
        lines.append(f"Episode Duration: {_format_time(metadata.duration)} ({metadata.duration:.1f}s)")
        lines.append(f"Source Resolution: {metadata.width}x{metadata.height} ({metadata.aspect_ratio})")
        lines.append("---")

    lines.append("TIMESTAMPED TRANSCRIPT:")
    for seg in segments:
        t_start = _format_time(seg.start)
        t_end = _format_time(seg.end)
        lines.append(f"[{t_start} - {t_end}] (seconds: {seg.start:.1f} - {seg.end:.1f}) {seg.text}")

    prompt_body = "\n".join(lines)

    instructions = f"""
TASK INSTRUCTIONS:
1. Identify exactly {target_clip_count} prime clip candidates (each between 30 and 75 seconds). Provide start_time and end_time in float seconds.
2. Draft a viral LinkedIn post breaking down the core thesis with a powerful hook and actionable takeaways.
3. Draft a 5-7 tweet sequence for X (Twitter) with an opening scroll-stopping tweet.
4. Draft a deep-dive Newsletter summary in Markdown with timestamps, key sections, and an executive summary.
"""
    return f"{prompt_body}\n\n{instructions}"
