"""Fish Speech V1.5 wrapper with reference-prompt voice cloning."""

from __future__ import annotations

import os
import subprocess

import gradio as gr

from pipeline.runtime import detect_device


def run_fish_speech(text: str, ref_wav: str, out_dir: str) -> str:
    device = detect_device()
    if device == "cpu":
        raise gr.Error(
            "GPU required: Fish Speech V1.5 needs CUDA. "
            "Set RAPIDEX_DEVICE=cuda on a CUDA host, or run with the full "
            "Compose recipe (infra/local/docker-compose.yml)."
        )
    dubbed = os.path.join(out_dir, "dubbed_voice.wav")
    r = subprocess.run([
        "python", "-m", "fish_speech.inference",
        "--text", text,
        "--reference-audio", ref_wav,
        "--output", dubbed,
        "--device", device,
    ], capture_output=True, text=True)
    if not os.path.exists(dubbed):
        raise RuntimeError(f"Fish Speech falhou:\n{r.stderr}")
    return dubbed
