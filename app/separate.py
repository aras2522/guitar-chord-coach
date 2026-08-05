from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

_lock = threading.Lock()


@lru_cache(maxsize=1)
def _load_model():
    """Prefer 6-stem model (has dedicated guitar); fall back to 4-stem."""
    for name in ("htdemucs_6s", "htdemucs"):
        try:
            model = get_model(name)
            model.eval()
            return model, name
        except Exception:
            continue
    raise RuntimeError("Could not load a Demucs separation model")


def isolate_guitar(y: np.ndarray, sr: int) -> tuple[np.ndarray, int, dict]:
    """
    Remove vocals/drums/etc. and keep a guitar-focused stem.

    Demucs 6-stem exposes a dedicated `guitar` source. On 4-stem models,
    guitar usually lives in `other` (sometimes with other non-bass instruments).
    """
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = y.astype(np.float32)

    with _lock:
        model, model_name = _load_model()

    # Demucs expects stereo (channels, samples) at the model's sample rate.
    wav = torch.from_numpy(y).float()
    if wav.dim() == 1:
        wav = wav.unsqueeze(0).repeat(2, 1)
    elif wav.shape[0] == 1:
        wav = wav.repeat(2, 1)

    target_sr = model.samplerate
    if sr != target_sr:
        # Lightweight resample via torchaudio if available, else numpy interp.
        try:
            import torchaudio.functional as F

            wav = F.resample(wav, sr, target_sr)
        except Exception:
            n_out = int(round(wav.shape[-1] * target_sr / sr))
            old_idx = np.linspace(0, 1, wav.shape[-1], endpoint=False)
            new_idx = np.linspace(0, 1, n_out, endpoint=False)
            left = np.interp(new_idx, old_idx, wav[0].numpy())
            right = np.interp(new_idx, old_idx, wav[1].numpy())
            wav = torch.from_numpy(np.stack([left, right]).astype(np.float32))
        sr = target_sr

    ref = wav.mean(0)
    std = float(ref.std()) + 1e-8
    wav_n = (wav - ref.mean()) / std

    with torch.no_grad():
        sources = apply_model(model, wav_n[None], device="cpu", split=True, overlap=0.25)[0]
    sources = sources * std

    names = list(model.sources)
    stem_map = {name: sources[i] for i, name in enumerate(names)}

    if "guitar" in stem_map:
        chosen = "guitar"
        stem = stem_map["guitar"]
    else:
        # 4-stem fallback: other is the usual home for guitar/keys/synths.
        chosen = "other" if "other" in stem_map else names[-1]
        stem = stem_map[chosen]
        # Mix a little bass back in if present — helps low guitar notes without drums/vocals.
        if "bass" in stem_map:
            stem = stem + 0.25 * stem_map["bass"]
            chosen = f"{chosen}+bass"

    mono = stem.mean(0).cpu().numpy().astype(np.float32)
    peak = float(np.max(np.abs(mono))) or 1.0
    mono = 0.95 * mono / peak

    info = {
        "model": model_name,
        "stem": chosen,
        "available_stems": names,
        "note": (
            "Dedicated guitar stem"
            if chosen == "guitar"
            else "Approx. guitar from residual stems (not perfect — other instruments may remain)"
        ),
    }
    return mono, sr, info
