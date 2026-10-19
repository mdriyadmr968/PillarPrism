from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from backend.app.modules.transcription.transcriber import WordTimestamp


def _seconds_to_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp format: H:MM:SS.cs (centiseconds)."""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


@dataclass
class WordChunk:
    start: float
    end: float
    words: List[WordTimestamp]


def chunk_words(
    words: List[WordTimestamp],
    max_words_per_chunk: int = 3,
    max_pause_sec: float = 0.45
) -> List[WordChunk]:
    if not words:
        return []

    chunks: List[WordChunk] = []
    current_words: List[WordTimestamp] = []

    for i, w in enumerate(words):
        if not current_words:
            current_words.append(w)
            continue

        prev_w = current_words[-1]
        pause = w.start - prev_w.end

        # Check chunk breaks: max words or long pause or punctuation
        has_break_punctuation = prev_w.word.rstrip().endswith((".", "!", "?", ",", ";", ":"))
        if len(current_words) >= max_words_per_chunk or pause > max_pause_sec or (has_break_punctuation and len(current_words) >= 2):
            chunks.append(WordChunk(
                start=current_words[0].start,
                end=max(current_words[-1].end, current_words[0].start + 0.3),
                words=list(current_words)
            ))
            current_words = [w]
        else:
            current_words.append(w)

    if current_words:
        chunks.append(WordChunk(
            start=current_words[0].start,
            end=max(current_words[-1].end, current_words[0].start + 0.3),
            words=list(current_words)
        ))

    return chunks


def generate_ass_subtitle(
    words: List[WordTimestamp],
    output_path: Path,
    font_name: str = "Montserrat Black",
    font_size: int = 58,
    primary_color: str = "&H00FFFFFF",      # White in &HAABBGGRR
    highlight_color: str = "&H0000FFFF",    # Yellow in &HAABBGGRR
    outline_color: str = "&H00000000",      # Black outline
    outline_width: int = 4,
    shadow_depth: int = 2,
    margin_v: int = 420                     # Distance from bottom (safe above mobile UI)
) -> Path:
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,1,0,1,{outline_width},{shadow_depth},2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines: List[str] = []
    chunks = chunk_words(words)

    for chunk in chunks:
        # For each word in chunk, emit a styled event when it is actively spoken
        for i, active_word in enumerate(chunk.words):
            event_start = _seconds_to_ass_time(active_word.start)
            # Active word duration extends to next word start or chunk end
            if i + 1 < len(chunk.words):
                next_start = chunk.words[i + 1].start
                event_end = _seconds_to_ass_time(max(active_word.end, next_start))
            else:
                event_end = _seconds_to_ass_time(chunk.end)

            # Build line where all words are visible, but active_word has highlight color + scale pop
            text_parts = []
            for j, w in enumerate(chunk.words):
                clean_word = w.word.upper()
                if j == i:
                    # Active highlight with pop scale
                    text_parts.append(f"{{\\c{highlight_color}\\fscx108\\fscy108}}{clean_word}{{\\r}}")
                else:
                    text_parts.append(clean_word)

            rendered_text = " ".join(text_parts)
            dialogue_lines.append(
                f"Dialogue: 0,{event_start},{event_end},Default,,0,0,0,,{rendered_text}"
            )

    full_ass_content = header + "\n".join(dialogue_lines) + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_ass_content)

    return output_path
