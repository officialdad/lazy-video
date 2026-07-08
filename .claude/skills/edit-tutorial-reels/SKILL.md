---
name: edit-tutorial-reels
description: Use when the user drops ANY video into input/ and says "edit this" (or "buat reels", "potong video ni"). Turns one dropped recording into branded vertical reels — one per micro-lesson for a marker-split tutorial, or a single reel for a promo/clip — with no manual editing. Claude crops non-9:16 input to portrait first. Mixed Bahasa Malaysia + English.
---

# Edit Tutorial Reels

Turn one dropped video into branded vertical reels. The working model is **drop any video,
Claude edits it**: the user drops a recording in `input/`, says **"edit this"**, and you
drive the pipeline and hand back finished reels in `output/<video-name>/`. It doesn't have
to be a 9:16 tutorial — if the video is any other aspect ratio, you crop it to portrait
first (Stage 0 below).

The intelligence is YOU: cropping to the right frame (Stage 0) and reading the transcript
(Stage 2). Remotion only renders.

## Trigger

User drops `input/<something>.mp4` (or `.mov`, any aspect ratio) and says any of: "edit
this", "buat reels", "potong jadi reels", "edit video ni".

## Two input shapes

- **Multi-lesson tutorial** — the creator speaks the marker phrase between lessons → one
  reel per lesson.
- **Single clip** (promo, announcement, anything with no marker phrase) → ONE reel. A
  1-segment EDL is normal here, not a bug.

## The one thing that makes this work

**Stage 2 is split: code drafts, you finalize.** `src/edl.py` produces a mechanical
draft (marker segmentation, flub/silence cuts, per-word caption timing). Then YOU rewrite
it into the approved `edl.json`. A pure-code pass cannot fix code-switched captions or
write hooks — that needs reading. Do not skip your pass.

## Steps

0. **Normalize to 9:16 (only if the input isn't already portrait).** Probe it first:
   ```bash
   ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of default=noprint_wrappers=1 input/<video>.mp4
   ```
   If it's not 9:16, crop to portrait with HandBrakeCLI, choosing the crop window from where
   the content actually sits (ask the user if it's unclear — centered, off to a side, webcam
   corner). Target width for a 9:16 out of a `H`-tall source is `H * 9 / 16`, centered.
   Keep the audio (transcription needs it). Example — 3440x1440 ultrawide, centered content:
   ```bash
   HandBrakeCLI -i input/<video>.mp4 -o cropped.mp4 --crop 0:0:1315:1315 \
     --non-anamorphic --encoder x264 --quality 20 --rate 30 --pfr --aencoder av_aac
   ```
   (`--crop top:bottom:left:right`; `(3440-810)/2 = 1315` per side → 810x1440.) Back up the
   original, then put the cropped file at `input/<video>.mp4` so the rest of the pipeline
   uses it. If the video is already 9:16, skip this step.

1. **Transcribe + draft EDL.** Run:
   ```bash
   uv run python run.py input/<video>.mp4
   ```
   This does Stage 1 (transcribe) + Stage 2 draft, then STOPS for approval. It writes
   `output/<name>/transcript.json` and `output/<name>/edl.draft.json`.

2. **Do the LLM final pass.** Read `transcript.json` and `edl.draft.json`. Write
   `output/<name>/edl.json` with `"stage": "final"`:
   - Fix transcription errors; restore technical terms (`cloud code` -> `Claude Code`,
     `cloud pro` -> `Claude Pro`, etc.).
   - **Preserve the BM/English mix exactly as spoken. Never translate.**
   - **Each caption has a `words: [{w, start, end}]` array** driving the karaoke word
     reveal. When you fix a word's text, edit it in BOTH `text` and the matching `words`
     entry, and KEEP each word's `start`/`end` timing. If you merge/split caption lines,
     keep words assigned to the line they're spoken in.
   - Catch flub re-takes the keyword pass missed (a sentence restarted without the flub
     word) — trim to the clean take by adjusting the segment `start` or adding a
     `cuts_to_remove` entry with `reason: "flub"`.
   - Write a short scroll-stopping `title` per segment and a kebab-case `filename_slug`.
     (An empty `title` renders no title overlay — the reel starts cold on the content.)
   - **Cut with restraint.** Remove only genuine fumbles (wrong-clicks, "oops",
     lost-in-navigation), dead air, and jarring zoom-ins. KEEP the narrative browsing,
     opening interactions (e.g. someone replying the creator), and content showcases — over-
     cutting reads as "too fast / hard to follow." Align each `cuts_to_remove` span to
     caption/word boundaries so audio doesn't chop mid-word.
   - When unsure of a mis-heard word, ASK the user rather than guessing — the user is the
     speaker and is the ground truth. Flag low-confidence whisper words (with timestamp).

3. **Show the EDL and get approval.** Summarize segments, cuts, and any guesses (esp.
   mis-heard words). Wait for approval/corrections.

4. **Cut + render.** Re-run the same command; it sees the approved EDL and finishes:
   ```bash
   uv run python run.py input/<video>.mp4
   ```
   Produces `output/<name>/NN_<slug>.mp4`, one branded reel per segment.

5. **Hand back** the reels in `output/<name>/`.

## Iterate on the cut

The user watches and asks for tweaks — this is expected, not failure. Common ones and where
they live:

- **Wording** (a caption doesn't match what they said) → edit the caption `text` AND its
  `words` entries, keeping each word's timing; re-cut+render.
- **Cut more / less** (keep a beat, drop a fumble or zoom) → adjust `cuts_to_remove` on
  caption/word boundaries.
- **Ending cut too early** → the trailing silence cut may be eating the tail; drop that
  silence cut and/or leave a ~0.5–1s buffer after the last word.
- **Caption too high/low** → `brand.caption_position` (see knobs).
- **Music too loud/soft** → `brand.bg_music_volume` (see knobs).

Most tweaks are a config or EDL edit plus a **render-only** re-run
(`uv run python -m src.render input/<video>.mp4`) when the EDL is unchanged.
**Before re-rendering, make sure no media player has the output reel open** (on Windows a
player like MPC-HC locks the file and `render.py` fails with `WinError 32`); close it first.

Speed up the re-render while iterating (the render cost is per-frame video decode):
- `--draft` renders at half scale (~2x faster) — use it for pacing/wording/cut checks, then
  re-run WITHOUT `--draft` for the final (draft overwrites the reel at half res).
- `--frames A-B` renders only that frame range (e.g. `--frames 0-90` for the first 3s at
  30fps) — perfect for checking one changed spot like the ending or CTA.
- `--concurrency N` uses more cores (default is ~half). `--gl angle` barely helped here.

## How segments + transitions work

- The user says the marker phrase **"langkah seterusnya adalah …"** between lessons. The
  boundary is the END of "adalah" (the phrase stays as the reel's spoken lead-out); the
  next reel starts at the next topic.
- Every reel ends with a **swipe-left CTA card** ("FOLLOW & STAY TUNED") that REPLACES the
  outro sting. Its icon is an MDI glyph (`mdiGestureSwipeLeft` from `@mdi/js`) rendered as
  SVG in the highlight color — swap the import in `remotion/src/Reel.tsx` for a different one.
- Optional background music plays under the whole reel (looped, fade in/out) when
  `brand.bg_music` is set.
- Reels start cold on the content (no intro sting by default — set `brand.show_intro: true`
  to prepend `assets/intro.mp4`).
- Default reel timeline: `content (drift + punch-in + karaoke captions) -> swipe CTA`.

## Config knobs (config.json)

All tunables live in `config.json`. Read them; don't hardcode.

- `marker_phrases` — spoken lesson boundaries (currently `["langkah seterusnya adalah"]`).
- `marker_keep_in_segment` — keep the marker phrase as the reel's lead-out (true).
- `flub_word` — re-take trigger (currently `"redo"`).
- `silence_threshold_sec` — dead-air gaps longer than this are trimmed (never
  mid-sentence).
- `default_intensity` — `gentle` | `medium` | `hype` retention motion.
- `whisper_model` / `whisper_device` — `large-v3` on `cuda` (cpu fallback).
- `output.*` — render resolution / fps / codec (1080x1920 H.264 30fps).
- `brand.*` — caption font (`Anton`), `caption_uppercase`, `caption_max_words` (words on
  screen at once, default 4; lower to 3 for strictly one row), color, `show_intro`
  (default false), intro asset, progress bar, and `cta` (text, swipe transition, duration).
- `brand.caption_position` — a named preset (`bottom-third`) OR a raw `"NN%"` for the caption
  box's bottom edge (percent of height; currently `"20%"`). Lower % = lower on screen; don't
  go below ~20% or the platform's own UI covers it.
- `brand.bg_music` / `brand.bg_music_volume` — optional background track under the reel
  (looped, fade in/out), linear volume kept well under the voice (currently
  `input/Le Freak - RAGE.mp3` at `0.075`). Empty `bg_music` = no music.

### Adjusting intensity per episode

`intensity` is per-segment in `edl.json`. Default `gentle`. Bump a punchy segment to
`medium`, or the whole reel to `hype` (tighter, faster, fixed-interval punch-ins). Edit
the segment's `intensity` before the cut+render step.

## Running stages individually (debugging)

```bash
uv run python -m src.transcribe input/<video>.mp4   # Stage 1
uv run python -m src.edl        input/<video>.mp4   # Stage 2 draft
uv run python -m src.cut        input/<video>.mp4   # Stage 3 (needs approved edl.json)
uv run python -m src.render     input/<video>.mp4   # Stage 4
```

## Notes

- First transcribe downloads large-v3 (~3GB) once.
- A tiny last "stub" segment means the recording was cut mid-lesson — tell the user.
- Brand assets in `assets/intro.mp4` are placeholders; swap in a real one any time (no
  code change). `assets/outro.mp4` is currently unused (CTA card replaces it).
