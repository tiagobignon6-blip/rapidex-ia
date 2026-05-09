# RAPIDEX IA

## What This Is

RAPIDEX IA is a video dubbing platform that takes a source video, transcribes the speaker, lets the user review and edit the translated text, then regenerates the audio in another language with synced lips on the original face. It's built as a Gradio web app on RunPod GPU and aimed at creators who need fast, cheap, multi-language reuse of their existing video content.

## Core Value

A creator should be able to drop a video in, edit the translated script, and walk out with a lip-synced dubbed version — without ever touching the underlying ML pipeline.

## Requirements

### Validated

- ✓ Gradio v2 UI with 3-column layout (Video & Languages | Review & Edit Text | Voice & Result) — shipped on RunPod
- ✓ WhisperX large-v3 transcription with VAD (no hallucinations) — shipped
- ✓ Translation via deep-translator (GoogleTranslator) — shipped
- ✓ Fish Speech V1.5 voice synthesis — shipped
- ✓ Demucs source separation (vocals + background) running invisibly — shipped
- ✓ MuseTalk lipsync with Wav2Lip fallback — shipped (models pre-downloaded)
- ✓ User-editable translation step between transcription and TTS — shipped
- ✓ Premium dark theme (#020409 / #6366f1 / #a855f7) with Syne + JetBrains Mono typography — shipped
- ✓ Numbered pipeline visual 1→2→3→4→5 in header — shipped
- ✓ One-shot launcher (`bash /workspace/startup.sh`) that boots the app and prints a public `gradio.live` URL — shipped

### Active

- [ ] Rename `app.py.py` → `app.py` in the repo (Windows naming bug)
- [ ] Add RAPIDEX IA logo PNG to the app header
- [ ] 9:16 vertical aspect support (Reels / TikTok / Shorts)
- [ ] End-to-end test with a real video covering the full pipeline
- [ ] Migration path to HuggingFace Spaces (deploy target alternative to RunPod)

### Out of Scope

- Alternative transcription engines (Whisper.cpp, Deepgram, etc.) — locked on WhisperX large-v3 with VAD
- Alternative TTS engines (XTTS, ElevenLabs, etc.) — locked on Fish Speech V1.5
- Alternative lipsync engines beyond MuseTalk + Wav2Lip fallback — current stack is final
- Translation providers beyond deep-translator/GoogleTranslator — keep dependency surface small
- Native mobile app — Gradio web is the only target
- Real-time / streaming dubbing — batch-only is the product
- User accounts, auth, billing — out of v1; deploy targets handle access control

## Context

- The pipeline lives on a RunPod GPU pod (`beautiful_gray_tiger`, id `59gpkaggh964b0`). RunPod balance was ~$7.55 as of last session — short runway for experimentation.
- Only the Gradio UI (`app.py.py`, ~15 KB) is in the GitHub repo. The actual ML stack (WhisperX, Fish Speech, MuseTalk models, Demucs, Wav2Lip) lives under `/workspace/` on the pod and is **not** in the repo. Any work involving the full pipeline has to happen on the pod.
- The duplicated extension `app.py.py` is a Windows naming bug from the upload step; the file works as-is and is the canonical app entry. Renaming is its own scoped task.
- HuggingFace Spaces is the planned secondary deploy target as a hedge against RunPod cost / availability.
- This is a brownfield project: the v2 product already runs end-to-end. Active work is incremental polish (logo, format support) and de-risking infra (E2E test, HF migration).

## Constraints

- **Tech stack**: WhisperX large-v3 + deep-translator + Fish Speech V1.5 + Demucs + MuseTalk (Wav2Lip fallback). Locked. Cannot change without explicit user approval.
- **Runtime**: RunPod GPU pod with limited remaining credit (~$7.55). Heavy iteration on the pod has direct $ cost.
- **Repo scope**: Only the Gradio UI lives in git. Pipeline code is on the pod and not versioned — refactoring deep ML code requires a separate workflow.
- **Filename**: `app.py.py` must stay until the rename task is executed; the launcher and pod scripts reference that path.
- **Branch discipline**: All dev on `claude/add-claude-skills-rmINY`. No direct push to `main`. No `--force`. No `--no-verify`.
- **Process**: All work must traverse the GSD lifecycle (Research → Discuss → Plan → Execute → Verify → Ship). Atomic commits per task.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| WhisperX large-v3 with VAD | Eliminates Whisper hallucinations on silence; still high-accuracy | ✓ Good |
| MuseTalk primary, Wav2Lip fallback | MuseTalk = better quality; Wav2Lip = robust safety net when MuseTalk fails | ✓ Good |
| Demucs runs hidden from the user | UX must show "transcribe → edit → dub", not "separate vocals" — keep ML invisible | ✓ Good |
| User edits the translation between WhisperX and Fish Speech | Translation quality is the human bottleneck; making it editable preserves accuracy | ✓ Good |
| Theme `#020409 / #6366f1 / #a855f7` + Syne + JetBrains Mono | Premium dark identity matching the "creator tool" positioning | ✓ Good |
| Gradio over a custom React frontend | Fastest path to GPU-app deploy; trades flexibility for time-to-market | — Pending (revisit if HF Spaces migration exposes limits) |
| Operate via GSD framework | Avoid 800-line dumps; force phase discipline and verification before merge | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-09 after initialization*
