# State: RAPIDEX IA

**Milestone:** v2.5 — Polish + Vertical + Multi-Deploy
**Last updated:** 2026-05-09 after `/gsd-new-project`

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-09)

**Core value:** A creator drops a video in, edits the translated script, and walks out with a lip-synced dubbed version — without ever touching the underlying ML pipeline.

**Current focus:** Phase 1 — Repo Restructure & Foundations

## Position

| Phase | Status |
|---|---|
| Phase 1 — Repo Restructure & Foundations | Not Started |
| Phase 2 — Rename app.py.py → app.py | Not Started |
| Phase 3 — Theme Tokens Extraction | Not Started |
| Phase 4 — Logo in Header | Not Started |
| Phase 5 — Aspect-Ratio Module Foundation | Not Started |
| Phase 6 — 9:16 Vertical Support | Not Started |
| Phase 7 — 1:1 Square Support | Not Started |
| Phase 8 — Unit Test Harness | Not Started |
| Phase 9 — Integration Test Harness | Not Started |
| Phase 10 — HF Spaces Dockerfile & Env | Not Started |
| Phase 11 — HF Spaces Model Persistence | Not Started |
| Phase 12 — HF Spaces Smoke + E2E Validation | Not Started |

## Recent Decisions

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-09 | Operate via the Get Shit Done (GSD) framework | Force phase discipline + verification before merge; avoid 800-line dumps |
| 2026-05-09 | Granularity = fine (12 phases) | Maps cleanly to the 5 backlog items + the implicit repo-restructure prerequisite + the cosmetic items + test harness split |
| 2026-05-09 | Mode = mvp (vertical slices) | Each phase delivers a discrete user-observable improvement |
| 2026-05-09 | Models stay out of git via aggressive `.gitignore` | Multi-GB blobs in git are nearly unrecoverable; HF Hub is the right home |
| 2026-05-09 | Repo restructure is Phase 1 (gating) | Without it, E2E + HF migration are blind |
| 2026-05-09 | Atomic pod swap strategy in Phase 1 | Old `/workspace/` stays as fallback until new layout validates |
| 2026-05-09 | A10G Small recommended for HF Spaces | Avoids ZeroGPU cold-start; T4 borderline at peak VRAM |

## Open Blockers / Concerns

(None.)

## Next Action

Run `/gsd-discuss-phase 1` to gather implementation decisions for **Phase 1 — Repo Restructure & Foundations**, then `/gsd-plan-phase 1` to produce the executable plan.

In autonomous mode, this happens automatically as the workflow advances.
