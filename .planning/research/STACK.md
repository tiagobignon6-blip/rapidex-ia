# Technology Stack — RAPIDEX IA Supporting Tools

**Project:** RAPIDEX IA
**Researched:** 2026-05-09
**Confidence:** MEDIUM (training-data + ecosystem knowledge; versions to be re-pinned during Plan phase via Context7)

## Core ML Stack (locked — for reference only, do not change)

| Layer | Tool | Notes |
|---|---|---|
| Transcription | WhisperX large-v3 | VAD enabled — anti-hallucination |
| Translation | deep-translator | GoogleTranslator backend |
| TTS | Fish Speech V1.5 | reference-prompt voice cloning |
| Audio separation | Demucs | hidden from user |
| Lipsync | MuseTalk | primary |
| Lipsync fallback | Wav2Lip | safety net when MuseTalk fails |
| UI | Gradio | v4.x recommended (4.44+) |
| GPU | RunPod (current) + HF Spaces (planned) | dual deploy target |

## Supporting Tools (research scope)

### Video Pre/Post Processing

| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `ffmpeg` (system) | 6.x+ | All video I/O, aspect-ratio transforms | De-facto standard, handles every codec MuseTalk emits | HIGH |
| `ffmpeg-python` | 0.2.0+ | Python bindings to ffmpeg pipes | Cleaner than `subprocess.run` for chained filters; no extra deps | HIGH |
| `moviepy` | 2.x | (Avoid) high-level video editing | Heavy + slow; replaced by direct ffmpeg | HIGH (anti-rec) |
| `opencv-python-headless` | 4.10+ | Frame-level reads for face crop / aspect probe | Already a transitive dep of MuseTalk; reuse | HIGH |
| `Pillow` | 10.4+ | Logo overlay, header image manipulation | Standard, lightweight | HIGH |

### Testing

| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `pytest` | 8.3+ | Test runner | Standard; integrates with everything | HIGH |
| `pytest-asyncio` | 0.24+ | Async fixtures for Gradio | Gradio 4 internally async | HIGH |
| `gradio_client` | matches Gradio version | Programmatic Gradio invocation for E2E | Official; same API surface as the app | HIGH |
| `pytest-xdist` | 3.6+ | Parallel test execution | Useful for CPU unit tests | MEDIUM |
| `pytest-recording` (`vcrpy`) | 0.13+ | Cassette translation API responses | deep-translator hits Google; freeze responses for repeatable tests | HIGH |
| `pytest-snapshot` | 0.9+ | Snapshot text/JSON outputs | Good for transcript / translation diffs | HIGH |
| `imagehash` | 4.3+ | Perceptual hash for video frame comparison | Tolerates small numeric drift in lipsync output | MEDIUM |

### Deployment Packaging

| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `huggingface_hub` | 0.25+ | Model download + cache mgmt on HF Spaces | Standard for HF Spaces apps; respects `HF_HOME` | HIGH |
| `Dockerfile` (HF Spaces SDK) | — | Custom Docker for heavy deps | `requirements.txt` SDK is too constrained for WhisperX+ctranslate2+Fish Speech matrix | HIGH |
| `uv` or `pip-tools` | uv 0.4+ / pip-tools 7.4+ | Pinning + resolving conflicting deps | PyTorch + ctranslate2 + faster-whisper + Fish Speech have brittle pin matrix | MEDIUM |
| `gradio[oauth]` | 4.44+ | Gradio with OAuth for HF Spaces auth (optional) | Future-proof if private-Space auth is needed | LOW (optional) |

### Repo Layout / Tooling

| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `git-lfs` | 3.5+ | Optional: track sample test fixtures (small mp4s) only | Do NOT use for model weights — those stay out of git | HIGH |
| `pre-commit` | 4.0+ | Lint hooks before commit | Cheap protection for the locked branch policy | MEDIUM |
| `ruff` | 0.6+ | Fast linter+formatter (replaces flake8+black+isort) | Single tool, low overhead | HIGH |
| `python-dotenv` | 1.0+ | `.env` for local secrets (HF_TOKEN, etc.) | Standard; keep `.env` in `.gitignore` | HIGH |

## HuggingFace Spaces Hardware Recommendation

**Recommended for the full pipeline:** `Nvidia A10G Small` (24 GB VRAM) or `A10G Large` (48 GB VRAM).

Reasoning:
- WhisperX large-v3 (FP16) ≈ 6 GB VRAM
- Fish Speech V1.5 ≈ 4 GB VRAM
- MuseTalk + face detection ≈ 4-6 GB VRAM (batch-size dependent)
- Demucs (htdemucs) ≈ 2 GB VRAM
- Concurrent residency: ~16-20 GB peak → A10G Small fits with headroom; T4 (16 GB) is borderline.

**Avoid ZeroGPU** for v1: cold-start downloads + ZeroGPU's 60-120s queue timeouts conflict with the long-running dub pipeline (typical run: 2-8 minutes).

**Cost note:** A10G Small on HF Spaces ≈ $0.60/hr (May 2026 rates — verify before committing). Cheaper than RunPod equivalent if usage is < 50% of a 24/7 pod.

## Alternatives Considered (and rejected)

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Video lib | `ffmpeg-python` | `moviepy` | 5-10x slower, larger surface, breaks under concurrent calls |
| Test runner | `pytest` | `unittest` | Nobody writes ML tests in `unittest` anymore |
| Programmatic Gradio | `gradio_client` | scripting via `requests` | Brittle to Gradio version changes; official client tracks the app |
| HF Spaces SDK | Custom `Dockerfile` | Default `requirements.txt` | requirements.txt SDK pins Python 3.10 + can't install `ffmpeg` system pkg |
| HF GPU tier | A10G Small | ZeroGPU | Cold-start + queue timeouts kill long pipelines |
| HF GPU tier | A10G Small | T4 | 16 GB borderline at peak; OOM under load |
| Repo: ML weights | gitignored, downloaded on first boot | Git LFS for weights | LFS quotas + bandwidth costs; HF model hub is the right home |

## Installation Snippet

```bash
# System deps (HF Spaces Dockerfile or RunPod startup)
apt-get install -y ffmpeg libsndfile1

# Python deps (pin matrix — refine with Context7 in Plan phase)
pip install \
    "gradio>=4.44,<5" \
    "gradio_client" \
    "ffmpeg-python>=0.2.0" \
    "huggingface_hub>=0.25" \
    "Pillow>=10.4" \
    "python-dotenv>=1.0"

# Dev / test deps
pip install \
    "pytest>=8.3" \
    "pytest-asyncio>=0.24" \
    "pytest-xdist>=3.6" \
    "pytest-recording>=0.13" \
    "pytest-snapshot>=0.9" \
    "imagehash>=4.3" \
    "ruff>=0.6" \
    "pre-commit>=4.0"
```

## Sources

- HuggingFace Spaces hardware tier docs: https://huggingface.co/docs/hub/spaces-gpus (verify before committing tier choice)
- Gradio E2E testing patterns: https://www.gradio.app/guides/testing-with-the-gradio-client
- WhisperX repo + ctranslate2 pin matrix: https://github.com/m-bain/whisperX
- Fish Speech docs: https://github.com/fishaudio/fish-speech
- MuseTalk repo: https://github.com/TMElyralab/MuseTalk

> **Confidence note:** Versions above are best-effort from current ecosystem knowledge (May 2026 cutoff). Re-pin during the per-phase research step using Context7 for any library that ships a major release.
