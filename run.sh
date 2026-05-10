#!/bin/bash
# RAPIDEX IA — script único: instala deps + copia app + roda
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RAPIDEX IA — Run"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/3] Instalando dependências Python..."
pip install -q --upgrade pip
pip install -q \
  gradio \
  openai-whisper \
  whisperx \
  deep-translator \
  demucs \
  opencv-python \
  ffmpeg-python \
  "transformers==4.40.0" \
  accelerate \
  ctranslate2 \
  huggingface_hub

echo "[2/3] Copiando app.py para /workspace..."
cp "$SCRIPT_DIR/app.py" /workspace/app.py

echo "[3/3] Iniciando app..."
python /workspace/app.py
