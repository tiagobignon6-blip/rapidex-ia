"""Demucs wrapper: split source audio into vocals + background stems."""

from __future__ import annotations

import os
import subprocess


def run_demucs(raw_audio: str, out_dir: str) -> tuple[str, str]:
    demucs_out = os.path.join(out_dir, "demucs")
    subprocess.run([
        "python", "-m", "demucs", "--two-stems=vocals", "-o", demucs_out, raw_audio,
    ], check=True, capture_output=True)
    stem_dir = None
    for root, _dirs, files in os.walk(demucs_out):
        if "vocals.wav" in files:
            stem_dir = root
            break
    if stem_dir is None:
        raise RuntimeError("Demucs não gerou vocals.wav")
    return os.path.join(stem_dir, "vocals.wav"), os.path.join(stem_dir, "no_vocals.wav")
