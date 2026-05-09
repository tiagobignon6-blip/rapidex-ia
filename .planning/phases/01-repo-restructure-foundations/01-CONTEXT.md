# Phase 1: Repo Restructure & Foundations - Context

**Gathered:** 2026-05-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Bring the `/workspace/` ML pipeline into the git repo under a clean modular layout (`pipeline/`, `ui/`, `infra/`, `scripts/`, `tests/`) WITHOUT committing model weights and WITHOUT breaking the currently running pod app. Includes the `.gitignore` hardening, the `scripts/download_models.py` model fetcher, and the atomic pod-swap procedure.

**In scope (delivers):** INFRA-01, INFRA-02, INFRA-03, INFRA-04.

**Out of scope (deferred to later phases):**
- Renaming `app.py.py` → `app.py` (Phase 2)
- Theme tokens extraction to `ui/theme.py` (Phase 3)
- Logo asset (Phase 4)
- Aspect-ratio module (Phase 5)
- Tests against the new layout (Phases 8-9)
- HF Spaces deploy artifacts (Phases 10-12)

</domain>

<decisions>
## Implementation Decisions

### Pod-swap strategy (anti-pitfall #2)
- **D-01:** Restructure happens in a **fresh repo clone at `/workspace-v3/`** on the pod. Old `/workspace/` is left untouched throughout. Only after the new layout boots successfully end-to-end is `infra/runpod/startup.sh` swapped to point at `/workspace-v3/`. **Zero downtime is a hard acceptance criterion.**

### Model fetcher (`scripts/download_models.py`)
- **D-02:** Use an **explicit URL + SHA256 manifest** (JSON file, e.g. `scripts/models.manifest.json`) — one entry per weight file with `url`, `dest_path`, `sha256`. Mirror-friendly, fails loudly on checksum drift, no hidden assumption that all models live on HF Hub. The fetcher is **idempotent** — checks SHA before downloading, skips on match.

### Legacy code import paths
- **D-03:** Phase 1 leaves the **legacy `app.py.py` imports unchanged** — it continues to point at the old `/workspace/...` paths. The import rewrite (to `from pipeline import ...`) lands in **Phase 2** alongside the rename. Reasoning: keeps Phase 1 commits scoped to "move + version" without behavior change; Phase 2 can do a single atomic "rename + rewire" commit.

### `/workspace/` retention policy
- **D-04:** After the swap, `/workspace/` (old) is **retained until E2E validation in 1 real-user session confirms the new path works**. Then a follow-up cleanup commit deletes it. Belt-and-suspenders against silent regressions; recoverable disk space is small relative to risk.

### Claude's Discretion
- Exact file split inside `pipeline/` modules (already prescribed in `.planning/research/ARCHITECTURE.md` §"Recommended Repo Layout"). Use that as the source of truth.
- Exact `.gitignore` entries (already prescribed in ARCHITECTURE.md). Land them as the *first* commit of the phase, before moving any files in.
- The exact order of `pipeline/` module extraction from `/workspace/` (audio, separator, transcribe, translate, tts, lipsync) — bottom-up (audio → separator → transcribe → translate → tts → lipsync) is the natural order; planner can adjust if dependencies dictate otherwise.
- Whether to use `git mv` vs `cp` + `git add` when moving `app.py.py` from repo root into the new layout (only relevant if Phase 2 needs git-blame continuity; planner decides).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project source of truth
- `.planning/PROJECT.md` — Locked stack constraints, branch discipline, hard "no weights in git" rule
- `.planning/REQUIREMENTS.md` §INFRA-01..04 — The four requirements this phase delivers, with their acceptance criteria
- `.planning/ROADMAP.md` §"Phase 1: Repo Restructure & Foundations" — Goal + 4 success criteria

### Research (load both fully)
- `.planning/research/ARCHITECTURE.md` §"Recommended Repo Layout" — The exact directory tree with `pipeline/`, `ui/`, `infra/`, `scripts/`, `tests/` and per-file responsibilities
- `.planning/research/ARCHITECTURE.md` §"Critical `.gitignore` entries" — The complete gitignore block (must land before any file move)
- `.planning/research/ARCHITECTURE.md` §"Component Boundaries" — Module ownership table (audio.py, separator.py, transcribe.py, etc.)
- `.planning/research/PITFALLS.md` §"Pitfall 1: Committing model weights" — Detection + prevention contract
- `.planning/research/PITFALLS.md` §"Pitfall 2: Breaking the running RunPod app" — The atomic-swap pattern that drives D-01
- `.planning/research/STACK.md` §"Repo Layout / Tooling" — Supporting tools (ruff, pre-commit, python-dotenv) introduced in this phase

### Operating protocol
- `CLAUDE.md` §"Operating Protocol — Senior Autonomous Engineer (GSD)" — Atomic commits, branch discipline, no `--force`, no `--no-verify`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Repo: `app.py.py`** (15 090 bytes, root) — The Gradio UI. Stays in place this phase (rename happens in Phase 2). Imports remain pointing at `/workspace/...` until Phase 2 rewrites them.
- **Repo: `setup_rapidex.sh`** (3 472 bytes, root) — Likely contains pod bootstrapping. Read it during planning; merge useful parts into `infra/runpod/startup.sh`, archive the rest.
- **Pod: `/workspace/startup.sh`** — Currently boots the live app. Must NOT be modified during Phase 1; the new `infra/runpod/startup.sh` is created in `/workspace-v3/` and only takes over via atomic swap.
- **Pod: `/workspace/Wav2Lip/`, `/workspace/MuseTalk/`, `/workspace/fish-speech/`** — Source dirs for the new `pipeline/lipsync.py` and `pipeline/tts.py`. Logic gets refactored into Python modules under `pipeline/`; weights stay on disk under `/workspace-v3/models/` (gitignored).

### Established Patterns
- **One file in git** — the entire repo currently has 4 files (`app.py.py`, `setup_rapidex.sh`, `desktop.ini`, `CLAUDE.md`). No prior layout precedent to break.
- **No tests, no CI yet** — Phase 1 doesn't introduce them; Phase 8-9 do. Phase 1 should leave a `tests/` placeholder dir with an `__init__.py` so the layout is forward-compatible.
- **No package manager pinning yet** — Phase 1 introduces a `requirements.txt` (or `pyproject.toml` — planner picks based on what `/workspace/` uses today) populated from observed deps on the pod.

### Integration Points
- **Pod `/workspace/startup.sh` → `/workspace-v3/infra/runpod/startup.sh`** — atomic swap is the only integration touch. Validated by booting the new path and confirming `gradio.live` URL renders.
- **`scripts/download_models.py` → on-disk model dirs** — runs at first boot of the new layout, populates `/workspace-v3/models/` (or `$RAPIDEX_MODELS_DIR`); idempotent.
- **`.gitignore` → entire repo** — single source-of-truth that prevents weight commits. **Must be the first commit of the phase, before any file move.**

</code_context>

<specifics>
## Specific Ideas

- The atomic-swap target dir is `/workspace-v3/` (not `/workspace-v2/` to avoid confusion with the v2 product naming).
- The model manifest is JSON at `scripts/models.manifest.json`; entries follow `{name, url, dest_path, sha256, bytes_expected}` schema.
- `desktop.ini` (Windows artifact) gets deleted as part of Phase 1 cleanup.
- `infra/runpod/startup.sh` includes a `[boot] models ready in Ns` log line (mirroring the HF Spaces convention from PITFALLS #5) so first vs subsequent boot times are observable on either deploy target.
- Phase 1 acceptance demo: `bash /workspace-v3/infra/runpod/startup.sh` produces a working `gradio.live` URL on a clean (or freshly-restarted) pod, with the same UI as the current v2 app.

</specifics>

<deferred>
## Deferred Ideas

- **Pre-commit hooks (`ruff`, `pre-commit`)** — STACK.md recommends them but they belong in Phase 8 (test harness) — adding them now without tests creates noise.
- **`pyproject.toml` migration vs `requirements.txt`** — planner's discretion; if existing pod uses plain `pip install`, stay with `requirements.txt` until Phase 8 introduces dev deps.
- **Pod cost-control heartbeat in `app.py`** — PITFALLS #10 mentions this as an idea; doesn't belong here, surface during a future ops phase.
- **Logo asset move** — UI-01 already maps to Phase 4. Only the `ui/assets/` directory placeholder is created in Phase 1.

</deferred>

---

*Phase: 1 — Repo Restructure & Foundations*
*Context gathered: 2026-05-09*
