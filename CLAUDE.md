# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local pipeline: the user drops ANY video in `input/`, says "edit this", and gets branded
9:16 reels in `output/<video-name>/` with no manual editing. Two input shapes:

- **Multi-lesson tutorial** — a spoken marker phrase between lessons → one reel per lesson.
- **Single clip** — promo/announcement with no marker → ONE reel (a 1-segment EDL is
  normal, not an error).

Non-9:16 input is cropped to portrait first (Stage 0). Speech is mixed Bahasa Malaysia +
English. The approved design lives in
`docs/superpowers/specs/2026-06-20-ai-tutorial-reel-pipeline-design.md` — read it before
architectural changes.

## The one architectural idea that matters

**Stage 2 (Edit Decision List) is split between code and the LLM. This is intentional and
load-bearing.** A pure-Python pass cannot fix code-switched captions, restore technical
terms, or write hook titles — that requires reading. So:

- `src/edl.py` does the **mechanical draft**: marker-phrase segmentation, flub-region
  detection, silence detection.
- **Claude (in-session)** does the **final pass**: fix transcription errors, restore terms
  (`cloud code` -> `Claude Code`), preserve the BM/English mix (never translate), write
  hook titles + filename slugs, sanity-check cut regions.
- The user approves the final `edl.json` **before** any cutting happens.

Remotion is ONLY the renderer. It never decides cuts. If you find yourself putting cut
logic in Remotion, stop — that belongs in the EDL.

## Pipeline stages (data flows through files, not memory)

Each stage reads/writes JSON or media under `output/<video-name>/`, so stages run and
debug independently.

| Stage | Code | In | Out |
|-------|------|----|-----|
| 0 Normalize | **Claude** + HandBrakeCLI | any-aspect video | 9:16 `input/<name>.mp4` |
| 1 Transcribe | `src/transcribe.py` | video | `transcript.json` (words+segments) |
| 2 EDL | `src/edl.py` + LLM | `transcript.json` | `edl.json` (user-approved) |
| 3 Cut | `src/cut.py` | `edl.json` + video | `clips/NN_slug.mp4` + `.captions.json` |
| 4 Render | `src/render.py` -> `remotion/` | `clips/` + captions | `NN_slug.mp4` |

**Stage 0 is Claude-driven, not a code module** — only runs when input isn't 9:16. Probe
with `ffprobe`, judge the crop window from where the content sits (ask if unclear), crop
with HandBrakeCLI keeping audio, back up the original, put the cropped file at
`input/<name>.mp4`. Example: 3440x1440 ultrawide, centered → `--crop 0:0:1315:1315`
(top:bottom:left:right) → 810x1440, exact 9:16.

`run.py` chains all stages and is **state-aware**: first run does Stage 1 + Stage 2 draft
then STOPS for the LLM final pass + user approval; re-running with an approved `edl.json`
(`"stage": "final"`) continues to cut + render. `cut.py`/`render.py` clear stale outputs
each run.

## Commands

Python deps are managed by **uv**; always invoke Python through it.

```bash
# Setup
uv sync                                    # python deps (faster-whisper + cuda libs)
cd remotion && npm install                 # remotion deps
cd remotion && npx remotion browser ensure # headless chrome (one-time)

# Single stage (modules -- note the -m)
uv run python -m src.transcribe input/video.mp4   # Stage 1
uv run python -m src.edl        input/video.mp4   # Stage 2 draft (edl.draft.json)
uv run python -m src.cut        input/video.mp4   # Stage 3 (needs approved edl.json)
uv run python -m src.render     input/video.mp4   # Stage 4

# Full pipeline (run once -> approval pause -> run again to cut + render)
uv run python run.py input/video.mp4
uv run python run.py input/video.mp4 --stage transcribe|edl|cut|render|all

# Faster renders while iterating (bottleneck = per-frame video decode, not bundling)
uv run python -m src.render input/video.mp4 --draft --concurrency 24  # half-scale, ~2x
uv run python -m src.render input/video.mp4 --frames 0-90             # one range only
# --draft overwrites the reel at half res; re-run WITHOUT it for the final.

# Remotion (preview only; renders go through src/render.py)
cd remotion && npm run dev
```

No test suite. Validate by running a stage on a real clip and inspecting its output.

## Config

`config.json` is the single source of all tunables; `src/config.py` loads it. Never
hardcode — read from config.

- `marker_phrases` (`["langkah seterusnya adalah"]`, boundary = end of phrase),
  `marker_keep_in_segment` (phrase stays as the reel's lead-out), `flub_word` (`"redo"`),
  `silence_threshold_sec`, `default_intensity` (`gentle`|`medium`|`hype`).
- `whisper_model`/`whisper_device`: large-v3 on cuda (RTX 3090), cpu fallback.
- `output.*`: 1080x1920 H.264 30fps.
- Captions: **Anton, ALL CAPS**, karaoke word-by-word reveal from per-word timestamps,
  `brand.caption_max_words` (4) per line. `brand.caption_position` takes a preset
  (`bottom-third`) or raw `"NN%"` = caption box bottom edge (currently `"20%"`; don't go
  below ~20% — platform UI covers it).
- Every reel ends with a **swipe-left CTA card** (`brand.cta`); its icon is an MDI SVG
  (`mdiGestureSwipeLeft` from `@mdi/js` in `remotion/src/Reel.tsx`). `assets/outro.mp4`
  unused. Intro sting off by default (`brand.show_intro: false`) — reels start cold.
  Timeline: `content -> swipe CTA`.
- `brand.bg_music` + `brand.bg_music_volume` (currently `input/Le Freak - RAGE.mp3` at
  `0.075`): looped under the whole reel with fade in/out, kept well below the voice.
  Empty = no music.

The skill lives at `.claude/skills/edit-tutorial-reels/SKILL.md` (must be under
`.claude/skills/` to be auto-discovered).

**EDL contract is enforced mechanically**: `src/validate_edl.py` checks every approved
`edl.json` (stage final, kebab slug, cuts sorted/in-span, non-empty karaoke `words`,
`text` == joined words). It runs as a PostToolUse hook (`.claude/settings.json`) the
moment an `edl.json` is written, and again in `cut.py` before cutting — script-written
EDLs are gated too. Exit 2 feeds the errors back; fix the EDL, don't bypass the check.

## Environment notes

- faster-whisper on CUDA needs the `nvidia-cudnn-cu12`/`nvidia-cublas-cu12` wheel DLLs on
  the search path — `config.add_cuda_dll_dirs()` registers them before model load;
  `transcribe.py` falls back to cpu/int8. large-v3 (~3GB) downloads on first run.
- Transcription uses `language=None` + `task="transcribe"` — never `translate` (preserves
  the BM/English mix).
- EDL captions carry per-word timing (`words: [{w, start, end}]`); `cut.py` remaps cue and
  word times to clip-local; Remotion drives the karaoke reveal off them. The LLM final
  pass edits word text but must keep each word's timing.
- `src/render.py` uses a small per-render staging dir as Remotion's `--public-dir` (clip +
  intro + bg music, referenced by basename). Never point `--public-dir` at the repo root —
  Remotion would copy all of `node_modules` every render.
- **Render perf:** `render.py` skips the blurred cover-bg layer (`coverBg` prop) when the
  clip already fills the 9:16 frame — that hidden second decode was ~40% of render time.
  Iteration flags: `--draft`, `--frames A-B`, `--concurrency N` (default ~half the cores).
  A ~90s reel renders in ~85s full / ~45s draft.
- **NVENC (GPU encode) is off** (`--hwaccel disable` default): Remotion's bundled ffmpeg
  lacks `h264_nvenc`, and no prebuilt Windows ffmpeg has both nvenc and the `libfdk_aac`
  Remotion requires. Plumbing (`--hwaccel`, `--binaries-directory`) exists if a from-source
  ffmpeg is ever supplied; the gain would only be ~10s of encode anyway.
- **Windows file lock:** a media player (e.g. MPC-HC) holding a rendered reel open makes
  `render.py` fail with `WinError 32`. Close the player before re-rendering.
- Windows: git warns LF->CRLF on commit; harmless.

## Working style for this repo

Build one stage, run it on a real clip, show output, get approval, move on. Pause and ask
before changing marker phrases, brand style, Whisper model, or encoding settings.

Editing a reel is iterative: crop (if needed) → transcribe → EDL final pass → user
approval → cut+render → user watches and asks for tweaks (wording, cuts, caption position,
music volume, ending buffer). **Default to restraint** — cut only genuine fumbles and dead
air, keep narrative/interaction/showcase beats — and confirm low-confidence transcription
words with the speaker instead of guessing. Most tweaks are a config or EDL edit + a
render-only re-run.
