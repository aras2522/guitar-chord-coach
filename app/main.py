from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.analyze import analyze_track
from app.audio import SUPPORTED_SUFFIXES, load_audio

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
DEMO_WAV = DATA / "demo_progression.wav"
LITE_MODE = os.environ.get("LITE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
DEMO_LYRICS = """INTRO

VERSE 1
Play this soft and slow
Hear the changes go
Sing along and learn
Watch each chord in turn
"""

UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Guitar Chord Coach", version="0.2.0")


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> Response:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "demo_available": DEMO_WAV.exists(),
        "lite_mode": LITE_MODE,
        "isolate_available": not LITE_MODE,
    }


@app.get("/api/demo")
def analyze_demo() -> dict:
    if not DEMO_WAV.exists():
        raise HTTPException(404, "Demo audio missing. Run: uv run python scripts/generate_demo.py")
    y, sr = load_audio(DEMO_WAV)
    result = analyze_track(y, sr, lyrics=DEMO_LYRICS, transcribe=False)
    result["filename"] = "demo_progression.wav"
    result["audio_url"] = "/api/demo/audio"
    result["isolated"] = False
    result["expected_chords"] = ["C", "G", "Am", "F"]
    result["tip"] = (
        "Demo chart: chords sit above the lyric words, like a printed guitar sheet."
    )
    return result


@app.get("/api/demo/audio")
def demo_audio() -> FileResponse:
    if not DEMO_WAV.exists():
        raise HTTPException(404, "Demo audio missing")
    return FileResponse(DEMO_WAV, media_type="audio/wav", filename="demo_progression.wav")


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    isolate: str = Form("false"),
    lyrics: str = Form(""),
    title: str = Form(""),
    artist: str = Form(""),
) -> dict:
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    want_isolate = isolate.strip().lower() in {"1", "true", "yes", "on"}
    if want_isolate and LITE_MODE:
        raise HTTPException(
            400,
            "Guitar isolation is disabled on the free/lite deploy. Uncheck Isolate guitar and try again.",
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            400,
            f"Unsupported type '{suffix}'. Use: {', '.join(sorted(SUPPORTED_SUFFIXES))}",
        )

    job_id = uuid.uuid4().hex
    dest = UPLOADS / f"{job_id}{suffix}"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        y_orig, sr_orig = load_audio(dest)
        if len(y_orig) < sr_orig * 0.5:
            raise HTTPException(400, "Audio is too short — need at least 0.5 seconds")
        if len(y_orig) > sr_orig * 240:
            raise HTTPException(400, "Audio is too long for this prototype (max 4 minutes)")

        separation = None
        play_name = dest.name
        y, sr = y_orig, sr_orig
        if want_isolate:
            from app.separate import isolate_guitar

            y, sr, separation = isolate_guitar(y_orig, sr_orig)
            play_name = f"{job_id}_guitar.wav"
            sf.write(UPLOADS / play_name, y, sr)

        # Chords from (optional) guitar stem; lyrics agent uses original mix + catalog lookup.
        result = analyze_track(
            y,
            sr,
            lyrics=lyrics,
            y_lyrics=y_orig,
            sr_lyrics=sr_orig,
            transcribe=not LITE_MODE and not bool((lyrics or "").strip()),
            filename=file.filename,
            title=title,
            artist=artist,
        )
        result["filename"] = file.filename
        result["audio_url"] = f"/api/audio/{play_name}"
        result["isolated"] = bool(want_isolate)
        result["separation"] = separation

        source = (result.get("chart") or {}).get("source")
        agent_tip = ((result.get("lyrics_agent") or {}).get("tip") or "").strip()
        tip_parts = []
        if want_isolate and separation:
            tip_parts.append(f"Isolated with {separation['model']} → {separation['stem']}.")
        if agent_tip:
            tip_parts.append(agent_tip)
        elif source == "pasted":
            tip_parts.append("Using your pasted lyrics; chords are placed above the words.")
        else:
            tip_parts.append("No clear lyrics found — showing a chord sheet.")
        result["tip"] = " ".join(tip_parts)
        return result
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface useful analyze errors to UI
        raise HTTPException(500, f"Could not analyze audio: {exc}") from exc


@app.get("/api/audio/{name}")
def serve_upload(name: str) -> FileResponse:
    path = UPLOADS / Path(name).name
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path)
