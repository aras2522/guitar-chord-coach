from __future__ import annotations

import tempfile
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

_lock = threading.Lock()


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel

    # Small/base is fast enough for a prototype; downloads once.
    return WhisperModel("base", device="cpu", compute_type="int8")


def transcribe_words(y: np.ndarray, sr: int) -> dict:
    """
    Transcribe singing/speech to timed lyric words.

    Returns:
      {
        "words": [{"text", "start", "end"}],
        "text": full transcript,
        "language": str | None,
      }
    """
    if y.size == 0:
        return {"words": [], "text": "", "language": None}

    if y.ndim > 1:
        y = y.mean(axis=1)
    y = y.astype(np.float32)

    # Whisper expects 16 kHz typically; faster-whisper resamples from file.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        sf.write(path, y, sr)
        with _lock:
            model = _model()
            segments, info = model.transcribe(
                str(path),
                word_timestamps=True,
                vad_filter=True,
                beam_size=1,
            )
            words: list[dict] = []
            parts: list[str] = []
            for seg in segments:
                if seg.text:
                    parts.append(seg.text.strip())
                if not seg.words:
                    continue
                for w in seg.words:
                    text = (w.word or "").strip()
                    if not text:
                        continue
                    words.append(
                        {
                            "text": text,
                            "start": round(float(w.start), 2),
                            "end": round(float(w.end), 2),
                        }
                    )
        return {
            "words": words,
            "text": " ".join(parts).strip(),
            "language": getattr(info, "language", None),
        }
    finally:
        path.unlink(missing_ok=True)
