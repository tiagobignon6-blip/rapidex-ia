#!/bin/bash
set -e
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RAPIDEX IA — Setup completo (v2.1)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── 1. Dependências base
echo "[1/6] Instalando dependências base..."
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

# ── 2. Fish Speech V1.5
echo "[2/6] Instalando Fish Speech V1.5..."
if [ ! -d "/workspace/fish-speech" ]; then
  cd /workspace
  git clone https://github.com/fishaudio/fish-speech.git --depth=1
  cd fish-speech
  pip install -q -e . || true
fi

echo "[2/6] Baixando checkpoints Fish Speech V1.5..."
mkdir -p /workspace/fish-speech/checkpoints
python - <<'PYEOF'
from huggingface_hub import snapshot_download
try:
    snapshot_download(
        repo_id="fishaudio/fish-speech-1.5",
        local_dir="/workspace/fish-speech/checkpoints/fish-speech-1.5",
        ignore_patterns=["*.md"]
    )
    print("  ✓ Fish Speech 1.5 weights")
except Exception as e:
    print(f"  ⚠ Fish Speech 1.5: {e}")
PYEOF

# Symlink do VQGAN (fica dentro do dir 1.5)
if [ -f "/workspace/fish-speech/checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth" ]; then
  ln -sf \
    "/workspace/fish-speech/checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth" \
    "/workspace/fish-speech/checkpoints/firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
fi

# ── 3. MuseTalk v1.5
echo "[3/6] Instalando MuseTalk..."
if [ ! -d "/workspace/MuseTalk" ]; then
  cd /workspace
  git clone https://github.com/TMElyralab/MuseTalk.git --depth=1
  cd MuseTalk
  pip install -q -r requirements.txt 2>/dev/null || true
fi

echo "[3/6] Baixando checkpoints MuseTalk..."
mkdir -p /workspace/MuseTalk/models/musetalk
mkdir -p /workspace/MuseTalk/models/dwpose
mkdir -p /workspace/MuseTalk/models/face-parse-bisenet
mkdir -p /workspace/MuseTalk/models/sd-vae-ft-mse
mkdir -p /workspace/MuseTalk/models/whisper

python - <<'PYEOF'
from huggingface_hub import hf_hub_download, snapshot_download
base = "/workspace/MuseTalk/models"

# MuseTalk weights (v1.5)
try:
    snapshot_download(
        repo_id="TMElyralab/MuseTalk",
        local_dir=f"{base}/musetalk",
        ignore_patterns=["*.md"]
    )
    print("  ✓ MuseTalk weights")
except Exception as e:
    print(f"  ⚠ MuseTalk weights: {e}")

# DWPose
try:
    for f in ["dw-ll_ucoco_384.onnx", "det_person.onnx"]:
        hf_hub_download(repo_id="yzd-v/DWPose", filename=f, local_dir=f"{base}/dwpose")
    print("  ✓ DWPose")
except Exception as e:
    print(f"  ⚠ DWPose: {e}")

# SD VAE
try:
    snapshot_download(
        repo_id="stabilityai/sd-vae-ft-mse",
        local_dir=f"{base}/sd-vae-ft-mse",
        ignore_patterns=["*.md"]
    )
    print("  ✓ SD VAE")
except Exception as e:
    print(f"  ⚠ SD VAE: {e}")
PYEOF

# ── 4. Wav2Lip (fallback)
echo "[4/6] Instalando Wav2Lip (fallback)..."
if [ ! -d "/workspace/Wav2Lip" ]; then
  cd /workspace
  git clone https://github.com/Rudrabha/Wav2Lip.git --depth=1 || true
  mkdir -p /workspace/Wav2Lip/checkpoints
  echo "  ⚠ Coloque manualmente wav2lip_gan.pth em /workspace/Wav2Lip/checkpoints/ (modelo não está no HF público)"
fi

# ── 5. Copia app.py para workspace
echo "[5/6] Instalando app RAPIDEX IA..."
if [ -f "/workspace/app.py" ]; then
  cp /workspace/app.py /workspace/app_backup_$(date +%s).py
fi
if [ -f "$SCRIPT_DIR/app.py" ]; then
  cp "$SCRIPT_DIR/app.py" /workspace/app.py
  echo "  ✓ app.py copiado"
else
  echo "  ⚠ app.py não encontrado em $SCRIPT_DIR"
fi

# ── 6. Atualiza startup.sh
echo "[6/6] Atualizando startup.sh..."
cat > /workspace/startup.sh << 'STARTUP'
#!/bin/bash
echo "Iniciando RAPIDEX IA..."
pip install -q gradio whisperx deep-translator demucs opencv-python ffmpeg-python "transformers==4.40.0" accelerate ctranslate2 2>/dev/null
python /workspace/app.py
STARTUP
chmod +x /workspace/startup.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Setup concluído!"
echo "  Para iniciar: python /workspace/app.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
