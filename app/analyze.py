from __future__ import annotations

import numpy as np

from app.chart import build_song_chart
from app.chords import detect_chords
from app.lyrics_agent import resolve_lyrics


def analyze_track(
    y: np.ndarray,
    sr: int,
    lyrics: str | None = None,
    y_lyrics: np.ndarray | None = None,
    sr_lyrics: int | None = None,
    transcribe: bool = True,
    filename: str | None = None,
    title: str | None = None,
    artist: str | None = None,
) -> dict:
    """Detect chords and build a lyric song sheet via the lyrics agent."""
    chord_result = detect_chords(y, sr)
    duration = float(chord_result.get("duration") or len(y) / max(sr, 1))

    src = y_lyrics if y_lyrics is not None else y
    src_sr = sr_lyrics if sr_lyrics is not None else sr

    lyrics_result = resolve_lyrics(
        y=src,
        sr=src_sr,
        duration=duration,
        filename=filename,
        title=title,
        artist=artist,
        pasted_lyrics=lyrics,
        allow_transcribe=transcribe,
    )

    lyrics_text = (lyrics_result.get("text") or "").strip()
    timed_words = lyrics_result.get("words") or []
    # Prefer synced/transcribed word timings when available.
    use_words = timed_words if lyrics_result.get("source") in {"lrclib", "transcription"} and timed_words else None
    use_plain = lyrics_text if not use_words else None

    chart = build_song_chart(
        chord_result.get("segments", []),
        duration,
        lyrics=use_plain,
        timed_words=use_words,
    )
    # Annotate chart source from the agent when applicable.
    if chart.get("has_lyrics") and lyrics_result.get("source") == "lrclib":
        chart["source"] = "lrclib"
    elif chart.get("has_lyrics") and lyrics_result.get("source") == "transcription":
        chart["source"] = "transcription"
    elif chart.get("has_lyrics") and lyrics_result.get("source") == "pasted":
        chart["source"] = "pasted"

    return {
        **chord_result,
        "chart": chart,
        "lyrics_agent": lyrics_result,
        "lyrics_used": lyrics_text,
        "song_title": lyrics_result.get("title"),
        "song_artist": lyrics_result.get("artist"),
    }
