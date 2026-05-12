"""ffmpeg helpers: extract source audio, mix voice + background to final mp4."""

from __future__ import annotations

import os
import subprocess


def extract_audio(video_path: str, out_dir: str) -> str:
    raw_audio = os.path.join(out_dir, "raw_audio.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", raw_audio,
    ], check=True, capture_output=True)
    return raw_audio


def mix_audio(dubbed: str, bgmusic: str, out_dir: str) -> str:
    mixed = os.path.join(out_dir, "mixed_audio.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", dubbed, "-i", bgmusic,
        "-filter_complex",
        "[0:a]volume=1.0[v];[1:a]volume=0.35[b];[v][b]amix=inputs=2:duration=longest[out]",
        "-map", "[out]", mixed,
    ], check=True, capture_output=True)
    return mixed
