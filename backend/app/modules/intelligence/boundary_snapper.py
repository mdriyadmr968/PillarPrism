from typing import List, Optional, Tuple
from pydantic import BaseModel, Field
from backend.app.modules.transcription.transcriber import TranscriptSegment, WordTimestamp


class SnappedClip(BaseModel):
    original_start: float
    original_end: float
    snapped_start: float
    snapped_end: float
    duration: float
    relative_words: List[WordTimestamp] = Field(default_factory=list)


def snap_clip_boundaries(
    suggested_start: float,
    suggested_end: float,
    segments: List[TranscriptSegment],
    tail_padding_seconds: float = 0.20
) -> SnappedClip:
    """
    Deterministically snaps suggested LLM start/end timecodes to exact spoken word boundaries.
    Also produces zero-offset relative word timestamps for downstream subtitle engines.
    """
    # Flatten all words with segment context
    all_words: List[WordTimestamp] = []
    sentence_starts: List[float] = []

    for seg in segments:
        if seg.words:
            sentence_starts.append(seg.words[0].start)
            all_words.extend(seg.words)
        elif seg.text:
            # Fallback if words list is empty
            all_words.append(WordTimestamp(
                word=seg.text,
                start=seg.start,
                end=seg.end,
                probability=1.0
            ))
            sentence_starts.append(seg.start)

    if not all_words:
        # Fallback if no words present at all
        duration = max(0.1, suggested_end - suggested_start)
        return SnappedClip(
            original_start=suggested_start,
            original_end=suggested_end,
            snapped_start=suggested_start,
            snapped_end=suggested_end,
            duration=duration,
            relative_words=[]
        )

    # 1. Snap Start: Find closest word start, favoring sentence starts within 1.0s window
    best_start_word = min(all_words, key=lambda w: abs(w.start - suggested_start))
    snapped_start = best_start_word.start

    # Check if a sentence start is within 1.2 seconds of the suggested start
    nearby_sentence_starts = [
        s for s in sentence_starts if abs(s - suggested_start) <= 1.2
    ]
    if nearby_sentence_starts:
        # Pick the sentence start closest to suggested_start
        snapped_start = min(nearby_sentence_starts, key=lambda s: abs(s - suggested_start))

    # 2. Snap End: Find closest word end
    best_end_word = min(all_words, key=lambda w: abs(w.end - suggested_end))
    snapped_end = best_end_word.end + tail_padding_seconds

    # Ensure start < end and min duration
    if snapped_end <= snapped_start:
        snapped_end = snapped_start + 5.0

    snapped_start = round(max(0.0, snapped_start), 3)
    snapped_end = round(snapped_end, 3)
    duration = round(snapped_end - snapped_start, 3)

    # 3. Collect all words in [snapped_start, snapped_end] with zero-based relative timestamps
    relative_words: List[WordTimestamp] = []
    for w in all_words:
        if w.end >= snapped_start and w.start <= snapped_end:
            rel_start = max(0.0, round(w.start - snapped_start, 3))
            rel_end = max(rel_start + 0.05, round(w.end - snapped_start, 3))
            relative_words.append(WordTimestamp(
                word=w.word,
                start=rel_start,
                end=rel_end,
                probability=w.probability
            ))

    return SnappedClip(
        original_start=suggested_start,
        original_end=suggested_end,
        snapped_start=snapped_start,
        snapped_end=snapped_end,
        duration=duration,
        relative_words=relative_words
    )
