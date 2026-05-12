#!/usr/bin/env bash
# RAPIDEX IA — local dev entrypoint.
#
# Used by the docker-compose service AND by bare-metal WSL2 runs:
#   bash infra/local/start.sh
#
# Bootstraps the from-git ML libs (MuseTalk, Wav2Lip, fish-speech) on first
# boot, fetches model weights via the manifest, then launches the Gradio app.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Profile defaults — overridable via .env or the host environment.
export RAPIDEX_MODELS_DIR="${RAPIDEX_MODELS_DIR:-$REPO_ROOT/models}"
export RAPIDEX_OUTPUTS_DIR="${RAPIDEX_OUTPUTS_DIR:-$REPO_ROOT/outputs}"
export MUSETALK_DIR="${MUSETALK_DIR:-$RAPIDEX_MODELS_DIR/musetalk}"
export WAV2LIP_DIR="${WAV2LIP_DIR:-$RAPIDEX_MODELS_DIR/wav2lip}"
export FISH_SPEECH_DIR="${FISH_SPEECH_DIR:-$RAPIDEX_MODELS_DIR/fish-speech}"
export GRADIO_SERVER_NAME="${GRADIO_SERVER_NAME:-0.0.0.0}"
export GRADIO_SHARE="${GRADIO_SHARE:-false}"

mkdir -p "$RAPIDEX_MODELS_DIR" "$RAPIDEX_OUTPUTS_DIR" \
         "$MUSETALK_DIR" "$WAV2LIP_DIR" "$FISH_SPEECH_DIR"

# ── From-git ML libraries (not in requirements.txt; PyPI distributions are
#    inconsistent for MuseTalk / Wav2Lip / fish-speech).
clone_or_skip() {
    local dest="$1" repo="$2" ref="${3:-main}"
    if [ -d "$dest/.git" ]; then
        echo "[boot] $dest already cloned"
        return
    fi
    echo "[boot] cloning $repo @ $ref → $dest"
    git clone --depth=1 -b "$ref" "$repo" "$dest" || git clone --depth=1 "$repo" "$dest"
}

clone_or_skip "$MUSETALK_DIR/src"       "https://github.com/TMElyralab/MuseTalk.git"
clone_or_skip "$WAV2LIP_DIR/src"        "https://github.com/Rudrabha/Wav2Lip.git"
clone_or_skip "$FISH_SPEECH_DIR/src"    "https://github.com/fishaudio/fish-speech.git"

# pipeline.lipsync invokes ${MUSETALK_DIR}/scripts/inference.py — that script
# lives inside the cloned src tree. Symlink it up so the existing app code
# doesn't need to change.
ln -sf "$MUSETALK_DIR/src/scripts"  "$MUSETALK_DIR/scripts"  2>/dev/null || true
ln -sf "$WAV2LIP_DIR/src/inference.py" "$WAV2LIP_DIR/inference.py" 2>/dev/null || true

# Install fish-speech (PyPI inconsistent — install editable from the clone)
if ! python -c "import fish_speech" 2>/dev/null; then
    echo "[boot] installing fish-speech from $FISH_SPEECH_DIR/src"
    pip install -e "$FISH_SPEECH_DIR/src" || true
fi

# ── Model weights via the manifest (idempotent; skips when present).
echo "[boot] verifying models in $RAPIDEX_MODELS_DIR ..."
boot_start=$(date +%s)
python scripts/download_models.py
echo "[boot] models ready in $(( $(date +%s) - boot_start ))s"

# ── Launch Gradio.
echo "[boot] launching app.py (GRADIO_SHARE=$GRADIO_SHARE, RAPIDEX_DEVICE=${RAPIDEX_DEVICE:-auto}) ..."
exec python app.py
