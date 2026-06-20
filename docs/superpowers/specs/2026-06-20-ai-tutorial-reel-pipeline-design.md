# AI Tutorial Reel Pipeline — Design

**Date:** 2026-06-20
**Status:** Approved

## Goal

Turn ONE long portrait screen-recording into a folder of polished, branded vertical
reels with zero manual editing. Workflow: record 9:16 tutorial (screen + webcam, mixed
Bahasa Malaysia + English) → drop into repo → say "edit this" → get finished reels.

Packaged as a Claude Code skill (`SKILL.md`) so future videos are drop-and-go.

The "intelligence" (where to cut, fixing captions, hook titles) is the LLM reading the
transcript. Remotion is only the final renderer; it does NOT decide cuts.

## Input / Output Contract

- **Input:** single `.mp4`/`.mov`, portrait 9:16, one continuous recording containing
  several micro-lessons and possible re-take flubs.
- **Output:** `/output/<video-name>/` with one finished reel per micro-lesson, numbered
  and named from its hook title:
  ```
  01_apa-itu-claude-code.mp4
  02_install-claude-code.mp4
  03_sign-in-setup.mp4
  ```
- Each reel: 9:16, branded intro sting → content with animated captions → outro CTA,
  gentle retention motion baked in.

## Locked Config (config.json)

```jsonc
{
  "marker_phrases": ["langkah seterusnya"],   // lesson boundary -> new reel
  "flub_word": "redo",                          // re-take trigger
  "silence_threshold_sec": 0.4,
  "default_intensity": "gentle",
  "whisper_model": "large-v3",
  "whisper_device": "cuda",                     // RTX 3090, 24GB
  "whisper_compute_type": "float16",
  "output": {
    "width": 1080, "height": 1920, "fps": 30,
    "vcodec": "libx264", "acodec": "aac", "crf": 19
  },
  "brand": {
    "caption_font": "Inter",
    "caption_position": "bottom-third",
    "caption_color": "#ffffff",
    "caption_highlight_color": "#ffd400",
    "caption_bg": "rgba(0,0,0,0.55)",
    "intro_asset": "assets/intro.mp4",
    "outro_asset": "assets/outro.mp4",
    "show_progress_bar": true
  }
}
```

## Architecture — 4 Stages, 1 Command

```
run.py <video.mp4>
  |
  ├─ Stage 1  src/transcribe.py  faster-whisper large-v3 (cuda)
  |             -> output/<name>/transcript.json  (words + start + end, multilingual)
  ├─ Stage 2  src/edl.py (draft) + LLM (final)
  |             -> output/<name>/edl.json   [PAUSE for approval]
  ├─ Stage 3  src/cut.py  ffmpeg slice + remove cuts
  |             -> output/<name>/clips/NN_slug.mp4
  └─ Stage 4  remotion render  per clip + captions + title
                -> output/<name>/NN_slug.mp4
```

### Stage 1 — Transcribe
- `faster-whisper` `large-v3`, device `cuda`, compute `float16`.
- Multilingual; do NOT force-translate. Word-level timestamps.
- Output `transcript.json`: list of words `{word, start, end}` plus segment text.
- Risk: CUDA needs cuBLAS + cuDNN 9 DLLs on Windows — install `nvidia-cudnn-cu12` /
  `nvidia-cublas-cu12` wheels; fall back to `device=cpu` if unavailable.

### Stage 2 — Edit Decision List (the brain)
Split into mechanical + LLM passes:
- `edl.py` mechanical draft:
  - Segment by `marker_phrases` (case-insensitive, fuzzy spacing). Each marker =
    boundary; each segment = one reel.
  - Flub removal: find `flub_word` token → cut from start of *its* sentence up to and
    including the flub word; keep the clean retake. Sentence start = prior marker, prior
    silence gap, or Whisper punctuation.
  - Silence trim: gaps > 0.4s → `cuts_to_remove`, but never split inside a sentence
    (gentle = breathing room). Capped so beginner pacing survives.
- LLM final pass (in-session, approved by user):
  - Fix transcription errors, restore technical terms (`cloud code` → `Claude Code`),
    preserve actual BM/English mix (do NOT translate).
  - Write hook title + `filename_slug` per segment (short, scroll-stopping, my tone).
  - Sanity-check cut regions.
- Output `edl.json` per the schema below. User approves before cutting.

EDL schema:
```json
{
  "segments": [
    {
      "index": 1,
      "title": "Apa itu Claude Code?",
      "filename_slug": "apa-itu-claude-code",
      "start": 0.0,
      "end": 95.3,
      "cuts_to_remove": [
        {"start": 12.1, "end": 14.0, "reason": "flub"},
        {"start": 40.5, "end": 41.2, "reason": "silence"}
      ],
      "captions": [{"start": 0.4, "end": 2.1, "text": "Apa itu Claude Code?"}],
      "intensity": "gentle"
    }
  ]
}
```

### Stage 3 — Cut (ffmpeg)
- Keep-ranges = segment span minus `cuts_to_remove`.
- Re-encode (not stream-copy) for frame-accurate cuts; concat via filtergraph.
- One raw mp4 per segment → `output/<name>/clips/NN_slug.mp4`.

### Stage 4 — Render branded reels (Remotion)
- Each raw clip + caption cues + title → one finished reel.
- Retention motion (gentle default):
  - Continuous scale drift 1.0 → 1.05 over clip duration.
  - Spring punch-in 1.08 → 1.0 on each real cut boundary.
  - `intensity` knob per segment: `gentle` | `medium` | `hype`. Default `gentle`
    (calm beginner tutorial). `hype` = tighter/faster, optional fixed-interval punch-ins.
- Animated captions: locked brand style (Inter bold, bottom-third, white + dark pill,
  word-by-word highlight), word-/phrase-synced.
- Intro sting + outro CTA from placeholder assets (generated solid-color + text mp4s so
  pipeline runs end-to-end before real brand assets exist).
- Optional thin progress bar.
- Output 1080x1920 H.264 30fps, AAC, crf 19, mp4.

## Repo Structure

```
/src            # python pipeline: transcribe.py, edl.py, cut.py
/remotion       # remotion project: templates, motion, captions
/assets         # intro, outro, fonts
/input          # drop videos here
/output         # finished reels per video
config.json
run.py          # single CLI entrypoint, runs all 4 stages
SKILL.md        # so Claude Code re-runs this on future videos
README.md
```

## Tech Stack
- Python (managed by `uv`) for Stages 1–3: faster-whisper + ffmpeg orchestration.
- Node + Remotion for Stage 4.
- Single entrypoint `python run.py <video>` running all 4 stages end to end.
- All local. No paid SaaS. ffmpeg 8.0.1, Python 3.12, Node 24 confirmed present.

## Build Order (incremental, approve each)
1. Scaffold: dirs, uv env + deps, config.json, .gitignore (done), README, placeholder
   assets. Verify ffmpeg + faster-whisper(cuda) + remotion run.
2. Stage 1 → show transcript.json on a real clip.
3. Stage 2 → show EDL.
4. Stage 3 → cut raw clips.
5. Stage 4 → Remotion template (drift + punch-in + captions + intro/outro), render one reel.
6. Wire `python run.py`, write SKILL.md.

## SKILL.md Trigger Flow
User drops a video, says "edit this". Skill then: (1) transcribe, (2) generate draft EDL
+ LLM caption-fix/titling → show user to approve, (3) cut, (4) render, (5) drop reels in
`/output`. Document trigger, steps, config knobs, per-episode intensity adjustment.

## Out of Scope (v1)
- Content-aware zoom (zoom to clicked button).
- Auto-posting to social.
- Multi-speaker tracking / reframing (input already correct 9:16).

## Acceptance Test
Given a ~10-min portrait recording with 5 markers and 2 `redo` flubs, `python run.py`
produces 5 numbered branded reels in `/output/<name>/`, captions correct in mixed
BM/English with technical terms intact, flubs gone, dead air trimmed, every clip gentle
motion. No manual editing.

## Revision 2026-06-20b (approved)

Changes after the first working end-to-end build:

- **SKILL.md location.** Moved to `.claude/skills/edit-tutorial-reels/SKILL.md` so Claude
  Code auto-discovers it (a root `SKILL.md` is not loaded as a skill).
- **Marker + transition.** Marker phrase is now `"langkah seterusnya adalah"`; the boundary
  is the END of the phrase (`marker_keep_in_segment: true`), keeping it as the reel's spoken
  lead-out. Every reel ends with a **swipe-left CTA card** ("FOLLOW & STAY TUNED",
  `brand.cta`) that REPLACES the outro sting. `assets/outro.mp4` is now unused. Timeline:
  `intro -> content -> swipe CTA`.
- **Captions.** Font is **Anton, bold, ALL CAPS** (`caption_uppercase`). Reveal is
  **karaoke build-up**: words appear one-by-one at their spoken time (per-word timestamps
  carried transcript -> EDL -> cut remap -> Remotion), accumulating across the line, current
  word highlighted. EDL captions now include a `words: [{w, start, end}]` array; the LLM
  final pass edits word text while preserving timing.
- **Robustness.** `cut.py` clears stale clips and `render.py` clears stale reels so output
  always matches the current EDL (segment count can change between runs).
