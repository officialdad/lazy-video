# lazy-video

Drop any video into `input/`, tell Claude Code **"edit this"**, get branded 9:16 reels in
`output/<name>/`. Zero manual editing.

> **New here?** Open Claude Code in this folder and say **"set me up"** — it detects your
> OS, installs the tools (with your permission), and configures everything. Prefer to do it
> by hand? See [Requirements](#requirements) + [Setup](#setup) below.

Built for portrait screen-recording tutorials, but it takes any input: non-9:16 video gets
cropped to portrait first, and a clip with no lesson markers becomes a single reel. Speech
in any language works — the pipeline preserves code-switched / mixed-language captions
instead of translating them.

The intelligence (crop window, where to cut, fixing captions, hook titles) is the LLM.
Remotion is only the renderer — it does not decide cuts.

## Pipeline

```
Stage 0   Claude crops non-9:16 input to portrait (HandBrakeCLI)   [only if needed]

uv run python run.py input/my-video.mp4
  ├─ 1 transcribe  faster-whisper (cuda, cpu fallback)    -> transcript.json
  ├─ 2 EDL         mechanical draft + LLM final pass       -> edl.json  [you approve]
  ├─ 3 cut         ffmpeg slice, remove flubs/silence      -> clips/
  └─ 4 render      Remotion: motion + karaoke captions + swipe CTA -> reels
```

Run once → pauses for EDL approval → run the same command again → finished reels
(`output/<name>/NN_<slug>.mp4`).

## Requirements

- **ffmpeg** + **HandBrakeCLI** on PATH
- **Python 3.12** + [uv](https://docs.astral.sh/uv/)
- **Node** + Remotion deps in `remotion/`
- NVIDIA GPU for `whisper_device: cuda` (set it to `cpu` in `config.json` otherwise)

## Setup

```bash
uv sync                        # python deps (faster-whisper + cuda libs)
cd remotion && npm install     # remotion deps
npx remotion browser ensure    # headless chrome (one-time)
```

## Config

All tunables live in `config.json`:

| Key | Meaning |
|-----|---------|
| `marker_phrases` | spoken lesson boundary — the phrase you say between lessons (boundary = end of phrase) |
| `flub_word` | spoken re-take trigger; flubbed take cut, clean take kept |
| `silence_threshold_sec` | trim dead-air gaps longer than this |
| `default_intensity` | `gentle` \| `medium` \| `hype` retention motion |
| `whisper_model` / `whisper_device` | e.g. large-v3, cuda/cpu |
| `output.*` | 1080x1920 H.264 30fps |
| `brand.*` | captions, CTA, intro, background music (below) |

Captions: karaoke word-by-word reveal, ALL CAPS in a configurable font (default Anton),
max 4 words on screen, positioned by `brand.caption_position` (raw `"NN%"` supported).
Reels start cold (no intro sting) and end on a **swipe-left CTA card** (MDI icon). Set
`brand.bg_music` to an audio file to loop it under the voice at `brand.bg_music_volume`
(empty = no music).

## Drop-and-go

See [the skill](.claude/skills/edit-tutorial-reels/SKILL.md): drop a video, say "edit
this", approve the EDL, get reels.

## Repo layout

```
src/        python pipeline (transcribe, edl, cut, render)
remotion/   renderer (Reel, Captions, motion)
assets/     caption font
input/      drop videos here
output/     finished reels per video
config.json single source of tunables
run.py      one command, all stages
```
