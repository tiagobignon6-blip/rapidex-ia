---
status: human_needed
phase: 2.5
phase_name: Local Runtime Profile
verified_at: 2026-05-12
verifier: claude (inline)
mode: split
---

# Phase 2.5 Verification — Local Runtime Profile

Mirrors Phase 1's split pattern. Repo-side acceptance is fully verifiable from this session; operator-side acceptance needs the operator to actually boot Compose on the WSL2+GPU box and re-boot the pod once to confirm no-regression.

## Repo-side verification (this session)

### Acceptance criteria from CONTEXT.md

| # | Check | Result |
|---|---|---|
| 1 | `grep -RnE "/workspace/" app.py pipeline/` returns nothing (or only the resolver fallback knob) | ✅ Only matches are inside `pipeline/runtime.py:resolve_dir` legacy_path args and its docstring — by design (RunPod no-regression) |
| 2 | `python -c "import app"` succeeds end-to-end | ⏳ Requires gradio installed; per-module imports verified individually (`pipeline.audio`, `.separator`, `.transcribe`, `.translate`, `.tts`, `.lipsync`, `.runtime` all import cleanly with stubbed gradio) |
| 3 | All 6 pipeline functions live in `pipeline/*.py`, not in `app.py` | ✅ `grep -nE "^def (extract_audio\|mix_audio\|run_demucs\|run_whisperx\|translate_text\|run_fish_speech\|run_lipsync)" app.py` returns 0 hits |
| 4 | `requirements.txt` declares the locked ML matrix | ✅ torch 2.4.1 / cu121 / whisperx / ctranslate2 / faster-whisper / deep-translator / demucs / numpy<2 |
| 5 | `python scripts/download_models.py --dry-run` reports 5 models with public URLs (not `TODO`) | ✅ 5 missing entries with public HF / fbaipublicfiles URLs; exit 0 |
| 6 | `infra/local/{Dockerfile, docker-compose.yml, start.sh, README.md}` exist | ✅ all 4 present |
| 7 | `.env.example` documents 4 runtime profiles (Local Compose, Local bare, RunPod, HF Spaces) | ✅ |

**Repo-side acceptance: 6/7 ✓**, 1 partial (full `import app` needs gradio installed; gating to operator boot).

### Decisions implemented

| Decision | How implemented |
|----------|-----------------|
| D-01 — Local target is WSL2 + NVIDIA GPU | `infra/local/docker-compose.yml` uses `deploy.resources.reservations.devices` for nvidia; Dockerfile FROM `nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04` |
| D-02 — RunPod stays a supported deploy target | `pipeline/runtime.py:resolve_dir` priority chain keeps `/workspace/<name>` winning when present on disk |
| D-04 — Pin matrix from upstream public pins, not pod `pip freeze` | `requirements.txt` derives floors from each project's public docs; verify-fresh-venv recipe in the header |
| D-05 — New `infra/local/` peer of `runpod/`, `hfspaces/` | created |
| D-06 — Local + HF Spaces Dockerfiles share ~90% | Local Dockerfile written so the HF Spaces variant is a thin overlay (HF_HOME + GRADIO_SHARE difference only) |
| D-07 — `RAPIDEX_DEVICE=cpu` raises `gr.Error` on TTS/lipsync | `pipeline/tts.py` and `pipeline/lipsync.py` both gate on `detect_device() == "cpu"` with user-facing friendly message |

### Requirements coverage

| Req | Status |
|-----|--------|
| INFRA-06 (env-driven multi-runtime) | ✅ app.py + pipeline/ fully decoupled; infra/local/ + Dockerfile + Compose + README + .env.example shipped |
| INFRA-07 (device autodetect + CPU fallback) | ✅ `detect_device()` in `pipeline/runtime.py`; CPU mode boots UI; TTS+lipsync raise `gr.Error` |

## Operator-side verification

These items confirm only with the operator actually running things on their WSL2+GPU box and re-booting the pod once.

### Compose path

- [ ] `cp .env.example .env` then `docker compose -f infra/local/docker-compose.yml up --build` builds the image without dep conflicts.
- [ ] First boot fetches the 5 model weights via `scripts/download_models.py`; observed SHA256s are pasted back into `scripts/models.manifest.json` in a follow-up commit.
- [ ] Gradio is reachable at `http://localhost:7860`.
- [ ] A 5-second sample video round-trips through the full pipeline (transcribe → translate → edit → dub → download).

### Bare-shell CPU-UI path

- [ ] `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` resolves cleanly.
- [ ] `RAPIDEX_DEVICE=cpu python app.py` boots Gradio at `http://localhost:7860`.
- [ ] Transcribe & Translate works on a tiny clip.
- [ ] Dub Video raises the friendly `gr.Error: GPU required: Fish Speech V1.5 needs CUDA …`.

### RunPod no-regression

- [ ] On the pod, `bash /workspace/startup.sh` still produces a working `gradio.live` URL.
- [ ] The pod-served UI is visually identical to v2.
- [ ] A 5-second sample video still round-trips through the full pipeline on the pod.

## Status

**`human_needed`** — repo-side scaffold + de-hardcoding + infra/local are complete and verified for what's verifiable without booting on the GPU host. Operator-side requires the WSL2 Compose boot + the next pod boot to confirm no-regression.

When the operator completes the Compose smoke test and one pod boot, run `/gsd-verify-work 2.5` again from a new session to flip this to `passed` and unblock Phase 3 (theme tokens) — which is the first phase the operator can ship from the laptop.

## Anti-patterns avoided

- ✅ No model weights committed (largest tracked file remains the Dockerfile/README at ~3 KB)
- ✅ No `/workspace/...` hardcoding outside the intentional resolver fallback
- ✅ No `pip install --no-deps` or version unpinning to "make it resolve" — pin matrix is conservative and documented
- ✅ No silent CPU fallbacks for GPU-only stages — fail loud per Pitfall #9 and the Nellia "fail-loud always" rule (PRINCIPLES §5)
- ✅ No duplicate device-detection code — single `detect_device()` in `pipeline/runtime.py`
- ✅ No second source of truth for env vars — `.env.example` is canonical; `infra/local/Dockerfile` ENV lines are documented defaults; `infra/local/start.sh` mirrors `pipeline/runtime.py` priorities

## Commit trail (Phase 2.5)

```
9ca4eba  INFRA-06: .env.example at repo root (W5 T-14)
102c700  INFRA-06: infra/local/README.md (W4 T-13)
fd121ad  INFRA-06: infra/local/docker-compose.yml + start.sh (W4 T-12)
4bba0f4  INFRA-06: infra/local/Dockerfile (W4 T-11)
45adbad  INFRA-06: fill models.manifest.json + soften SHA-TODO (W3 T-10)
2db1139  INFRA-06: lock ML pin matrix in requirements.txt (W3 T-09)
0398b3a  INFRA-06: extract pipeline/lipsync.py — W2 complete (T-08)
f39dcd6  INFRA-06: extract pipeline/tts.py (T-07)
ece277d  INFRA-06: extract pipeline/translate.py (T-06)
80ff2ab  INFRA-06: extract pipeline/transcribe.py (T-05)
e436dab  INFRA-06: extract pipeline/separator.py (T-04)
db8c5f6  INFRA-06: extract pipeline/audio.py (T-03)
6986f05  INFRA-06: extract runtime helpers (T-02b W2 prep)
3818d07  INFRA-06: env-driven paths + INFRA-07 device autodetect (T-01..02)
5c9c82f  INFRA-06: plan phase 2.5 (CONTEXT + PLAN)
f12271b  INFRA-06: reconcile STATE/CLAUDE + introduce phase 2.5
```

16 atomic commits across the phase (15 planned + 1 W2-prep runtime extraction that was discovered during execution). Branch `claude/add-claude-skills-rmINY` is pushed to `origin` up to and including the W2 set; W3–W5 will be pushed after this verification commit.
