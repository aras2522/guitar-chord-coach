from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
import librosa
import numpy as np
import soundfile as sf

SUPPORTED_SUFFIXES = {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".webm"}


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def convert_to_wav(src: Path, dst: Path, sr: int = 22050) -> None:
    """Convert any ffmpeg-supported media to mono WAV."""
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "wav",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-800:]}")


def load_audio(path: Path, sr: int = 22050) -> tuple[np.ndarray, int]:
    """Load audio from wav/mp3/mp4/etc. Returns mono float32 samples and sample rate."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {suffix or '(none)'}")

    if suffix == ".wav":
        y, file_sr = sf.read(str(path), always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if file_sr != sr:
            y = librosa.resample(y.astype(np.float32), orig_sr=file_sr, target_sr=sr)
        return y.astype(np.float32), sr

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "audio.wav"
        convert_to_wav(path, wav_path, sr=sr)
        y, file_sr = sf.read(str(wav_path), always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y.astype(np.float32), int(file_sr)
