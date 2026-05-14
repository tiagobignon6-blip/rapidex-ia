#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# RAPIDEX IA — Startup RunPod
# Roda: bash startup_runpod.sh
# ─────────────────────────────────────────────────────────────────────────────

echo "⚡ RAPIDEX IA — Setup RunPod..."

# 1. Dependências pip
echo "[1/4] Instalando dependências..."
pip install -q gradio openai-whisper whisperx deep-translator demucs \
    gtts opencv-python matplotlib transformers accelerate ctranslate2 2>/dev/null
pip install -q --upgrade click 'typer<0.25' 2>/dev/null

# 2. Puxa código mais recente do GitHub
echo "[2/4] Atualizando código do GitHub..."
cd /workspace
if [ -d "rapidex-ia/.git" ]; then
    cd rapidex-ia && git pull && cd ..
else
    git clone https://github.com/tiagobignon6-blip/rapidex-ia.git
fi
cp rapidex-ia/app.py /workspace/app.py

# 3. Verifica modelos essenciais
echo "[3/4] Verificando modelos..."
# Wav2Lip (fallback de lipsync)
if [ ! -f "/workspace/Wav2Lip/checkpoints/wav2lip_gan.pth" ]; then
    echo "  ↳ Baixando Wav2Lip..."
    mkdir -p /workspace/Wav2Lip/checkpoints
    wget -q "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth" \
         -O /workspace/Wav2Lip/checkpoints/wav2lip_gan.pth
fi

# 4. Sobe o app
echo "[4/4] Subindo RAPIDEX IA..."
cd /workspace
nohup python app.py > /tmp/rapidex.log 2>&1 &
sleep 40 && grep -m1 'gradio.live' /tmp/rapidex.log || tail -5 /tmp/rapidex.log
