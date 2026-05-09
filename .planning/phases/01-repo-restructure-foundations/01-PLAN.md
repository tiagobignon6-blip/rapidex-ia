---
status: ready
phase: 1
phase_name: Repo Restructure & Foundations
requirements:
  - INFRA-01
  - INFRA-02
  - INFRA-03
  - INFRA-04
decisions_implemented:
  - D-01
  - D-02
  - D-03
  - D-04
mode: inline
created: 2026-05-09
---

# Phase 1 PLAN — Repo Restructure & Foundations

## Goal

Bring the `/workspace/` ML pipeline into the git repo under a clean modular layout (`pipeline/`, `ui/`, `infra/`, `scripts/`, `tests/`) without committing model weights and without breaking the currently running pod app. Land the gating `.gitignore` first, then scaffold dirs + skeleton files, then the model fetcher, then the runbook for the atomic pod swap.

## Must-haves (goal-backward)

1. **`.gitignore` blocks weights** before any file is moved → no chance of committing multi-GB blobs (anti-pitfall #1).
2. **Skeleton repo layout exists** (`pipeline/`, `ui/`, `infra/runpod/`, `infra/hfspaces/`, `scripts/`, `tests/{unit,integration,fixtures}/`) with `__init__.py` markers for Python packages.
3. **`scripts/download_models.py` + `scripts/models.manifest.json`** exist, idempotent, SHA-verified per D-02.
4. **`infra/runpod/startup.sh`** exists as the canonical pod entrypoint (replaces `/workspace/startup.sh`).
5. **`infra/runpod/SWAP-PROCEDURE.md`** documents the operator runbook for the atomic swap per D-01.
6. **Legacy `/workspace/` content stays unmoved** until the operator runs the swap — Phase 1 deliverables are scaffold-only on the repo side.
7. **`app.py.py` import paths unchanged** per D-03 (rewrite happens in Phase 2).
8. **`/workspace/` retention** is documented in SWAP-PROCEDURE.md per D-04 (delete only after E2E validation in 1 real session).

## Execution split: repo vs pod

| Action | Where | Who |
|--------|-------|-----|
| Write `.gitignore` | Repo (this session) | Claude |
| Scaffold dirs + `__init__.py` + skeleton module files | Repo (this session) | Claude |
| Write `scripts/download_models.py` + `scripts/models.manifest.json` (placeholder URLs) | Repo (this session) | Claude |
| Write `infra/runpod/startup.sh` skeleton | Repo (this session) | Claude |
| Write `infra/runpod/SWAP-PROCEDURE.md` runbook | Repo (this session) | Claude |
| Delete `desktop.ini` (Windows artifact) | Repo (this session) | Claude |
| Add `tests/` placeholder structure | Repo (this session) | Claude |
| Copy real ML pipeline code from pod `/workspace/` into `pipeline/*.py` modules | Pod | Operator (manual via runbook) |
| Fill `scripts/models.manifest.json` with real URLs + SHA256s | Pod | Operator (manual, runbook step) |
| Atomic swap (`/workspace/` → `/workspace-v3/`) | Pod | Operator (manual, runbook step) |
| E2E validation in 1 real session | Pod | Operator |
| Delete old `/workspace/` after validation | Pod | Operator (post-validation cleanup) |

The repo-side scaffold is the GSD-managed deliverable. The pod-side execution is documented in SWAP-PROCEDURE.md and tracked as a manual checkpoint outside this PLAN.

## Tasks (waves)

### Wave 1 — Foundation (atomic, sequential)

**T-01: Land `.gitignore` (gating commit)**
- *Action:* Create `.gitignore` at repo root with the full block from `.planning/research/ARCHITECTURE.md` §"Critical `.gitignore` entries". Include weight extensions (`*.pth`, `*.ckpt`, `*.safetensors`, `*.bin`), explicit weight dirs (`MuseTalk/models/`, `Wav2Lip/checkpoints/`, `fish-speech/checkpoints/`, `checkpoints/`, `weights/`, `models/`), Python venvs (`.venv/`, `venv/`), caches (`__pycache__/`, `.pytest_cache/`, `*.pyc`), local secrets (`.env`, `.env.local`), outputs (`outputs/`, `*.mp4`, `*.wav`), with explicit allow for `tests/fixtures/*.mp4`.
- *Decision:* per D-01 / D-02 (must precede any file move).
- *Commit:* `chore(01): land .gitignore (gating, blocks weights)`
- *Verify:* `git check-ignore -v MuseTalk/models/foo.pth` → ignored. `git check-ignore -v tests/fixtures/sample.mp4` → not ignored.

**T-02: Delete `desktop.ini` (Windows artifact cleanup)**
- *Action:* `git rm desktop.ini`.
- *Decision:* per Phase 1 §Specifics (cleanup item).
- *Commit:* `chore(01): remove desktop.ini windows artifact`
- *Verify:* `ls desktop.ini` → file not found.

### Wave 2 — Scaffold (parallel-safe)

**T-03: Scaffold `pipeline/` module skeleton**
- *Action:* Create `pipeline/__init__.py` (empty), `pipeline/audio.py`, `pipeline/separator.py`, `pipeline/transcribe.py`, `pipeline/translate.py`, `pipeline/tts.py`, `pipeline/lipsync.py` — each with a one-line module docstring and a `# TODO(phase-2+): port from /workspace/...` placeholder. `pipeline/aspect.py` is NOT created — that's Phase 5 territory (out of Phase 1 scope per CONTEXT.md §Out of scope).
- *Decision:* per D-03 (skeleton only — actual import rewiring is Phase 2).
- *Commit:* `feat(01): scaffold pipeline/ module skeleton`
- *Verify:* `python -c "import pipeline"` succeeds (empty pkg loads).

**T-04: Scaffold `ui/` module skeleton + `ui/assets/` placeholder**
- *Action:* `ui/__init__.py`, `ui/theme.py` (empty stub), `ui/components.py` (empty stub), `ui/assets/.gitkeep` (placeholder for the future logo asset).
- *Decision:* per CONTEXT.md §Specifics (`ui/assets/` placeholder created in Phase 1; logo wiring is Phase 4).
- *Commit:* `feat(01): scaffold ui/ module skeleton`
- *Verify:* `python -c "import ui"` succeeds.

**T-05: Scaffold `infra/` (runpod + hfspaces placeholders)**
- *Action:* Create `infra/runpod/` and `infra/hfspaces/`. The latter gets a `.gitkeep` (Phases 10-12 populate it). The former gets a real `infra/runpod/startup.sh` (Phase 1 deliverable).
- *Decision:* per ARCHITECTURE.md §"Recommended Repo Layout".
- *Commit:* `feat(01): scaffold infra/ structure (runpod + hfspaces placeholders)`
- *Verify:* `ls infra/runpod/startup.sh infra/hfspaces/.gitkeep` both exist.

**T-06: Scaffold `tests/` with unit/integration/fixtures dirs**
- *Action:* Create `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/fixtures/.gitkeep` (Phases 8-9 populate the actual tests + fixtures).
- *Decision:* per CONTEXT.md §"Established Patterns" (forward-compatible placeholder).
- *Commit:* `feat(01): scaffold tests/ structure (unit, integration, fixtures placeholders)`
- *Verify:* `ls tests/unit/__init__.py tests/integration/__init__.py tests/fixtures/.gitkeep` all exist.

### Wave 3 — Tooling (sequential after Wave 2)

**T-07: `scripts/download_models.py` + `scripts/models.manifest.json`**
- *Action:* Create `scripts/__init__.py`. Create `scripts/models.manifest.json` with the JSON schema `{"models": [{"name", "url", "dest_path", "sha256", "bytes_expected"}]}` and placeholder entries for: WhisperX large-v3, Fish Speech V1.5, MuseTalk, Wav2Lip, Demucs htdemucs. Operator fills in real URLs/SHAs during the pod swap. Create `scripts/download_models.py` — argparse-based, reads manifest, for each entry: skip if `dest_path` exists AND SHA256 matches; else download with retries; verify SHA256 post-download; abort the run on mismatch.
- *Decision:* per D-02 (explicit URL+SHA manifest, idempotent).
- *Commit:* `feat(01): add download_models.py + models.manifest.json (D-02)`
- *Verify:* `python scripts/download_models.py --dry-run` parses manifest and reports each model's status (present/missing) without downloading.

**T-08: `infra/runpod/startup.sh` (canonical pod entrypoint)**
- *Action:* Write `infra/runpod/startup.sh` that: (a) sources env defaults (`RAPIDEX_MODELS_DIR=${RAPIDEX_MODELS_DIR:-$PWD/models}`, `RAPIDEX_OUTPUTS_DIR`, `GRADIO_SERVER_NAME=0.0.0.0`, `GRADIO_SHARE=true`), (b) runs `scripts/download_models.py` and times it, (c) prints `[boot] models ready in Ns`, (d) launches `python app.py` in the foreground (NOT background — operator wants visible logs during validation), (e) emits the `gradio.live` URL when Gradio prints it.
- *Decision:* per CONTEXT.md §Specifics (boot log line for observability).
- *Commit:* `feat(01): add infra/runpod/startup.sh canonical pod entrypoint`
- *Verify:* `bash -n infra/runpod/startup.sh` (syntax-only) succeeds.

**T-09: `infra/runpod/SWAP-PROCEDURE.md` (operator runbook for D-01)**
- *Action:* Step-by-step runbook the operator follows on the pod to perform the atomic swap: (1) `ssh` into the pod, (2) `git clone <repo>` into `/workspace-v3/`, (3) `cd /workspace-v3 && pip install -r requirements.txt`, (4) edit `scripts/models.manifest.json` to fill real URLs+SHAs (or copy weights from `/workspace/{MuseTalk,Wav2Lip,fish-speech}/` into `/workspace-v3/models/` and compute SHAs), (5) `bash infra/runpod/startup.sh` from the new dir, (6) verify `gradio.live` URL renders the v2 UI, (7) run a 5-second sample video through end-to-end, (8) if successful → update the pod's process manager / cron to point at `/workspace-v3/infra/runpod/startup.sh`, (9) wait 1 real-user session, (10) confirm + delete `/workspace/` (D-04 cleanup). Includes rollback note: if any step fails, leave `/workspace/` untouched and the v2 service keeps running.
- *Decision:* per D-01 (atomic swap, zero-downtime) + D-04 (retention until validated).
- *Commit:* `docs(01): add infra/runpod/SWAP-PROCEDURE.md operator runbook (D-01, D-04)`
- *Verify:* Runbook covers all 10 steps; rollback section explicit.

**T-10: Add `requirements.txt` skeleton**
- *Action:* Create `requirements.txt` at repo root with the supporting deps from `.planning/research/STACK.md` §"Installation Snippet" (gradio, gradio_client, ffmpeg-python, huggingface_hub, Pillow, python-dotenv). The locked ML stack deps (whisperx, fish-speech, demucs, deep-translator, MuseTalk torch matrix) are added by the operator from the pod's existing pinned set during the swap (we don't have visibility into those exact pins from this side).
- *Decision:* per ARCHITECTURE.md §"Recommended Repo Layout" (`requirements.txt` in root) + scoped split with operator handling pinned ML deps from the pod.
- *Commit:* `feat(01): add requirements.txt skeleton (supporting deps)`
- *Verify:* `pip install --dry-run -r requirements.txt` resolves without conflicts on the supporting deps.

### Wave 4 — Integration (after Wave 3)

**T-11: Update `CLAUDE.md` and `STATE.md` for Phase 1 completion**
- *Action:* Mark Phase 1 as "In Progress" in `STATE.md` (was "Not Started"); add the post-execution note that the repo-side scaffold is done, pod-side swap is the operator's manual checkpoint via `infra/runpod/SWAP-PROCEDURE.md`. CLAUDE.md gets a footer note linking to SWAP-PROCEDURE.md so future sessions know there's a pending operator action.
- *Commit:* `docs(state): phase 1 repo-side scaffold complete; pod swap pending operator`
- *Verify:* `grep "In Progress" .planning/STATE.md` returns the Phase 1 line.

## Dependency Graph

```
T-01 (.gitignore)  ──gates──→  T-03, T-04, T-05, T-06, T-07, T-08, T-09, T-10
T-02 (desktop.ini) ──parallel with T-01──
T-03..T-06 (scaffold) ──parallel within Wave 2──
T-07, T-08, T-09, T-10 ──Wave 3, can run after Wave 2 finishes──
T-11 (state update) ──Wave 4, sequential──
```

## Verification Plan (must pass before /gsd-verify-work signs off)

### Repo-side acceptance (this session)
- [ ] `git check-ignore -v MuseTalk/models/foo.pth` returns ignored
- [ ] `git check-ignore -v tests/fixtures/sample.mp4` returns NOT ignored
- [ ] `git ls-files | wc -l` shows the new scaffold files committed
- [ ] No file in `git ls-files` is > 1 MB (proves no weight committed)
- [ ] `python -c "import pipeline; import ui"` succeeds
- [ ] `bash -n infra/runpod/startup.sh` syntax check passes
- [ ] `python scripts/download_models.py --dry-run` parses manifest cleanly
- [ ] `infra/runpod/SWAP-PROCEDURE.md` contains all 10 operator steps + rollback section

### Pod-side acceptance (operator, after running SWAP-PROCEDURE.md)
- [ ] `bash /workspace-v3/infra/runpod/startup.sh` produces a working `gradio.live` URL
- [ ] The v2 UI renders identically to the current `/workspace/` build
- [ ] A 5-second sample video round-trips through the full pipeline → mp4 output downloads
- [ ] Old `/workspace/` is untouched until validation passes
- [ ] After 1 real session of validation, `/workspace/` is cleanly deleted

## Anti-patterns this plan avoids

- **No file moves before .gitignore lands** (T-01 is the gating commit)
- **No weights in any task** (T-07 only writes a manifest with placeholder URLs; operator fills + downloads on the pod, where weights are gitignored)
- **No in-place `/workspace/` mutation** (T-09 documents the swap-via-fresh-clone pattern; this session never touches the pod)
- **No `app.py.py` import rewrites** (deferred to Phase 2 per D-03)
- **No premature `pipeline/aspect.py`** (Phase 5 territory)
- **No premature pre-commit hooks / ruff config** (Phase 8 territory per CONTEXT.md §Deferred)

## Files this PLAN will create/modify

```
NEW:
  .gitignore
  pipeline/__init__.py
  pipeline/audio.py
  pipeline/separator.py
  pipeline/transcribe.py
  pipeline/translate.py
  pipeline/tts.py
  pipeline/lipsync.py
  ui/__init__.py
  ui/theme.py
  ui/components.py
  ui/assets/.gitkeep
  infra/runpod/startup.sh
  infra/runpod/SWAP-PROCEDURE.md
  infra/hfspaces/.gitkeep
  scripts/__init__.py
  scripts/download_models.py
  scripts/models.manifest.json
  tests/__init__.py
  tests/unit/__init__.py
  tests/integration/__init__.py
  tests/fixtures/.gitkeep
  requirements.txt

DELETE:
  desktop.ini

MODIFY:
  .planning/STATE.md
  CLAUDE.md (add SWAP-PROCEDURE.md pointer)
```

## Out of this plan (will be re-attempted in their own phases)

- Real ML module ports (Phase 2 partially via rename + import rewire; Phases 5-7 expand `pipeline/` substantively)
- Theme tokens with concrete values (Phase 3)
- Logo asset (Phase 4)
- Aspect-ratio module (Phase 5)
- 9:16 / 1:1 vertical (Phases 6-7)
- Tests beyond the placeholder dirs (Phases 8-9)
- HF Spaces Dockerfile (Phase 10)

---
*Phase 1 plan written inline (no sub-agent dispatch due to API rate limit). Ready for execution.*
