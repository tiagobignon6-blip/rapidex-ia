# Requirements: RAPIDEX IA

**Defined:** 2026-05-09
**Core Value:** A creator can drop a video in, edit the translated script, and walk out with a lip-synced dubbed version — without ever touching the underlying ML pipeline.

## v1 Requirements

Requirements for the next milestone (post-v2 polish + structural de-risking). Each maps to roadmap phases during `/gsd-discuss-phase`.

### Infrastructure

- [ ] **INFRA-01**: The full ML pipeline lives under version control (`pipeline/`, `ui/`, `infra/`, `scripts/`, `tests/`) instead of inside the unversioned `/workspace/` directory on the pod.
- [ ] **INFRA-02**: Model weight files (`.pth`, `.ckpt`, `.safetensors`, `.bin`) are excluded from git via `.gitignore`; cloning the repo never pulls multi-GB blobs.
- [ ] **INFRA-03**: A `scripts/download_models.py` script idempotently fetches all required model weights on first boot and skips on subsequent boots.
- [ ] **INFRA-04**: The RunPod startup path swaps to the new repo layout atomically — old `/workspace/` stays as fallback until validated; zero in-flight user sessions are interrupted.
- [x] **INFRA-05**: The repo entrypoint is `app.py` (not `app.py.py`); the legacy `app.py.py` is removed and all references (startup scripts, docs) are updated. _Done: commit `f6f93bd` (Phase 2)._
- [ ] **INFRA-06**: The same `app.py` boots on RunPod, HF Spaces, and the operator's local WSL2+CUDA machine, driven entirely by env vars (`RAPIDEX_MODELS_DIR`, `RAPIDEX_OUTPUTS_DIR`, `MUSETALK_DIR`, `WAV2LIP_DIR`, `FISH_SPEECH_DIR`, `GRADIO_SERVER_NAME`, `GRADIO_SHARE`, `RAPIDEX_DEVICE`). No hardcoded `/workspace/...` paths remain in `app.py` or pipeline modules. A local Compose recipe (`infra/local/docker-compose.yml`) brings up the full pipeline on `localhost:7860`.
- [ ] **INFRA-07**: Device selection is auto-detected (`cuda` → `mps` → `cpu`) with an env override (`RAPIDEX_DEVICE`). `whisperx` + `fish_speech` consume the detected device; CPU fallback boots the UI even when CUDA is unavailable (GPU-only stages raise a clear user-facing error rather than crashing on import).

### UI

- [ ] **UI-01**: The Gradio header displays the RAPIDEX IA logo (sourced from `ChatGPT_Image_8_de_mai__de_2026__01_19_21.png`, optimized to ≤ 50 KB and stored at `ui/assets/logo.png`).
- [ ] **UI-02**: The premium dark theme tokens (`#020409` background, `#6366f1` primary, `#a855f7` secondary, Syne + JetBrains Mono) are extracted into `ui/theme.py` as named constants and consumed by every Gradio component.

### Video / Aspect

- [ ] **VIDEO-01**: A new `pipeline/aspect.py` module detects input video aspect ratio and emits a `Literal["16:9", "9:16", "1:1"]` token.
- [ ] **VIDEO-02**: The detected aspect token is threaded through `pipeline/lipsync.py` and used to choose MuseTalk batch_size and face-box parameters appropriate to the orientation.
- [ ] **VIDEO-03**: 9:16 (vertical) input video produces a 9:16 output mp4 with synced lips, no face-crop drift, and audio sync within ±50 ms of the original timing.
- [ ] **VIDEO-04**: 1:1 (square) input video produces a 1:1 output mp4 with the same correctness guarantees as 9:16.
- [ ] **VIDEO-05**: 16:9 (existing) input video continues to produce a 16:9 output with no regression vs the v2 baseline.

### Testing

- [ ] **TEST-01**: Every module under `pipeline/` has a unit test in `tests/unit/` that runs on CPU in under 5 seconds without GPU dependencies (mocks where needed).
- [ ] **TEST-02**: A GPU-gated integration test (`tests/integration/test_e2e_dub.py`) runs one 5-second 16:9 fixture and one 5-second 9:16 fixture end-to-end through the full pipeline; both produce non-empty mp4 outputs of correct duration and aspect.
- [ ] **TEST-03**: Test fixtures in `tests/fixtures/` are capped at 5 seconds, 480p, ≤ 500 KB each; no full-resolution sample videos are committed.
- [ ] **TEST-04**: Tests are deterministic — `torch.manual_seed(42)` and `np.random.seed(42)` are set at fixture load; flaky-test rate < 1% across 10 consecutive runs.
- [ ] **TEST-05**: Translation calls (deep-translator → Google) are recorded via `pytest-recording` cassettes; unit tests run offline.

### Deploy

- [ ] **DEPLOY-01**: The repo contains a Dockerfile at `infra/hfspaces/Dockerfile` that produces a working HuggingFace Spaces image (`sdk: docker`).
- [ ] **DEPLOY-02**: Model weights persist across HF Spaces restarts via `HF_HOME=/data/.cache/huggingface` (no re-download on every restart).
- [ ] **DEPLOY-03**: Environment variables (`RAPIDEX_MODELS_DIR`, `RAPIDEX_OUTPUTS_DIR`, `GRADIO_SERVER_NAME`, `GRADIO_SHARE`) drive all path / network differences between RunPod and HF Spaces; the same `app.py` runs on both.
- [ ] **DEPLOY-04**: A smoke test on the deployed HF Space confirms WhisperX returns non-empty word-level timestamps for a known reference clip (catches the PyTorch + ctranslate2 + Fish Speech version-conflict pitfall).
- [ ] **DEPLOY-05**: A 5-second sample video round-trips through the full pipeline on the deployed HF Space and produces a downloadable mp4.

## v2 Requirements

Acknowledged but deferred to a future milestone.

### Captions
- **CAP-01**: Burn-in optional captions on output mp4 (creator engagement boost on Reels/TikTok).
- **CAP-02**: Export translated transcript as SRT/VTT file alongside the mp4.

### Workflow
- **FLOW-01**: Auto-detect source language (skip selector step).
- **FLOW-02**: Per-segment retry on lipsync failure (one bad segment doesn't fail the whole video).
- **FLOW-03**: Side-by-side preview (original + dubbed) before final download.
- **FLOW-04**: Project library — re-edit and re-render past videos.
- **FLOW-05**: Batch processing — multiple videos in one session.

### Quality
- **QUAL-01**: TTS speed multiplier to match original speaker pacing.
- **QUAL-02**: Multi-speaker diarization via WhisperX, distinct voice clones per speaker.
- **QUAL-03**: Voice-cloning consent UX (legal hygiene).

### Translation
- **TRAN-01**: Rate-limit-aware Google Translate batching with exponential backoff (mitigates pitfall #12).

## Out of Scope

Explicit exclusions. Documented to prevent scope creep and re-asking.

| Feature | Reason |
|---------|--------|
| Alternative transcription engines (Whisper.cpp, Deepgram, etc.) | WhisperX large-v3 + VAD is locked per PROJECT.md |
| Alternative TTS engines (XTTS, ElevenLabs, etc.) | Fish Speech V1.5 is locked per PROJECT.md |
| Alternative lipsync engines beyond MuseTalk + Wav2Lip fallback | Current stack is final |
| Translation providers other than deep-translator/GoogleTranslator | Keep dependency surface small; user can edit the text |
| Native mobile app | Gradio web is the only target |
| Real-time / streaming dubbing | Pipeline is inherently batch (Demucs + MuseTalk) |
| User accounts / auth / billing inside the app | Out of v1; deploy targets handle access control |
| Full video editor (cuts, transitions) | Not the product; user edits in CapCut/Premiere |
| In-app social posting (TikTok/IG/YouTube upload) | Brittle external APIs; creator does it themselves |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 — Repo Restructure & Foundations | Pending |
| INFRA-02 | Phase 1 — Repo Restructure & Foundations | Pending |
| INFRA-03 | Phase 1 — Repo Restructure & Foundations | Pending |
| INFRA-04 | Phase 1 — Repo Restructure & Foundations | Pending |
| INFRA-05 | Phase 2 — Rename app.py.py → app.py | ✅ Done (`f6f93bd`) |
| INFRA-06 | Phase 2.5 — Local Runtime Profile | Pending |
| INFRA-07 | Phase 2.5 — Local Runtime Profile | Pending |
| UI-01 | Phase 4 — Logo in Header | Pending |
| UI-02 | Phase 3 — Theme Tokens Extraction | Pending |
| VIDEO-01 | Phase 5 — Aspect-Ratio Module Foundation | Pending |
| VIDEO-02 | Phase 5 — Aspect-Ratio Module Foundation | Pending |
| VIDEO-03 | Phase 6 — 9:16 Vertical Support | Pending |
| VIDEO-04 | Phase 7 — 1:1 Square Support | Pending |
| VIDEO-05 | Phase 5 — Aspect-Ratio Module Foundation | Pending |
| TEST-01 | Phase 8 — Unit Test Harness | Pending |
| TEST-02 | Phase 9 — Integration Test Harness | Pending |
| TEST-03 | Phase 9 — Integration Test Harness | Pending |
| TEST-04 | Phase 8 — Unit Test Harness | Pending |
| TEST-05 | Phase 8 — Unit Test Harness | Pending |
| DEPLOY-01 | Phase 10 — HF Spaces Dockerfile & Env | Pending |
| DEPLOY-02 | Phase 11 — HF Spaces Model Persistence | Pending |
| DEPLOY-03 | Phase 10 — HF Spaces Dockerfile & Env | Pending |
| DEPLOY-04 | Phase 12 — HF Spaces Smoke + E2E Validation | Pending |
| DEPLOY-05 | Phase 12 — HF Spaces Smoke + E2E Validation | Pending |

**Coverage:**
- v1 requirements: 24 total (22 original + INFRA-06, INFRA-07)
- Mapped to phases: 24
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-09*
*Last updated: 2026-05-09 after initial definition*
