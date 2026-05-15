#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# RAPIDEX IA v3.3 - startup_runpod.sh
# Instala TUDO e sobe o app. Rodar: bash startup_runpod.sh
# Versoes pinadas com base em testes E2E reais.
# ─────────────────────────────────────────────────────────────────────────────
set -e

export WORKSPACE="${WORKSPACE:-/workspace}"
export COQUI_TOS_AGREED=1
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false

REPO_URL="https://github.com/tiagobignon6-blip/rapidex-ia.git"
REPO_DIR="$WORKSPACE/rapidex-ia"
LOG="$WORKSPACE/rapidex.log"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     RAPIDEX IA v3.3 - Startup           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Python deps (versoes compativeis testadas) ─────────────────────────────
echo "[1/6] Instalando dependencias Python..."
pip install -q --upgrade pip

# torch + torchvision + torchaudio precisam ser TRIPLET compativel.
# Em RunPod com CUDA, geralmente vem pre-instalado. So instalamos se faltar.
python -c "import torch, torchvision, torchaudio" 2>/dev/null || {
  echo "  Instalando triplet torch CUDA..."
  pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 2>/dev/null \
    || pip install -q torch torchvision torchaudio
}

pip install -q \
  "gradio>=4.44.0" \
  whisperx \
  deep-translator \
  demucs \
  gtts \
  opencv-python-headless \
  "transformers>=4.48.0,<4.55.0" \
  accelerate \
  ctranslate2 \
  ffmpeg-python \
  librosa \
  scipy \
  huggingface_hub \
  2>&1 | tail -5

# Coqui TTS OPCIONAL - pode conflitar com transformers novos.
# Se nao instalar, o pipeline cai pro gTTS automaticamente (sem clonagem mas funciona).
pip install -q TTS 2>/dev/null && echo "  OK Coqui TTS (clonagem de voz disponivel)" \
  || echo "  Coqui TTS nao instalado - usara gTTS (voz sintetica) como fallback"
echo "  OK dependencias Python"

# ── 2. FFmpeg ─────────────────────────────────────────────────────────────────
echo "[2/6] Verificando FFmpeg..."
if ! command -v ffmpeg &>/dev/null; then
  apt-get install -y -q ffmpeg 2>/dev/null || true
fi
command -v ffmpeg &>/dev/null && echo "  OK FFmpeg" || echo "  AVISO: FFmpeg nao encontrado"

# ── 3. Codigo do GitHub ───────────────────────────────────────────────────────
echo "[3/6] Atualizando codigo do GitHub..."
if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR" && git pull --quiet && cd "$WORKSPACE"
else
  git clone --quiet "$REPO_URL" "$REPO_DIR"
fi
cp "$REPO_DIR/app.py"      "$WORKSPACE/app.py"
cp "$REPO_DIR/pipeline.py" "$WORKSPACE/pipeline.py"
# Garante que o python ache pipeline.py (mesmo dir do app.py)
echo "  OK codigo atualizado"

# ── 4. Wav2Lip (lipsync principal) ────────────────────────────────────────────
echo "[4/6] Instalando Wav2Lip..."
WAV2LIP_DIR="$WORKSPACE/Wav2Lip"
WAV2LIP_CK="$WAV2LIP_DIR/checkpoints/wav2lip_gan.pth"
WAV2LIP_SFD="$WAV2LIP_DIR/face_detection/detection/sfd/s3fd.pth"

if [ ! -d "$WAV2LIP_DIR/.git" ]; then
  echo "  Clonando Wav2Lip..."
  git clone --quiet https://github.com/Rudrabha/Wav2Lip.git "$WAV2LIP_DIR"
fi

cd "$WAV2LIP_DIR"

# Instalar requirements do Wav2Lip
pip install -q -r requirements.txt 2>/dev/null || \
  pip install -q librosa scipy batch_face_alignment 2>/dev/null || true

# Criar diretorios
mkdir -p checkpoints face_detection/detection/sfd results temp

# Baixar modelo wav2lip_gan.pth
if [ ! -f "$WAV2LIP_CK" ]; then
  echo "  Baixando wav2lip_gan.pth..."
  wget -q --show-progress \
    "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth" \
    -O "$WAV2LIP_CK" && echo "  OK wav2lip_gan.pth" || echo "  ERRO wav2lip_gan.pth"
else
  echo "  OK wav2lip_gan.pth ja presente"
fi

# Baixar s3fd.pth (detector facial - OBRIGATORIO para Wav2Lip funcionar)
if [ ! -f "$WAV2LIP_SFD" ]; then
  echo "  Baixando s3fd.pth (detector facial)..."
  # Tenta HuggingFace primeiro
  wget -q --show-progress \
    "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth" \
    -O "$WAV2LIP_SFD" 2>/dev/null || \
  wget -q --show-progress \
    "https://huggingface.co/camenduru/Wav2Lip/resolve/main/face_detection/detection/sfd/s3fd.pth" \
    -O "$WAV2LIP_SFD" 2>/dev/null || \
  python3 -c "
import urllib.request
url = 'https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth'
urllib.request.urlretrieve(url, '$WAV2LIP_SFD')
print('s3fd.pth baixado via Python')
" 2>/dev/null || echo "  AVISO: s3fd.pth nao baixado - Wav2Lip pode falhar"

  [ -f "$WAV2LIP_SFD" ] && echo "  OK s3fd.pth" || echo "  AVISO: s3fd.pth ausente"
else
  echo "  OK s3fd.pth ja presente"
fi

cd "$WORKSPACE"
echo "  OK Wav2Lip instalado"

# ── 5. Pastas e modelos ───────────────────────────────────────────────────────
echo "[5/6] Preparando estrutura de pastas..."
mkdir -p "$WORKSPACE/outputs" "$WORKSPACE/models"
echo "  OK estrutura pronta"

# ── 6. Sobe o app ─────────────────────────────────────────────────────────────
echo "[6/6] Iniciando RAPIDEX IA..."
echo ""

cd "$WORKSPACE"
nohup python app.py > "$LOG" 2>&1 &
APP_PID=$!
echo "  PID: $APP_PID"
echo "  Log: tail -f $LOG"
echo ""

# Aguarda link do Gradio
echo "  Aguardando link publico (max 120s)..."
for i in $(seq 1 60); do
  LINK=$(grep -m1 "gradio.live\|Running on public" "$LOG" 2>/dev/null || true)
  if [ -n "$LINK" ]; then
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║  RAPIDEX IA ESTA NO AR!                 ║"
    echo "║  $LINK"
    echo "╚══════════════════════════════════════════╝"
    break
  fi
  sleep 2
done

if [ -z "$LINK" ]; then
  echo ""
  echo "AVISO: Link nao apareceu em 120s. Log:"
  tail -15 "$LOG"
fi
