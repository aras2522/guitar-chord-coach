#!/usr/bin/env python3
"""Generate a demo with chord changes plus a clear melody line."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "demo_progression.wav"

# Soft chord beds (MIDI).
CHORDS: list[tuple[str, list[int]]] = [
    ("C", [48, 52, 55, 60]),
    ("G", [43, 47, 50, 55]),
    ("Am", [45, 52, 57, 60]),
    ("F", [41, 48, 53, 57]),
]

# Melody phrases over each chord (single notes, easier for pitch tracking).
MELODIES: list[list[int]] = [
    [60, 62, 64, 67],  # C D E G
    [59, 62, 67, 71],  # B D G B
    [57, 60, 64, 67],  # A C E G
    [53, 57, 60, 65],  # F A C F
]


def midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def pluck(freq: float, duration: float, sr: int, amp: float = 0.2) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    env = np.exp(-2.4 * t) * (1.0 - np.exp(-100 * t))
    wave = (
        np.sin(2 * np.pi * freq * t)
        + 0.32 * np.sin(2 * np.pi * 2 * freq * t)
        + 0.12 * np.sin(2 * np.pi * 3 * freq * t)
    )
    return (amp * env * wave).astype(np.float32)


def soft_pad(notes: list[int], duration: float, sr: int, amp: float = 0.025) -> np.ndarray:
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    mix = np.zeros(n, dtype=np.float32)
    fade = np.minimum(t / 0.05, 1.0) * np.minimum((duration - t) / 0.08, 1.0)
    for midi in notes:
        freq = midi_to_hz(midi)
        mix += amp * fade * np.sin(2 * np.pi * freq * t).astype(np.float32)
    return mix


def phrase(chord_notes: list[int], melody: list[int], sr: int) -> np.ndarray:
    note_dur = 0.5
    gap = 0.06
    # Longer chord attack helps chord detection before melody starts.
    intro = 0.7
    total = intro + len(melody) * (note_dur + gap) + 0.1
    bed = soft_pad(chord_notes, total, sr)
    attack = soft_pad(chord_notes, intro + 0.2, sr, amp=0.08)
    mix = bed.copy()
    mix[: len(attack)] += attack[: len(mix)]
    cursor = intro
    for midi in melody:
        tone = pluck(midi_to_hz(midi), note_dur, sr, amp=0.34)
        start = int(cursor * sr)
        end = start + len(tone)
        if end > len(mix):
            mix = np.pad(mix, (0, end - len(mix)))
        mix[start:end] += tone
        cursor += note_dur + gap
    peak = np.max(np.abs(mix)) or 1.0
    return (0.92 * mix / peak).astype(np.float32)


def main() -> None:
    sr = 22050
    parts = [phrase(chord, melody, sr) for (_, chord), melody in zip(CHORDS, MELODIES)]
    silence = np.zeros(int(0.12 * sr), dtype=np.float32)
    audio_parts: list[np.ndarray] = []
    for i, part in enumerate(parts):
        audio_parts.append(part)
        if i < len(parts) - 1:
            audio_parts.append(silence)
    audio = np.concatenate(audio_parts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sf.write(OUT, audio, sr)
    print(f"Wrote {OUT} ({len(audio) / sr:.2f}s)")
    print("Chords: C G Am F")
    print("Melody: C-D-E-G | B-D-G-B | A-C-E-G | F-A-C-F")


if __name__ == "__main__":
    main()
