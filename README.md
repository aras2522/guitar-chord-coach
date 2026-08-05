# Guitar Chord Coach

Prototype that listens to an MP3/MP4 (or WAV), estimates guitar chords, and shows them above the lyrics.

## What it does

1. Upload audio/video **or** click **Try demo progression**
2. Detects major/minor chords
3. Transcribes lyrics (or uses pasted lyrics)
4. Shows a song sheet: **chords above the words**, plus chord diagrams

## Run

```bash
cd ~/guitar-chord-coach
source ~/.local/bin/env   # if `uv` is not already on PATH
uv run python scripts/generate_demo.py
uv run uvicorn app.main:app --reload --port 8765
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) (or **8770** if that’s the port you’re using)

## Free public website

AWS/Azure free tiers are usually too small for this ML app.  
Use **Hugging Face Spaces** (free) — see **[DEPLOY.md](DEPLOY.md)**.

You can keep editing locally and re-deploy after changes.

## Quick test

1. Click **Try demo progression** (C → G → Am → F)
2. Press play and follow the chords above the lyrics
3. Or upload your own MP3/MP4

## Stack

- FastAPI + librosa chroma chord templates
- faster-whisper for lyric transcription
- Demucs for optional guitar isolation
- Bundled ffmpeg via `imageio-ffmpeg`

## Lyrics agent

When you upload a song, a lyrics agent:
1. Looks up real lyrics (LRCLIB) using title/artist or the filename
2. Prefers **synced** lyrics with timestamps
3. Falls back to Whisper transcription if no catalog match
4. Places detected chords above the lyric words

Enter title + artist for best results (e.g. Free Bird / Lynyrd Skynyrd).


Tick **Isolate guitar** before uploading a full-band track. Demucs keeps a guitar-focused stem, then chord detection runs on that.

## Limits

- Chords: major/minor only (no 7ths, sus, slash chords yet)
- Lyric placement is approximate
- Full-band mixes and heavy distortion are harder
- Max clip length: 4 minutes
