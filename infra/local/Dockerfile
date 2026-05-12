# RAPIDEX IA — local dev image (WSL2 + NVIDIA GPU).
#
# Shares ~90% with the upcoming infra/hfspaces/Dockerfile (Phase 10).
# Differences are env defaults + GRADIO_SHARE + HF_HOME (handled there,
# not here). Keep the body in sync when Phase 10 lands.
#
# CUDA 11.8 base picked for maximum host-driver compatibility (NVIDIA
# driver ≥520.61 supports it — i.e. virtually any modern Windows host
# with WSL2 GPU passthrough). Pair with cu118 torch wheels in
# requirements.txt. If you upgrade your host driver to ≥535, you can
# safely move both to cu121 — they share the same PyTorch 2.4.1 release.

FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps. ffmpeg is mandatory (audio extraction + mix). git/wget needed
# because MuseTalk, Wav2Lip, and fish-speech are git-clones at boot, not pip.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 \
        python3.10-venv \
        python3-pip \
        ffmpeg \
        git \
        wget \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python

WORKDIR /app

# Install Python deps first (cache layer). The cu121 extra-index is already
# in requirements.txt so torch wheels resolve correctly.
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r /app/requirements.txt

# App source (everything except weights, outputs, venvs — covered by .gitignore
# and .dockerignore if present).
COPY . /app

# Runtime profile — Local dev defaults. Override via .env / compose env_file.
ENV RAPIDEX_MODELS_DIR=/app/models \
    RAPIDEX_OUTPUTS_DIR=/app/outputs \
    MUSETALK_DIR=/app/models/musetalk \
    WAV2LIP_DIR=/app/models/wav2lip \
    FISH_SPEECH_DIR=/app/models/fish-speech \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SHARE=false

EXPOSE 7860

CMD ["bash", "infra/local/start.sh"]
