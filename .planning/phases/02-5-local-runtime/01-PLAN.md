---
phase: 2.5
phase_name: Local Runtime Profile
plan_version: 1
created: 2026-05-12
mode: mvp
requirements:
  - INFRA-06
  - INFRA-07
status: ready_to_execute
---

# Phase 2.5 — Local Runtime Profile — Plan

Context: `01-CONTEXT.md`. This plan breaks the phase into 5 execution waves and 15 atomic tasks. Each task = one commit. Subject prefix is `INFRA-06:` (multi-runtime) or `INFRA-07:` (device autodetect) per the QG hook convention.

## Waves

| Wave | What | Why this order |
|---|---|---|
| W1 | App-layer decoupling (paths + device) in `app.py` only | Fastest path to "boots on laptop." No new modules introduced; no pin matrix yet. Minimal blast radius — if it breaks the pod, revert one commit. |
| W2 | Pipeline module extraction (6 atomic commits) | Each function moves from `app.py` to its module with zero behavior change. Done after W1 so the modules inherit the env-driven paths. |
| W3 | Dependency + manifest fill | `requirements.txt` ML pin matrix; `models.manifest.json` public URLs. Done after W2 so the modules being installed are stable. |
| W4 | Local infra | `infra/local/{Dockerfile,docker-compose.yml,start.sh,README.md}`. Validates W1–W3 by actually booting the app in a container. |
| W5 | Env example + verification | `.env.example` at repo root; verification doc that checks the 7 acceptance criteria from CONTEXT.md. |

## Tasks

### W1 — App-layer decoupling (2 tasks)

**T-01 — INFRA-06: env-driven paths in app.py**
- Replace the 3 hardcoded `/workspace/...` strings in `app.py` with env-resolved paths:
  - `MUSETALK_DIR` (default `/workspace/MuseTalk` if dir exists else `${RAPIDEX_MODELS_DIR}/musetalk`)
  - `WAV2LIP_DIR` (default `/workspace/Wav2Lip` if dir exists else `${RAPIDEX_MODELS_DIR}/wav2lip`)
  - `RAPIDEX_OUTPUTS_DIR` (default `/workspace` if exists else `${REPO_ROOT}/outputs`)
- Helper `_resolve_dir(env_name, legacy_path, fallback_under_models)` keeps the smart-default logic in one place.
- File only changed: `app.py`. Surface ~25 lines. Single commit.
- Verification: `grep -nE "/workspace/" app.py` returns 0 lines.

**T-02 — INFRA-07: device autodetect helper**
- Add `def detect_device(override: str | None = None) -> str` at module scope. Returns `cuda` if `torch.cuda.is_available()`, else `mps` if `torch.backends.mps.is_available()`, else `cpu`. `RAPIDEX_DEVICE` env overrides.
- `run_whisperx` consumes `detect_device()` (was: literal `"cuda" if torch.cuda.is_available() else "cpu"` inline — keep behavior, just refactor through the helper for one source of truth).
- `run_fish_speech` consumes `detect_device()` and passes via `--device`. On `cpu`, raise `gr.Error("GPU required: Fish Speech V1.5 needs CUDA. Run with RAPIDEX_DEVICE unset on a CUDA host.")` instead of attempting.
- `run_lipsync` raises the same `gr.Error` on `cpu` for both MuseTalk and Wav2Lip paths.
- Single commit. Verification: `python -c "import app; print(app.detect_device('cpu'))"` prints `cpu`.

### W2 — Pipeline module extraction (6 tasks)

Each task moves one function from `app.py` to its corresponding `pipeline/*.py` module. `app.py` then imports + calls the function instead of defining it inline. Zero behavior change.

**T-03 — INFRA-06: extract pipeline/audio.py** — `extract_audio` + `mix_audio`.
**T-04 — INFRA-06: extract pipeline/separator.py** — `run_demucs`.
**T-05 — INFRA-06: extract pipeline/transcribe.py** — `run_whisperx` (uses `detect_device`).
**T-06 — INFRA-06: extract pipeline/translate.py** — `translate_text`.
**T-07 — INFRA-06: extract pipeline/tts.py** — `run_fish_speech` (uses `detect_device`, env-driven `FISH_SPEECH_DIR`).
**T-08 — INFRA-06: extract pipeline/lipsync.py** — `run_lipsync` (uses `MUSETALK_DIR` + `WAV2LIP_DIR` from W1).

Each commit includes:
- The module body (function moved verbatim, module docstring updated from "TODO" to one-line purpose).
- An `app.py` diff that adds `from pipeline.<name> import <fn>` and removes the inline definition.
- No new tests in this phase; unit tests come in Phase 8.

Per-commit verification: `python -c "from pipeline.<name> import <fn>"` succeeds; `python -c "import app"` succeeds (no NameError).

### W3 — Dependencies & manifest (2 tasks)

**T-09 — INFRA-06: lock ML pin matrix in requirements.txt**
- Append the locked ML stack to `requirements.txt`:
  - `torch==2.4.1+cu121 --extra-index-url https://download.pytorch.org/whl/cu121`
  - `torchaudio==2.4.1+cu121`
  - `whisperx>=3.1.5` (uses ctranslate2; pin transitively if conflict)
  - `ctranslate2>=4.4,<5`
  - `faster-whisper>=1.0.3`
  - `deep-translator>=1.11.4`
  - `demucs>=4.0.1`
  - `fish-speech-api` (pip name) OR install from git in start.sh — decide during this task by `pip show fish-speech` on the pod once we have access; default to git install since PyPI publishing of fish-speech is inconsistent.
  - `librosa>=0.10`, `soundfile>=0.12` (audio I/O transitive but explicit for clarity).
- Run `pip install --dry-run -r requirements.txt` in a fresh venv. Capture conflicts. Iterate pins until clean.
- Single commit. Verification: dry-run output attached to commit message (truncated to "resolved N packages without conflict").

**T-10 — INFRA-06: fill models.manifest.json with public HF URLs**
- For each of the 5 models, set `url` to a public HuggingFace `resolve/main` URL:
  - `whisperx-large-v3` → from `Systran/faster-whisper-large-v3` repo.
  - `fish-speech-v1.5` → from `fishaudio/fish-speech-1.5` repo.
  - `musetalk` → from `TMElyralab/MuseTalk` repo.
  - `wav2lip` → from `nguyenanh412/Wav2lip` or upstream Rudrabha repo if available.
  - `demucs-htdemucs` → from `facebook/demucs` or torchhub-redirected URL.
- Set `bytes_expected` from the HF UI's "View raw" file-size header.
- Keep `sha256: "TODO"` — operator's first successful fetch verifies and updates the manifest in a follow-up commit (the verifier itself will print the actual SHA on mismatch).
- Update `download_models.py` to emit a 1-line hint on `sha256: "TODO"` rather than treating it as fatal: print `[would-skip-verify]` and proceed with download, then print the actual SHA so the operator can paste it back.
- Two-file commit: `models.manifest.json` + `download_models.py` minor change.

### W4 — Local infra (3 tasks)

**T-11 — INFRA-06: infra/local/Dockerfile**
- Base: `nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04`.
- System: `python3.10`, `python3-pip`, `ffmpeg`, `git`, `wget`.
- Workdir `/app`; copy `requirements.txt` first, `pip install`, then copy the rest.
- `ENV` defaults for the 7 vars (matching Local profile from CONTEXT D-01).
- `CMD ["bash", "infra/local/start.sh"]`.

**T-12 — INFRA-06: infra/local/docker-compose.yml + start.sh**
- `docker-compose.yml`: single service `rapidex`, `image` built from local Dockerfile, `deploy.resources.reservations.devices` for NVIDIA, `ports: ["7860:7860"]`, `volumes: ["./models:/app/models", "./outputs:/app/outputs"]`, `env_file: .env`.
- `start.sh`: `python scripts/download_models.py` → `exec python app.py`. Shares 80% of `infra/runpod/startup.sh`'s shape but with local defaults.

**T-13 — INFRA-06: infra/local/README.md**
- 5 sections: Prerequisites (WSL2 + NVIDIA + nvidia-container-toolkit + Docker Compose v2), First-time setup (`cp .env.example .env`, `docker compose up`), CPU-only UI mode (`RAPIDEX_DEVICE=cpu python app.py`), Troubleshooting (3 common errors), Next steps (link to roadmap).

### W5 — Env example + verification (2 tasks)

**T-14 — INFRA-06: .env.example at repo root**
- Comment-grouped sections: Local-GPU profile / Local-CPU-UI profile / RunPod profile / HF Spaces profile.
- Every var lists default + brief description.

**T-15 — INFRA-06: phase 2.5 verification doc**
- `.planning/phases/02-5-local-runtime/01-VERIFICATION.md` walking the 7 acceptance criteria from CONTEXT.md.
- Two columns: repo-side (can verify from this session) and operator-side (boots Compose, smoke tests, runs `bash /workspace/startup.sh` on the pod for no-regression check).
- Mode `split` (mirrors Phase 1's pattern).

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Pin matrix doesn't resolve on a fresh venv (Pitfall #3) | Medium | T-09 iterates `pip install --dry-run`; if blocked > 30 min, fall back to "install ML deps from inline `pip install` lines in `start.sh`" while we research the conflict — same hack as the legacy pod's startup.sh |
| Operator's WSL2 lacks `nvidia-container-toolkit` | Medium | T-13 README has explicit setup section; CPU-only UI path always works as a fallback |
| Extracted module breaks `app.py` import chain | Low | Each W2 task includes the `app.py` import edit + a `python -c "import app"` smoke check in the commit |
| RunPod regression (legacy `/workspace/startup.sh` stops working) | Low | T-01's `_resolve_dir` defaults keep `/workspace/...` as the legacy fallback; operator's next pod boot is the regression test |
| Fish Speech PyPI package missing / wrong | High | T-09 handles by git-install path; explicit note in commit |
| Model manifest SHAs still `TODO` after this phase | Expected | Operator's first successful fetch fills them; documented in T-10 |

## What we are NOT doing in this phase

- Adding any tests. The pipeline modules end this phase without unit tests; Phase 8 adds them.
- Refactoring the existing inline pipeline for performance, batching, error handling, etc. Pure mechanical extraction.
- Filling SHA256s in `models.manifest.json`. That's an operator step on first download.
- Touching `setup_rapidex.sh` (legacy pod installer). It stays until Phase 10 obsoletes it.
- Building or pushing the `infra/hfspaces/Dockerfile` (Phase 10).

## Commit order (so far)

```
W1: T-01 → T-02
W2: T-03 → T-04 → T-05 → T-06 → T-07 → T-08
W3: T-09 → T-10
W4: T-11 → T-12 → T-13
W5: T-14 → T-15
```

15 atomic commits. Linear; no parallelism within the phase (the dependency chain is mostly serial).

## Stop conditions (when to halt and re-plan)

- Two consecutive tasks fail to merge cleanly: stop, re-read CONTEXT, decide whether the plan is wrong or the implementation drifted.
- Pin matrix resolution exceeds 1 hour of iteration: stop, capture the conflict, document the workaround, ship W4 against a `requirements-runtime.txt` derived from the pod instead.
- Operator's local Compose boot fails for a non-fixable reason (e.g. no GPU passthrough): stop W4, ship just W1+W2+W3+W5, defer infra/local to a follow-up.
