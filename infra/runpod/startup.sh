#!/usr/bin/env bash
# RAPIDEX IA — canonical pod entrypoint.
# Replaces the legacy /workspace/startup.sh after the swap (see SWAP-PROCEDURE.md).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Env defaults — override via the pod's env or .env
export RAPIDEX_MODELS_DIR="${RAPIDEX_MODELS_DIR:-$REPO_ROOT/models}"
export RAPIDEX_OUTPUTS_DIR="${RAPIDEX_OUTPUTS_DIR:-$REPO_ROOT/outputs}"
export GRADIO_SERVER_NAME="${GRADIO_SERVER_NAME:-0.0.0.0}"
export GRADIO_SHARE="${GRADIO_SHARE:-true}"

mkdir -p "$RAPIDEX_MODELS_DIR" "$RAPIDEX_OUTPUTS_DIR"

# Idempotent model fetch (per D-02 — manifest-driven, SHA-verified, skip if present)
boot_start=$(date +%s)
echo "[boot] verifying models in $RAPIDEX_MODELS_DIR ..."
python scripts/download_models.py
boot_elapsed=$(( $(date +%s) - boot_start ))
echo "[boot] models ready in ${boot_elapsed}s"

# Launch the Gradio app in the foreground — operator wants visible logs during validation
echo "[boot] launching app.py (GRADIO_SHARE=$GRADIO_SHARE) ..."
exec python app.py
