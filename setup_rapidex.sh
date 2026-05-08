#!/bin/bash
set -e
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RAPIDEX IA — Setup completo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Dependências base
echo "[1/5] Instalando dependências base..."
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
  ctranslate2

# ── 2. Fish Speech V1.5
echo "[2/5] Instalando Fish Speech V1.5..."
pip install -q fish-speech 2>/dev/null || {
  cd /workspace
  git clone https://github.com/fishaudio/fish-speech.git --depth=1 2>/dev/null || true
  cd fish-speech
  pip install -q -e . 2>/dev/null || true
  cd /workspace
}

# ── 3. MuseTalk
echo "[3/5] Instalando MuseTalk..."
if [ ! -d "/workspace/MuseTalk" ]; then
  cd /workspace
  git clone https://github.com/TMElyralab/MuseTalk.git --depth=1
  cd MuseTalk
  pip install -q -r requirements.txt 2>/dev/null || true
fi

# Checkpoints MuseTalk
echo "[3/5] Baixando checkpoints MuseTalk..."
mkdir -p /workspace/MuseTalk/models/musetalk
mkdir -p /workspace/MuseTalk/models/dwpose
mkdir -p /workspace/MuseTalk/models/face-parse-bisenet
mkdir -p /workspace/MuseTalk/models/sd-vae-ft-mse

# Download via huggingface-cli
pip install -q huggingface_hub
python - <<'PYEOF'
from huggingface_hub import hf_hub_download, snapshot_download
import os

base = "/workspace/MuseTalk/models"

# MuseTalk weights
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
        hf_hub_download(
            repo_id="yzd-v/DWPose",
            filename=f,
            local_dir=f"{base}/dwpose"
        )
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

print("  Checkpoints concluídos.")
PYEOF

# ── 4. Copia app.py para workspace
echo "[4/5] Instalando app RAPIDEX IA..."
if [ -f "/workspace/app.py" ]; then
  cp /workspace/app.py /workspace/app_backup_$(date +%s).py
fi
cp "$(dirname "$0")/app.py" /workspace/app.py 2>/dev/null || echo "  (coloque o app.py manualmente em /workspace/app.py)"

# ── 5. Atualiza startup.sh
echo "[5/5] Atualizando startup.sh..."
cat > /workspace/startup.sh << 'STARTUP'
#!/bin/bash
echo "Iniciando RAPIDEX IA..."
pip install -q gradio whisperx deep-translator demucs fish-speech opencv-python ffmpeg-python "transformers==4.40.0" accelerate ctranslate2 2>/dev/null
python /workspace/app.py
STARTUP
chmod +x /workspace/startup.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Setup concluído!"
echo "  Para iniciar: python /workspace/app.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
