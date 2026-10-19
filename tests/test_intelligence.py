from pathlib import Path
import pytest
from backend.app.modules.transcription.transcriber import TranscriptSegment, WordTimestamp
from backend.app.modules.ingestion.job_store import VideoMetadata
from backend.app.modules.intelligence.boundary_snapper import snap_clip_boundaries
from backend.app.modules.intelligence.prompts import build_synthesis_prompt
from backend.app.modules.intelligence.gemini_client import GeminiSynthesizer
from backend.app.modules.intelligence.schemas import ContentSynthesisOutput


@pytest.fixture
def sample_segments():
    return [
        TranscriptSegment(
            id=0,
            start=1.2,
            end=4.5,
            text="Welcome to the masterclass on content repurposing.",
            words=[
                WordTimestamp(word="Welcome", start=1.2, end=1.8),
                WordTimestamp(word="to", start=1.8, end=2.0),
                WordTimestamp(word="the", start=2.0, end=2.2),
                WordTimestamp(word="masterclass", start=2.2, end=3.0),
                WordTimestamp(word="on", start=3.0, end=3.2),
                WordTimestamp(word="content", start=3.2, end=3.8),
                WordTimestamp(word="repurposing.", start=3.8, end=4.5),
            ]
        ),
        TranscriptSegment(
            id=1,
            start=5.0,
            end=9.5,
            text="Today we are discussing viral short form formats.",
            words=[
                WordTimestamp(word="Today", start=5.0, end=5.4),
                WordTimestamp(word="we", start=5.4, end=5.6),
                WordTimestamp(word="are", start=5.6, end=5.8),
                WordTimestamp(word="discussing", start=5.8, end=6.6),
                WordTimestamp(word="viral", start=6.6, end=7.2),
                WordTimestamp(word="short", start=7.2, end=7.6),
                WordTimestamp(word="form", start=7.6, end=8.0),
                WordTimestamp(word="formats.", start=8.0, end=8.7),
            ]
        )
    ]


def test_boundary_snapper(sample_segments):
    # Request clip from 2.1 to 8.5
    snapped = snap_clip_boundaries(
        suggested_start=2.1,
        suggested_end=8.5,
        segments=sample_segments,
        tail_padding_seconds=0.20
    )

    # Starts near 2.0 or sentence start, ends after formats (8.7 + 0.20 = 8.90)
    assert snapped.snapped_start <= 2.2
    assert snapped.snapped_end >= 8.7
    assert len(snapped.relative_words) > 0
    # The first relative word must be non-negative
    assert snapped.relative_words[0].start >= 0.0
    # Relative timing offsets must preserve word durations
    assert snapped.relative_words[0].end > snapped.relative_words[0].start


def test_prompt_builder(sample_segments):
    meta = VideoMetadata(duration=120.0, width=1920, height=1080, fps=30.0)
    prompt = build_synthesis_prompt(sample_segments, meta)
    assert "Episode Duration:" in prompt
    assert "TIMESTAMPED TRANSCRIPT:" in prompt
    assert "Welcome to the masterclass" in prompt


def test_gemini_client_fallback_and_caching(sample_segments, tmp_path: Path):
    synthesizer = GeminiSynthesizer(api_key="")
    cache_file = tmp_path / "analysis.json"

    synthesis, snapped_clips = synthesizer.find_and_snap_clips(
        segments=sample_segments,
        cached_json_path=cache_file
    )

    assert isinstance(synthesis, ContentSynthesisOutput)
    assert len(synthesis.clips) >= 1
    assert len(synthesis.linkedin.key_takeaways) >= 3
    assert len(synthesis.twitter_thread.tweets) >= 3
    assert cache_file.exists()

    # Re-reading from cache without recomputing
    cached_synthesis = synthesizer.synthesize_content(sample_segments, cached_json_path=cache_file)
    assert cached_synthesis.linkedin.hook == synthesis.linkedin.hook
