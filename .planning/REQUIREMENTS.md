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
- [ ] **INFRA-05**: The repo entrypoint is `app.py` (not `app.py.py`); the legacy `app.py.py` is removed and all references (startup scripts, docs) are updated.

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

Empty initially. Populated during roadmap creation in the next step.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | TBD | Pending |
| INFRA-02 | TBD | Pending |
| INFRA-03 | TBD | Pending |
| INFRA-04 | TBD | Pending |
| INFRA-05 | TBD | Pending |
| UI-01 | TBD | Pending |
| UI-02 | TBD | Pending |
| VIDEO-01 | TBD | Pending |
| VIDEO-02 | TBD | Pending |
| VIDEO-03 | TBD | Pending |
| VIDEO-04 | TBD | Pending |
| VIDEO-05 | TBD | Pending |
| TEST-01 | TBD | Pending |
| TEST-02 | TBD | Pending |
| TEST-03 | TBD | Pending |
| TEST-04 | TBD | Pending |
| TEST-05 | TBD | Pending |
| DEPLOY-01 | TBD | Pending |
| DEPLOY-02 | TBD | Pending |
| DEPLOY-03 | TBD | Pending |
| DEPLOY-04 | TBD | Pending |
| DEPLOY-05 | TBD | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 0 (will be filled by roadmapper)
- Unmapped: 22 ⚠️ (expected at this stage — roadmap will resolve)

---
*Requirements defined: 2026-05-09*
*Last updated: 2026-05-09 after initial definition*
