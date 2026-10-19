import json
from pathlib import Path
import pytest
from backend.app.modules.transcription.transcriber import (
    WordTimestamp,
    TranscriptSegment,
    TranscriptOutput,
    WhisperTranscriber,
)


def test_transcript_models_serialization(tmp_path: Path):
    word = WordTimestamp(word="Pillar", start=0.1, end=0.5, probability=0.98)
    segment = TranscriptSegment(id=0, start=0.0, end=1.0, text="Pillar", words=[word])
    output = TranscriptOutput(
        language="en",
        duration=1.0,
        full_text="Pillar",
        segments=[segment]
    )

    json_file = tmp_path / "transcript.json"
    with open(json_file, "w", encoding="utf-8") as f:
        f.write(output.model_dump_json(indent=2))

    with open(json_file, "r", encoding="utf-8") as f:
        loaded_data = json.load(f)

    validated = TranscriptOutput.model_validate(loaded_data)
    assert validated.language == "en"
    assert len(validated.segments) == 1
    assert validated.segments[0].words[0].word == "Pillar"
    assert validated.segments[0].words[0].start == 0.1


def test_transcription_caching(tmp_path: Path):
    cached_file = tmp_path / "cached_transcript.json"
    dummy_output = TranscriptOutput(
        language="en",
        duration=3.5,
        full_text="Cached transcript test.",
        segments=[
            TranscriptSegment(
                id=0,
                start=0.0,
                end=3.5,
                text="Cached transcript test.",
                words=[
                    WordTimestamp(word="Cached", start=0.0, end=0.8, probability=0.99),
                    WordTimestamp(word="transcript", start=0.8, end=1.5, probability=0.97),
                    WordTimestamp(word="test.", start=1.5, end=2.0, probability=0.95),
                ]
            )
        ]
    )
    with open(cached_file, "w", encoding="utf-8") as f:
        f.write(dummy_output.model_dump_json())

    # WhisperTranscriber should immediately load the cache without needing audio
    transcriber = WhisperTranscriber(model_size="tiny")
    dummy_audio = tmp_path / "dummy.wav"
    dummy_audio.touch()

    result = transcriber.transcribe(dummy_audio, output_json_path=cached_file)
    assert result.duration == 3.5
    assert result.full_text == "Cached transcript test."
    assert len(result.segments[0].words) == 3


def test_transcribe_missing_audio():
    transcriber = WhisperTranscriber()
    with pytest.raises(FileNotFoundError):
        transcriber.transcribe(Path("non_existent_audio_file.wav"))
