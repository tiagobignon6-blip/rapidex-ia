# RAPIDEX IA — Project Memory

## Identity

- **Repo**: https://github.com/tiagobignon6-blip/rapidex-ia
- **Owner**: tiagobignon6-blip (tiagobignon6@gmail.com)
- **Active dev branch**: `claude/add-claude-skills-rmINY`
- **Runtime**: RunPod pod `beautiful_gray_tiger` (id `59gpkaggh964b0`)

## Stack (definitive — do not change without explicit confirmation)

| Layer | Tool |
|---|---|
| Transcription | WhisperX large-v3 (VAD, no hallucinations) |
| Translation | deep-translator (GoogleTranslator) |
| TTS / Voice | Fish Speech V1.5 |
| Audio separation | Demucs (auto, hidden from user) |
| Lipsync | MuseTalk (primary) · Wav2Lip (fallback) |

## Pipeline (hidden from end user)

```
Video → extract audio → Demucs (vocals + bg) → WhisperX(vocals)
      → translate → user edits text → Fish Speech → mix(voice + bg)
      → MuseTalk → final video
```

## Runtime layouts

### RunPod pod (production, legacy + post-swap)
- `/workspace/app.py` — currently running v2 (legacy path)
- `/workspace/startup.sh` — boots the app and prints `gradio.live` URL
- `/workspace/{MuseTalk,Wav2Lip,fish-speech}/` — model dirs (pre-downloaded)
- Post-swap (Phase 1 D-04): `/workspace-v3/infra/runpod/startup.sh` is the canonical entrypoint. Swap is deferred — runbook still valid in `infra/runpod/SWAP-PROCEDURE.md`.

### Local dev (WSL2 + NVIDIA GPU — Phase 2.5)
- `infra/local/start.sh` — bootstraps env, fetches models via `scripts/download_models.py`, launches `app.py` on `localhost:7860`
- `infra/local/docker-compose.yml` — single-service `--gpus all` mode mounting `./models` and `./outputs`
- Env-driven paths: `MUSETALK_DIR`, `WAV2LIP_DIR`, `FISH_SPEECH_DIR`, `RAPIDEX_MODELS_DIR`, `RAPIDEX_OUTPUTS_DIR`, `RAPIDEX_DEVICE`

### HF Spaces (planned — Phase 10)
- `infra/hfspaces/Dockerfile` — shares ~90% with `infra/local/Dockerfile`; differs in `HF_HOME=/data/.cache/huggingface` + `GRADIO_SHARE=false`.

## Operational commands

| Where | Command |
|---|---|
| Local (Compose) | `docker compose -f infra/local/docker-compose.yml up` |
| Local (bare WSL2+CUDA) | `bash infra/local/start.sh` |
| RunPod (legacy) | `bash /workspace/startup.sh` |
| RunPod (post-swap) | `bash /workspace-v3/infra/runpod/startup.sh` |

## UI / Design system (v2)

- **Layout**: 3 columns — Video & Languages | Review & Edit Text | Voice & Result
- **Flow**: Transcribe & Translate → edit text → Dub Video
- **Theme** (premium dark):
  - Background `#020409`
  - Primary `#6366f1` (indigo)
  - Secondary `#a855f7` (violet)
- **Typography**: Syne (display) + JetBrains Mono (mono)
- **Header**: numbered pipeline 1→2→3→4→5

## Open backlog

- [x] Rename `app.py.py` → `app.py` (commit `f6f93bd`, Phase 2)
- [ ] Local runtime profile — env-driven paths + device autodetect + `infra/local/` Compose (Phase 2.5)
- [ ] Add RAPIDEX IA logo to header (`ChatGPT_Image_8_de_mai__de_2026__01_19_21.png`)
- [ ] 9:16 support (Reels / TikTok)
- [ ] End-to-end test with real video
- [ ] Migrate to HuggingFace Spaces

---

# Operating Protocol — Senior Autonomous Engineer (GSD)

This project is operated **strictly through the Get Shit Done (GSD) framework**
(https://github.com/gsd-build/get-shit-done). GSD is installed globally
(`~/.claude/skills/gsd-*`).

## Core mandate

Act as a senior autonomous software engineer. Drive the project to completion in
**atomic steps**, keeping context clean via meta-prompting and spec-driven
development. Orchestrate fresh subagent contexts; do not bloat the main thread
with raw research or execution traces.

## Lifecycle — non-negotiable

Every feature or milestone MUST traverse the GSD phases in order:

1. **Research** — gather facts via subagents, never code yet
2. **Discuss** — `/gsd-discuss-phase` — capture implementation decisions
3. **Plan** — `/gsd-plan-phase` — produce a verified plan; loop until sound
4. **Execute** — `/gsd-execute-phase` — run the plan in parallel waves with fresh contexts
5. **Verify** — `/gsd-verify-work` — manual acceptance + diagnosis
6. **Ship** — `/gsd-ship` — atomic commit / PR

Never code outside this loop. Never skip phases. Never dump 800 lines without a plan.

## Autonomy rules

- **Proactive debugging**: if execution fails (compile error, broken test, runtime
  exception), do **not** stop and ask for input. Use GSD to diagnose root cause,
  produce a verified fix plan, re-execute. Only escalate when blocked by a
  decision only the user can make.
- **Verification is law**: writing code ≠ delivery. A phase is only "done" after
  `/gsd-verify-work` passes — code runs without errors and matches the plan.
- **Atomic commits**: each successfully executed task gets its own atomic commit
  with a clear semantic message. No batched mega-commits.
- **Branch discipline**: develop on `claude/add-claude-skills-rmINY` unless the
  user authorizes otherwise. Push with `git push -u origin <branch>`. Never push
  to `main`. Never `--force` push. Never `--no-verify`.

## Shared memory artifacts (GSD)

These survive sessions and are the source of truth — keep them updated:

- `PROJECT.md` — vision
- `REQUIREMENTS.md` — scope
- `ROADMAP.md` — phases
- `STATE.md` — current decisions and position
- `CONTEXT.md` — phase implementation details

## Session start protocol

On every new session, before acting:

1. Read `STATE.md` (if present) to recover position.
2. If `STATE.md` is missing or stale, ask whether to run `/gsd-map-codebase`
   (re-index existing architecture) or `/gsd-new-project` / `/gsd-autonomous`
   (bootstrap roadmap from scratch).

## Hard constraints

- Do **not** alter the stack (WhisperX / Fish Speech / MuseTalk / Demucs /
  deep-translator) without explicit user approval — those choices are final.
- Do **not** rename files or paths in `/workspace` without confirmation; the
  `app.py.py` filename is intentional until the GitHub rename task is done.
- Never commit secrets, `.env`, credentials, model weights, or large binaries.
- Comments only when the WHY is non-obvious. No narrative docstrings.

<!-- GSD:project-start source:PROJECT.md -->
## Project

**RAPIDEX IA**

RAPIDEX IA is a video dubbing platform that takes a source video, transcribes the speaker, lets the user review and edit the translated text, then regenerates the audio in another language with synced lips on the original face. It's built as a Gradio web app on RunPod GPU and aimed at creators who need fast, cheap, multi-language reuse of their existing video content.

**Core Value:** A creator should be able to drop a video in, edit the translated script, and walk out with a lip-synced dubbed version — without ever touching the underlying ML pipeline.

### Constraints

- **Tech stack**: WhisperX large-v3 + deep-translator + Fish Speech V1.5 + Demucs + MuseTalk (Wav2Lip fallback). Locked. Cannot change without explicit user approval.
- **Runtime**: RunPod GPU pod with limited remaining credit (~$7.55). Heavy iteration on the pod has direct $ cost.
- **Repo scope**: Only the Gradio UI lives in git. Pipeline code is on the pod and not versioned — refactoring deep ML code requires a separate workflow.
- **Filename**: `app.py.py` must stay until the rename task is executed; the launcher and pod scripts reference that path.
- **Branch discipline**: All dev on `claude/add-claude-skills-rmINY`. No direct push to `main`. No `--force`. No `--no-verify`.
- **Process**: All work must traverse the GSD lifecycle (Research → Discuss → Plan → Execute → Verify → Ship). Atomic commits per task.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Core ML Stack (locked — for reference only, do not change)
| Layer | Tool | Notes |
|---|---|---|
| Transcription | WhisperX large-v3 | VAD enabled — anti-hallucination |
| Translation | deep-translator | GoogleTranslator backend |
| TTS | Fish Speech V1.5 | reference-prompt voice cloning |
| Audio separation | Demucs | hidden from user |
| Lipsync | MuseTalk | primary |
| Lipsync fallback | Wav2Lip | safety net when MuseTalk fails |
| UI | Gradio | v4.x recommended (4.44+) |
| GPU | RunPod (current) + HF Spaces (planned) | dual deploy target |
## Supporting Tools (research scope)
### Video Pre/Post Processing
| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `ffmpeg` (system) | 6.x+ | All video I/O, aspect-ratio transforms | De-facto standard, handles every codec MuseTalk emits | HIGH |
| `ffmpeg-python` | 0.2.0+ | Python bindings to ffmpeg pipes | Cleaner than `subprocess.run` for chained filters; no extra deps | HIGH |
| `moviepy` | 2.x | (Avoid) high-level video editing | Heavy + slow; replaced by direct ffmpeg | HIGH (anti-rec) |
| `opencv-python-headless` | 4.10+ | Frame-level reads for face crop / aspect probe | Already a transitive dep of MuseTalk; reuse | HIGH |
| `Pillow` | 10.4+ | Logo overlay, header image manipulation | Standard, lightweight | HIGH |
### Testing
| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `pytest` | 8.3+ | Test runner | Standard; integrates with everything | HIGH |
| `pytest-asyncio` | 0.24+ | Async fixtures for Gradio | Gradio 4 internally async | HIGH |
| `gradio_client` | matches Gradio version | Programmatic Gradio invocation for E2E | Official; same API surface as the app | HIGH |
| `pytest-xdist` | 3.6+ | Parallel test execution | Useful for CPU unit tests | MEDIUM |
| `pytest-recording` (`vcrpy`) | 0.13+ | Cassette translation API responses | deep-translator hits Google; freeze responses for repeatable tests | HIGH |
| `pytest-snapshot` | 0.9+ | Snapshot text/JSON outputs | Good for transcript / translation diffs | HIGH |
| `imagehash` | 4.3+ | Perceptual hash for video frame comparison | Tolerates small numeric drift in lipsync output | MEDIUM |
### Deployment Packaging
| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `huggingface_hub` | 0.25+ | Model download + cache mgmt on HF Spaces | Standard for HF Spaces apps; respects `HF_HOME` | HIGH |
| `Dockerfile` (HF Spaces SDK) | — | Custom Docker for heavy deps | `requirements.txt` SDK is too constrained for WhisperX+ctranslate2+Fish Speech matrix | HIGH |
| `uv` or `pip-tools` | uv 0.4+ / pip-tools 7.4+ | Pinning + resolving conflicting deps | PyTorch + ctranslate2 + faster-whisper + Fish Speech have brittle pin matrix | MEDIUM |
| `gradio[oauth]` | 4.44+ | Gradio with OAuth for HF Spaces auth (optional) | Future-proof if private-Space auth is needed | LOW (optional) |
### Repo Layout / Tooling
| Tool | Version | Purpose | Why | Confidence |
|------|---------|---------|-----|------------|
| `git-lfs` | 3.5+ | Optional: track sample test fixtures (small mp4s) only | Do NOT use for model weights — those stay out of git | HIGH |
| `pre-commit` | 4.0+ | Lint hooks before commit | Cheap protection for the locked branch policy | MEDIUM |
| `ruff` | 0.6+ | Fast linter+formatter (replaces flake8+black+isort) | Single tool, low overhead | HIGH |
| `python-dotenv` | 1.0+ | `.env` for local secrets (HF_TOKEN, etc.) | Standard; keep `.env` in `.gitignore` | HIGH |
## HuggingFace Spaces Hardware Recommendation
- WhisperX large-v3 (FP16) ≈ 6 GB VRAM
- Fish Speech V1.5 ≈ 4 GB VRAM
- MuseTalk + face detection ≈ 4-6 GB VRAM (batch-size dependent)
- Demucs (htdemucs) ≈ 2 GB VRAM
- Concurrent residency: ~16-20 GB peak → A10G Small fits with headroom; T4 (16 GB) is borderline.
## Alternatives Considered (and rejected)
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Video lib | `ffmpeg-python` | `moviepy` | 5-10x slower, larger surface, breaks under concurrent calls |
| Test runner | `pytest` | `unittest` | Nobody writes ML tests in `unittest` anymore |
| Programmatic Gradio | `gradio_client` | scripting via `requests` | Brittle to Gradio version changes; official client tracks the app |
| HF Spaces SDK | Custom `Dockerfile` | Default `requirements.txt` | requirements.txt SDK pins Python 3.10 + can't install `ffmpeg` system pkg |
| HF GPU tier | A10G Small | ZeroGPU | Cold-start + queue timeouts kill long pipelines |
| HF GPU tier | A10G Small | T4 | 16 GB borderline at peak; OOM under load |
| Repo: ML weights | gitignored, downloaded on first boot | Git LFS for weights | LFS quotas + bandwidth costs; HF model hub is the right home |
## Installation Snippet
# System deps (HF Spaces Dockerfile or RunPod startup)
# Python deps (pin matrix — refine with Context7 in Plan phase)
# Dev / test deps
## Sources
- HuggingFace Spaces hardware tier docs: https://huggingface.co/docs/hub/spaces-gpus (verify before committing tier choice)
- Gradio E2E testing patterns: https://www.gradio.app/guides/testing-with-the-gradio-client
- WhisperX repo + ctranslate2 pin matrix: https://github.com/m-bain/whisperX
- Fish Speech docs: https://github.com/fishaudio/fish-speech
- MuseTalk repo: https://github.com/TMElyralab/MuseTalk
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
