#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# RAPIDEX IA v3.2 - setup_rapidex.sh
# Setup pesado (uma vez por pod): Fish Speech, MuseTalk, checkpoints.
# Para boot diario: use startup_runpod.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

export WORKSPACE="${WORKSPACE:-/workspace}"
export COQUI_TOS_AGREED=1

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RAPIDEX IA - Setup completo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Dependencias base ──────────────────────────────────────────────────────
echo "[1/5] Instalando dependencias base..."
pip install -q --upgrade pip
pip install -q \
  "gradio>=4.44.0" \
  openai-whisper \
  whisperx \
  deep-translator \
  demucs \
  gtts \
  opencv-python-headless \
  ffmpeg-python \
  librosa \
  scipy \
  "transformers>=4.40.0" \
  accelerate \
  ctranslate2 \
  torchaudio \
  2>/dev/null || true

# Coqui XTTS opcional (clonagem de voz)
pip install -q TTS 2>/dev/null || echo "  Coqui TTS nao instalado (opcional)"

# ── 2. Fish Speech V1.5 (opcional) ────────────────────────────────────────────
echo "[2/5] Instalando Fish Speech V1.5..."
pip install -q fish-speech 2>/dev/null || {
  cd "$WORKSPACE"
  [ ! -d fish-speech ] && git clone --depth=1 https://github.com/fishaudio/fish-speech.git 2>/dev/null || true
  [ -d fish-speech ] && cd fish-speech && pip install -q -e . 2>/dev/null || true
  cd "$WORKSPACE"
}

# ── 3. MuseTalk ───────────────────────────────────────────────────────────────
echo "[3/5] Instalando MuseTalk..."
if [ ! -d "$WORKSPACE/MuseTalk" ]; then
  cd "$WORKSPACE"
  git clone --depth=1 https://github.com/TMElyralab/MuseTalk.git
  cd MuseTalk
  pip install -q -r requirements.txt 2>/dev/null || true
fi

echo "[3/5] Baixando checkpoints MuseTalk..."
mkdir -p "$WORKSPACE/MuseTalk/models/musetalk"
mkdir -p "$WORKSPACE/MuseTalk/models/dwpose"
mkdir -p "$WORKSPACE/MuseTalk/models/face-parse-bisenet"
mkdir -p "$WORKSPACE/MuseTalk/models/sd-vae-ft-mse"

pip install -q huggingface_hub
python - <<'PYEOF'
import os
from huggingface_hub import hf_hub_download, snapshot_download

base = os.path.join(os.environ.get("WORKSPACE", "/workspace"), "MuseTalk", "models")

# MuseTalk weights
try:
    snapshot_download(repo_id="TMElyralab/MuseTalk",
                      local_dir=f"{base}/musetalk",
                      ignore_patterns=["*.md"])
    print("  OK MuseTalk weights")
except Exception as e:
    print(f"  AVISO MuseTalk weights: {e}")

# DWPose
try:
    for f in ["dw-ll_ucoco_384.onnx", "det_person.onnx"]:
        hf_hub_download(repo_id="yzd-v/DWPose", filename=f, local_dir=f"{base}/dwpose")
    print("  OK DWPose")
except Exception as e:
    print(f"  AVISO DWPose: {e}")

# SD VAE
try:
    snapshot_download(repo_id="stabilityai/sd-vae-ft-mse",
                      local_dir=f"{base}/sd-vae-ft-mse",
                      ignore_patterns=["*.md"])
    print("  OK SD VAE")
except Exception as e:
    print(f"  AVISO SD VAE: {e}")
PYEOF

# ── 4. Copia codigo do app + pipeline ─────────────────────────────────────────
echo "[4/5] Instalando codigo RAPIDEX IA..."
SRC_DIR="$(dirname "$(readlink -f "$0")")"
for f in app.py pipeline.py; do
  if [ -f "$WORKSPACE/$f" ]; then
    cp "$WORKSPACE/$f" "$WORKSPACE/${f}.bak_$(date +%s)"
  fi
  cp "$SRC_DIR/$f" "$WORKSPACE/$f" 2>/dev/null || echo "  AVISO: $f nao encontrado em $SRC_DIR"
done

# ── 5. Gera startup.sh portavel ───────────────────────────────────────────────
echo "[5/5] Gerando startup.sh..."
cat > "$WORKSPACE/startup.sh" << 'STARTUP'
#!/bin/bash
set -e
export WORKSPACE="${WORKSPACE:-/workspace}"
export COQUI_TOS_AGREED=1
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false

echo "Iniciando RAPIDEX IA..."
pip install -q \
  "gradio>=4.44.0" whisperx deep-translator demucs gtts \
  opencv-python-headless ffmpeg-python librosa scipy \
  "transformers>=4.40.0" accelerate ctranslate2 torchaudio \
  2>/dev/null || true

cd "$WORKSPACE"
exec python app.py
STARTUP
chmod +x "$WORKSPACE/startup.sh"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup concluido!"
echo "  Iniciar: bash $WORKSPACE/startup.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
