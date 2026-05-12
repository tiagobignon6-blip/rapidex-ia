# Architecture Patterns — RAPIDEX IA Evolution

**Researched:** 2026-05-09
**Confidence:** MEDIUM-HIGH

## Current Architecture (as-is)

```
┌─────────────────────────────────────────────────────────┐
│ Gradio UI  (app.py.py, ~15 KB, in git)                  │
│  3-column flow:                                         │
│   [Col 1] Vídeo & Idiomas                               │
│   [Col 2] Revisar & Editar Texto                        │
│   [Col 3] Voz & Resultado                               │
└────────────────────────┬────────────────────────────────┘
                         │ direct function calls
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Pipeline  (NOT in git — lives at /workspace/ on pod)    │
│                                                         │
│   extract audio (ffmpeg) ──► Demucs (vocals + bg)       │
│        ──► WhisperX(vocals) ──► deep-translator         │
│        ──► [user edits text in UI col 2]                │
│        ──► Fish Speech ──► mix(voice + bg, ffmpeg)      │
│        ──► MuseTalk (Wav2Lip fallback) ──► final mp4    │
└─────────────────────────────────────────────────────────┘
```

**Repo today:**
```
/home/user/rapidex-ia/
├── app.py.py          ← Gradio UI (the only versioned code)
├── setup_rapidex.sh
├── desktop.ini        ← can be deleted (Windows artifact)
└── CLAUDE.md
```

**Pod today (`/workspace/`, NOT versioned):**
```
/workspace/
├── app.py             ← duplicate of repo's app.py.py
├── startup.sh
├── Wav2Lip/           ← models pre-downloaded
├── MuseTalk/          ← models pre-downloaded
└── fish-speech/       ← TTS code + reference voices
```

## Recommended Repo Layout (target)

```
rapidex-ia/
├── app.py                    ← entrypoint (renamed from app.py.py)
├── pipeline/
│   ├── __init__.py
│   ├── audio.py              ← ffmpeg extract + mix helpers
│   ├── separator.py          ← Demucs wrapper
│   ├── transcribe.py         ← WhisperX wrapper (VAD config, alignment)
│   ├── translate.py          ← deep-translator wrapper
│   ├── tts.py                ← Fish Speech wrapper
│   ├── lipsync.py            ← MuseTalk + Wav2Lip fallback router
│   └── aspect.py             ← 9:16 / 16:9 / 1:1 handling
├── ui/
│   ├── __init__.py
│   ├── theme.py              ← #020409 / #6366f1 / #a855f7 + Syne/JetBrains
│   ├── components.py         ← header, pipeline progress, columns
│   └── assets/
│       └── logo.png          ← RAPIDEX IA logo (small enough for git)
├── infra/
│   ├── runpod/
│   │   └── startup.sh        ← current /workspace/startup.sh, moved
│   └── hfspaces/
│       ├── Dockerfile        ← HF Spaces deploy
│       └── README.md         ← HF Spaces metadata YAML header
├── tests/
│   ├── unit/                 ← per-stage tests, CPU-fast, mocked GPU
│   │   ├── test_aspect.py
│   │   ├── test_translate.py
│   │   └── ...
│   ├── integration/          ← single real run, scheduled / on-demand only
│   │   └── test_e2e_dub.py
│   └── fixtures/
│       ├── tiny_16x9.mp4     ← 5s test fixture, ~200 KB
│       └── tiny_9x16.mp4     ← 5s vertical fixture
├── scripts/
│   └── download_models.py    ← model fetcher for first boot
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml            ← pinned deps via uv or pip-tools
├── requirements.txt          ← generated, locked
├── README.md
└── CLAUDE.md
```

**Critical `.gitignore` entries** (model weights stay out, always):
```gitignore
# Models — downloaded at boot, never committed
**/*.pth
**/*.ckpt
**/*.safetensors
**/*.bin
checkpoints/
weights/
models/
fish-speech/checkpoints/
MuseTalk/models/
Wav2Lip/checkpoints/

# Virtualenvs
.venv/
venv/

# Cache
__pycache__/
.pytest_cache/
*.pyc

# Local secrets
.env
.env.local

# Outputs
outputs/
*.mp4
*.wav
!tests/fixtures/*.mp4   # explicit allow for tests fixtures only
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `app.py` | Gradio entrypoint, layout assembly, callback wiring | `ui/`, `pipeline/` |
| `ui/theme.py` | Tokens (`#020409` / `#6366f1` / `#a855f7`), font tokens | imported by `app.py` |
| `ui/components.py` | Header (logo, 1→2→3→4→5 progress), 3-column shell | imported by `app.py` |
| `pipeline/audio.py` | Extract source audio, mix voice + bg → mp4 | ffmpeg (subprocess via `ffmpeg-python`) |
| `pipeline/separator.py` | Run Demucs, return `(vocals.wav, bg.wav)` | Demucs CLI / Python API |
| `pipeline/transcribe.py` | WhisperX → segments + word timestamps | calls `pipeline/audio.py` for input |
| `pipeline/translate.py` | deep-translator wrapper, retry logic, language map | network egress (Google) |
| `pipeline/tts.py` | Fish Speech inference, reference-voice cache | reads from `models/fish-speech/` |
| `pipeline/lipsync.py` | MuseTalk primary; on failure → Wav2Lip; aspect-aware face crop | reads from `models/musetalk/`, `models/wav2lip/` |
| `pipeline/aspect.py` | 9:16 / 16:9 / 1:1 detection, pre-crop, post-pad | called before `lipsync.py`, after `audio.py` mix |
| `infra/runpod/startup.sh` | Boots app on the pod | calls `app.py` |
| `infra/hfspaces/Dockerfile` | HF Spaces image | calls `app.py` |
| `tests/unit/` | CPU-fast, no GPU, mocked stages | only `pipeline/*` modules |
| `tests/integration/test_e2e_dub.py` | One real video through the full pipeline; gated | full app, GPU required |

### Data Flow

```
User uploads video
   │
   ▼
ui Gradio submits → app.py callback
   │
   ▼
pipeline/audio.extract_audio(video)        → vocals_only.wav
pipeline/separator.split(vocals_only)       → (vocals.wav, bg.wav)
pipeline/transcribe.run(vocals.wav)         → segments[]
pipeline/translate.run(segments, lang_pair) → translated_segments[]
   │
   ▼
[user edits text in UI col 2 — Gradio state held in app.py]
   │
   ▼
pipeline/tts.synthesize(edited_segments)    → voice.wav
pipeline/audio.mix(voice.wav, bg.wav)       → mixed.wav
pipeline/aspect.detect(video)               → "16:9" | "9:16" | "1:1"
pipeline/lipsync.run(video, mixed.wav, aspect) → out.mp4
   │
   ▼
ui returns out.mp4 → user downloads
```

## Where 9:16 Aspect Logic Lives

**Recommendation:** New module `pipeline/aspect.py`. Detect aspect ratio at the **top of the pipeline** (right after upload), and emit a single `aspect_mode: Literal["16:9", "9:16", "1:1"]` token threaded through subsequent stages.

Three intervention points:

1. **Pre-MuseTalk** — face crop logic in `pipeline/lipsync.py` reads `aspect_mode` and adjusts the face_box / pad params (MuseTalk works best when face fills ~60-70% of frame; portrait video already does this naturally — sometimes face is *too* tight).
2. **Inside MuseTalk batch params** — keep the recommended batch_size (typically 4-8); for 9:16 portrait the face is larger so peak VRAM goes up — drop batch to 2-4 to avoid OOM.
3. **Post-FFmpeg** — if any pad/letterbox was applied pre-pipeline (e.g. user uploaded 9:16 but MuseTalk needed 16:9 input), restore original aspect via `ffmpeg-python` crop filter.

Reasoning for layer choice: aspect is **cross-cutting** (touches lipsync, output mp4 dims, possibly future caption overlay). Centralizing in `pipeline/aspect.py` prevents the magic ratio constants from spreading. Alternatives rejected:

- **(a) Pre-pipeline only:** breaks the contract — MuseTalk silently re-aspects internally and you lose the user's intent.
- **(b) Inside `lipsync.py` only:** couples aspect handling to MuseTalk; future Wav2Lip-only path or codec changes have to re-implement.

## E2E Test Harness Boundary

**Split:**

- **Unit tests (CPU, fast, run on every commit):**
  - `pipeline/audio.py` — extract a 1-second clip from a 5-second fixture, assert duration; mix two known sine waves, assert RMS ratio
  - `pipeline/translate.py` — VCR-recorded Google Translate cassettes; assert structure
  - `pipeline/aspect.py` — feed metadata-only fixtures of known aspect; assert correct token returned
  - `pipeline/separator.py` — mock Demucs binary; assert correct args were called
  - `pipeline/transcribe.py` — feed pre-recorded WhisperX json output; assert segment parsing
  - `pipeline/tts.py` — mock Fish Speech inference; assert call signature
  - `pipeline/lipsync.py` — mock both MuseTalk and Wav2Lip; assert fallback router works on simulated MuseTalk failure

- **Integration tests (GPU, slow, scheduled or on-demand only):**
  - `test_e2e_dub.py` — one 5-second fixture video through the entire real pipeline. Asserts: output mp4 exists, duration within ±10% of input, output has audio track, output frame dims match input aspect.
  - Use perceptual hash (`imagehash`) for one frame at midpoint vs golden snapshot to catch lipsync drift.
  - Gate via env var (`RUN_GPU_TESTS=1`) or `pytest -m gpu`.

**Where they run:**
- Unit tests: GitHub Actions CPU runners, on every PR.
- Integration tests: manually triggered on the pod (until HF Spaces migration; then on a small HF runner via scheduled action).

**Boundary rule:** "If it imports torch and calls `.cuda()`, it's an integration test." Everything else is unit.

## Dual Deployment Strategy (RunPod + HF Spaces)

**Single source of truth: the repo.** Both deploy targets pull the same `app.py` + `pipeline/`.

```
infra/
├── runpod/
│   └── startup.sh           ← bash wrapper; sets paths, calls `python app.py`
└── hfspaces/
    ├── Dockerfile           ← FROM nvidia/cuda:12.x, apt ffmpeg, pip install requirements.txt, CMD python app.py
    ├── README.md            ← HF Spaces YAML header (sdk: docker, hardware: a10g-small, ...)
    └── space.yaml           ← optional: HF Spaces metadata
```

**Env-specific differences handled via env vars in `app.py`:**

| Variable | RunPod default | HF Spaces default | Purpose |
|----------|---------------|-------------------|---------|
| `RAPIDEX_MODELS_DIR` | `/workspace/models` | `/data/models` | Where weights live |
| `RAPIDEX_OUTPUTS_DIR` | `/workspace/outputs` | `/tmp/outputs` | Where rendered mp4s go |
| `GRADIO_SERVER_NAME` | `0.0.0.0` | `0.0.0.0` | Bind addr |
| `GRADIO_SHARE` | `true` | `false` | Use `gradio.live` on RunPod; HF Spaces has its own URL |
| `HF_TOKEN` | unused | secret | For private model fetches |

**Model bootstrap:** `scripts/download_models.py` runs at first boot on either target. Idempotent, checks SHA, skips if already present. Solves the "/tmp ephemeral" problem on HF Spaces by downloading to a persistent path.

## Suggested Build Order for Active Backlog

| # | Item | Depends on | Unblocks | Phase rationale |
|---|------|-----------|----------|-----------------|
| 1 | Repo restructure (bring `/workspace/` in, gitignore weights) | nothing | 4, 5, 6 | Fundamental — without this, E2E + HF migration are blind |
| 2 | Rename `app.py.py` → `app.py` | 1 | nothing | Trivial; do during repo restructure for one atomic move |
| 3 | Logo in header | 1 (asset path) | nothing | Polish; low effort; can ship in parallel |
| 4 | 9:16 vertical aspect support | 1, 2, 3 (clean codebase) | nothing | The big feature; needs `pipeline/aspect.py` module |
| 5 | E2E test harness | 1, 2, 4 (test against final feature shape) | 6 (gates HF migration) | Safety net before changing deploy target |
| 6 | HuggingFace Spaces migration | 1, 5 | nothing | Final deploy alternative; needs hardened code + tests |

**Critical path:** 1 → 4 → 5 → 6. Items 2 and 3 are parallelizable cosmetic work that should happen alongside 1.

## Anti-Patterns to Avoid

| Anti-Pattern | Why Bad | Instead |
|--------------|---------|---------|
| `git add MuseTalk/checkpoints/` | Multi-GB commits explode repo size, break clones | Use `scripts/download_models.py` + gitignore |
| Refactoring `app.py.py` and `/workspace/app.py` independently | Pod and repo drift; nobody knows which is canonical | Pick one (the repo) and make pod a checkout |
| Putting 9:16 logic inside `app.py` Gradio callback | Conflates UI and ML logic; impossible to unit-test | `pipeline/aspect.py` module |
| Running E2E tests on the live pod during user sessions | GPU contention, unpredictable failures | Separate test pod or scheduled HF runner |
| Hardcoding `/workspace/` paths in pipeline modules | Breaks the moment you deploy to HF Spaces | Use `RAPIDEX_MODELS_DIR` env var |
| `pip install` inside `app.py` at runtime | Cold-start blowup; non-reproducible | Bake into Docker image or RunPod template |
| `git push --force` to recover from a bad restructure | Loses history; user already mandated no `--force` | Revert commits cleanly; small atomic commits make this easy |

## Sources

- HuggingFace Spaces Docker SDK docs: https://huggingface.co/docs/hub/spaces-sdks-docker
- Coqui-TTS repo layout (similar Gradio + ML weight bundling): https://github.com/coqui-ai/TTS
- Wav2Lip / MuseTalk integration patterns from open-source dub projects (community-driven, May 2026)

> **Confidence note:** Repo layout is HIGH confidence (standard Python ML project shape). The exact env-var split between RunPod / HF Spaces is MEDIUM (verify `/data/` persistence semantics on HF Spaces during HF migration phase).
