"""Lyrics agent: find correct lyrics and timed lines for chord alignment.

Strategy:
1. Use pasted lyrics if provided
2. Else look up synced lyrics via LRCLIB (title/artist or filename hints)
3. Else fall back to Whisper transcription from the audio
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import numpy as np

LRCLIB_SEARCH = "https://lrclib.net/api/search"
LRCLIB_GET = "https://lrclib.net/api/get"


def hints_from_filename(filename: str | None) -> dict[str, str]:
    """Best-effort title guess from a file name like free-bird-under-4min.mp3."""
    if not filename:
        return {}
    stem = Path(filename).stem
    cleaned = re.sub(r"[_\-]+", " ", stem)
    cleaned = re.sub(
        r"\b(official|audio|video|lyrics|hd|hq|live|remaster(ed)?|under\s*\d+\s*min|\d+\s*min|clip|karaoke)\b",
        " ",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    if not cleaned:
        return {}
    return {"title": cleaned, "query": cleaned}


def _parse_lrc(lrc: str) -> list[dict]:
    """Parse LRC into timed lyric lines."""
    pattern = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\](.*)")
    entries: list[tuple[float, str]] = []
    for raw in lrc.splitlines():
        m = pattern.match(raw.strip())
        if not m:
            continue
        mins, secs, frac, text = m.groups()
        frac = (frac or "0").ljust(3, "0")[:3]
        t = int(mins) * 60 + int(secs) + int(frac) / 1000.0
        text = text.strip()
        if not text:
            continue
        # Skip metadata tags like [ar:Artist]
        if re.match(r"^[a-z]{2}:", text):
            continue
        entries.append((t, text))
    entries.sort(key=lambda x: x[0])

    lines: list[dict] = []
    for i, (start, text) in enumerate(entries):
        end = entries[i + 1][0] if i + 1 < len(entries) else start + 4.0
        if end <= start:
            end = start + 2.0
        lines.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return lines


def timed_words_from_lines(lines: list[dict]) -> list[dict]:
    """Split timed lyric lines into word-level timings for the chart."""
    words: list[dict] = []
    for line in lines:
        tokens = [w for w in re.findall(r"\S+", line["text"]) if w]
        if not tokens:
            continue
        start = float(line["start"])
        end = float(line["end"])
        dur = max(end - start, 0.2)
        step = dur / len(tokens)
        for i, token in enumerate(tokens):
            w_start = start + i * step
            w_end = start + (i + 1) * step
            words.append(
                {
                    "text": token,
                    "start": round(w_start, 2),
                    "end": round(w_end, 2),
                }
            )
    return words


def _lrclib_search(query: str, duration: float | None = None) -> dict | None:
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(LRCLIB_SEARCH, params={"q": query})
            resp.raise_for_status()
            results = resp.json()
    except Exception:
        return None
    if not isinstance(results, list) or not results:
        return None

    # Prefer tracks with synced lyrics; if duration known, prefer closest length.
    scored: list[tuple[float, dict]] = []
    for item in results:
        if not item.get("syncedLyrics") and not item.get("plainLyrics"):
            continue
        score = 0.0
        if item.get("syncedLyrics"):
            score += 10.0
        if duration and item.get("duration"):
            score -= abs(float(item["duration"]) - duration) / 10.0
        scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _lrclib_get(artist: str, title: str, duration: float | None = None) -> dict | None:
    params: dict[str, Any] = {"artist_name": artist, "track_name": title}
    if duration:
        params["duration"] = int(round(duration))
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(LRCLIB_GET, params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def fetch_catalog_lyrics(
    *,
    title: str | None = None,
    artist: str | None = None,
    query: str | None = None,
    duration: float | None = None,
) -> dict | None:
    """Fetch lyrics from LRCLIB. Returns normalized payload or None."""
    hit = None
    if artist and title:
        hit = _lrclib_get(artist, title, duration)
    if hit is None:
        q = query or " ".join(x for x in [artist, title] if x).strip()
        if q:
            hit = _lrclib_search(q, duration)
    if not hit:
        return None

    synced = (hit.get("syncedLyrics") or "").strip()
    plain = (hit.get("plainLyrics") or "").strip()
    lines = _parse_lrc(synced) if synced else []
    words = timed_words_from_lines(lines) if lines else []
    text = "\n".join(line["text"] for line in lines) if lines else plain
    if not text:
        return None
    return {
        "source": "lrclib",
        "title": hit.get("trackName") or title,
        "artist": hit.get("artistName") or artist,
        "album": hit.get("albumName"),
        "text": text,
        "lines": lines,
        "words": words,
        "has_sync": bool(words),
    }


def resolve_lyrics(
    *,
    y: np.ndarray | None = None,
    sr: int | None = None,
    duration: float | None = None,
    filename: str | None = None,
    title: str | None = None,
    artist: str | None = None,
    pasted_lyrics: str | None = None,
    allow_transcribe: bool = True,
) -> dict:
    """
    Lyrics agent entrypoint.

    Returns:
      {
        source: pasted|lrclib|transcription|none,
        text, words, title, artist, tip, ...
      }
    """
    pasted = (pasted_lyrics or "").strip()
    if pasted:
        return {
            "source": "pasted",
            "text": pasted,
            "words": [],
            "title": title,
            "artist": artist,
            "tip": "Using your pasted lyrics.",
        }

    file_hints = hints_from_filename(filename)
    title = (title or "").strip() or file_hints.get("title")
    artist = (artist or "").strip() or None
    query = " ".join(x for x in [artist, title] if x).strip() or file_hints.get("query")

    if query:
        catalog = fetch_catalog_lyrics(
            title=title,
            artist=artist,
            query=query,
            duration=duration,
        )
        if catalog:
            sync_note = "with synced timestamps" if catalog.get("has_sync") else "as plain text"
            return {
                **catalog,
                "tip": (
                    f"Lyrics agent found “{catalog.get('title') or title}”"
                    f"{(' by ' + catalog['artist']) if catalog.get('artist') else ''} "
                    f"via LRCLIB ({sync_note})."
                ),
            }

    if allow_transcribe and y is not None and sr is not None:
        import os

        if os.environ.get("LITE_MODE", "").strip() in {"1", "true", "yes", "on"}:
            return {
                "source": "none",
                "text": "",
                "words": [],
                "title": title,
                "artist": artist,
                "tip": (
                    "Lite mode: enter song title/artist so the lyrics agent can look up catalog lyrics "
                    "(audio transcription is disabled on free hosting)."
                ),
            }
        try:
            from app.lyrics import transcribe_words
        except Exception:
            return {
                "source": "none",
                "text": "",
                "words": [],
                "title": title,
                "artist": artist,
                "tip": "Transcription unavailable. Enter title/artist or paste lyrics.",
            }
        transcript = transcribe_words(y, sr)
        words = transcript.get("words") or []
        text = transcript.get("text") or ""
        if words or text:
            return {
                "source": "transcription",
                "text": text,
                "words": words,
                "title": title,
                "artist": artist,
                "language": transcript.get("language"),
                "tip": (
                    "Lyrics agent could not find a catalog match, so it transcribed the audio. "
                    "For better accuracy, enter the song title/artist."
                ),
            }

    return {
        "source": "none",
        "text": "",
        "words": [],
        "title": title,
        "artist": artist,
        "tip": "Lyrics agent found no lyrics. Enter title/artist or paste lyrics.",
    }
