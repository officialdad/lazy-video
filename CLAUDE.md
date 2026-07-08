# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local pipeline that turns ONE dropped video into a folder of branded vertical reels,
with no manual video editing. It began as a tool for 9:16 screen+webcam tutorials (mixed
Bahasa Malaysia + English) split into one reel per micro-lesson — but the working model is
now **drop any video, Claude edits it**: the user drops any recording in `input/`, Claude
normalizes it to 9:16 if needed, and the pipeline produces finished reels in
`output/<video-name>/`.

Two input shapes, both supported:
- **Multi-lesson tutorial** — the creator speaks a marker phrase between lessons, so the
  EDL splits it into one reel per lesson.
- **Single clip** — a promo, announcement, or any recording with no marker phrase becomes
  ONE reel. This is common; a 1-segment EDL is not an error.

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
| 0 Normalize | **Claude** + HandBrakeCLI/ffmpeg | any-aspect video | 9:16 `input/<name>.mp4` |
| 1 Transcribe | `src/transcribe.py` | video | `transcript.json` (words+segments) |
| 2 EDL | `src/edl.py` + LLM | `transcript.json` | `edl.json` (user-approved) |
| 3 Cut | `src/cut.py` | `edl.json` + video | `clips/NN_slug.mp4` + `clips/NN_slug.captions.json` |
| 4 Render | `src/render.py` -> `remotion/` | `clips/` + per-clip `captions.json` | `NN_slug.mp4` |

**Stage 0 is Claude-driven, not a code module** — it only runs when the dropped video
isn't already 9:16. Claude probes the video (`ffprobe`), decides the crop window from where
the content actually sits (centered, off to one side, webcam placement), and runs
HandBrakeCLI to crop to portrait, keeping the audio (transcription needs it). The crop is
per-video judgment, so it stays in Claude's hands rather than in code. Example: a
3440x1440 ultrawide with centered content → `HandBrakeCLI --crop 0:0:1315:1315` (top:bottom:
left:right) → 810x1440, an exact 9:16 that scales cleanly to 1080x1920 at render. Back up
the original before overwriting `input/<name>.mp4` with the cropped version.

`run.py` is the single entrypoint chaining all four. It is **state-aware**: it runs Stage 1
+ Stage 2 draft, then STOPS for the LLM final pass + user approval; re-running the same
command sees the approved `edl.json` (`"stage": "final"`) and continues to cut + render.

`src/cut.py` clears stale clips and `src/render.py` clears stale reels each run, so output
always matches the current EDL when the segment count changes.

## Commands

Python deps are managed by **uv**; always invoke Python through it.

```bash
# Setup
uv sync                                    # python deps (faster-whisper + cuda libs)
cd remotion && npm install                 # remotion deps
cd remotion && npx remotion browser ensure # headless chrome (one-time)

# Run a single stage (modules, not scripts -- note the -m and package path)
uv run python -m src.transcribe input/video.mp4   # Stage 1
uv run python -m src.edl        input/video.mp4   # Stage 2 draft (edl.draft.json)
uv run python -m src.cut        input/video.mp4   # Stage 3 (needs approved edl.json)
uv run python -m src.render     input/video.mp4   # Stage 4

# Full pipeline: run once -> pauses for EDL approval -> Claude writes edl.json
# (stage: final) -> user approves -> run the SAME command again to cut + render.
uv run python run.py input/video.mp4
uv run python run.py input/video.mp4 --stage transcribe|edl|cut|render|all

# Remotion (preview only; renders go through src/render.py)
cd remotion && npm run dev          # studio
cd remotion && npx remotion compositions   # validate the bundle builds

# Faster renders while iterating (render bottleneck is per-frame VIDEO DECODE, not bundle)
uv run python -m src.render input/video.mp4 --draft --concurrency 24  # half-scale, ~2x faster
uv run python -m src.render input/video.mp4 --frames 0-90             # only the first 3s (30fps)
uv run python -m src.render input/video.mp4 --concurrency 24          # use more of the cores
# --draft overwrites the reel at half res; re-run WITHOUT --draft for the final.
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
`brand.*` (caption font/uppercase/color/position, intro asset, progress bar, `cta`,
optional `bg_music`/`bg_music_volume`).

Current locked values: marker `"langkah seterusnya adalah"` (boundary = end of the phrase),
flub `"redo"`, large-v3 on cuda (RTX 3090), 1080x1920 H.264 30fps. Captions: **Anton, bold,
ALL CAPS**, karaoke word-by-word reveal driven by per-word timestamps, capped at
`brand.caption_max_words` (default 4) per line so the on-screen word count stays steady
(whisper cues are split into balanced lines rather than shown whole). Every reel ends with
a **swipe-left CTA card** (`brand.cta`) that REPLACES the outro sting; `assets/outro.mp4` is
unused. The intro sting is **off by default** (`brand.show_intro: false`) so reels start
cold on the hook, like native reels. Default timeline: `content -> swipe CTA` (intro
prepended only when `show_intro` is true).

Newer brand knobs (all live in `config.json`, tuned by re-rendering — never hardcode):
- `brand.caption_position` accepts a named preset (`bottom-third`) OR a raw `"NN%"` giving
  the caption box's bottom edge as a percent of height (currently `"20%"`). Lower % sits
  lower; don't go below ~20% or the platform's own UI (username, buttons) covers it. The
  `"NN%"` path is handled in `remotion/src/Captions.tsx`.
- `brand.bg_music` (path, currently `input/Le Freak - RAGE.mp3`) plays under the whole reel,
  looped, with a short fade in/out, at `brand.bg_music_volume` (linear, currently `0.075` —
  kept well under the voice). Empty `bg_music` = no music. Wired via a Remotion `<Audio>` in
  `Reel.tsx`; `render.py` stages the file into the render public dir as `bgm.<ext>`.
- The CTA card's icon is an MDI glyph rendered as SVG (`mdiGestureSwipeLeft` from `@mdi/js`)
  in the highlight color — swap the import in `remotion/src/Reel.tsx` for a different icon.

The skill lives at `.claude/skills/edit-tutorial-reels/SKILL.md` (must be under
`.claude/skills/` for Claude Code to auto-discover it — a root SKILL.md is not loaded).

## Environment notes

- faster-whisper runs on CUDA via the `nvidia-cudnn-cu12` / `nvidia-cublas-cu12` pip
  wheels. On Windows those DLLs are NOT on the search path by default — `config.add_cuda_dll_dirs()`
  registers `site-packages/nvidia/*/bin` (add_dll_directory + PATH) before the model loads;
  `transcribe.py` calls it and falls back to cpu/int8 if cuda load still fails. large-v3
  (~3GB) downloads on first run.
- Transcription uses `language=None` (auto-detect) and `task="transcribe"` — never
  `translate`, to preserve the spoken BM/English mix.
- EDL captions carry per-word timing (`words: [{w, start, end}]`) from `transcript.json`;
  `cut.py` remaps both cue and word times to clip-local; Remotion drives the karaoke reveal
  off them. The LLM final pass edits word text but must keep each word's timing.
- `src/render.py` renders via a small per-render staging dir as Remotion's `--public-dir`
  (the clip + intro + `bg_music` copied in, referenced by basename) — do NOT point
  `--public-dir` at the repo root, or Remotion copies all of `node_modules` (~3GB) every
  render.
- Remotion deps include `@mdi/js` (Material Design Icon path data) for the CTA glyph.
- **Render perf:** the bottleneck is per-frame video decode, not bundling (~4s, webpack-cached).
  `render.py` probes each clip and sets the `coverBg` prop false when the clip already fills
  the 9:16 frame, so `Reel.tsx` skips the blurred background layer — that hidden second decode
  was ~40% of render time. Iteration flags on `src/render.py`: `--draft` (`--scale=0.5`, ~2x),
  `--frames A-B` (render one range), `--concurrency N` (default ~half the cores), `--gl angle`
  (GPU; negligible here). `npx remotion benchmark` finds the best concurrency for the machine.
- **NVENC (GPU encode) is NOT enabled** and default `--hwaccel disable`. Remotion 4.0.486
  supports NVENC on Windows, but only via an external ffmpeg passed with `--binaries-directory`
  (its bundled ffmpeg has no `h264_nvenc`). The catch: that ffmpeg also needs `libfdk_aac`
  (Remotion's audio path uses it), and common Windows nvenc builds (chocolatey/gyan) omit it —
  so a merged dir fails on audio encode. A BtbN "nonfree" ffmpeg (nvenc + libfdk_aac) in a dir
  alongside Remotion's `remotion.exe` would work: `--hwaccel required --binaries-directory <dir>`
  (or set `render_binaries_dir` in config.json). Low ROI — NVENC only speeds the encode
  (~10s), not the decode-bound frame render, so it's left off.
- **Stage 0 crop** uses HandBrakeCLI (on PATH via WinGet); `ffprobe`/`ffmpeg` (chocolatey)
  are used for probing and cutting.
- **Output file lock (Windows):** a media player holding a rendered reel open (e.g. MPC-HC)
  locks the file, so `render.py`'s stale-reel `unlink()` fails with `PermissionError:
  [WinError 32]`. Close the player before re-rendering (a `Stop-Process` on the player, or
  ask the user). Re-rendering is cheap — after a wording/knob tweak, run just
  `uv run python -m src.render input/<video>.mp4` (skip re-cut) once the EDL is unchanged.
- Windows: git warns LF->CRLF on commit; harmless.

## Working style for this repo

Follow the incremental build order in the spec — build one stage, run it on a real clip,
show the output, get approval, then move on. Do not build all stages at once. Pause and
ask before changing marker phrases, brand style, Whisper model, or encoding settings.

Editing a reel is iterative: crop (if needed) → transcribe → your EDL final pass → user
approval → cut+render → the user watches and asks for tweaks (exact caption wording, which
fumbles to cut, caption position, music volume, ending buffer). Default to restraint —
cut only genuine fumbles and dead air, keep the narrative and any interaction/showcase
beats — and confirm low-confidence transcription words with the speaker rather than
guessing. Most tweaks are a config or EDL edit + a render-only re-run.
