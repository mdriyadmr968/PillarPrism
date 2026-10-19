import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from backend.app.config import settings
from backend.app.modules.ingestion.job_store import VideoMetadata
from backend.app.modules.transcription.transcriber import TranscriptSegment
from backend.app.modules.intelligence.schemas import (
    ClipCandidate,
    LinkedInPost,
    TwitterThread,
    NewsletterSummary,
    NewsletterSection,
    ContentSynthesisOutput,
)
from backend.app.modules.intelligence.prompts import SYSTEM_PROMPT, build_synthesis_prompt
from backend.app.modules.intelligence.boundary_snapper import SnappedClip, snap_clip_boundaries

logger = logging.getLogger(__name__)


def _generate_mock_synthesis(segments: List[TranscriptSegment], metadata: Optional[VideoMetadata] = None) -> ContentSynthesisOutput:
    """Fallback heuristic synthesis for testing when no Gemini API key is configured."""
    total_duration = metadata.duration if metadata else (segments[-1].end if segments else 60.0)
    
    # Heuristically pick segments to form a 45s clip
    c_start = 0.0
    c_end = min(total_duration, 45.0)
    if segments:
        c_start = segments[0].start
        target_end = c_start + 45.0
        for s in segments:
            if s.end >= target_end:
                c_end = s.end
                break

    clip = ClipCandidate(
        title="Key Insight from Episode",
        start_time=round(c_start, 2),
        end_time=round(c_end, 2),
        hook_score=88,
        hook_summary="Powerful opening statement capturing the audience's attention.",
        virality_reason="Clear single thesis with high information density for mobile feeds."
    )

    full_txt = " ".join([s.text for s in segments[:10]]) if segments else "Episode highlight summary."

    return ContentSynthesisOutput(
        clips=[clip],
        linkedin=LinkedInPost(
            hook="Most creators get content repurposing completely wrong.",
            context="Turning a 1-hour episode into 20+ viral assets shouldn't take days.",
            key_takeaways=[
                "Extract word-level millisecond timestamps to automate slicing.",
                "Keep the speaker centered with smooth camera panning.",
                "Highlight active words dynamically to double mobile watch time."
            ],
            discussion_prompt="What is your biggest bottleneck when editing video podcasts?",
            hashtags=["#ContentCreation", "#AItools", "#VideoEditing", "#Podcasting"],
            full_text="Most creators get content repurposing completely wrong.\n\nTurning a 1-hour episode into 20+ viral assets shouldn't take days.\n\nHere are 3 key takeaways:\n• Extract word-level millisecond timestamps to automate slicing.\n• Keep the speaker centered with smooth camera panning.\n• Highlight active words dynamically to double mobile watch time.\n\nWhat is your biggest bottleneck when editing video podcasts?\n\n#ContentCreation #AItools #VideoEditing"
        ),
        twitter_thread=TwitterThread(
            hook_tweet="How to turn 1 video into 10 high-performing pieces of content (without an editing team): 🧵👇",
            tweets=[
                "1/ Long-form content holds the deepest insights, but short-form drives 90% of algorithmic discovery.",
                "2/ The secret is extracting high-retention 30-60s hooks where the speaker answers a core problem.",
                "3/ Reframe 16:9 widescreen footage into 9:16 vertical shorts keeping the speaker face centered.",
                "4/ Burn animated word-by-word karaoke captions to retain silent mobile viewers.",
                "5/ Repurpose the core transcript into a LinkedIn post and Twitter thread simultaneously."
            ],
            call_to_action="If you enjoyed this breakdown, repost the first tweet and follow for more system design breakdowns!"
        ),
        newsletter=NewsletterSummary(
            title="The Pillar Content Blueprint",
            subtitle="Maximizing ROI on Every Long-Form Video Asset",
            executive_summary="A masterclass breakdown on automating video transcription, hook identification, and multi-channel content distribution.",
            sections=[
                NewsletterSection(
                    heading="1. The Power of Word-Level Slicing",
                    timestamp="00:00",
                    content="Why manual video clipping is obsolete and how automated millisecond timestamping transforms editing workflows."
                ),
                NewsletterSection(
                    heading="2. Dynamic Vertical Reframing",
                    timestamp="00:30",
                    content="Using computer vision to automatically track speakers and eliminate camera jitter."
                )
            ],
            actionable_takeaway="Start by identifying the single highest-value 45-second segment in your last video and repurpose it across 3 platforms today.",
            full_markdown="# The Pillar Content Blueprint\n\n### Maximizing ROI on Every Long-Form Video Asset\n\nA masterclass breakdown on automating video transcription, hook identification, and multi-channel content distribution.\n\n---\n\n## 1. The Power of Word-Level Slicing [00:00]\nWhy manual video clipping is obsolete and how automated millisecond timestamping transforms editing workflows.\n\n## 2. Dynamic Vertical Reframing [00:30]\nUsing computer vision to automatically track speakers and eliminate camera jitter.\n\n---\n**Actionable Takeaway:** Start by identifying the single highest-value 45-second segment in your last video and repurpose it across 3 platforms today."
        )
    )


class GeminiSynthesizer:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model

    def synthesize_content(
        self,
        segments: List[TranscriptSegment],
        metadata: Optional[VideoMetadata] = None,
        cached_json_path: Optional[Path] = None
    ) -> ContentSynthesisOutput:
        # Check cache first
        if cached_json_path:
            cached_json_path = Path(cached_json_path).resolve()
            if cached_json_path.exists() and cached_json_path.stat().st_size > 0:
                try:
                    with open(cached_json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return ContentSynthesisOutput.model_validate(data)
                except Exception:
                    pass

        # If no valid API key is present or is placeholder/test key, fallback to deterministic mock
        if not self.api_key or self.api_key in ["your_gemini_api_key_here", "test_key_123"] or len(self.api_key) < 20:
            logger.warning("No valid GEMINI_API_KEY detected. Using deterministic fallback synthesis.")
            output = _generate_mock_synthesis(segments, metadata)
        else:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                prompt = build_synthesis_prompt(segments, metadata)

                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ContentSynthesisOutput,
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.7,
                )

                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )

                raw_text = response.text
                output_data = json.loads(raw_text)
                output = ContentSynthesisOutput.model_validate(output_data)
            except Exception as e:
                logger.warning(f"Gemini API request failed ({e}). Falling back to heuristic synthesis.")
                output = _generate_mock_synthesis(segments, metadata)

        if cached_json_path:
            cached_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cached_json_path, "w", encoding="utf-8") as f:
                f.write(output.model_dump_json(indent=2))

        return output

    def find_and_snap_clips(
        self,
        segments: List[TranscriptSegment],
        metadata: Optional[VideoMetadata] = None,
        cached_json_path: Optional[Path] = None,
        tail_padding_seconds: float = 0.20
    ) -> Tuple[ContentSynthesisOutput, List[Tuple[ClipCandidate, SnappedClip]]]:
        synthesis = self.synthesize_content(segments, metadata, cached_json_path=cached_json_path)
        snapped_results: List[Tuple[ClipCandidate, SnappedClip]] = []

        for candidate in synthesis.clips:
            snapped = snap_clip_boundaries(
                suggested_start=candidate.start_time,
                suggested_end=candidate.end_time,
                segments=segments,
                tail_padding_seconds=tail_padding_seconds
            )
            snapped_results.append((candidate, snapped))

        return synthesis, snapped_results
