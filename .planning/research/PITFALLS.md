# Domain Pitfalls — RAPIDEX IA

**Researched:** 2026-05-09
**Confidence:** MEDIUM-HIGH (drawn from ML/dub ecosystem post-mortems, GitHub issues, RunPod / HF Spaces operator threads)

## Critical Pitfalls (cause rewrites or major issues)

### Pitfall 1: Committing model weights into the repo

- **What goes wrong:** During the repo restructure, `git add .` sweeps in multi-GB `.pth` / `.safetensors` / `.bin` files from `/workspace/MuseTalk/`, `/workspace/fish-speech/`, `/workspace/Wav2Lip/`.
- **Why it happens:** The default `.gitignore` won't catch them; user is moving stuff fast.
- **Consequences:** Repo size explodes from ~50 KB to several GB. Clone times become unusable. GitHub may reject the push. Rolling back without history loss is painful.
- **Prevention:** **Land the `.gitignore` BEFORE moving any code in.** The gitignore in ARCHITECTURE.md (`**/*.pth`, `**/*.ckpt`, `**/*.safetensors`, `**/*.bin`, plus explicit `MuseTalk/models/`, `Wav2Lip/checkpoints/`, `fish-speech/checkpoints/`) is the gate.
- **Detection:** `git status` before commit; check `du -sh .git/` after first commit; `git ls-files | xargs ls -lS | head -20` to surface largest tracked files.
- **Phase to address:** **Phase 1** (repo restructure) — gating step before moving any pipeline code.

### Pitfall 2: Breaking the running RunPod app during refactor

- **What goes wrong:** While restructuring `/workspace/`, the Gradio app crashes mid-session because path X no longer resolves; user is mid-render and loses the output.
- **Why it happens:** `/workspace/` is BOTH the dev environment AND the production runtime — there's no staging.
- **Consequences:** Lost user work, lost RunPod credit, broken trust in the dev process.
- **Prevention:** Do the restructure in a clean **clone of the repo** at a different path on the pod (e.g. `/workspace-v3/`), validate it boots end-to-end, then atomically swap `startup.sh` to point at the new path. Old `/workspace/` stays untouched as fallback until validated.
- **Detection:** Run `bash startup.sh` against the new path before swap; tail logs for the full pipeline test.
- **Phase to address:** **Phase 1** (repo restructure) — explicit acceptance criterion: zero downtime swap.

### Pitfall 3: PyTorch + ctranslate2 + Fish Speech version conflict on HF Spaces

- **What goes wrong:** `pip install -r requirements.txt` on HF Spaces fails or installs a stale `ctranslate2` that breaks WhisperX large-v3 alignment.
- **Why it happens:** WhisperX pins `ctranslate2`, Fish Speech pins a specific PyTorch, and the HF Spaces base image may already have a conflicting torch. Default HF Spaces SDK auto-resolution doesn't always pick a compatible matrix.
- **Consequences:** App boots but transcription returns garbage, or alignment silently produces empty word timestamps, breaking lipsync.
- **Prevention:** Use a custom **Dockerfile** (`sdk: docker` in the Spaces YAML), pin all 3 explicitly in `requirements.txt` from the same matrix that works on RunPod, and run a smoke test that asserts WhisperX returns non-empty word timestamps before declaring HF migration done.
- **Detection:** Smoke test: `transcribe.run(known_5s_clip)` → assert `len(segments) > 0` and `all(seg.words for seg in segments)`.
- **Phase to address:** **Phase 6** (HF migration) — bake into the migration acceptance criteria.

### Pitfall 4: 9:16 video face-crop drift in MuseTalk

- **What goes wrong:** Portrait phone-shot video has the face occupying ~80% of the frame height; MuseTalk's face detector picks up shoulders/neck as part of the face box and produces glitched lipsync output (lips appear on the chin or below the chin).
- **Why it happens:** MuseTalk's training distribution skews toward 16:9 talking-head footage where faces are ~30-50% of frame height. Portrait input is out-of-distribution.
- **Consequences:** Output looks broken; users blame the product.
- **Prevention:** In `pipeline/lipsync.py`, before MuseTalk inference, run a tighter face crop using `face_recognition` or MuseTalk's bundled detector with explicit margin parameters tuned for portrait. Optionally letterbox the portrait video to 16:9 (with bg fill) before MuseTalk and crop back after.
- **Detection:** Visual QA on portrait fixture in `tests/fixtures/tiny_9x16.mp4`; perceptual hash drift > threshold flags regression.
- **Phase to address:** **Phase 4** (9:16 support) — primary technical risk.

### Pitfall 5: HF Spaces ephemeral storage = re-downloading 6+ GB of models on every restart

- **What goes wrong:** HF Spaces restarts (on Space sleep, on push, on hardware change) wipe `/tmp` and reinstall the env. If models live in `/tmp` they re-download every time → 5-10 min cold start.
- **Why it happens:** HF Spaces' container is mostly ephemeral; only specific paths persist (`/data` on paid hardware, `~/.cache/huggingface` is sometimes cached but unreliable).
- **Consequences:** First user after restart waits 5-10 minutes; bad demo experience.
- **Prevention:** Set `HF_HOME=/data/.cache/huggingface` in the Dockerfile env. Use `huggingface_hub.snapshot_download()` to fetch models to `/data/models/` once and reuse across restarts. Verify on first boot via SHA check (`scripts/download_models.py`).
- **Detection:** Time the second boot (after first restart); should be < 30s. Add a startup log line `[boot] models ready in Ns`.
- **Phase to address:** **Phase 6** (HF migration).

## Moderate Pitfalls

### Pitfall 6: WhisperX VAD over-trims short utterances

- **What goes wrong:** VAD aggressively marks silence and trims out short single-syllable utterances ("oi", "sim", "no"), causing missing segments in transcription.
- **Prevention:** Use VAD `min_speech_duration_ms=200` (not the default 250+); validate on a fixture that includes single-syllable words.

### Pitfall 7: Fish Speech long-input quality drift

- **What goes wrong:** Fish Speech V1.5 quality degrades on inputs > 30 seconds (voice timbre drifts, occasional hallucinated phonemes).
- **Prevention:** Chunk TTS by sentence/segment; concatenate. Already implicit in the current segment-based pipeline; document the chunking contract explicitly in `pipeline/tts.py`.

### Pitfall 8: Demucs "vocals" includes vocal-like SFX (laughs, vocalizations)

- **What goes wrong:** Demucs separates vocals from music decently but music with vocal samples (or videos with laughter, screams) may keep them in vocals → WhisperX tries to transcribe them.
- **Prevention:** Filter WhisperX output by no_speech_prob / VAD confidence; drop segments with low confidence to avoid garbage transcriptions.

### Pitfall 9: Flaky E2E tests due to non-deterministic ML output

- **What goes wrong:** Same input → slightly different output every run (Fish Speech sampling, MuseTalk batch ordering effects). Strict equality assertions fail intermittently.
- **Prevention:** Set `torch.manual_seed(42)` + `np.random.seed(42)` in test fixtures; assert on **structure** (len, duration, dims), not exact bytes; use perceptual hash for video frames with a tolerance.

### Pitfall 10: RunPod idle pod cost drain

- **What goes wrong:** User leaves the pod running overnight; ~$7.55 credit gone in a day.
- **Prevention:** Document the stop pattern (`runpodctl stop pod ID` or web UI) in CLAUDE.md / README. Optionally: a heartbeat in `app.py` that auto-stops the pod after N minutes idle (paranoid mode).

### Pitfall 11: Logo PNG too large breaks first paint

- **What goes wrong:** User adds `ChatGPT_Image_8_de_mai__de_2026__01_19_21.png` directly (probably 2-5 MB) → Gradio header takes 2+ seconds to render on slow connections.
- **Prevention:** Optimize the PNG (convert to WebP or compress to < 50 KB). Bake the optimized version into `ui/assets/logo.png`.

### Pitfall 12: deep-translator Google rate-limit on long videos

- **What goes wrong:** A 10-minute video with 200 segments hits Google Translate's anonymous rate limit; deep-translator returns blank / error.
- **Prevention:** Batch segments into single calls (Google Translate accepts up to ~5000 chars per request); add exponential backoff on rate-limit errors; surface a friendly "translation rate limited, try again in N seconds" UI message instead of a blank failure.

## Minor Pitfalls

### Pitfall 13: `app.py.py` rename breaks pod startup script

- **What goes wrong:** Rename happens in repo; pod's `startup.sh` still calls `app.py.py` and crashes.
- **Prevention:** Coordinate the rename atomically with `infra/runpod/startup.sh` update. Test the swap path (Pitfall 2 mitigation covers this).

### Pitfall 14: Pre-commit hooks slow down dev

- **What goes wrong:** `ruff` + `pre-commit` checks add 5-10s on every commit; user gets annoyed.
- **Prevention:** Keep hooks fast; restrict ruff to changed files (`--diff`); only block on errors, not warnings.

### Pitfall 15: Test fixtures committed at full resolution blow up the repo

- **What goes wrong:** `tests/fixtures/sample.mp4` is a 50 MB sample video; clones become slow.
- **Prevention:** Cap fixtures at 5 seconds, 480p, ~200-500 KB each. Use a vertical fixture and a horizontal fixture; nothing else.

## Phase-Specific Warning Map

| Active Backlog Item | Likely Pitfalls | Mitigation Priority |
|---------------------|-----------------|---------------------|
| **Phase 1 — Repo restructure** | #1 (model weights), #2 (breaking pod) | **CRITICAL** — gating |
| **Phase 2 — Rename app.py.py** | #13 (startup.sh) | Low — covered by Phase 1 atomicity |
| **Phase 3 — Logo in header** | #11 (logo too large) | Low |
| **Phase 4 — 9:16 vertical** | #4 (face-crop drift), #6 (WhisperX VAD edge cases) | **HIGH** — primary feature risk |
| **Phase 5 — E2E test harness** | #9 (flaky tests), #15 (fixture size) | Medium |
| **Phase 6 — HF Spaces migration** | #3 (dep conflict), #5 (cold-start) | **HIGH** — gates ship |
| **Cross-cutting / ops** | #10 (idle pod), #14 (slow hooks) | Low — document, don't gate |

## Sources

- WhisperX VAD discussions: https://github.com/m-bain/whisperX/issues (alignment + VAD threads)
- MuseTalk portrait video issues: https://github.com/TMElyralab/MuseTalk/issues (community reports of 9:16 face-detect failures)
- HF Spaces Docker SDK persistence: https://huggingface.co/docs/hub/spaces-config-reference
- Fish Speech long-input quality: https://github.com/fishaudio/fish-speech/discussions
- deep-translator rate limits: https://github.com/nidhaloff/deep-translator/issues
- RunPod cost-management threads: r/RunPod (Q1 2026)

> **Confidence note:** Pitfalls #1, #2, #5, #10 are HIGH confidence (general dev hygiene + well-documented HF Spaces patterns). #3, #4, #6, #7, #8 are MEDIUM (specific to our locked stack; should be re-validated during Plan-phase research per item).
