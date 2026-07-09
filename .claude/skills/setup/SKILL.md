---
name: setup
description: Use when a new user wants to set up / install / get started with this repo after cloning — "set me up", "install the tools", "getting started", "onboard me". Detects the platform, installs the missing tools (ffmpeg, HandBrakeCLI, uv, Node) with the user's permission, runs project setup, and verifies. Do NOT install NVIDIA drivers/CUDA.
---

# Setup (guided onboarding)

Walk a fresh clone to a working pipeline. **Detect what's missing, ASK before installing,
install with the native package manager, then verify.** Never touch GPU drivers/CUDA.

## Steps

1. **Detect platform** and pick the package manager:
   - Windows → `winget`
   - macOS → `brew` (if absent, point to https://brew.sh)
   - Linux → `apt` / `dnf` / `pacman` (whichever exists)

2. **Check what's already there** — run each, note the misses:
   ```bash
   ffmpeg -version        # ffmpeg
   HandBrakeCLI --version # HandBrakeCLI
   uv --version           # uv (also manages Python 3.12 — no separate Python install)
   node -v && npm -v      # Node
   ```

3. **Show the gap and ASK permission** before installing anything. List exactly what you'll
   install and the commands. Wait for a yes.

4. **Install the missing tools.** Package names below; if an ID is stale, `search` the
   manager instead of guessing (e.g. `winget search handbrake`).

   | Tool | Windows (winget) | macOS (brew) | Linux (apt) |
   |------|------------------|--------------|-------------|
   | ffmpeg | `Gyan.FFmpeg` | `ffmpeg` | `ffmpeg` |
   | HandBrakeCLI | `HandBrake.HandBrake.CLI` | `handbrake` | `handbrake-cli` |
   | uv | `astral-sh.uv` | `uv` | *(script: `curl -LsSf https://astral.sh/uv/install.sh \| sh`)* |
   | Node | `OpenJS.NodeJS.LTS` | `node` | `nodejs npm` |

   On Windows, a freshly `winget`-installed binary may not be on PATH until a **new shell** —
   if a just-installed tool isn't found, tell the user to reopen Claude Code (or open a new
   terminal) and re-run this.

5. **Run project setup:**
   ```bash
   uv sync                                    # python deps (fetches Python 3.12 if needed)
   cd remotion && npm install                 # remotion deps
   cd remotion && npx remotion browser ensure # headless chrome (one-time)
   ```

6. **GPU check.** Run `nvidia-smi`. If it fails (no NVIDIA GPU), edit `config.json`:
   `whisper_device` → `"cpu"`, `whisper_compute_type` → `"int8"`. With a GPU, leave the
   `cuda`/`float16` defaults — the CUDA libs come from `uv sync`, no driver install needed.

7. **Verify** (light — don't trigger the 3GB model download here):
   ```bash
   uv run python -c "import faster_whisper; print('whisper ok')"
   ffmpeg -version | head -1
   HandBrakeCLI --version
   node -v
   ```
   All four succeed → done.

8. **Hand off:** tell the user to drop a video in `input/` and say **"edit this"** — that
   fires the `edit-tutorial-reels` skill. First transcribe downloads the Whisper model
   (~3GB) once. Point them at `config.json` to set `marker_phrases` (their spoken
   lesson-boundary phrase) and the `brand.*` look.
