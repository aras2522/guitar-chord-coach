from __future__ import annotations

from dataclasses import asdict, dataclass

import librosa
import numpy as np
from scipy.ndimage import median_filter

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Common open/closed shapes for the UI fretboard diagrams (string 6→1, fret or -1 mute).
CHORD_SHAPES: dict[str, list[int]] = {
    "C": [-1, 3, 2, 0, 1, 0],
    "C#": [-1, 4, 3, 1, 2, 1],
    "D": [-1, -1, 0, 2, 3, 2],
    "D#": [-1, -1, 1, 3, 4, 3],
    "E": [0, 2, 2, 1, 0, 0],
    "F": [1, 3, 3, 2, 1, 1],
    "F#": [2, 4, 4, 3, 2, 2],
    "G": [3, 2, 0, 0, 0, 3],
    "G#": [4, 6, 6, 5, 4, 4],
    "A": [-1, 0, 2, 2, 2, 0],
    "A#": [-1, 1, 3, 3, 3, 1],
    "B": [-1, 2, 4, 4, 4, 2],
    "Cm": [-1, 3, 5, 5, 4, 3],
    "C#m": [-1, 4, 6, 6, 5, 4],
    "Dm": [-1, -1, 0, 2, 3, 1],
    "D#m": [-1, -1, 1, 3, 4, 2],
    "Em": [0, 2, 2, 0, 0, 0],
    "Fm": [1, 3, 3, 1, 1, 1],
    "F#m": [2, 4, 4, 2, 2, 2],
    "Gm": [3, 5, 5, 3, 3, 3],
    "G#m": [4, 6, 6, 4, 4, 4],
    "Am": [-1, 0, 2, 2, 1, 0],
    "A#m": [-1, 1, 3, 3, 2, 1],
    "Bm": [-1, 2, 4, 4, 3, 2],
    "N": [-1, -1, -1, -1, -1, -1],
}


@dataclass
class ChordSegment:
    start: float
    end: float
    chord: str
    confidence: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["shape"] = CHORD_SHAPES.get(self.chord, CHORD_SHAPES["N"])
        return d


def _build_templates() -> tuple[list[str], np.ndarray]:
    """Major + minor triad templates over 12 pitch classes."""
    names: list[str] = []
    rows: list[np.ndarray] = []
    for root in range(12):
        major = np.zeros(12, dtype=np.float32)
        major[[root, (root + 4) % 12, (root + 7) % 12]] = 1.0
        names.append(NOTE_NAMES[root])
        rows.append(major / np.linalg.norm(major))

        minor = np.zeros(12, dtype=np.float32)
        minor[[root, (root + 3) % 12, (root + 7) % 12]] = 1.0
        names.append(NOTE_NAMES[root] + "m")
        rows.append(minor / np.linalg.norm(minor))
    return names, np.stack(rows, axis=0)


TEMPLATE_NAMES, TEMPLATES = _build_templates()


def _smooth_labels(labels: np.ndarray, confidences: np.ndarray, hop_s: float) -> list[ChordSegment]:
    """Median-filter frame labels, then merge into timed segments."""
    if len(labels) == 0:
        return []

    # ~0.55s median window stabilizes flicker without killing changes.
    win = max(5, int(round(0.55 / hop_s)) | 1)
    smoothed = median_filter(labels.astype(np.int32), size=win)

    segments: list[ChordSegment] = []
    start_i = 0
    for i in range(1, len(smoothed) + 1):
        if i == len(smoothed) or smoothed[i] != smoothed[start_i]:
            chord = TEMPLATE_NAMES[int(smoothed[start_i])]
            conf = float(np.mean(confidences[start_i:i]))
            # Drop very short spikes (< 0.35s) unless at edges of silence-like N handling.
            start_t = start_i * hop_s
            end_t = i * hop_s
            if end_t - start_t >= 0.5:
                segments.append(
                    ChordSegment(start=round(start_t, 2), end=round(end_t, 2), chord=chord, confidence=round(conf, 3))
                )
            start_i = i

    # Merge identical neighbors that may have been split by short drops.
    merged: list[ChordSegment] = []
    for seg in segments:
        if merged and merged[-1].chord == seg.chord:
            prev = merged[-1]
            total = (prev.end - prev.start) + (seg.end - seg.start)
            conf = (prev.confidence * (prev.end - prev.start) + seg.confidence * (seg.end - seg.start)) / total
            merged[-1] = ChordSegment(prev.start, seg.end, seg.chord, round(conf, 3))
        else:
            merged.append(seg)
    return merged


def detect_chords(y: np.ndarray, sr: int) -> dict:
    """Estimate major/minor chord timeline from mono audio."""
    if y.size == 0:
        return {"duration": 0.0, "segments": [], "unique_chords": []}

    # Prefer harmonic layer so plucked melody notes wobble the chord less.
    y_harm = librosa.effects.harmonic(y, margin=2.0)

    hop_length = 2048
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop_length, n_chroma=12)
    # Boost harmonic content slightly via L2 normalize per frame.
    norms = np.linalg.norm(chroma, axis=0, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    chroma = chroma / norms

    # Cosine similarity vs templates.
    sims = TEMPLATES @ chroma  # (24, frames)
    labels = np.argmax(sims, axis=0)
    confidences = sims.max(axis=0)

    # Treat very low-energy frames as no-chord (silence / noise).
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    if rms.shape[0] != labels.shape[0]:
        rms = np.resize(rms, labels.shape[0])
    quiet = rms < (np.percentile(rms, 20) * 0.5 + 1e-5)
    # Map quiet to nearest chord still; just lower confidence.
    confidences = confidences * (~quiet | (confidences > 0.55))

    hop_s = hop_length / sr
    segments = _smooth_labels(labels, confidences, hop_s)
    duration = float(len(y) / sr)

    # Clamp last end to duration.
    if segments:
        segments[-1] = ChordSegment(
            segments[-1].start,
            round(duration, 2),
            segments[-1].chord,
            segments[-1].confidence,
        )

    unique = []
    seen = set()
    for seg in segments:
        if seg.chord not in seen:
            seen.add(seg.chord)
            unique.append({"chord": seg.chord, "shape": CHORD_SHAPES.get(seg.chord, CHORD_SHAPES["N"])})

    return {
        "duration": round(duration, 2),
        "segments": [s.to_dict() for s in segments],
        "unique_chords": unique,
    }
