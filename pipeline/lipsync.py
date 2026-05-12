"""MuseTalk primary lipsync; Wav2Lip fallback on MuseTalk failure."""

from __future__ import annotations

import os
import subprocess

import gradio as gr

from pipeline.runtime import MUSETALK_DIR, WAV2LIP_DIR, detect_device


def run_lipsync(video: str, audio: str, out_dir: str) -> str:
    if detect_device() == "cpu":
        raise gr.Error(
            "GPU required: lipsync (MuseTalk + Wav2Lip) needs CUDA. "
            "Set RAPIDEX_DEVICE=cuda on a CUDA host, or run with the full "
            "Compose recipe (infra/local/docker-compose.yml)."
        )
    output = os.path.join(out_dir, "rapidex_output.mp4")
    subprocess.run([
        "python", f"{MUSETALK_DIR}/scripts/inference.py",
        "--video_path", video, "--audio_path", audio,
        "--output_path", output, "--bbox_shift", "0",
    ], capture_output=True, text=True, cwd=MUSETALK_DIR)
    if os.path.exists(output):
        return output
    # fallback Wav2Lip
    subprocess.run([
        "python", f"{WAV2LIP_DIR}/inference.py",
        "--checkpoint_path", f"{WAV2LIP_DIR}/checkpoints/wav2lip_gan.pth",
        "--face", video, "--audio", audio,
        "--outfile", output,
        "--pads", "0", "10", "0", "0", "--resize_factor", "1",
    ], check=True, capture_output=True, cwd=WAV2LIP_DIR)
    return output
