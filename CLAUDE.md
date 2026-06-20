# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local pipeline that turns ONE long portrait screen-recording into a folder of branded
vertical reels (one per micro-lesson), with no manual video editing. The user records a
9:16 tutorial (screen + webcam, mixed Bahasa Malaysia + English), drops it in `input/`,
and the pipeline produces finished reels in `output/<video-name>/`.

The approved design lives in
`docs/superpowers/specs/2026-06-20-ai-tutorial-reel-pipeline-design.md` — read it before
making architectural changes.

## The one architectural idea that matters

**Stage 2 (Edit Decision List) is split between code and the LLM. This is intentional and
load-bearing.** A pure-Python pass cannot fix code-switched captions, restore technical
terms, or write hook titles — that requires reading. So:

- `src/edl.py` does the **mechanical draft**: marker-phrase segmentation, flub-region
  detection, silence detection. It produces a draft EDL.
- **Claude (in-session)** does the **final pass**: fix transcription errors, restore terms
  (`cloud code` -> `Claude Code`), preserve the actual BM/English mix (never translate),
  write hook titles + filename slugs, sanity-check cut regions.
- The user approves the final `edl.json` **before** any cutting happens.

Remotion is ONLY the renderer. It never decides cuts. If you find yourself putting cut
logic in Remotion, stop — that belongs in the EDL.

## Pipeline stages (data flows through files, not memory)

Each stage reads/writes JSON or media under `output/<video-name>/`, so stages run
independently and are debuggable in isolation.

| Stage | Code | In | Out |
|-------|------|----|-----|
| 1 Transcribe | `src/transcribe.py` | video | `transcript.json` (words+segments) |
| 2 EDL | `src/edl.py` + LLM | `transcript.json` | `edl.json` (user-approved) |
| 3 Cut | `src/cut.py` | `edl.json` + video | `clips/NN_slug.mp4` |
| 4 Render | `remotion/` | `clips/` + caption cues | `NN_slug.mp4` |

`run.py` is the single entrypoint chaining all four (Stage 2 pauses for approval).

## Commands

Python deps are managed by **uv**; always invoke Python through it.

```bash
# Setup
uv sync                                    # python deps (faster-whisper + cuda libs)
cd remotion && npm install                 # remotion deps
cd remotion && npx remotion browser ensure # headless chrome (one-time)

# Run a single stage (modules, not scripts -- note the -m and package path)
uv run python -m src.transcribe input/video.mp4
uv run python -m src.transcribe input/video.mp4 --out output/video/transcript.json

# Full pipeline (once run.py exists)
uv run python run.py input/video.mp4

# Remotion
cd remotion && npm run dev      # studio (preview templates)
cd remotion && npm run render   # render a composition
```

There is no test suite yet. Validation is done by running a stage on a real clip and
inspecting its JSON/media output (per the incremental build order in the spec).

## Config

`config.json` at the repo root is the single source of all tunables; `src/config.py`
loads it and provides path/slug helpers. Do not hardcode any of these — read from config.

Key knobs: `marker_phrases` (lesson boundaries -> one reel each), `marker_keep_in_segment`
(keep the marker phrase as the reel's spoken lead-out), `flub_word` (re-take trigger),
`silence_threshold_sec`, `default_intensity` (`gentle`|`medium`|`hype` retention motion),
`whisper_model`/`whisper_device` (cuda with cpu fallback), `output.*` (render res/fps/codec),
`brand.*` (caption font/uppercase/color/position, intro asset, progress bar, `cta`).

Current locked values: marker `"langkah seterusnya adalah"` (boundary = end of the phrase),
flub `"redo"`, large-v3 on cuda (RTX 3090), 1080x1920 H.264 30fps. Captions: **Anton, bold,
ALL CAPS**, karaoke word-by-word reveal driven by per-word timestamps, capped at
`brand.caption_max_words` (default 4) per line so the on-screen word count stays steady
(whisper cues are split into balanced lines rather than shown whole). Every reel ends with
a **swipe-left CTA card** (`brand.cta`) that REPLACES the outro sting; `assets/outro.mp4` is
unused. The intro sting is **off by default** (`brand.show_intro: false`) so reels start
cold on the hook, like native reels. Default timeline: `content -> swipe CTA` (intro
prepended only when `show_intro` is true).

The skill lives at `.claude/skills/edit-tutorial-reels/SKILL.md` (must be under
`.claude/skills/` for Claude Code to auto-discover it — a root SKILL.md is not loaded).

## Environment notes

- faster-whisper runs on CUDA via the `nvidia-cudnn-cu12` / `nvidia-cublas-cu12` pip
  wheels (ctranslate2 finds the DLLs). `transcribe.py` falls back to cpu/int8 if cuda load
  fails. large-v3 (~3GB) downloads on first run.
- Transcription uses `language=None` (auto-detect) and `task="transcribe"` — never
  `translate`, to preserve the spoken BM/English mix.
- Windows: git warns LF->CRLF on commit; harmless.

## Working style for this repo

Follow the incremental build order in the spec — build one stage, run it on a real clip,
show the output, get approval, then move on. Do not build all stages at once. Pause and
ask before changing marker phrases, brand style, Whisper model, or encoding settings.
