from __future__ import annotations

import re
from typing import Any


def _chord_at(segments: list[dict], t: float) -> str | None:
    for seg in segments:
        if seg["start"] <= t < seg["end"]:
            return seg.get("chord")
    if segments and t >= segments[-1]["start"]:
        return segments[-1].get("chord")
    return None


def _split_lyric_lines(lyrics: str) -> list[str]:
    lines = []
    for raw in lyrics.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _tokenize_words(line: str) -> list[str]:
    return [w for w in re.findall(r"\S+", line) if w]


def _is_section_header(line: str) -> bool:
    cleaned = re.sub(r"[^A-Za-z0-9 ]", "", line).strip()
    if not cleaned:
        return False
    words = cleaned.split()
    if len(words) > 4:
        return False
    return cleaned.isupper() and any(
        k in cleaned.upper()
        for k in ("VERSE", "CHORUS", "BRIDGE", "INTRO", "OUTRO", "SOLO", "PRE")
    )


def _annotate_chords(cells: list[dict], chord_segments: list[dict]) -> list[dict]:
    """Attach chord labels; show a chord only when it changes."""
    last_chord: str | None = None
    out = []
    for cell in cells:
        t = float(cell["start"])
        chord = _chord_at(chord_segments, t)
        show_chord = chord if chord and chord != last_chord else None
        if show_chord:
            last_chord = show_chord
        out.append({**cell, "chord": show_chord})
    return out


def build_chart_from_timed_words(
    words: list[dict],
    chord_segments: list[dict],
) -> dict[str, Any]:
    """Build a lyric sheet from transcribed timed words."""
    if not words:
        return {"mode": "chords", "lines": [], "has_lyrics": False, "source": "none"}

    chart_lines: list[dict] = [
        {"type": "section", "label": "LYRICS", "start": None, "end": None, "cells": []}
    ]
    line_words: list[dict] = []

    def flush() -> None:
        nonlocal line_words
        if not line_words:
            return
        cells = _annotate_chords(
            [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in line_words],
            chord_segments,
        )
        chart_lines.append(
            {
                "type": "lyric",
                "start": round(float(line_words[0]["start"]), 2),
                "end": round(float(line_words[-1]["end"]), 2),
                "cells": cells,
            }
        )
        line_words = []

    for word in words:
        if not line_words:
            line_words.append(word)
            continue
        gap = float(word["start"]) - float(line_words[-1]["end"])
        if gap >= 0.45 or len(line_words) >= 8:
            flush()
        line_words.append(word)
    flush()

    return {
        "mode": "lyrics",
        "lines": chart_lines,
        "has_lyrics": True,
        "source": "transcription",
    }


def build_chart_from_lyrics(
    lyrics: str,
    chord_segments: list[dict],
    duration: float,
) -> dict[str, Any]:
    """Place chord labels above pasted lyric words."""
    lines_raw = _split_lyric_lines(lyrics)
    content_idxs = [i for i, ln in enumerate(lines_raw) if ln and not _is_section_header(ln)]
    n = max(len(content_idxs), 1)
    line_dur = max(duration, 0.1) / n

    chart_lines: list[dict] = []
    content_pos = 0

    for raw in lines_raw:
        if raw == "":
            chart_lines.append({"type": "break", "start": None, "end": None, "cells": []})
            continue
        if _is_section_header(raw):
            chart_lines.append(
                {
                    "type": "section",
                    "label": raw.upper(),
                    "start": None,
                    "end": None,
                    "cells": [],
                }
            )
            continue

        start = content_pos * line_dur
        end = (content_pos + 1) * line_dur
        words = _tokenize_words(raw)
        if not words:
            content_pos += 1
            continue
        word_dur = (end - start) / len(words)
        raw_cells = [
            {
                "text": word,
                "start": round(start + wi * word_dur, 2),
                "end": round(start + (wi + 1) * word_dur, 2),
            }
            for wi, word in enumerate(words)
        ]
        cells = _annotate_chords(raw_cells, chord_segments)
        chart_lines.append(
            {
                "type": "lyric",
                "start": round(start, 2),
                "end": round(end, 2),
                "cells": cells,
            }
        )
        content_pos += 1

    return {
        "mode": "lyrics",
        "lines": chart_lines,
        "has_lyrics": True,
        "source": "pasted",
    }


def build_chart_from_chords(chord_segments: list[dict]) -> dict[str, Any]:
    """Fallback sheet when no lyrics — chords in readable rows."""
    if not chord_segments:
        return {"mode": "chords", "lines": [], "has_lyrics": False, "source": "none"}

    chart_lines: list[dict] = [
        {"type": "section", "label": "CHORD SHEET", "start": None, "end": None, "cells": []}
    ]
    row: list[dict] = []
    row_start = chord_segments[0]["start"]
    for seg in chord_segments:
        row.append(
            {
                "text": "·",
                "start": seg["start"],
                "end": seg["end"],
                "chord": seg["chord"],
            }
        )
        if len(row) >= 4:
            chart_lines.append(
                {
                    "type": "lyric",
                    "start": round(row_start, 2),
                    "end": round(row[-1]["end"], 2),
                    "cells": row,
                }
            )
            row = []
            row_start = seg["end"]
    if row:
        chart_lines.append(
            {
                "type": "lyric",
                "start": round(row_start, 2),
                "end": round(row[-1]["end"], 2),
                "cells": row,
            }
        )
    return {"mode": "chords", "lines": chart_lines, "has_lyrics": False, "source": "none"}


def build_song_chart(
    chord_segments: list[dict],
    duration: float,
    lyrics: str | None = None,
    timed_words: list[dict] | None = None,
) -> dict[str, Any]:
    lyrics = (lyrics or "").strip()
    if lyrics:
        return build_chart_from_lyrics(lyrics, chord_segments, duration)
    if timed_words:
        return build_chart_from_timed_words(timed_words, chord_segments)
    return build_chart_from_chords(chord_segments)
