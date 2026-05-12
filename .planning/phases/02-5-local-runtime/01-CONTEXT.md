---
phase: 2.5
phase_name: Local Runtime Profile
created: 2026-05-12
mode: mvp
status: in_planning
requirements:
  - INFRA-06
  - INFRA-07
---

# Phase 2.5 — Local Runtime Profile

## Problem

The product runs only on the RunPod pod. `app.py` hardcodes `/workspace/MuseTalk`, `/workspace/Wav2Lip`, `/workspace/output_*.mp4`, and `--device cuda` as a literal string. There is no way to:

1. Iterate on the UI / aspect / theme work without burning RunPod credit (~$7.55 remaining as of 2026-05-09).
2. Run unit tests locally — the pipeline modules (`pipeline/*.py`) are empty 1-line skeletons; all real logic is inline in `app.py`.
3. Trivially produce the HF Spaces Docker image (Phase 10) — that work is currently scoped as if from scratch, but ~90% of it is the same problem solved here.

The RunPod pod swap (Phase 1 D-04) is also currently blocking everything downstream in the original roadmap, because it's the only validated runtime. Decoupling the runtime makes the swap a side-quest instead of a gate.

## Decisions captured (from session 2026-05-12)

| ID | Decision | Rationale |
|---|---|---|
| D-01 | Local target is WSL2 + NVIDIA GPU (CUDA works for the operator) | Full pipeline can run locally; we don't need to design heroic CPU paths beyond a UI-boot safety net |
| D-02 | RunPod stays a supported deploy target | No-regression on the pod is a hard acceptance criterion; the existing `infra/runpod/startup.sh` must still work after this phase |
| D-03 | Phase 2.5 starts immediately after STATE/CLAUDE reconciliation | Plan + first execution wave in the same session |
| D-04 | Pin matrix derived from upstream public pins, not the pod's `pip freeze` | Operator hasn't done the pod swap; we can't wait. Risk: matrix may differ slightly from the pod's frozen env. Mitigation: smoke test on the pod after pin matrix lands, before declaring no-regression. |
| D-05 | New `infra/local/` dir as a peer of `runpod/` and `hfspaces/` | Three runtime profiles, three subdirs. Avoids a top-level `Dockerfile` that pretends to serve all targets. |
| D-06 | `infra/local/Dockerfile` and `infra/hfspaces/Dockerfile` share a common base layer | The two are 90% identical (same system deps, same Python deps, same entrypoint). Difference is env defaults + `HF_HOME` + `GRADIO_SHARE`. Achieved via ARG / multi-stage or just a shared snippet that's `cat`-ed in — chosen during plan. |
| D-07 | `RAPIDEX_DEVICE=cpu` boots the UI but raises a clear user-facing error on dub | Letting Fish Speech / MuseTalk attempt CPU inference would hang for minutes and look like a bug. The honest path is a Gradio `gr.Error("GPU required for this step")` with a one-liner explaining the local-CPU mode. |

## Scope

### In scope
- Env-driven paths in `app.py` (and any pipeline modules extracted in this phase).
- Device autodetect helper used by transcription + TTS.
- Extract the current `app.py` pipeline functions into the existing `pipeline/*.py` skeletons. (One commit per module; no behavior change beyond pulling the function into the module and importing it back.)
- ML pin matrix added to `requirements.txt`, sourced from upstream public pins (WhisperX / Fish Speech / MuseTalk / Demucs / deep-translator).
- `models.manifest.json` filled with public HF URLs + `bytes_expected`. `sha256` stays `TODO` until first verified local download — that's the first thing the operator's first local run will produce.
- `infra/local/` with `Dockerfile`, `docker-compose.yml`, `start.sh`, `README.md`.
- `.env.example` at repo root listing all env vars with per-profile defaults.

### Out of scope (deferred to later phases)
- Theme tokens extraction (Phase 3).
- Logo in header (Phase 4).
- Aspect detection module (Phase 5).
- Unit/integration test harness (Phases 8–9).
- HF Spaces Dockerfile (Phase 10) — but the local Dockerfile MUST be drop-in compatible so Phase 10 is a thin diff.
- Filling SHA256s in the manifest (operator action on first successful local fetch).

## Constraints

- No regression on the pod. `bash infra/runpod/startup.sh` must produce a working `gradio.live` URL with the same UX after this phase. Defaults for `MUSETALK_DIR` etc. preserve legacy `/workspace/...` paths *when the env vars are unset and the legacy dirs exist*.
- No model weights committed (Phase 1 D-01 still holds).
- Branch `claude/add-claude-skills-rmINY`. No push to `main`. No `--force`. No `--no-verify`.
- Commits are atomic per task. Subject prefix uses the requirement code (`INFRA-06:` or `INFRA-07:`) per the QG hook convention.
- The locked stack (WhisperX large-v3 / deep-translator / Fish Speech V1.5 / Demucs / MuseTalk + Wav2Lip fallback) is not changed by this phase.

## Open questions (resolve during plan or first execution)

1. **Pin matrix sources.** Public pins from WhisperX `setup.py`, Fish Speech `pyproject.toml`, MuseTalk `requirements.txt`, Demucs PyPI. Risk: torch/ctranslate2 conflict on a fresh resolver (Pitfall #3). Mitigation: use `pip install --dry-run` on a fresh venv before locking, capture conflicts, pin conservatively.
2. **Shared Dockerfile pattern.** Three options:
   - (a) Single `infra/Dockerfile.base` + thin `infra/local/Dockerfile` + thin `infra/hfspaces/Dockerfile` that each `FROM` the base.
   - (b) Multi-stage Dockerfile with profile ARG.
   - (c) Just duplicate the Dockerfile in both dirs (KISS; 90% similar but explicit).
   Decided at plan time. Default lean = (c) for now (rapid iteration; Phase 10 can refactor if a third profile lands).
3. **`infra/local/start.sh` vs Docker default.** Do we encourage Compose-first (best for parity with HF Spaces) or bare-script-first (best for fast iteration without container rebuilds)? Answer: both, but `README.md` recommends Compose for first-time setup and bare script for code iteration.
4. **NVIDIA Container Toolkit on WSL2.** Operator may need `nvidia-container-toolkit` installed in WSL2 distro for Compose `--gpus all`. `infra/local/README.md` includes a one-paragraph setup check (`nvidia-smi` inside container).

## Acceptance shape (filled out fully in PLAN.md)

A successful Phase 2.5 verification means:
1. `grep -RnE "/workspace/" app.py pipeline/` returns nothing.
2. On the operator's laptop: `docker compose -f infra/local/docker-compose.yml up` boots Gradio at `http://localhost:7860` and a 5-second sample video round-trips through the full pipeline.
3. On the operator's laptop: `RAPIDEX_DEVICE=cpu python app.py` boots the UI; transcribe button works on a tiny clip; dub button shows a clear "GPU required" `gr.Error`.
4. On the RunPod pod (legacy path): `bash /workspace/startup.sh` still produces a working `gradio.live` URL with no UX change. (No-regression gate. Validated by operator next time they boot the pod.)
5. `pipeline/audio.py`, `pipeline/separator.py`, `pipeline/transcribe.py`, `pipeline/translate.py`, `pipeline/tts.py`, `pipeline/lipsync.py` each contain real implementations (not skeletons), each importable, each callable by `app.py`.
6. `requirements.txt` resolves cleanly on a fresh Python 3.10 + CUDA 12.1 venv: `pip install -r requirements.txt --dry-run` succeeds.
7. `python scripts/download_models.py --dry-run` reports 5 models with public URLs (not `TODO`); SHAs may still be `TODO` until first fetch.
