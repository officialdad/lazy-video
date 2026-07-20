# Mini PC build timelapse — design

Date: 2026-07-20
Status: approved (design), not yet implemented

## Goal

Turn ~30 min of unedited 4K footage in `input/mini-pc/` into **two** finished 9:16 reels
of the same story — unboxing a mini PC, opening the case, installing RAM + SSD — ending
on a photo of the finished machine booting CachyOS. The two versions differ only in
background music and the timing grid that music implies.

There is **no narration**. This is the pipeline's first music-driven, speech-free reel, so
Stage 1 (Whisper) is skipped entirely and the EDL is written by hand.

## Source material

| file | duration | container | notes |
|------|----------|-----------|-------|
| `input/mini-pc/1.mp4` | 10:53 | 3840x2160 HEVC 60fps, `rotation=-90` | unboxing, accessories, first look |
| `input/mini-pc/2.mp4` | 4:03 | 3840x2160 HEVC 120fps, `rotation=-90` | SSD in hand, case opened |
| `input/mini-pc/3.mp4` | 15:20 | 3840x2160 HEVC 120fps, `rotation=-90` | board out, RAM + SSD install, teardown of the table |
| `input/mini-pc/final.jpg` | — | 2252x4000 | the payoff photo: mini PC + keyboard + monitor booting CachyOS |

Total 1816s / ~14 GB.

`rotation=-90` means every clip already **displays as portrait 2160x3840**, an exact 9:16.
No Stage 0 crop is needed — only a downscale. `final.jpg` at 2252x4000 is also exact 9:16.

Audio is present but quiet (mean -29.7 dB over a 15s sample): ambient room noise, no
narration. It is kept in the proxy only because `cut.py`'s filter graph maps an audio
stream; it is muted in the final reel (fast-forward audio is already muted by
`build_filter`, and the music bed replaces it).

## Music

Both tracks were analysed with an onset-autocorrelation BPM estimate and a per-second RMS
envelope.

**Circuit Rush — The Mini Vandals** (2:12): **89.0 BPM**, bar = **2.697s**. Envelope is
flat (-14 to -7.6 dB) — heavily compressed, no drop. Peak region 0:44–0:53, a small
breakdown at 0:32–0:34, fade-out from 2:02. Because there is no drop, the photo reveal
lands on a bar downbeat rather than a musical event. Needs no offset: the slightly quieter
first 11s works as a natural intro under the opening box shot.

**Land of the RetroOnes — RAGE** (2:15): **71.75 BPM**, bar = **3.345s**. Real dynamics:
silent intro 0:00–0:13 (-30 dB), ramp to 0:20, full energy 0:20–1:00 (-6.5 dB), breakdown
1:03–1:35 (-14 dB), full again 1:38–1:54, then ends. The 15s dead intro would kill the
hook, so this version **starts the track at 0:15** and the reel must finish before the
1:03 breakdown — which caps it at roughly 45s.

Music is the entire audio bed here, so `bg_music_volume` goes from `0.0403` (a
ducked-under-voice level) to **0.7**.

## Output

Two reels, both from one `edl.json` with two segments over the same source span:

| | segment 1 | segment 2 |
|---|---|---|
| `filename_slug` | `mini-pc-build-circuit-rush` | `mini-pc-build-retrowave` |
| music | `Circuit Rush - The Mini Vandals.mp3` @ 0:00 | `Land of the RetroOnes - RAGE.mp3` @ 0:15 |
| bar length | 2.697s | 3.345s |
| timelapse | 0:00–0:48.5 (18 bars) | 0:00–36.80 (11 bars) |
| final photo | 48.5–53.9 (2 bars) | 36.80–43.49 (2 bars) |
| CTA | 53.9–56.6 (1 bar) | 43.49–46.84 (1 bar) |
| **total** | **56.60s** | **46.84s** |

Chapter cards land on bar downbeats. Segment 1: 0.0 / 10.8 / 24.3 / 35.1 / 45.8.
Segment 2's are placed on its own 3.345s grid during implementation.

Using two segments of one EDL is what makes the second version nearly free: `cut.py` and
`render.py` already loop over segments, so no new orchestration is required — only a
per-segment music override.

## Architecture

Five pieces. Three are new, two are existing stages the work rides on.

### 1. Proxy build (Stage 0, Claude-driven, no new module)

One `ffmpeg` invocation: decode the three sources (NVDEC), scale to 1080x1920 at 30fps,
`setsar=1`, concat video+audio, encode H.264 CRF 20. Result: `input/mini-pc.mp4`, ~30 min,
a few hundred MB instead of 14 GB.

Everything downstream reads the proxy, so a cut+render iteration is seconds rather than
minutes. Sources stay untouched in `input/mini-pc/`, consistent with how the pipeline
already keeps `<name>.original.mp4` beside a normalised input.

Segment boundaries in the concatenated timeline are at 0s, 652.9s and 895.9s — the EDL is
written against that single timeline.

### 2. `src/motion.py` — dead-frame detection (new module, ~30 lines)

The user steps out of frame for long stretches. This is the visual analogue of the
`detect_silences()` that already exists in `edl.py`.

- Input: the proxy. Output: JSON list of `{start, end}` regions, shaped exactly like
  `cuts_to_remove`, printed to stdout.
- Method: `ffmpeg -vf "fps=1,scale=160:-1,tblend=all_mode=difference,signalstats,
  metadata=print:key=lavfi.signalstats.YAVG"`, parse `YAVG` per second — the mean luma of
  the frame-to-frame difference. Runs below a threshold, lasting longer than a minimum
  duration, are dead.
- Two tunables, both CLI flags with defaults: `--threshold` (YAVG below which a second
  counts as static) and `--min-dur` (default 3.0s). The threshold is scene-dependent and
  **must be tuned against a visual check** — the module prints each detected region with
  its timestamp so it can be spot-checked with `ffplay -ss` before anything is cut.
- Never auto-applied. Its output is reviewed, then pasted into the EDL. This matches the
  repo's existing rule that the user approves the EDL before any cutting happens.
- Self-check: a `demo()` under `__main__` asserting the run-detection logic against a
  synthetic YAVG series (a known static run in the middle of a moving one).

### 3. `edl.json` — hand-written, no transcript

`stage: "final"`, two segments, both spanning the whole proxy.

- `cuts_to_remove` — the reviewed dead regions from `motion.py`, plus any obviously boring
  stretch. Identical in both segments.
- `speedups` — the complement of the cuts, tiered by beat:

  | beat | speed |
  |------|-------|
  | box arrives, first open | ~6x |
  | unwrap accessories | ~30x |
  | unscrew case | ~20x |
  | RAM click in, SSD seat | ~4x |
  | screw back, cable up | ~30x |

  The exact factors are solved during implementation so that
  `sum((end - start) / factor)` equals the target timelapse length for that segment
  (48.5s for segment 1, 36.8s for segment 2). The tiers set the *ratios*; a single
  scaling pass fits them to the target. `validate_edl.py` already enforces
  `factor > 1`, in-span, and no overlap with a cut.
- `captions` — five chapter cards, not karaoke. Text: `MINI PC SAMPAI` → `BUKA CASING` →
  `RAM 32GB` → `SSD 1TB` → `LINUX · CACHYOS`. The validator requires a non-empty `words[]`
  whose joined text equals `text`, so each card's words all carry the **same** start/end
  as the card itself. That makes the whole line appear at once instead of revealing
  word-by-word, which is what a title card should do — there is no speech to sync to.
- Caption times are stored in **source** time, but they need to be chosen in **clip-local**
  time (a card must be readable for ~2s on screen, which at 30x is a 60s source span). A
  throwaway script in the scratchpad — not in the repo — inverts `cut.py`'s
  `apply_speedups()` + `remap_time()` to convert the desired local times into source
  times. Reusing the real functions keeps the two in agreement.

### 4. Per-segment music override (small change to existing code)

Today `render.py` reads `bg_music` once from config and applies it to every reel. Two
segments need two different tracks and one needs a start offset.

- `edl.json` segment gains optional `bg_music` (repo-relative path) and
  `bg_music_offset` (seconds, default 0). `cut.py` copies both into the segment's
  `.captions.json`, the way it already copies `title`, `intensity` and `overlays`.
- `render.py`: stage each distinct music file into the public dir under a distinct
  basename (the current code stages exactly one as `bgm.<ext>`); pick per-clip values from
  the cues, falling back to config.
- `schema.ts`: `bgMusicOffset: z.number().default(0)`.
- `Reel.tsx`: pass it as `trimBefore={Math.round(props.bgMusicOffset * fps)}` on the
  existing `<Audio>`. The existing loop and fade-in/out behaviour is unchanged.

### 5. `endImage` — the final photo beat (small change to existing code)

- `schema.ts`: `endImage: z.string().default("")`, `endImageDur: z.number().default(0)`.
- `Reel.tsx`: a `<Sequence from={introF + clipF} durationInFrames={endF}>` holding an
  `<Img>` with a slow ken-burns zoom (scale ~1.0 → ~1.08 across the sequence), inserted
  between the content clip and the CTA. The CTA's `from` shifts by `endF`.
- `Root.tsx`: `calculateMetadata` adds `endImageDur` to the total duration. Missing this
  truncates the reel — the composition length is computed there, not in `Reel.tsx`.
- `render.py`: stage the image into the public dir, pass the two props. Source is a
  segment-level `end_image` field in the EDL, so segment 2 could use a different photo
  later without a code change.
- `config.json`: `cta.duration_sec` `1.6` → `2.7` (one bar of Circuit Rush). Segment 2's
  CTA is one bar of its own track (3.345s), so CTA duration also becomes a per-segment
  EDL override rather than a pure config value.

### Bug to fix on the way

`render.py::cut_points_sec()` computes `cum += r[1] - r[0]` over `keep_ranges`. With the
new `speedups` work those entries are `(start, end, speed)` triples in **source** time, so
a sped-up range contributes its full source duration to what is supposed to be a
**clip-local** punch-in point. It must be `cum += (r[1] - r[0]) / r[2]`. At 30x this is off
by minutes, which would push every punch-in past the end of the reel. This is a latent bug
in the uncommitted speedup work, not something this feature introduces, but this is the
first edit that would trip it.

## Data flow

```
input/mini-pc/{1,2,3}.mp4  --ffmpeg concat+scale-->  input/mini-pc.mp4  (proxy)
                                                            |
                                    src/motion.py ----------+--> dead regions (JSON, reviewed)
                                                            |
                        hand-written  output/mini-pc/edl.json  <-- chapter cards, speedups,
                                                            |       per-segment music, end_image
                                          validate_edl.py (hook + cut.py)
                                                            |
                                      src/cut.py  -->  clips/01_*.mp4 + .captions.json
                                                       clips/02_*.mp4 + .captions.json
                                                            |
                                     src/render.py --> output/mini-pc/01_*.mp4
                                                       output/mini-pc/02_*.mp4
```

## Error handling

- `motion.py` on a proxy that does not exist, or with no regions found: exits non-zero with
  a message naming the threshold it used, so a silent empty result is never mistaken for
  "no dead time".
- The EDL is gated by `validate_edl.py` twice — the PostToolUse hook when it is written,
  and again inside `cut.py`. Both existing. New per-segment fields (`bg_music`,
  `bg_music_offset`, `end_image`, `cta_duration_sec`) are optional; the validator gains a
  check that `bg_music` / `end_image` paths, when present, exist on disk. A missing asset
  should fail before an hour of cutting, not during a Remotion render.
- A media player holding a rendered reel open locks the file on Windows (`WinError 32`).
  Known repo hazard; close players before re-rendering.

## Testing

No test suite in this repo — validation is running a stage on real media and inspecting
the output. Concretely:

1. `motion.py`'s run-detection assert-based `demo()` (the one automated check).
2. Proxy: `ffprobe` it — expect 1080x1920, 30fps, ~1816s. Spot-check a frame from each
   source region to confirm the concat order and that rotation was applied.
3. Dead regions: `ffplay -ss <start>` on three detected regions, confirm the frame is
   static and the user is out of shot.
4. First cut: render segment 1 with `--draft --frames 0-90` to check the opening hook,
   then a full draft render to check pacing and that chapter cards are readable.
5. Ending: confirm the photo holds for its full 2 bars and the CTA is not truncated —
   this is what catches a forgotten `calculateMetadata` change.
6. Watch both finished reels end-to-end before publishing.

## Out of scope

- Whisper / transcription of any kind.
- Beat detection at cut-point granularity; bar-grid snapping is done from the measured BPM
  by arithmetic, not by an onset-tracking library.
- A third version, or per-platform variants.
- Making `motion.py` part of `run.py`'s automatic chain. It is a manual, reviewed tool for
  now; folding it into the EDL draft can happen once its threshold proves stable across
  more than one video.
