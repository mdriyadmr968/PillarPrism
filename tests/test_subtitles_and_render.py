from pathlib import Path
import pytest
from backend.app.modules.transcription.transcriber import WordTimestamp
from backend.app.modules.subtitles.ass_generator import chunk_words, generate_ass_subtitle
from backend.app.modules.video_processing.renderer import escape_ffmpeg_path, render_vertical_short
from backend.app.modules.ingestion.extractor import extract_metadata


def test_chunk_words():
    words = [
        WordTimestamp(word="This", start=0.0, end=0.3),
        WordTimestamp(word="is", start=0.3, end=0.5),
        WordTimestamp(word="a", start=0.5, end=0.7),
        WordTimestamp(word="viral", start=0.7, end=1.0),
        WordTimestamp(word="short.", start=1.0, end=1.4),
        # Long pause after sentence
        WordTimestamp(word="Next", start=2.2, end=2.5),
        WordTimestamp(word="sentence", start=2.5, end=2.8),
    ]

    chunks = chunk_words(words, max_words_per_chunk=3)
    assert len(chunks) >= 2
    # First chunk has at most 3 words
    assert len(chunks[0].words) <= 3
    # Chunk with punctuation or pause broke naturally
    assert chunks[0].start == 0.0


def test_generate_ass_subtitle(tmp_path: Path):
    words = [
        WordTimestamp(word="VIRAL", start=0.0, end=0.4),
        WordTimestamp(word="CONTENT", start=0.4, end=0.9),
    ]
    ass_path = tmp_path / "test.ass"
    result_path = generate_ass_subtitle(words, ass_path)

    assert result_path.exists()
    content = result_path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "Dialogue:" in content
    assert "\\c&H0000FFFF" in content  # Highlight color tag


def test_escape_ffmpeg_path():
    test_path = Path("C:/videos/test.ass")
    escaped = escape_ffmpeg_path(test_path)
    assert "\\:" in escaped
    assert "\\" not in escaped.replace("\\:", "")


def test_render_vertical_short(synthetic_video: Path, tmp_path: Path):
    # Prepare test ass subtitle
    words = [
        WordTimestamp(word="HELLO", start=0.1, end=0.5),
        WordTimestamp(word="WORLD", start=0.5, end=0.9),
    ]
    ass_path = tmp_path / "sub.ass"
    generate_ass_subtitle(words, ass_path)

    out_mp4 = tmp_path / "rendered_short.mp4"
    crop_filter = "crop=404:720:438:0"  # 9:16 crop for 1280x720

    rendered = render_vertical_short(
        source_video_path=synthetic_video,
        output_clip_path=out_mp4,
        start_sec=0.0,
        end_sec=1.0,
        crop_filter=crop_filter,
        ass_subtitle_path=ass_path,
        target_width=1080,
        target_height=1920
    )

    assert rendered.exists()
    assert rendered.stat().st_size > 0

    # Probe rendered video to verify exact 1080x1920 9:16 dimensions
    meta = extract_metadata(rendered)
    assert meta.width == 1080
    assert meta.height == 1920
    assert meta.aspect_ratio == "9:16"
    assert meta.duration > 0.8
