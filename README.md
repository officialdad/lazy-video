# lazy-video

Local pipeline: one long portrait screen-recording → folder of polished, branded vertical
reels. Zero manual editing.

Record a 9:16 tutorial (screen + webcam, mixed Bahasa Malaysia + English) → drop it in
`input/` → tell Claude Code **"edit this"** → finished reels land in `output/<name>/`.

The intelligence (where to cut, fixing captions, hook titles) is the LLM reading the
transcript. Remotion is only the final renderer — it does NOT decide cuts.

## Pipeline (4 stages, 1 command)

```
python run.py input/my-video.mp4
  ├─ Stage 1  transcribe   faster-whisper large-v3 (cuda)  -> transcript.json
  ├─ Stage 2  EDL          mechanical draft + LLM clean     -> edl.json  [you approve]
  ├─ Stage 3  cut          ffmpeg slice + remove flubs/silence -> clips/
  └─ Stage 4  render       Remotion: motion + captions + intro/outro -> reels
```

Output: `output/<video-name>/NN_<slug>.mp4`, one branded reel per micro-lesson.

## Requirements

- **ffmpeg** on PATH (tested 8.0.1)
- **Python 3.12** + [uv](https://docs.astral.sh/uv/) (deps in `pyproject.toml`)
- **Node** (tested 24) + Remotion deps in `remotion/`
- NVIDIA GPU for `whisper_device: cuda` (falls back to `cpu` in `config.json`)

## Setup

```bash
uv sync                       # python deps (faster-whisper + cuda libs)
cd remotion && npm install    # remotion deps
npx remotion browser ensure   # headless chrome for rendering
```

## Config

All tunables live in `config.json`. Key knobs:

| Key | Meaning |
|-----|---------|
| `marker_phrases` | spoken phrases that split lessons (one reel per segment) |
| `flub_word` | spoken re-take trigger; flub sentence is cut, clean take kept |
| `silence_threshold_sec` | gaps longer than this are trimmed (never mid-sentence) |
| `default_intensity` | `gentle` \| `medium` \| `hype` retention motion |
| `whisper_model` / `whisper_device` | transcription model + cuda/cpu |
| `output.*` | render resolution / fps / codec |
| `brand.*` | caption font/color/position, intro+outro assets, progress bar |

Per-episode you can override `intensity` on individual segments in the EDL.

## Drop-and-go

See [SKILL.md](SKILL.md) — drop a video, say "edit this", approve the EDL, get reels.

## Repo layout

```
src/        python pipeline (transcribe, edl, cut)
remotion/   remotion renderer (templates, motion, captions)
assets/     intro.mp4, outro.mp4, fonts  (placeholders included)
input/      drop videos here
output/     finished reels per video
config.json single source of tunables
run.py      one command, all 4 stages
SKILL.md    drop-and-go trigger doc
```
