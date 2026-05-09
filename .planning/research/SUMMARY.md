# Research Summary: RAPIDEX IA

**Domain:** AI video dubbing / multilingual content automation for creators
**Researched:** 2026-05-09
**Overall confidence:** MEDIUM-HIGH

## Executive Summary

RAPIDEX IA's core ML stack (WhisperX large-v3 / deep-translator / Fish Speech V1.5 / Demucs / MuseTalk + Wav2Lip / Gradio) is locked and proven — the v2 product already ships end-to-end on RunPod. The active backlog is **incremental polish + structural de-risking**: filename rename, logo, 9:16 vertical aspect support, end-to-end test harness, and HuggingFace Spaces migration as a deploy alternative.

The **dominant architectural risk** is implicit and not in the named backlog: only the Gradio UI (`app.py.py`) is in git; the entire pipeline lives at `/workspace/` on the pod and is unversioned. Three of the five backlog items (E2E tests, HF migration, and durable 9:16 work) require bringing `/workspace/` into the repo first. **Repo restructure must be Phase 1**; if it isn't, subsequent phases will be working blind.

The **dominant feature gap** vs creator-tool competitors (HeyGen, Rask, ElevenLabs Dubbing) is 9:16 vertical aspect — table-stakes for Reels/TikTok/Shorts, currently absent in RAPIDEX. The **dominant operational risk** in HF Spaces migration is the PyTorch + ctranslate2 + Fish Speech dependency matrix, which silently breaks WhisperX alignment if mis-pinned. Both must be guarded by the E2E test harness landing before HF migration ships.

The other two backlog items (rename, logo) are cosmetic and parallelizable with Phase 1.

## Key Findings

**Stack:** Core ML is locked. Supporting tools to add: `ffmpeg-python` (video I/O), `gradio_client` + `pytest-recording` + `imagehash` (E2E testing), `huggingface_hub` + custom Dockerfile (HF Spaces). Recommended HF tier: A10G Small (avoid ZeroGPU — cold-start + queue timeouts conflict with multi-minute pipeline runs).

**Architecture:** Bring `/workspace/` into git under a clean layout: `pipeline/` (one module per stage), `ui/` (theme + components + assets), `infra/runpod/` and `infra/hfspaces/` (per-target deploy), `tests/unit/` (CPU, fast) + `tests/integration/` (GPU, gated). 9:16 logic centralizes in a new `pipeline/aspect.py` module called between audio mixing and lipsync. Models stay out of git via aggressive `.gitignore` (`.pth`, `.ckpt`, `.safetensors`, `.bin`, plus explicit dirs); a `scripts/download_models.py` fetches them on first boot.

**Critical pitfall:** Committing model weights during the repo restructure. The `.gitignore` MUST land before any file is moved into the repo. Multi-GB blobs in git are nearly unrecoverable without history rewrite.

## Implications for Roadmap

Recommended phase structure (granularity: fine, per the user's config — so split aggressively):

1. **Phase 1 — Repo Restructure & Foundations**
   - `.gitignore` hardening (anti-pitfall #1)
   - Move `/workspace/` content into the repo under `pipeline/`, `ui/`, `infra/`, `scripts/`
   - Atomic swap of pod startup to use new layout (anti-pitfall #2)
   - Addresses: gating step for everything else
   - Avoids: pitfalls #1 (weights), #2 (breaking pod)

2. **Phase 2 — Filename + Cosmetic Polish**
   - Rename `app.py.py` → `app.py`
   - Wire logo asset into the Gradio header
   - Compress logo PNG to < 50 KB (anti-pitfall #11)
   - Addresses: 2 backlog items in one go (low-risk, parallelizable with Phase 1)

3. **Phase 3 — Aspect-Ratio Module & Detection**
   - New `pipeline/aspect.py` (16:9 / 9:16 / 1:1 detect + token threading)
   - Plumb `aspect_mode` through pipeline (no behavior change yet — just plumbing)
   - Addresses: foundation for Phase 4
   - Avoids: scattered aspect constants

4. **Phase 4 — 9:16 Vertical Support (the big feature)**
   - MuseTalk batch + face-box tuning for portrait
   - Optional letterbox-and-restore strategy for out-of-distribution faces
   - Addresses: #1 missing table stake
   - Avoids: pitfall #4 (face-crop drift)

5. **Phase 5 — E2E Test Harness**
   - Unit tests for every `pipeline/*` module (mocked GPU, CPU-fast)
   - Integration test: one 5s vertical fixture + one 5s horizontal fixture through full pipeline
   - GPU-gated via `RUN_GPU_TESTS=1`
   - Addresses: release confidence; gates Phase 6
   - Avoids: pitfall #9 (flaky tests), pitfall #15 (fixture bloat)

6. **Phase 6 — HuggingFace Spaces Migration**
   - Custom Dockerfile in `infra/hfspaces/`
   - `HF_HOME=/data/.cache/huggingface` model persistence
   - PyTorch + ctranslate2 + Fish Speech matrix pinned and validated
   - Smoke test gate (WhisperX returns non-empty timestamps)
   - Addresses: deploy alternative + free/demo channel
   - Avoids: pitfall #3 (dep conflict), pitfall #5 (model cold-start)

**Phase ordering rationale:**
- **1 → 2 → 3 → 4 → 5 → 6** is a hard chain (each phase depends on the previous)
- **Phase 2 (cosmetic)** can run in parallel with the tail end of Phase 1 if granularity is fine
- **Phase 5 (tests)** is required before **Phase 6 (HF)** — can't validate the migration without a harness

**Research flags for phases:**
- **Phase 4** (9:16 / MuseTalk): likely needs phase-specific research — MuseTalk's actual portrait-handling capability and batch-size impact on 24 GB VRAM should be validated empirically (test on the pod) during the discuss/plan step.
- **Phase 6** (HF Spaces): likely needs phase-specific research — exact PyTorch/ctranslate2/faster-whisper/Fish Speech version matrix that HF Spaces' base image plays nicely with.
- **Phases 1, 2, 3, 5**: standard patterns — no extra research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core stack is locked; supporting tools well-known; versions to re-pin via Context7 in Plan phase |
| Features | MEDIUM | Competitor feature lists drift fast; the categorization (table stakes vs differentiator) is solid |
| Architecture | HIGH | Standard Python ML project layout; the env-var split for dual deploy is the only MEDIUM piece |
| Pitfalls | MEDIUM-HIGH | Anti-patterns #1/#2/#5/#10 are universal; #3/#4 are stack-specific and need empirical validation in Phase 4/6 |

## Gaps to Address

- Exact MuseTalk batch_size that fits inside 24 GB VRAM with 9:16 portrait input + WhisperX + Fish Speech residency — needs empirical test in Phase 4.
- Whether HF Spaces' `/data/` persistence semantics survive Space restarts vs. only Space pauses — needs verification during Phase 6 (test by force-restarting a throwaway Space).
- Translation engine fallback when Google rate-limits — out of scope for v1, but could surface as an emergency phase if it bites.
- User's intended monetization model (paid features, free tier with watermark, etc.) — out of v1 scope per PROJECT.md, but informs whether captioning / watermarking become differentiators.

## Files Created

| File | Purpose |
|------|---------|
| `.planning/research/SUMMARY.md` | This document — executive synthesis |
| `.planning/research/STACK.md` | Supporting tools, versions, HF hardware tier recommendation |
| `.planning/research/FEATURES.md` | Competitive feature landscape; table stakes vs differentiators vs anti |
| `.planning/research/ARCHITECTURE.md` | Repo layout, component boundaries, build order, anti-patterns |
| `.planning/research/PITFALLS.md` | 15 pitfalls with detection / prevention / phase mapping |
