---
gsd_state_version: 1.0
milestone: v2.5
milestone_name: milestone
status: in_progress
last_updated: "2026-05-12T00:00:00.000Z"
progress:
  total_phases: 13
  completed_phases: 2
  total_plans: 3
  completed_plans: 2
---

# State: RAPIDEX IA

**Milestone:** v2.5 — Polish + Vertical + Multi-Deploy
**Last updated:** 2026-05-12 after refinement (Phase 2.5 added; STATE drift fixed)

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-09)

**Core value:** A creator drops a video in, edits the translated script, and walks out with a lip-synced dubbed version — without ever touching the underlying ML pipeline.

**Current focus:** Phase 2.5 — Local Runtime Profile (new; unblocks downstream work without RunPod minutes)

## Position

| Phase | Status |
|---|---|
| Phase 1 — Repo Restructure & Foundations | Repo-side ✓ · pod swap **deferred** (operator runbook `infra/runpod/SWAP-PROCEDURE.md` still valid; not blocking) |
| Phase 2 — Rename app.py.py → app.py | ✅ Done (commit `f6f93bd`, 2026-05-12) |
| Phase 2.5 — Local Runtime Profile | In Progress (planning) |
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
| 2026-05-12 | Phase 2 rename completed inline (`f6f93bd`) without waiting for pod swap | Rename is repo-only; pod still boots from legacy path until swap |
| 2026-05-12 | Insert Phase 2.5 — Local Runtime Profile | Unblocks Phases 3–9 on the laptop (WSL2 + NVIDIA GPU) without burning RunPod credit; also pre-builds 90% of Phase 10's HF Spaces Dockerfile |
| 2026-05-12 | RunPod stays a supported deploy target | Pod swap remains valid; Phase 2.5 must preserve no-regression on the pod (env defaults keep legacy `/workspace/...` working) |

## Open Blockers / Concerns

- **Pod swap (Phase 1 D-04)** is now *deferred*, not blocking. The runbook `infra/runpod/SWAP-PROCEDURE.md` still applies and can be executed whenever convenient.
- **`requirements.txt`** still lacks the locked ML pin matrix (whisperx / fish-speech / demucs / deep-translator / torch / ctranslate2). Phase 2.5 W3 derives these from public upstream pins instead of waiting for a pod `pip freeze`.
- **`models.manifest.json`** has placeholder URLs/SHAs. Phase 2.5 W3 fills the public HF URLs + `bytes_expected`; SHA stays `TODO` until first verified download.

## Next Action

Execute Phase 2.5 — Local Runtime Profile (see `.planning/phases/02-5-local-runtime/01-PLAN.md`).
