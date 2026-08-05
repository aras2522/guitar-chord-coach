# Free-tier friendly CPU image for Hugging Face Spaces / Render / Fly
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    HF_HOME=/tmp/hf \
    TORCH_HOME=/tmp/torch \
    XDG_CACHE_HOME=/tmp/cache

WORKDIR /app

# System libs for audio (soundfile/librosa) + curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY static ./static
COPY scripts ./scripts

# CPU-only PyTorch first (much smaller than CUDA builds), then the app deps
RUN pip install --upgrade pip \
    && pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
    && pip install \
      "fastapi>=0.139.0" \
      "uvicorn[standard]>=0.51.0" \
      "python-multipart>=0.0.32" \
      "numpy>=2.4.6" \
      "librosa>=0.11.0" \
      "soundfile>=0.14.0" \
      "imageio-ffmpeg>=0.6.0" \
      "demucs>=4.0.1" \
      "faster-whisper>=1.2.1" \
      "httpx>=0.28.0" \
      "yt-dlp>=2026.7.4"

# Demo audio for the "Try demo" button
RUN python scripts/generate_demo.py && mkdir -p data/uploads

EXPOSE 7860

# HF Spaces and most PaaS inject $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
