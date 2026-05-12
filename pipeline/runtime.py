"""Runtime profile: env-driven paths + device autodetect.

Shared by app.py and every pipeline/*.py module. Centralizing here avoids
circular imports back to app.py.

Resolution priority for paths:
    1. Explicit env var (e.g. MUSETALK_DIR=/foo)
    2. Legacy /workspace/<name> if that dir exists on disk (pod no-regression)
    3. ${RAPIDEX_MODELS_DIR}/<fallback> (local + HF Spaces default)
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_dir(env_name: str, legacy_path: str, fallback_under_models: str) -> str:
    if env_value := os.environ.get(env_name):
        return env_value
    if os.path.isdir(legacy_path):
        return legacy_path
    models_dir = os.environ.get("RAPIDEX_MODELS_DIR", str(REPO_ROOT / "models"))
    return str(Path(models_dir) / fallback_under_models)


MUSETALK_DIR = resolve_dir("MUSETALK_DIR", "/workspace/MuseTalk", "musetalk")
WAV2LIP_DIR = resolve_dir("WAV2LIP_DIR", "/workspace/Wav2Lip", "wav2lip")
FISH_SPEECH_DIR = resolve_dir("FISH_SPEECH_DIR", "/workspace/fish-speech", "fish-speech")
OUTPUTS_DIR = os.environ.get(
    "RAPIDEX_OUTPUTS_DIR",
    "/workspace" if os.path.isdir("/workspace") else str(REPO_ROOT / "outputs"),
)
os.makedirs(OUTPUTS_DIR, exist_ok=True)


def detect_device(override: str | None = None) -> str:
    """Return cuda → mps → cpu. RAPIDEX_DEVICE env overrides everything."""
    forced = override or os.environ.get("RAPIDEX_DEVICE")
    if forced:
        return forced
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"
