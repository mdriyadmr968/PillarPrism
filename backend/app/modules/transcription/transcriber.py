import json
from pathlib import Path
from typing import Callable, List, Optional
from faster_whisper import WhisperModel
from pydantic import BaseModel, Field


class WordTimestamp(BaseModel):
    word: str
    start: float  # in seconds
    end: float    # in seconds
    probability: float = 1.0


class TranscriptSegment(BaseModel):
    id: int
    start: float  # in seconds
    end: float    # in seconds
    text: str
    words: List[WordTimestamp] = Field(default_factory=list)


class TranscriptOutput(BaseModel):
    language: str = "en"
    duration: float = 0.0
    full_text: str = ""
    segments: List[TranscriptSegment] = Field(default_factory=list)


class WhisperTranscriber:
    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8"
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        output_json_path: Optional[Path] = None,
        vad_filter: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> TranscriptOutput:
        audio_path = Path(audio_path).resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Check for existing cached output
        if output_json_path:
            output_json_path = Path(output_json_path).resolve()
            if output_json_path.exists() and output_json_path.stat().st_size > 0:
                try:
                    with open(output_json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if progress_callback:
                        progress_callback(1.0, "Loaded cached transcription.")
                    return TranscriptOutput.model_validate(data)
                except Exception:
                    pass

        if progress_callback:
            progress_callback(0.1, f"Loading Whisper ({self.model_size}) model...")

        model = self._get_model()

        if progress_callback:
            progress_callback(0.3, "Transcribing audio with word-level alignment...")

        segments_raw, info = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            vad_filter=vad_filter,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        segments: List[TranscriptSegment] = []
        all_text_parts: List[str] = []

        for seg_idx, segment in enumerate(segments_raw):
            words: List[WordTimestamp] = []
            if segment.words:
                for w in segment.words:
                    words.append(WordTimestamp(
                        word=w.word.strip(),
                        start=round(w.start, 3),
                        end=round(w.end, 3),
                        probability=round(w.probability, 3)
                    ))

            clean_text = segment.text.strip()
            all_text_parts.append(clean_text)
            segments.append(TranscriptSegment(
                id=seg_idx,
                start=round(segment.start, 3),
                end=round(segment.end, 3),
                text=clean_text,
                words=words
            ))

        output = TranscriptOutput(
            language=info.language or "en",
            duration=round(info.duration, 3),
            full_text=" ".join(all_text_parts),
            segments=segments
        )

        if output_json_path:
            output_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                f.write(output.model_dump_json(indent=2))

        if progress_callback:
            progress_callback(1.0, f"Transcription completed. {len(segments)} segments aligned.")

        return output
