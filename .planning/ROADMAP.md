# Roadmap: RAPIDEX IA — v2.5 (Polish + Vertical + Multi-Deploy)

**Created:** 2026-05-09
**Mode:** Vertical MVP (each phase delivers a discrete, verifiable improvement)
**Granularity:** Fine (12 phases)
**Requirements coverage:** 22 / 22 ✓

This roadmap takes RAPIDEX IA from its current shipped v2 state (Gradio app on RunPod, only the UI in git, pipeline at `/workspace/`) to v2.5 (full pipeline in git, vertical/square aspect support, E2E test harness, HuggingFace Spaces as a secondary deploy target).

## Phase Summary

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | Repo Restructure & Foundations | Bring `/workspace/` into git under a clean layout without breaking the running pod or committing model weights | INFRA-01, INFRA-02, INFRA-03, INFRA-04 | 4 |
| 2 | Rename app.py.py → app.py | Eliminate the Windows-naming-bug duplicate file and update all references | INFRA-05 | 3 |
| 3 | Theme Tokens Extraction | Extract `#020409` / `#6366f1` / `#a855f7` + Syne / JetBrains Mono into `ui/theme.py` constants | UI-02 | 2 |
| 4 | Logo in Header | Add the RAPIDEX IA logo PNG to the Gradio header, optimized for fast paint | UI-01 | 3 |
| 5 | Aspect-Ratio Module Foundation | Build `pipeline/aspect.py`, plumb the aspect token through the pipeline, verify zero regression on 16:9 | VIDEO-01, VIDEO-02, VIDEO-05 | 3 |
| 6 | 9:16 Vertical Support | MuseTalk batch + face-box tuning for portrait video; output 9:16 with synced lips and ±50 ms audio sync | VIDEO-03 | 3 |
| 7 | 1:1 Square Support | Apply the same correctness guarantees to 1:1 input | VIDEO-04 | 2 |
| 8 | Unit Test Harness | Per-module CPU-fast unit tests with mocked GPU and recorded translation cassettes | TEST-01, TEST-04, TEST-05 | 4 |
| 9 | Integration Test Harness | GPU-gated E2E test on 5s 16:9 + 5s 9:16 fixtures with capped fixture sizes | TEST-02, TEST-03 | 3 |
| 10 | HF Spaces Dockerfile & Env | Custom Dockerfile + env-var split that runs the same `app.py` on RunPod and HF Spaces | DEPLOY-01, DEPLOY-03 | 3 |
| 11 | HF Spaces Model Persistence | `HF_HOME`-driven model cache so models do not re-download on Space restart | DEPLOY-02 | 2 |
| 12 | HF Spaces Smoke + E2E Validation | Smoke test catches PyTorch/ctranslate2 conflicts; full sample video round-trips on the deployed Space | DEPLOY-04, DEPLOY-05 | 3 |

---

## Phase Details

### Phase 1: Repo Restructure & Foundations
**Goal:** Bring the `/workspace/` ML pipeline into the git repo under a clean modular layout (`pipeline/`, `ui/`, `infra/`, `scripts/`, `tests/`) without committing model weights and without breaking the currently running pod.
**Mode:** mvp
**Requirements:** INFRA-01, INFRA-02, INFRA-03, INFRA-04
**Success Criteria:**
1. `pipeline/`, `ui/`, `infra/runpod/`, `infra/hfspaces/` (placeholder), `scripts/`, `tests/` directories exist in git with the file split described in `.planning/research/ARCHITECTURE.md`.
2. `.gitignore` blocks `**/*.pth`, `**/*.ckpt`, `**/*.safetensors`, `**/*.bin` plus the explicit weights dirs (`MuseTalk/models/`, `Wav2Lip/checkpoints/`, `fish-speech/checkpoints/`); `git ls-files | xargs -I{} ls -la {} | sort -k5 -nr | head` shows no file > 1 MB.
3. `scripts/download_models.py` exists, is idempotent (skips downloads when SHA matches), and pulls all required weights for WhisperX, Fish Speech, MuseTalk, Wav2Lip, Demucs.
4. The pod runs `bash infra/runpod/startup.sh` against the new layout and produces a working `gradio.live` URL; the old `/workspace/` is preserved as a fallback path until validation completes.

### Phase 2: Rename app.py.py → app.py
**Goal:** Eliminate the Windows-naming-bug duplicate filename so the entrypoint is a clean `app.py`.
**Mode:** mvp
**Requirements:** INFRA-05
**Success Criteria:**
1. `git ls-files` shows `app.py` (not `app.py.py`); the duplicate file is removed from the repo.
2. All references in `infra/runpod/startup.sh`, `infra/hfspaces/Dockerfile` placeholder, `README.md`, and `CLAUDE.md` point to `app.py`.
3. The pod's launcher boots successfully against `app.py` and produces a working `gradio.live` URL.

### Phase 3: Theme Tokens Extraction
**Goal:** Centralize the premium dark theme tokens (`#020409` background, `#6366f1` indigo primary, `#a855f7` violet secondary, Syne display font, JetBrains Mono mono font) into `ui/theme.py` named constants consumed by every Gradio component.
**Mode:** mvp
**Requirements:** UI-02
**Success Criteria:**
1. `ui/theme.py` exports `BG`, `PRIMARY`, `SECONDARY`, `FONT_DISPLAY`, `FONT_MONO` constants matching the locked palette.
2. Gradio component code in `ui/components.py` and `app.py` consumes these constants — no hardcoded hex strings or font names elsewhere; `grep -RnE '#[0-9a-fA-F]{6}|Syne|JetBrains' app.py ui/` returns only matches inside `ui/theme.py`.

### Phase 4: Logo in Header
**Goal:** Add the RAPIDEX IA logo PNG to the Gradio header without slowing first paint.
**Mode:** mvp
**Requirements:** UI-01
**Success Criteria:**
1. `ui/assets/logo.png` exists, is ≤ 50 KB, and visually matches the source `ChatGPT_Image_8_de_mai__de_2026__01_19_21.png`.
2. The Gradio header renders the logo above the numbered pipeline (1→2→3→4→5).
3. Time-to-interactive on a typical broadband connection is within 200 ms of the pre-logo baseline (visual check; no formal LCP harness needed at this stage).

### Phase 5: Aspect-Ratio Module Foundation
**Goal:** Create `pipeline/aspect.py`, plumb a `Literal["16:9","9:16","1:1"]` token through the pipeline, and prove zero regression on existing 16:9 input.
**Mode:** mvp
**Requirements:** VIDEO-01, VIDEO-02, VIDEO-05
**Success Criteria:**
1. `pipeline/aspect.py` exposes `detect(video_path) -> Literal["16:9","9:16","1:1"]`; calling it on the existing 16:9 demo video returns `"16:9"`.
2. `pipeline/lipsync.py` accepts the aspect token and selects MuseTalk batch_size + face-box parameters per orientation; the 16:9 path uses the existing parameters unchanged.
3. The existing 16:9 demo video produces an output mp4 that is byte-comparable in dims and audio sync within ±50 ms of the v2 baseline (regression check).

### Phase 6: 9:16 Vertical Support
**Goal:** Output a working 9:16 dubbed mp4 from a 9:16 input — synced lips, no face-crop drift, audio sync within ±50 ms.
**Mode:** mvp
**Requirements:** VIDEO-03
**Success Criteria:**
1. A 5-second 9:16 fixture (vertical phone-shot talking head) round-trips through the full pipeline on the pod and produces a 9:16 output mp4.
2. Visual QA: lips track the speaker through at least 3 spoken phrases; no chin/neck "lip-on-shoulder" artifacts (pitfall #4).
3. Audio sync between the dubbed voice and original lip movements stays within ±50 ms across the full clip (measured via WhisperX-aligned timestamps on the output).

### Phase 7: 1:1 Square Support
**Goal:** Apply the same correctness guarantees as Phase 6 to 1:1 (square) input.
**Mode:** mvp
**Requirements:** VIDEO-04
**Success Criteria:**
1. A 5-second 1:1 fixture round-trips through the full pipeline and produces a 1:1 output mp4.
2. Audio sync within ±50 ms; no face-crop artifacts; visual QA passes the same checks as Phase 6.

### Phase 8: Unit Test Harness
**Goal:** Land per-module unit tests under `tests/unit/` that run on CPU in under 5 seconds without GPU access, with translation calls recorded as cassettes for offline runs.
**Mode:** mvp
**Requirements:** TEST-01, TEST-04, TEST-05
**Success Criteria:**
1. Every module under `pipeline/` (`audio`, `separator`, `transcribe`, `translate`, `tts`, `lipsync`, `aspect`) has at least one corresponding unit test in `tests/unit/`.
2. `pytest tests/unit/` completes in < 5 seconds total on a CPU-only machine (no GPU import required).
3. Translation tests use `pytest-recording` cassettes; `pytest tests/unit/test_translate.py` runs offline.
4. Across 10 consecutive runs of `pytest tests/unit/`, the flaky-test rate is < 1% (i.e. < 1 failure across all runs); seeds (`torch.manual_seed(42)`, `np.random.seed(42)`) are set in shared `conftest.py`.

### Phase 9: Integration Test Harness
**Goal:** GPU-gated E2E integration test that runs a 5-second 16:9 fixture and a 5-second 9:16 fixture through the full pipeline, with capped fixture sizes.
**Mode:** mvp
**Requirements:** TEST-02, TEST-03
**Success Criteria:**
1. `tests/fixtures/tiny_16x9.mp4` and `tests/fixtures/tiny_9x16.mp4` exist, are each ≤ 500 KB, and play locally as 5-second 480p clips.
2. `pytest -m gpu tests/integration/test_e2e_dub.py` (or `RUN_GPU_TESTS=1 pytest tests/integration/`) runs both fixtures end-to-end on the pod and asserts: output mp4 exists, duration within ±10% of input, output aspect matches input aspect, output has an audio track.
3. The integration suite is gated — it does NOT run by default on `pytest`; it only runs when the GPU marker / env var is active.

### Phase 10: HF Spaces Dockerfile & Env
**Goal:** Build `infra/hfspaces/Dockerfile` and the env-var split (`RAPIDEX_MODELS_DIR`, `RAPIDEX_OUTPUTS_DIR`, `GRADIO_SERVER_NAME`, `GRADIO_SHARE`) so the same `app.py` runs on RunPod and HF Spaces.
**Mode:** mvp
**Requirements:** DEPLOY-01, DEPLOY-03
**Success Criteria:**
1. `infra/hfspaces/Dockerfile` builds locally (or in a HF Spaces sandbox) without errors; image includes `ffmpeg` system pkg + the pinned Python deps.
2. `app.py` reads its model dir, outputs dir, server bind, and share toggle from env vars; running with `RAPIDEX_MODELS_DIR=/data/models GRADIO_SHARE=false python app.py` boots without modification.
3. The same `app.py` boots on the pod (with the existing env defaults) and produces the v2 baseline behavior — no regression.

### Phase 11: HF Spaces Model Persistence
**Goal:** Configure `HF_HOME=/data/.cache/huggingface` and `scripts/download_models.py` so model weights persist across HF Space restarts and re-downloading takes < 30 seconds (only checksum verification, no re-fetch).
**Mode:** mvp
**Requirements:** DEPLOY-02
**Success Criteria:**
1. `infra/hfspaces/Dockerfile` sets `ENV HF_HOME=/data/.cache/huggingface`.
2. After a forced HF Space restart, `[boot] models ready in Ns` log line shows N < 30 seconds (verified via Space logs).

### Phase 12: HF Spaces Smoke + E2E Validation
**Goal:** Deploy to a real HuggingFace Space, smoke-test for PyTorch+ctranslate2+Fish Speech version conflicts, and round-trip a sample video through the deployed pipeline.
**Mode:** mvp
**Requirements:** DEPLOY-04, DEPLOY-05
**Success Criteria:**
1. A reachable HF Space URL exists; opening it loads the Gradio UI with no console errors.
2. Smoke test on the deployed Space: `gradio_client.Client(<space_url>).predict(...)` for `transcribe(known_5s_clip)` returns non-empty word-level timestamps (catches the dep-conflict pitfall).
3. Full pipeline round-trip on the deployed Space: a 5-second sample video → translated, voiced, lip-synced output mp4 — downloadable from the UI; perceptual-hash similarity to the local-pod output is ≥ 0.9 (i.e. visually equivalent within ML noise).

---

## Phase Ordering Rationale

- **1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12** is the dependency chain.
- Phase 1 (repo restructure) is **gating** — Phases 5-12 all assume the pipeline lives in the repo. Without it, every later phase works against an unversioned moving target.
- Phases 2-4 (rename, theme, logo) are **cosmetic** — they could run in parallel with each other once Phase 1 lands, but each gets its own atomic commit per the GSD protocol.
- Phase 5 (aspect plumbing) **must precede** Phase 6 (9:16) because shipping 9:16 without the aspect token concept would mean re-implementing the pattern later.
- Phases 8-9 (tests) are inserted **after** the feature work (Phases 1-7) to avoid the trap of writing tests against an unstable pipeline shape, but **before** Phase 10 (HF migration) so the migration has a safety net.
- Phases 10-12 (HF Spaces) are last — they need the hardened pipeline, the test harness, and the dual-deploy env split.

## Research Flags for Phases

- **Phase 6** (9:16 vertical): likely needs phase-specific research during `/gsd-discuss-phase 6` to validate MuseTalk batch_size on portrait input. The architecture doc has a hypothesis (drop batch to 2-4); empirical test on the pod will confirm.
- **Phase 12** (HF Spaces deploy): likely needs phase-specific research during `/gsd-discuss-phase 12` to lock down the exact PyTorch + ctranslate2 + faster-whisper + Fish Speech version matrix that HF Spaces' base image accepts.
- **Phases 1, 2, 3, 4, 5, 7, 8, 9, 10, 11**: standard patterns documented in `.planning/research/`; no extra phase-level research expected.

## Out of Scope for This Milestone

Carried forward from `REQUIREMENTS.md`:
- Captions burn-in / SRT-VTT export (CAP-01, CAP-02)
- Auto-detect source language (FLOW-01)
- Per-segment retry, side-by-side preview, project library, batch processing (FLOW-02 to FLOW-05)
- TTS speed multiplier, multi-speaker diarization, voice-cloning consent UX (QUAL-01 to QUAL-03)
- Translation rate-limit-aware batching (TRAN-01)

These move to a future v3 milestone.

---
*Roadmap defined: 2026-05-09*
*Last updated: 2026-05-09 after initial creation*
