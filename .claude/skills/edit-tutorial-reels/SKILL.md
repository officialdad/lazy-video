---
name: edit-tutorial-reels
description: Use when the user drops ANY video into input/ and says "edit this" (or "buat reels", "potong video ni"). Turns one dropped recording into branded vertical reels — one per micro-lesson for a marker-split tutorial, or a single reel for a promo/clip — with no manual editing. Claude crops non-9:16 input to portrait first. Mixed Bahasa Malaysia + English.
---

# Edit Tutorial Reels

**Drop any video, Claude edits it.** The user drops a recording in `input/`, says "edit
this", and you drive the pipeline to finished reels in `output/<video-name>/`. Two input
shapes: a marker-split tutorial → one reel per lesson; a marker-less clip (promo,
announcement) → ONE reel (a 1-segment EDL is normal, not a bug).

The intelligence is YOU: the crop window (Stage 0) and the transcript pass (Stage 2).
Remotion only renders.

## Trigger

User drops `input/<something>.mp4` (or `.mov`, any aspect ratio) and says any of: "edit
this", "buat reels", "potong jadi reels", "edit video ni".

## The one thing that makes this work

**Stage 2 is split: code drafts, you finalize.** `src/edl.py` produces a mechanical draft
(marker segmentation, flub/silence cuts, per-word caption timing). Then YOU rewrite it
into the approved `edl.json`. A pure-code pass cannot fix code-switched captions or write
hooks. Do not skip your pass.

## Steps

0. **Normalize to 9:16** (skip if already portrait). Probe:
   ```bash
   ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of default=noprint_wrappers=1 input/<video>.mp4
   ```
   Crop with HandBrakeCLI, judging the window from where the content sits (ask the user if
   unclear). Target width = `H * 9 / 16`, centered. Keep the audio. Example — 3440x1440
   ultrawide, centered content (`--crop top:bottom:left:right`, `(3440-810)/2 = 1315`):
   ```bash
   HandBrakeCLI -i input/<video>.mp4 -o cropped.mp4 --crop 0:0:1315:1315 \
     --non-anamorphic --encoder x264 --quality 20 --rate 30 --pfr --aencoder av_aac
   ```
   Back up the original, then place the cropped file at `input/<video>.mp4`.

1. **Transcribe + draft EDL.**
   ```bash
   uv run python run.py input/<video>.mp4
   ```
   Writes `output/<name>/transcript.json` + `edl.draft.json`, then STOPS for approval.

2. **LLM final pass.** Read both, write `output/<name>/edl.json` with `"stage": "final"`:
   - Fix transcription errors; restore technical terms (`cloud code` -> `Claude Code`).
   - **Preserve the BM/English mix exactly as spoken. Never translate.**
   - Each caption's `words: [{w, start, end}]` drives the karaoke reveal. Fix text in BOTH
     `text` and the matching `words` entry; KEEP each word's timing. If merging/splitting
     lines, keep words on the line they're spoken in.
   - Catch flub re-takes the keyword pass missed — trim to the clean take (`reason: "flub"`).
   - Write a scroll-stopping `title` + kebab-case `filename_slug` per segment. Empty
     `title` = no title overlay (reel starts cold).
   - **Cut with restraint.** Remove only genuine fumbles ("oops", wrong-clicks,
     lost-in-navigation), dead air, jarring zoom-ins. KEEP narrative browsing, opening
     interactions, and showcases — over-cutting reads as "too fast". Align cut spans to
     caption/word boundaries so audio doesn't chop mid-word.
   - Unsure of a mis-heard word? ASK the user (they're the speaker) — flag low-confidence
     words with timestamps.

3. **Show the EDL, get approval.** Summarize segments, cuts, guesses. Wait.

4. **Cut + render.** Re-run the same command; it sees the approved EDL and finishes:
   ```bash
   uv run python run.py input/<video>.mp4
   ```

5. **Hand back** the reels in `output/<name>/`.

## Iterate on the cut

The user watches and asks for tweaks — expected, not failure:

- **Wording** → edit caption `text` AND `words` (keep timing); re-cut+render.
- **Cut more/less** → adjust `cuts_to_remove` on word boundaries.
- **Ending cut too early** → a trailing silence cut is eating the tail; drop it and leave
  ~0.5–1s buffer after the last word.
- **Caption position** → `brand.caption_position` (`"NN%"` = box bottom edge; currently
  `20%`; don't go below ~20%, platform UI covers it).
- **Music volume** → `brand.bg_music_volume`.

EDL unchanged → **render-only** re-run: `uv run python -m src.render input/<video>.mp4`.
Speed flags: `--draft` (half-scale ~2x; re-run without it for the final), `--frames A-B`
(one range, e.g. `0-90` = first 3s), `--concurrency N`. **Close any media player holding
the output reel first** — on Windows it locks the file (`WinError 32`).

## Segments + transitions

- Marker phrase **"langkah seterusnya adalah …"** splits lessons; boundary = END of
  "adalah" (phrase stays as the reel's spoken lead-out).
- Every reel ends with a **swipe-left CTA card** (MDI icon via `@mdi/js` in
  `remotion/src/Reel.tsx`). Optional `brand.bg_music` loops under the reel.
- Reels start cold (no intro; drop your own `assets/intro.mp4` and set
  `brand.show_intro: true` to prepend it).
- Timeline: `content (drift + punch-in + karaoke captions) -> swipe CTA`.
- `intensity` is per-segment in the EDL: `gentle` (default) | `medium` | `hype`.

All other tunables: `config.json` (read it; never hardcode).

## Running stages individually (debugging)

```bash
uv run python -m src.transcribe input/<video>.mp4   # Stage 1
uv run python -m src.edl        input/<video>.mp4   # Stage 2 draft
uv run python -m src.cut        input/<video>.mp4   # Stage 3 (needs approved edl.json)
uv run python -m src.render     input/<video>.mp4   # Stage 4
```

## Notes

- First transcribe downloads large-v3 (~3GB) once.
- A tiny last "stub" segment = recording cut mid-lesson — tell the user.
