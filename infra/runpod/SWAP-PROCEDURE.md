# Pod Swap Procedure — `/workspace/` → `/workspace-v3/`

**Operator runbook for Phase 1 (D-01 / D-04).** Atomic, zero-downtime swap.
The currently running app at `/workspace/` stays untouched throughout. Only
after end-to-end validation passes do we point the launcher at the new layout.
Old `/workspace/` is retained until 1 real user session validates the swap.

> **Rollback at any point:** stop, leave `/workspace/` untouched, the v2 app
> keeps running. Nothing in this procedure mutates the live service until step 7.

---

## Prerequisites

- SSH access to the RunPod pod `beautiful_gray_tiger` (id `59gpkaggh964b0`).
- Git installed on the pod.
- The `claude/add-claude-skills-rmINY` branch is pushed to `origin` (it is — verified by `git push -u origin claude/add-claude-skills-rmINY`).

---

## Steps

### 1. SSH into the pod
```bash
ssh root@<pod-ssh-host>
```

### 2. Clone the repo into `/workspace-v3/`
```bash
cd /workspace
git clone -b claude/add-claude-skills-rmINY \
    https://github.com/tiagobignon6-blip/rapidex-ia.git \
    /workspace-v3
cd /workspace-v3
```

### 3. Install Python deps (supporting tools)
```bash
pip install -r requirements.txt
```
The pinned ML deps (`whisperx`, `fish-speech`, `demucs`, `deep-translator`, MuseTalk's torch matrix) are NOT yet in `requirements.txt`. **Step 4 below** brings them in from the running pod.

### 4. Bring the locked ML deps into `requirements.txt`

On the pod, dump the currently working pin set from the live env:
```bash
pip freeze | grep -iE 'whisperx|fish-speech|demucs|deep-translator|torch|ctranslate2|faster-whisper|moviepy' \
  > /tmp/locked-ml-deps.txt
cat /tmp/locked-ml-deps.txt
```

Append the relevant entries to `/workspace-v3/requirements.txt` (keep one entry per line, with `==` pin). Commit later.

### 5. Fill `scripts/models.manifest.json` with real URLs + SHA256s

For each model in the manifest (`whisperx-large-v3`, `fish-speech-v1.5`, `musetalk`, `wav2lip`, `demucs-htdemucs`):

```bash
# Find the existing weight file under /workspace/<engine>/
find /workspace/MuseTalk /workspace/Wav2Lip /workspace/fish-speech \
     -type f \( -name '*.pth' -o -name '*.ckpt' -o -name '*.safetensors' -o -name '*.bin' -o -name '*.th' \) \
     -exec ls -la {} \;

# For each found weight, compute SHA and copy to /workspace-v3/models/<dest_path>
sha256sum /workspace/MuseTalk/models/musetalk.pth
mkdir -p /workspace-v3/models/musetalk
cp /workspace/MuseTalk/models/musetalk.pth /workspace-v3/models/musetalk/
```

Edit `scripts/models.manifest.json` and replace each `"url": "TODO"` and `"sha256": "TODO"` with real values. URL can be a HuggingFace Hub URL (`https://huggingface.co/.../resolve/main/...`) or any reachable HTTP(S) endpoint. The fetcher only downloads when the file is missing — since you've copied the weights from `/workspace/`, the URL is just a rebuild-from-scratch fallback.

**Verify** the manifest:
```bash
python scripts/download_models.py --dry-run
# Expect: every model shows "[present]" status
```

### 6. Launch from the new layout (still NOT swapped — old service runs in parallel)

```bash
bash /workspace-v3/infra/runpod/startup.sh
```

Watch the boot log. Expect:
- `[boot] models ready in <N>s` (where N is small — under 5s if SHAs all matched)
- Gradio server starts
- `gradio.live` URL prints

Open the URL in a browser. Verify:
- The v2 UI renders (3 columns, premium dark theme, pipeline header 1→2→3→4→5).
- Identical look-and-feel to the current `/workspace/`-served URL.

### 7. End-to-end smoke test (still no swap — old service untouched)

Through the new `gradio.live` URL:
1. Upload a 5-second sample video.
2. Pick a language pair you've used before (e.g. PT→EN).
3. Click Transcribe & Translate. Confirm transcript appears.
4. Edit one word in the translated text.
5. Click Dub Video. Wait for completion.
6. Download the output mp4. Verify it plays + lips track.

**If any step fails**: stop here. Old service at `/workspace/` is still running. Investigate, fix in `/workspace-v3/`, re-run from step 6. No rollback needed because nothing was swapped.

### 8. Atomic swap of the launcher

This is the only step that touches the live service. It's a single file edit on whatever launches the app on pod boot (typically a systemd unit, a `~/.bashrc` line, or a RunPod template entrypoint).

Find the current launcher reference:
```bash
grep -rn '/workspace/startup.sh\|/workspace/app.py' /etc/systemd /root /workspace 2>/dev/null
```

Replace `/workspace/startup.sh` with `/workspace-v3/infra/runpod/startup.sh` in the appropriate file. Reload (e.g. `systemctl daemon-reload` if systemd).

The currently running Gradio process is unaffected — the launcher change only takes effect on the next pod boot or service restart.

### 9. Validate via 1 real user session (D-04 retention gate)

Wait for at least one real session by an actual user (could be you opening the app fresh and dubbing a real video) against the v3 path. Confirm:
- The pod boots into the new launcher cleanly after a restart.
- The app behaves identically to the v2 app from the user's perspective.
- No new errors in the logs.

### 10. Cleanup `/workspace/` (D-04 final step)

Only after step 9 passes:
```bash
# Backup the legacy launcher in case you want to inspect it later
cp /workspace/startup.sh /tmp/legacy-workspace-startup.sh.bak

# Remove the legacy directory tree
rm -rf /workspace/MuseTalk /workspace/Wav2Lip /workspace/fish-speech \
       /workspace/app.py /workspace/app.py.py /workspace/startup.sh
```

If you reused `/workspace/` for any other artifacts (notes, scratch), preserve those. The cleanup is targeted at the legacy app stack, not the entire `/workspace/` mount.

---

## Acceptance criteria for Phase 1 (pod-side)

- [ ] Step 6 produced a working `gradio.live` URL from `/workspace-v3/`.
- [ ] Step 7 round-tripped a 5-second sample video end-to-end.
- [ ] Step 8 launcher swap committed (or persisted in pod template).
- [ ] Step 9 — 1 real user session validated the new path.
- [ ] Step 10 — old `/workspace/` cleaned up.

When all 5 are checked, Phase 1 is done end-to-end. Reach out to Claude (next session) to advance to Phase 2 (`/gsd-plan-phase 2` → `app.py.py` → `app.py` rename + import rewrite).

---

## Notes

- This procedure assumes the pod has the same Python version + CUDA + system `ffmpeg` as the v2 setup. If `pip install -r requirements.txt` in step 3 fails, capture the error — likely a torch/cuda mismatch — and add the resolved pins to `requirements.txt` before continuing.
- If RunPod credit runs out mid-procedure, all state is recoverable from git. The old `/workspace/` is a backup until step 10.
