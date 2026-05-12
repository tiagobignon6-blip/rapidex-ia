# Local Runtime — RAPIDEX IA

Run the full RAPIDEX IA pipeline on your own machine (WSL2 + NVIDIA GPU) using Docker Compose, or as a bare WSL2 process. Two modes — Compose (recommended) or bare-shell — share the same entrypoint script and the same env-driven runtime profile.

## Prerequisites

| Requirement | Why | Verify |
|---|---|---|
| WSL2 (Ubuntu 22.04 recommended) | Linux runtime for Docker + NVIDIA passthrough | `wsl -l -v` from PowerShell shows `Ubuntu` with `Version 2` |
| NVIDIA driver on Windows host | GPU passthrough into WSL2 | `nvidia-smi` inside WSL2 reports your GPU |
| Docker Desktop with WSL2 backend | Compose v2 + Linux container engine | `docker --version` and `docker compose version` |
| `nvidia-container-toolkit` (in the WSL2 distro) | Lets Compose see the GPU | `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi` |
| Disk: ~15 GB free | Model weights (~6 GB) + container layers | `df -h ~` |

If `nvidia-container-toolkit` is missing inside WSL2:

```bash
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker  # or restart Docker Desktop from Windows
```

## First-time setup (Compose, recommended)

```bash
cd /mnt/c/Users/jow/code/rapidex-ia   # or wherever you cloned
cp .env.example .env                  # edit if you need non-defaults

docker compose -f infra/local/docker-compose.yml up --build
```

What happens on first boot:

1. Compose builds the `rapidex-ia:local` image (~5–10 min, dominated by the PyTorch wheel pull).
2. `start.sh` clones MuseTalk + Wav2Lip + fish-speech into `./models/<engine>/src/` and symlinks the entrypoint scripts where `pipeline/lipsync.py` expects them.
3. `scripts/download_models.py` fetches the 5 model weights (~6 GB) into `./models/`. On first run each weight prints its observed SHA256 — paste those back into `scripts/models.manifest.json` in a follow-up commit to enable strict verification on subsequent boots.
4. Gradio launches on `http://localhost:7860`.

Subsequent boots reuse the cached image, the cloned ML libs, and the cached weights. Boot time should be < 30 seconds (`[boot] models ready in Ns`).

## CPU-only UI mode (no GPU available)

Useful for iterating on the UI / theme / aspect logic without burning GPU time. The dub step will fail loudly with a friendly `gr.Error` — that's by design.

```bash
# Bare-shell, no Docker:
cd /mnt/c/Users/jow/code/rapidex-ia
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
RAPIDEX_DEVICE=cpu python app.py
```

Then open `http://localhost:7860`. The "Transcribe & Translate" button works (slowly) on CPU; the "Dub Video" button raises `GPU required: Fish Speech V1.5 needs CUDA`.

## Troubleshooting

### `docker compose up` fails with `could not select device driver "nvidia"`
NVIDIA Container Toolkit isn't wired up. Run the install snippet under Prerequisites, restart Docker, retry.

### Gradio loads but transcription returns empty / garbage text
Likely a PyTorch + ctranslate2 + faster-whisper version mismatch (Pitfall #3 in `.planning/research/PITFALLS.md`). Inside the container: `pip show ctranslate2 faster-whisper torch` and compare against the pins in `requirements.txt`. If they drifted, rebuild with `--no-cache`.

### `[boot] models ready in 0s` but the container still hangs
Model weights downloaded but the from-git clones failed silently. Check container logs for the `clone_or_skip` lines. Most likely your network blocks github.com or HuggingFace; configure a proxy or use a VPN.

### Compose says GPU has 0 capabilities
Restart Docker Desktop from Windows, not from inside WSL2. The WSL2-side `systemctl restart docker` only restarts the dockerd in the distro, which isn't the engine Compose talks to.

## Next steps

- After first successful boot, paste the observed SHA256 values into `scripts/models.manifest.json` and commit. Future boots will enforce verification.
- Phase 3 (theme tokens), Phase 4 (logo), Phase 5 (aspect detection) all work fine in CPU-only UI mode — no need to keep the GPU container running during UI iteration.
- The HF Spaces image (Phase 10) reuses ~90% of `infra/local/Dockerfile`. When that lands, this README gets a sibling at `infra/hfspaces/README.md`.
