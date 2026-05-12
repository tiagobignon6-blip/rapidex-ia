---
status: human_needed
phase: 1
verified_at: 2026-05-09
verifier: claude (inline, no sub-agent)
mode: split
---

# Phase 1 Verification — Repo Restructure & Foundations

## Repo-side verification (this session)

### Acceptance criteria from PLAN

| # | Check | Result |
|---|-------|--------|
| 1 | `git check-ignore -v MuseTalk/models/foo.pth` returns ignored | ✅ matches `MuseTalk/models/` (line 11) |
| 2 | `git check-ignore -v tests/fixtures/sample.mp4` returns NOT ignored | ✅ matches `!tests/fixtures/*.mp4` negation (line 44) |
| 3 | `git ls-files \| wc -l` shows new scaffold files committed | ✅ 39 files tracked (was 4 before Phase 1) |
| 4 | No file in `git ls-files` is > 1 MB | ✅ largest is `app.py.py` at 15 KB |
| 5 | `python -c "import pipeline; import ui"` succeeds | ✅ imports OK |
| 6 | `bash -n infra/runpod/startup.sh` syntax check passes | ✅ syntax OK |
| 7 | `python scripts/download_models.py --dry-run` parses manifest cleanly | ✅ reports 5 models, all `manifest-incomplete` (expected — operator fills) |
| 8 | `infra/runpod/SWAP-PROCEDURE.md` contains all 10 operator steps + rollback | ✅ steps 1–10 present, rollback note in header + per-step |

**Repo-side acceptance: 8/8 ✓**

### Decisions implemented

| Decision | How implemented |
|----------|-----------------|
| D-01 — fresh clone at `/workspace-v3/`, validate, atomic launcher swap | `infra/runpod/SWAP-PROCEDURE.md` steps 2, 6, 8 |
| D-02 — explicit URL+SHA256 manifest | `scripts/models.manifest.json` schema + `scripts/download_models.py` SHA verification |
| D-03 — legacy `app.py.py` import paths unchanged in Phase 1 | `app.py.py` not modified this phase; pipeline modules are skeleton-only with `# TODO(phase-2+):` markers |
| D-04 — old `/workspace/` retained until 1 real session validates | `infra/runpod/SWAP-PROCEDURE.md` steps 9 (validate) + 10 (cleanup gate) |

### Requirements coverage

| Req | Status |
|-----|--------|
| INFRA-01 (modular layout in git) | ✅ `pipeline/`, `ui/`, `infra/`, `scripts/`, `tests/` all scaffolded |
| INFRA-02 (`.gitignore` blocks weights) | ✅ verified above |
| INFRA-03 (`scripts/download_models.py` idempotent + SHA-verified) | ✅ implemented + dry-run verified |
| INFRA-04 (atomic pod swap, zero-downtime) | ⏳ procedure documented; **operator action pending** on the pod |

## Pod-side verification (operator)

These items can only be confirmed AFTER the operator runs `infra/runpod/SWAP-PROCEDURE.md`:

- [ ] **Step 6:** `bash /workspace-v3/infra/runpod/startup.sh` produces a working `gradio.live` URL
- [ ] **Step 6:** v2 UI renders identically to the current pod
- [ ] **Step 7:** 5-second sample video round-trips through the full pipeline → output mp4 downloads
- [ ] **Step 8:** Launcher swapped to point at `/workspace-v3/infra/runpod/startup.sh` (atomic)
- [ ] **Step 9:** 1 real user session validates the new path
- [ ] **Step 10:** Old `/workspace/` cleaned up after validation

## Status

**`human_needed`** — repo-side scaffold is complete and verified; pod-side execution requires the operator to run through `infra/runpod/SWAP-PROCEDURE.md` (10 steps) on the RunPod pod. Phase 1 cannot be fully signed off until the pod-side checks pass.

When the operator finishes the swap and validates, run `/gsd-verify-work 1` again from a new session to flip this to `passed` and unblock Phase 2.

## Anti-patterns avoided

- ✅ `.gitignore` landed before any file move (T-01 was the gating commit `cd76ee3`)
- ✅ No model weights committed (largest tracked file is 15 KB)
- ✅ No in-place `/workspace/` mutation (this session never touched the pod)
- ✅ `app.py.py` imports unchanged (D-03 honored)
- ✅ No premature `pipeline/aspect.py` (Phase 5 territory, deferred)
- ✅ No premature pre-commit hooks (Phase 8 territory, deferred)

## Commit trail (Phase 1)

```
1905d07  docs(state): phase 1 repo-side scaffold complete; pod swap pending operator
                                                                                      (T-11)
[next 4]  feat(01): add requirements.txt skeleton (supporting deps)                   (T-10)
          docs(01): add SWAP-PROCEDURE.md operator runbook (D-01, D-04)               (T-09)
          feat(01): add infra/runpod/startup.sh canonical pod entrypoint              (T-08)
          feat(01): add download_models.py + manifest (D-02)                          (T-07)
[next 4]  feat(01): scaffold tests/ structure (unit, integration, fixtures)           (T-06)
          feat(01): scaffold infra/hfspaces/ placeholder (phases 10-12 populate)      (T-05)
          feat(01): scaffold ui/ module skeleton + assets placeholder                 (T-04)
          feat(01): scaffold pipeline/ module skeleton                                (T-03)
[wave 1]  c8d4506  chore(01): remove desktop.ini windows artifact                     (T-02)
          cd76ee3  chore(01): land .gitignore (gating, blocks weights)                (T-01)
[plan]    8a7d8bb  docs(01): plan phase 1 (11 tasks across 4 waves)
[discuss] 7110cab  docs(01): capture phase context
```

11 atomic commits across the phase. Branch `claude/add-claude-skills-rmINY` is pushed to `origin`.
