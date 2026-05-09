# Phase 1 Discussion Log

**Phase:** 1 — Repo Restructure & Foundations
**Date:** 2026-05-09
**Mode:** Batch (4 questions, single turn)

This is a human-readable audit trail. Downstream agents (researcher, planner, executor) read `01-CONTEXT.md`, not this file.

---

## Areas Discussed

### 1. Pod-swap strategy

**Question:** How should we restructure the pod's `/workspace/` without breaking the currently running app?

**Options presented:**
- ✅ **Fresh clone at `/workspace-v3/`, validate, then swap startup.sh** *(Recommended — zero downtime, anti-pitfall #2)*
- ❌ In-place file moves in `/workspace/` *(faster but risks killing the live app)*

**User chose:** Fresh clone at `/workspace-v3/`.
**Captured as:** D-01.

### 2. Model fetcher source

**Question:** How should `scripts/download_models.py` retrieve weights?

**Options presented:**
- ✅ **Explicit URL + SHA256 manifest** *(Recommended — reproducible, mirror-friendly, fails on checksum drift)*
- ❌ `huggingface_hub.snapshot_download` *(simpler but no SHA verification, single-source dependency)*

**User chose:** Explicit URL + SHA256 manifest.
**Captured as:** D-02.

### 3. Legacy `app.py.py` import paths

**Question:** When do we rewrite the imports in `app.py.py` from `/workspace/...` to `pipeline/...`?

**Options presented:**
- ✅ **Defer to Phase 2** (rename + rewrite together) *(Recommended — keeps Phase 1 commits scoped to "move + version" with no behavior change)*
- ❌ Bundle into Phase 1 *(more risk per commit, larger blast radius)*

**User chose:** Defer to Phase 2.
**Captured as:** D-03.

### 4. `/workspace/` retention policy after swap

**Question:** When do we delete the old `/workspace/` after swap?

**Options presented:**
- ✅ **Keep until E2E validation confirmed in 1 real-user session** *(Recommended — belt-and-suspenders)*
- ❌ Delete immediately post-swap *(reclaims disk but loses fallback)*
- ❌ Keep forever *(unnecessary persistent waste)*

**User chose:** Keep until E2E validation confirmed.
**Captured as:** D-04.

---

## Claude's Discretion (no user question needed)

These were not asked because the research artifacts already prescribe the answer:

- Exact directory tree under `pipeline/` / `ui/` / `infra/` / `scripts/` / `tests/` — see `research/ARCHITECTURE.md`.
- Exact `.gitignore` entries — see `research/ARCHITECTURE.md`.
- Module extraction order from `/workspace/` (audio → separator → transcribe → translate → tts → lipsync, bottom-up) — natural dependency order; planner can re-order if it discovers a constraint.

---

## Deferred (not for this phase)

- Pre-commit hooks → Phase 8 (test harness lands first)
- `pyproject.toml` vs `requirements.txt` migration → Phase 8 (dev deps are introduced there)
- Pod cost-control heartbeat → future ops phase
- Logo asset wiring → Phase 4 (Phase 1 only creates the `ui/assets/` placeholder dir)

---

## Outcome

CONTEXT.md created with 4 captured decisions (D-01 .. D-04), 6 canonical references (PROJECT, REQUIREMENTS, ROADMAP, ARCHITECTURE, PITFALLS, STACK), and the `.gitignore-first` ordering constraint flagged as the most-critical implementation rule for the executor.

Ready for `/gsd-plan-phase 1`.
