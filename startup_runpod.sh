#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# RAPIDEX IA v3.0 — startup_runpod.sh
# Roda no RunPod ao iniciar o pod. Instala tudo e sobe o app.
# ─────────────────────────────────────────────────────────────────────────────

set -e
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     ⚡ RAPIDEX IA — Startup v3.0         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

WORKSPACE="/workspace"
REPO_URL="https://github.com/tiagobignon6-blip/rapidex-ia.git"
REPO_DIR="$WORKSPACE/rapidex-ia"
LOG="$WORKSPACE/rapidex.log"

# ── 1. Dependências Python ────────────────────────────────────────────────────
echo "[1/5] Instalando dependências Python..."

pip install -q --upgrade pip

pip install -q \
  "gradio>=4.44.0" \
  whisperx \
  deep-translator \
  demucs \
  gtts \
  opencv-python-headless \
  transformers \
  accelerate \
  ctranslate2 \
  torchaudio \
  ffmpeg-python \
  2>/dev/null || true

pip install -q TTS 2>/dev/null || echo "  Coqui TTS nao instalado (opcional)"

echo "  ✓ Dependências OK"

# ── 2. FFmpeg ─────────────────────────────────────────────────────────────────
echo "[2/5] Verificando FFmpeg..."
if ! command -v ffmpeg &>/dev/null; then
  apt-get install -y -q ffmpeg 2>/dev/null || true
fi
ffmpeg -version 2>/dev/null | head -1 && echo "  ✓ FFmpeg OK" || echo "  ⚠ FFmpeg não encontrado"

# ── 3. Código do GitHub ───────────────────────────────────────────────────────
echo "[3/5] Atualizando código do GitHub..."
if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR" && git pull --quiet && cd "$WORKSPACE"
else
  git clone --quiet "$REPO_URL" "$REPO_DIR"
fi

cp "$REPO_DIR/app.py"      "$WORKSPACE/app.py"
cp "$REPO_DIR/pipeline.py" "$WORKSPACE/pipeline.py"
echo "  ✓ Código atualizado"

# ── 4. Lipsync ────────────────────────────────────────────────────────────────
echo "[4/5] Verificando lipsync..."

WAV2LIP_CK="$WORKSPACE/Wav2Lip/checkpoints/wav2lip_gan.pth"
if [ ! -f "$WAV2LIP_CK" ]; then
  echo "  ↳ Baixando Wav2Lip checkpoint..."
  mkdir -p "$WORKSPACE/Wav2Lip/checkpoints"
  wget -q --show-progress \
    "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth" \
    -O "$WAV2LIP_CK" && echo "  ✓ Wav2Lip OK" || echo "  ⚠ Wav2Lip nao baixado"
else
  echo "  ✓ Wav2Lip ja presente"
fi

mkdir -p "$WORKSPACE/outputs" "$WORKSPACE/models"

# ── 5. Sobe o app ─────────────────────────────────────────────────────────────
echo "[5/5] Iniciando RAPIDEX IA..."
echo ""

cd "$WORKSPACE"
nohup python app.py > "$LOG" 2>&1 &
APP_PID=$!
echo "  PID: $APP_PID"
echo "  Log: $LOG"
echo ""

echo "  Aguardando link público..."
for i in $(seq 1 60); do
  LINK=$(grep -m1 "gradio.live\|Running on public" "$LOG" 2>/dev/null || true)
  if [ -n "$LINK" ]; then
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║  ✅  RAPIDEX IA ESTA NO AR!              ║"
    echo "║  $LINK"
    echo "╚══════════════════════════════════════════╝"
    break
  fi
  sleep 2
done

if [ -z "$LINK" ]; then
  echo ""
  echo "⚠ Link nao apareceu em 120s. Ultimas linhas do log:"
  tail -10 "$LOG"
fi
