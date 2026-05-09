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

## Workspace layout (RunPod pod)

- `/workspace/app.py` and `/workspace/app.py.py` — same file (Windows naming bug; `app.py.py` is what's in the repo)
- `/workspace/startup.sh` — boots the app and prints `gradio.live` URL
- `/workspace/Wav2Lip/` — fallback lipsync
- `/workspace/MuseTalk/` — primary lipsync (models pre-downloaded)
- `/workspace/fish-speech/` — TTS

## Operational commands

- Start app each new session: `bash /workspace/startup.sh`

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

- [ ] Rename `app.py.py` → `app.py` on GitHub
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
