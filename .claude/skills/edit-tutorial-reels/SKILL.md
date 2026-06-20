---
name: edit-tutorial-reels
description: Use when the user drops a portrait tutorial recording into input/ and says "edit this" (or "buat reels", "potong video ni"). Turns ONE long 9:16 screen-recording into a folder of branded vertical reels, one per micro-lesson, with no manual editing. Mixed Bahasa Malaysia + English.
---

# Edit Tutorial Reels

Turn one long portrait recording into branded vertical reels. The user records a 9:16
tutorial (screen + webcam, mixed BM/English), drops it in `input/`, and says **"edit
this"**. You drive the 4-stage pipeline and hand back finished reels in
`output/<video-name>/`.

The intelligence is YOU reading the transcript (Stage 2). Remotion only renders.

## Trigger

User drops `input/<something>.mp4` (or `.mov`) and says any of: "edit this", "buat
reels", "potong jadi reels", "edit video ni".

## The one thing that makes this work

**Stage 2 is split: code drafts, you finalize.** `src/edl.py` produces a mechanical
draft (marker segmentation, flub/silence cuts, per-word caption timing). Then YOU rewrite
it into the approved `edl.json`. A pure-code pass cannot fix code-switched captions or
write hooks — that needs reading. Do not skip your pass.

## Steps

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
   - Sanity-check `cuts_to_remove`.
   - When unsure of a mis-heard word, ASK the user rather than guessing.

3. **Show the EDL and get approval.** Summarize segments, cuts, and any guesses (esp.
   mis-heard words). Wait for approval/corrections.

4. **Cut + render.** Re-run the same command; it sees the approved EDL and finishes:
   ```bash
   uv run python run.py input/<video>.mp4
   ```
   Produces `output/<name>/NN_<slug>.mp4`, one branded reel per segment.

5. **Hand back** the reels in `output/<name>/`.

## How segments + transitions work

- The user says the marker phrase **"langkah seterusnya adalah …"** between lessons. The
  boundary is the END of "adalah" (the phrase stays as the reel's spoken lead-out); the
  next reel starts at the next topic.
- Every reel ends with a **swipe-left CTA card** ("FOLLOW & STAY TUNED") that REPLACES the
  outro sting.
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
  screen at once, default 4; lower to 3 for strictly one row), color/position, `show_intro`
  (default false), intro asset, progress bar, and `cta` (text, swipe transition, duration).

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
