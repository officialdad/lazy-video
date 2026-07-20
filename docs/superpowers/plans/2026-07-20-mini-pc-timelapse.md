# Mini PC Build Timelapse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn ~30 min of unedited 4K footage in `input/mini-pc/` into two finished 9:16 reels of the same build story, differing only in background music and the timing grid that music implies.

**Architecture:** Downscale the three sources into one proxy, detect the dead stretches where the user is out of frame with a new `src/motion.py`, hand-write a two-segment `edl.json` (no Whisper — there is no speech) whose `speedups` compress the rest, and extend Remotion with a final-photo beat plus a per-segment music override. Stages 3 and 4 already loop over segments, so the second reel costs one extra cut and one extra render.

**Tech Stack:** Python 3 via `uv`, ffmpeg/ffprobe, Remotion 4.0.486 + React 19 + zod 4, no new dependencies.

## Global Constraints

- Python is always invoked through `uv` — `uv run python ...`. Never bare `python`.
- Source modules run as modules: `uv run python -m src.<name>`.
- No new pip or npm dependencies. numpy 2.4.6 is already available; ffmpeg/ffprobe are on PATH.
- Tests in this repo are plain `assert` scripts at the repo root named `test_*.py`, run directly (`uv run python test_cut.py`). No pytest, no fixtures, no framework. Match `test_cut.py`'s style exactly.
- `config.json` is the single source of tunables. Never hardcode a value that belongs there.
- Every `edl.json` write is gated by `src/validate_edl.py` — as a PostToolUse hook and again inside `cut.py`. Exit 2 feeds errors back; fix the EDL, never bypass.
- Deliberate simplifications get a `ponytail:` comment naming the ceiling and the upgrade path.
- Measured music values, used verbatim: Circuit Rush = **89.0 BPM**, bar **2.696629s**. Land of the RetroOnes = **71.75 BPM**, bar **3.344948s**, start offset **15.0s**.
- Proxy total duration: **1816.373s** (652.915 + 242.935 + 920.523). Concat boundaries at **0.0 / 652.915 / 895.850**.
- Reel A total **56.629s** (timelapse 48.539 + photo 5.393 + CTA 2.697). Reel B total **46.829s** (timelapse 36.794 + photo 6.690 + CTA 3.345).
- Chapter card copy, exact: `MINI PC SAMPAI`, `BUKA CASING`, `RAM 32GB`, `SSD 1TB`, `LINUX · CACHYOS`.
- Windows: close any media player holding a rendered reel before re-rendering (`WinError 32`).

---

### Task 1: Fix `cut_points_sec` for sped-up keep-ranges

`render.py::cut_points_sec()` sums `r[1] - r[0]` over `keep_ranges`. Since the speedup work landed, those entries are `(start, end, speed)` triples in **source** time, but the function must return **clip-local** punch-in points. At 30x a single range overshoots by minutes and every punch-in lands past the end of the reel. This blocks everything downstream, so it goes first.

**Files:**
- Modify: `src/render.py:48-55`
- Test: `test_render.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `cut_points_sec(keep_ranges: list[list[float]]) -> list[float]` — accepts both 2-element `[start, end]` (legacy cues files) and 3-element `[start, end, speed]` entries.

- [ ] **Step 1: Write the failing test**

Create `test_render.py`:

```python
"""Runnable check for render.py prop math.

    uv run python test_render.py

cut_points_sec turns source-time keep_ranges into clip-local punch-in points.
A sped-up range contributes its COMPRESSED duration; forgetting to divide by the
speed pushes every punch-in past the end of the reel.
"""

from src.render import cut_points_sec


def approx_list(a, b, eps=0.001):
    return len(a) == len(b) and all(abs(x - y) <= eps for x, y in zip(a, b))


# legacy 2-element ranges still work (older captions.json files)
assert cut_points_sec([[0, 10], [10, 20]]) == [0.0, 10.0]

# speed 1.0 triples behave like the legacy form
assert cut_points_sec([[0, 10, 1.0], [10, 20, 1.0]]) == [0.0, 10.0]

# a 60s range at 30x contributes 2s of clip-local time, not 60s
assert approx_list(cut_points_sec([[0, 10, 1.0], [10, 70, 30.0], [70, 80, 1.0]]),
                   [0.0, 10.0, 12.0])

# the last range is intentionally excluded -- points mark joins, not the end
assert cut_points_sec([[0, 5, 1.0]]) == [0.0]

print("render.py prop math OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python test_render.py`
Expected: FAIL — `AssertionError` on the 30x case, because it returns `[0.0, 10.0, 70.0]`.

- [ ] **Step 3: Write minimal implementation**

In `src/render.py`, replace `cut_points_sec` (currently lines 48-55) with:

```python
def cut_points_sec(keep_ranges: list[list[float]]) -> list[float]:
    """Clip-local times where shots join (punch-in points), plus 0 for the opening.

    keep_ranges are source-time (start, end[, speed]); a sped-up range occupies
    only duration/speed on the clip's own timeline."""
    points = [0.0]
    cum = 0.0
    for r in keep_ranges[:-1]:
        speed = r[2] if len(r) > 2 else 1.0
        cum += (r[1] - r[0]) / speed
        points.append(round(cum, 3))
    return points
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python test_render.py`
Expected: PASS, prints `render.py prop math OK`

- [ ] **Step 5: Commit**

```bash
git add src/render.py test_render.py
git commit -m "fix: cut_points_sec must divide sped-up ranges by their speed"
```

---

### Task 2: `src/motion.py` — dead-frame detection

The visual analogue of `edl.py::detect_silences()`. A speech-free source has no transcript to find dead air in, but it has plenty of dead air: the stretches where the user steps out of frame. This finds them and prints them in `cuts_to_remove` shape for review.

**Files:**
- Create: `src/motion.py`
- Test: `test_motion.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `yavg_per_second(video: Path) -> list[float]` — mean luma of the frame-to-frame difference, one value per second.
  - `static_runs(yavg: list[float], threshold: float, min_dur: float) -> list[dict]` — returns `[{"start": float, "end": float}, ...]` in seconds, the exact shape of an EDL `cuts_to_remove` entry.

- [ ] **Step 1: Write the failing test**

Create `test_motion.py`:

```python
"""Runnable check for the motion.py dead-region detector.

    uv run python test_motion.py

static_runs turns a per-second motion series into cuts_to_remove entries. The
run-boundary math is what decides whether real footage gets deleted, so the
edge cases (run at the very end, run one second too short) are asserted here.
"""

from src.motion import static_runs

# a quiet run in the middle of a busy series
y = [5.0, 5.0, 0.1, 0.1, 0.1, 0.1, 5.0, 5.0]
assert static_runs(y, 1.0, 3.0) == [{"start": 2.0, "end": 6.0}], static_runs(y, 1.0, 3.0)

# same series, longer minimum -> the run no longer qualifies
assert static_runs(y, 1.0, 5.0) == []

# a run that reaches the end of the series is still reported (no trailing busy second)
assert static_runs([5.0, 0.1, 0.1, 0.1, 0.1], 1.0, 3.0) == [{"start": 1.0, "end": 5.0}]

# nothing quiet at all
assert static_runs([5.0, 5.0, 5.0], 1.0, 3.0) == []

# entirely quiet
assert static_runs([0.1] * 4, 1.0, 3.0) == [{"start": 0.0, "end": 4.0}]

# two separate runs
y2 = [0.1, 0.1, 0.1, 9.0, 0.1, 0.1, 0.1, 0.1]
assert static_runs(y2, 1.0, 3.0) == [{"start": 0.0, "end": 3.0}, {"start": 4.0, "end": 8.0}]

# threshold is exclusive: a value exactly at the threshold counts as motion
assert static_runs([1.0, 1.0, 1.0], 1.0, 3.0) == []

print("motion.py run detection OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python test_motion.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.motion'`

- [ ] **Step 3: Write minimal implementation**

Create `src/motion.py`:

```python
"""Detect dead regions in a speech-free video -- stretches where nothing moves.

The visual analogue of edl.py's detect_silences(): a music-driven timelapse has no
transcript to find dead air in, but it has plenty of dead air -- every stretch where
the person steps out of frame while the camera keeps rolling.

Method: one frame per second, downscaled, differenced against the previous frame
(tblend), then signalstats' YAVG = the mean luma of that difference. A still frame
differences to near-black, so YAVG collapses toward 0. Runs below --threshold that
last at least --min-dur are reported.

The threshold is scene-dependent -- lighting, camera noise and compression all move
it. Regions are printed with a ready-to-paste ffplay command so each one can be
eyeballed before it is trusted. Nothing here edits the EDL; the output is reviewed,
then pasted into `cuts_to_remove` by hand.

    uv run python -m src.motion input/mini-pc.mp4
    uv run python -m src.motion input/mini-pc.mp4 --threshold 1.2 --min-dur 4
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=([\d.]+)")


def yavg_per_second(video: Path) -> list[float]:
    """Mean luma of the frame-to-frame difference, one value per second of video."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(video),
        "-vf", ("fps=1,scale=160:-1,tblend=all_mode=difference,signalstats,"
                "metadata=print:key=lavfi.signalstats.YAVG:file=-"),
        "-an", "-f", "null", "-",
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return [float(m) for m in YAVG_RE.findall(out)]


def static_runs(yavg: list[float], threshold: float, min_dur: float) -> list[dict]:
    """Contiguous seconds below `threshold` lasting >= `min_dur`, as {start, end}.

    Sampling is 1 fps, so index == second. A value exactly at the threshold counts
    as motion (keep footage when in doubt -- deleting real content is the costly
    mistake, an extra second of stillness is not)."""
    runs: list[dict] = []
    start: int | None = None
    for i, v in enumerate(yavg):
        if v < threshold:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= min_dur:
                runs.append({"start": float(start), "end": float(i)})
            start = None
    if start is not None and len(yavg) - start >= min_dur:
        runs.append({"start": float(start), "end": float(len(yavg))})
    return runs


def main() -> None:
    ap = argparse.ArgumentParser(description="find dead (motionless) regions in a video")
    ap.add_argument("video", type=Path, help="video to scan (use the proxy, not the 4K source)")
    ap.add_argument("--threshold", type=float, default=1.5,
                    help="YAVG below which a second counts as static (default 1.5)")
    ap.add_argument("--min-dur", type=float, default=3.0,
                    help="shortest run worth cutting, seconds (default 3.0)")
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"[motion] no such video: {args.video}")

    yavg = yavg_per_second(args.video)
    if not yavg:
        sys.exit(f"[motion] no frames analysed in {args.video} -- is it a valid video?")

    runs = static_runs(yavg, args.threshold, args.min_dur)
    if not runs:
        sys.exit(f"[motion] no static runs >= {args.min_dur}s below YAVG {args.threshold} "
                 f"in {len(yavg)}s of video -- raise --threshold and try again")

    dead = sum(r["end"] - r["start"] for r in runs)
    print(f"[motion] {len(runs)} static region(s), {dead:.0f}s dead of {len(yavg)}s "
          f"(threshold {args.threshold}, min-dur {args.min_dur})", file=sys.stderr)
    for r in runs:
        print(f"  {r['start']:8.1f} -> {r['end']:8.1f}  ({r['end'] - r['start']:5.1f}s)  "
              f"ffplay -ss {r['start']:.0f} -t 3 {args.video}", file=sys.stderr)
    print(json.dumps(runs, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python test_motion.py`
Expected: PASS, prints `motion.py run detection OK`

- [ ] **Step 5: Commit**

```bash
git add src/motion.py test_motion.py
git commit -m "feat: detect dead motionless regions for speech-free sources"
```

---

### Task 3: Build the proxy

One ffmpeg pass turns 14 GB of 4K into a single ~30 min portrait proxy. Every later stage reads the proxy, so a cut+render iteration is seconds rather than minutes.

`rotation=-90` on all three sources means ffmpeg's decoder auto-rotates them to portrait 2160x3840, so `scale=1080:1920` is a straight downscale with no transpose. Step 3 verifies this rather than assuming it.

**Files:**
- Create: `input/mini-pc.mp4` (build artifact, not committed)
- Modify: none

**Interfaces:**
- Consumes: nothing.
- Produces: `input/mini-pc.mp4` — 1080x1920, 30fps, ~1816.373s, one audio stream. Source-time offsets for the three parts: `1.mp4` at 0.0, `2.mp4` at 652.915, `3.mp4` at 895.850.

- [ ] **Step 1: Build the proxy**

Run from the repo root:

```bash
ffmpeg -y -i "input/mini-pc/1.mp4" -i "input/mini-pc/2.mp4" -i "input/mini-pc/3.mp4" \
  -filter_complex "[0:v]scale=1080:1920,fps=30,setsar=1[v0];\
[1:v]scale=1080:1920,fps=30,setsar=1[v1];\
[2:v]scale=1080:1920,fps=30,setsar=1[v2];\
[0:a]aresample=48000[a0];[1:a]aresample=48000[a1];[2:a]aresample=48000[a2];\
[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -preset veryfast -pix_fmt yuv420p \
  -c:a aac -b:a 128k \
  "input/mini-pc.mp4"
```

This decodes ~30 min of 4K HEVC and will take several minutes. Audio is kept even though the reel is music-only: `cut.py`'s filter graph maps an audio stream and would fail without one.

`ponytail: CPU decode. Adding -hwaccel cuda before the inputs is worth trying if this is
too slow, but it interacts with autorotation, so verify Step 3 again if you do.`

- [ ] **Step 2: Verify the container**

Run:

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate \
  -show_entries format=duration -of default=nw=1 "input/mini-pc.mp4"
```

Expected: `width=1080`, `height=1920`, `r_frame_rate=30/1`, `duration` ≈ `1816.4`.

If width/height come back `1920x1080`, autorotation did not apply — add `transpose=2,` immediately before each `scale=` in the filter graph and rebuild.

- [ ] **Step 3: Verify the concat order and orientation visually**

Run:

```bash
mkdir -p "C:/Temp/claude/C--Users-opari-OneDrive-Desktop-claude-code-lazy-video/40ac1b9b-661a-457b-b39b-cf3c5e1f4b8a/scratchpad/proxy" && \
for t in 60 700 1000 1700; do \
  ffmpeg -v error -y -ss $t -i "input/mini-pc.mp4" -frames:v 1 -vf "scale=270:-1" \
    "C:/Temp/claude/C--Users-opari-OneDrive-Desktop-claude-code-lazy-video/40ac1b9b-661a-457b-b39b-cf3c5e1f4b8a/scratchpad/proxy/t$t.jpg"; \
done
```

Read all four JPEGs. Expected: portrait framing (taller than wide) in every one; `t60` shows the cardboard box, `t700` shows the case being opened, `t1000` and `t1700` show board/RAM/SSD work. If `t700` still shows unboxing, the concat order is wrong.

- [ ] **Step 4: No commit**

`input/` holds media, not source. Confirm the proxy is not staged:

```bash
git status --short input/
```

Expected: no `input/mini-pc.mp4` entry (the existing `.gitignore` covers `input/`). If it does appear, stop and report — do not commit a 500 MB file.

---

### Task 4: `endImage` — the final photo beat

A new Sequence between the content clip and the CTA that holds `final.jpg` with a slow ken-burns zoom. The easy mistake here is editing `Reel.tsx` alone: the composition's length is computed in `Root.tsx::calculateMetadata`, so without that change the reel is simply truncated and the photo never appears.

**Files:**
- Modify: `remotion/src/schema.ts:33-56` (add fields to `reelSchema`)
- Modify: `remotion/src/Reel.tsx` (imports, new `EndImageCard`, Sequence wiring at lines 215-256)
- Modify: `remotion/src/Root.tsx:19-64` (default props + `calculateMetadata`)
- Modify: `src/render.py` (stage the image, pass the props)

**Interfaces:**
- Consumes: `cut_points_sec` from Task 1 (unchanged usage).
- Produces:
  - Remotion props `endImage: string` (basename in the staging dir, `""` = no photo beat) and `endImageDur: number` (seconds, `0` = no photo beat).
  - EDL segment fields `end_image` (repo-relative path) and `end_image_dur` (seconds), consumed in Task 5.

- [ ] **Step 1: Add the schema fields**

In `remotion/src/schema.ts`, inside `reelSchema`, immediately after the `overlays` line:

```ts
  overlays: z.array(overlaySchema).default([]),
  /** Payoff photo held after the content clip, before the CTA. "" = no photo beat. */
  endImage: z.string().default(""),
  endImageDur: z.number().default(0),
```

- [ ] **Step 2: Add the card component and wire the Sequence**

In `remotion/src/Reel.tsx`, add `Img` and `useCurrentFrame` to the existing `remotion` import if they are not already there.

Add this component next to the other card components (above `export const Reel`):

```tsx
/** The payoff photo: held for its full duration with a slow ken-burns push-in. */
const EndImageCard: React.FC<{ image: string; durationInFrames: number }> = ({
  image,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames], [1, 1.08], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#000", overflow: "hidden" }}>
      <Img
        src={src(image)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale})`,
        }}
      />
    </AbsoluteFill>
  );
};
```

In the `Reel` component, add `endF` beside the existing frame counts:

```tsx
  const ctaF = Math.round(props.cta.durationSec * fps);
  const endF = props.endImage ? Math.round(props.endImageDur * fps) : 0;
```

Then replace the final CTA Sequence block with the photo beat followed by a shifted CTA:

```tsx
      {endF > 0 ? (
        <Sequence from={introF + clipF} durationInFrames={endF}>
          <EndImageCard image={props.endImage} durationInFrames={endF} />
        </Sequence>
      ) : null}

      <Sequence from={introF + clipF + endF} durationInFrames={ctaF}>
        <CtaCard text={props.cta.text} brand={props.brand} />
      </Sequence>
```

- [ ] **Step 3: Extend the composition duration**

In `remotion/src/Root.tsx`, add the two fields to `DEFAULT_PROPS` after `overlays: []`:

```ts
  overlays: [],
  endImage: "",
  endImageDur: 0,
```

and include the photo beat in the computed length:

```ts
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.round(
          (props.introDur + props.clipDur + props.endImageDur + props.cta.durationSec) * FPS,
        ),
        fps: FPS,
        width: 1080,
        height: 1920,
      })}
```

- [ ] **Step 4: Pass the props from render.py**

In `src/render.py::render_clip`, add to the `props` dict after the `"overlays"` line:

```python
        "endImage": end_image_src,
        "endImageDur": cues.get("end_image_dur", 0.0),
```

and add the parameter to the signature, after `bg_music_vol`:

```python
                bg_music_src: str = "", bg_music_vol: float = 0.0,
                end_image_src: str = "",
```

Leave the `run()` call site passing `""` for now — Task 5 wires the real value from the cues.

- [ ] **Step 5: Verify the composition builds and the length is right**

Run:

```bash
cd remotion && npx tsc --noEmit
```

Expected: no errors. A `Property 'endImage' does not exist` error means Step 1 was skipped.

- [ ] **Step 6: Commit**

```bash
git add remotion/src/schema.ts remotion/src/Reel.tsx remotion/src/Root.tsx src/render.py
git commit -m "feat: hold a payoff photo between the clip and the CTA"
```

---

### Task 5: Per-segment music, offset, CTA length and end image

Today `render.py` stages one music file for every reel and reads the CTA length from config. The two reels need different tracks, one needs a 15s start offset, and each needs a CTA of one bar of its own track. All four become optional EDL segment fields that fall back to config.

**Files:**
- Modify: `src/cut.py` (copy the fields into the cues JSON)
- Modify: `src/render.py` (per-clip asset staging, per-clip CTA/music/image props)
- Modify: `src/validate_edl.py` (validate the new optional fields)
- Modify: `remotion/src/schema.ts` (`bgMusicOffset`)
- Modify: `remotion/src/Reel.tsx` (`trimBefore` on the existing `<Audio>`)
- Modify: `remotion/src/Root.tsx` (default prop)
- Test: `test_validate_edl.py` (create)

**Interfaces:**
- Consumes: `end_image` / `end_image_dur` props from Task 4.
- Produces:
  - EDL segment fields, all optional: `bg_music` (repo-relative path), `bg_music_offset` (seconds, default 0), `cta_duration_sec` (seconds), `end_image`, `end_image_dur`.
  - `src/render.py::stage_asset(rel: str, public_dir: Path) -> str` — copies a repo-relative asset into the staging dir under a filesystem-safe basename and returns that basename.
  - Remotion prop `bgMusicOffset: number` (seconds).

- [ ] **Step 1: Write the failing test**

Create `test_validate_edl.py`:

```python
"""Runnable check for the edl.json contract, including the per-segment overrides.

    uv run python test_validate_edl.py

validate_edl is the gate between a hand-written EDL and an hour of cutting. These
asserts cover the failure modes that are expensive to discover late: an asset path
that does not exist, and a negative duration that would silently truncate a reel.
"""

from src.validate_edl import validate


def base_segment(**over):
    seg = {
        "index": 1,
        "start": 0.0,
        "end": 10.0,
        "filename_slug": "a-slug",
        "intensity": "gentle",
        "title": "T",
        "cuts_to_remove": [],
        "captions": [{
            "start": 0.0, "end": 2.0, "text": "HELLO WORLD",
            "words": [{"w": "HELLO", "start": 0.0, "end": 2.0},
                      {"w": "WORLD", "start": 0.0, "end": 2.0}],
        }],
    }
    seg.update(over)
    return seg


def edl(**over):
    return {"stage": "final", "segments": [base_segment(**over)]}


# a clean EDL with none of the optional fields still passes
assert validate(edl()) == [], validate(edl())

# an existing asset passes (config.json is guaranteed to be in the repo root)
assert validate(edl(bg_music="config.json")) == []

# a missing music file is caught before cutting starts
errs = validate(edl(bg_music="input/does-not-exist.mp3"))
assert any("bg_music" in e and "does not exist" in e for e in errs), errs

# a missing end image is caught too
errs = validate(edl(end_image="input/nope.jpg"))
assert any("end_image" in e and "does not exist" in e for e in errs), errs

# negative or zero durations are rejected
assert any("end_image_dur" in e for e in validate(edl(end_image_dur=-1.0)))
assert any("cta_duration_sec" in e for e in validate(edl(cta_duration_sec=0)))
assert any("bg_music_offset" in e for e in validate(edl(bg_music_offset=-2.0)))

# a zero offset is legal (it is the default)
assert validate(edl(bg_music_offset=0.0)) == []

print("validate_edl contract OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python test_validate_edl.py`
Expected: FAIL — `AssertionError` on the missing-music case, because no such check exists yet.

- [ ] **Step 3: Add the validator checks**

In `src/validate_edl.py`, add the import below the existing ones:

```python
from .config import ROOT
```

and insert this block inside the segment loop, immediately before the `for cap in seg.get("captions")` loop:

```python
        # optional per-segment overrides: a music track, its start offset, the payoff
        # photo and the CTA length. Assets are checked here because discovering a bad
        # path during a render wastes the whole cut that preceded it.
        for key in ("bg_music", "end_image"):
            rel = seg.get(key)
            if rel and not (ROOT / rel).exists():
                errs.append(f"{tag}: {key} {rel!r} does not exist")
        for key in ("end_image_dur", "cta_duration_sec"):
            v = seg.get(key)
            if v is not None and (not isinstance(v, (int, float)) or v <= 0):
                errs.append(f"{tag}: {key} {v!r} must be a positive number")
        off = seg.get("bg_music_offset")
        if off is not None and (not isinstance(off, (int, float)) or off < 0):
            errs.append(f"{tag}: bg_music_offset {off!r} must be >= 0")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python test_validate_edl.py`
Expected: PASS, prints `validate_edl contract OK`

Also re-run the existing checks to confirm nothing regressed:

Run: `uv run python test_cut.py && uv run python test_render.py && uv run python test_motion.py`
Expected: all three print their OK lines.

- [ ] **Step 5: Carry the fields through cut.py**

In `src/cut.py::cut_segment`, extend the dict written to `cues_path` — add these entries after `"overlays": overlays,`:

```python
        # per-segment render overrides; "" / None means "fall back to config.json"
        "bg_music": seg.get("bg_music", ""),
        "bg_music_offset": seg.get("bg_music_offset", 0.0),
        "cta_duration_sec": seg.get("cta_duration_sec"),
        "end_image": seg.get("end_image", ""),
        "end_image_dur": seg.get("end_image_dur", 0.0),
```

- [ ] **Step 6: Stage assets per clip in render.py**

In `src/render.py`, add `import re` to the imports, then add this helper above `render_clip`:

```python
def stage_asset(rel: str, public_dir: Path) -> str:
    """Copy a repo-relative asset into the render staging dir; return its basename.

    Remotion resolves props through staticFile() against the staging dir, so the
    name must be filesystem- and URL-safe: 'Circuit Rush - The Mini Vandals.mp3'
    becomes 'Circuit_Rush_-_The_Mini_Vandals.mp3'."""
    src_path = ROOT / rel
    if not src_path.exists():
        sys.exit(f"[render] missing asset: {rel}")
    dest = public_dir / re.sub(r"[^A-Za-z0-9._-]", "_", Path(rel).name)
    shutil.copy2(src_path, dest)
    return dest.name
```

Replace the body of `render_clip` between the `cover_bg` line and the `props` dict with:

```python
    brand = dict(cfg["brand"])
    brand.setdefault("bg_color", "#0B132B")
    cta = brand.get("cta", {"text": "FOLLOW & STAY TUNED", "duration_sec": 1.6})

    # per-segment overrides beat config; config beats nothing
    music_rel = cues.get("bg_music") or cfg["brand"].get("bg_music", "")
    bg_src = stage_asset(music_rel, public_dir) if music_rel else ""
    bg_vol = cfg["brand"].get("bg_music_volume", 0.15) if bg_src else 0.0
    image_rel = cues.get("end_image") or ""
    end_src = stage_asset(image_rel, public_dir) if image_rel else ""
    cta_dur = cues.get("cta_duration_sec") or cta.get("duration_sec", 1.6)
```

and set these keys in the `props` dict:

```python
        "cta": {"text": cta["text"], "durationSec": cta_dur},
        "bgMusic": bg_src,
        "bgMusicVolume": bg_vol,
        "bgMusicOffset": cues.get("bg_music_offset", 0.0),
        "endImage": end_src,
        "endImageDur": cues.get("end_image_dur", 0.0),
```

Then simplify the signature — music and image now come from the cues, so drop the three parameters:

```python
def render_clip(cues_path: Path, cfg: cfg_t, public_dir: Path,
                intro_src: str, intro_dur: float, out_dir: Path,
                extra_flags: list[str] | None = None) -> Path:
```

In `run()`, delete the whole `bg_music` staging block (the `bg_music = cfg["brand"].get(...)` through `bg_src, bg_vol = "", 0.0` lines) and update the call:

```python
        outputs = [render_clip(cf, cfg, public_dir, intro_src, intro_dur, out_dir,
                               extra_flags)
                   for cf in cue_files]
```

- [ ] **Step 7: Add the offset prop to Remotion**

In `remotion/src/schema.ts`, beside the existing music fields:

```ts
  bgMusicVolume: z.number().default(0.15),
  /** Seconds to skip at the start of the music file (e.g. past a dead intro). */
  bgMusicOffset: z.number().default(0),
```

In `remotion/src/Root.tsx`, add to `DEFAULT_PROPS` after `bgMusicVolume`:

```ts
  bgMusicOffset: 0,
```

In `remotion/src/Reel.tsx`, add `trimBefore` to the existing `<Audio>` (this is the current Remotion 4.x prop; `startFrom` is deprecated):

```tsx
        <Audio
          src={src(props.bgMusic)}
          loop
          trimBefore={Math.round(props.bgMusicOffset * fps)}
          volume={(f) =>
```

- [ ] **Step 8: Verify types and re-run every check**

Run:

```bash
cd remotion && npx tsc --noEmit
```

Expected: no errors.

Run from the repo root:

```bash
uv run python test_cut.py && uv run python test_render.py && \
uv run python test_motion.py && uv run python test_validate_edl.py
```

Expected: four OK lines.

- [ ] **Step 9: Commit**

```bash
git add src/cut.py src/render.py src/validate_edl.py test_validate_edl.py \
        remotion/src/schema.ts remotion/src/Reel.tsx remotion/src/Root.tsx
git commit -m "feat: per-segment music, offset, CTA length and end image"
```

---

### Task 6: Author the two-segment EDL

The creative task. Everything before this was plumbing; this decides what the reels actually look like. It ends with a validated `output/mini-pc/edl.json` and nothing cut yet.

**Files:**
- Create: `output/mini-pc/edl.json`
- Create: scratchpad helper at `C:/Temp/claude/C--Users-opari-OneDrive-Desktop-claude-code-lazy-video/40ac1b9b-661a-457b-b39b-cf3c5e1f4b8a/scratchpad/plan_edl.py` (throwaway, never committed)

**Interfaces:**
- Consumes: `src.motion.static_runs` output; `src.cut.keep_ranges`, `src.cut.apply_speedups` (for the factor solve and the caption time inversion); the EDL segment fields from Task 5.
- Produces: `output/mini-pc/edl.json` with `stage: "final"` and segments indexed 1 and 2.

- [ ] **Step 1: Find the dead regions**

Run:

```bash
uv run python -m src.motion input/mini-pc.mp4 > "C:/Temp/claude/C--Users-opari-OneDrive-Desktop-claude-code-lazy-video/40ac1b9b-661a-457b-b39b-cf3c5e1f4b8a/scratchpad/dead.json"
```

The human-readable table goes to stderr (visible), the JSON to the file. If it exits with "no static runs", raise `--threshold` to 2.5 and retry; if it reports more than ~40% of the video dead, lower it to 1.0.

- [ ] **Step 2: Spot-check three detected regions before trusting them**

Pick the first, a middle, and the last region from the table and extract a frame from each:

```bash
ffmpeg -v error -y -ss <START> -i input/mini-pc.mp4 -frames:v 1 -vf "scale=270:-1" \
  "C:/Temp/claude/C--Users-opari-OneDrive-Desktop-claude-code-lazy-video/40ac1b9b-661a-457b-b39b-cf3c5e1f4b8a/scratchpad/dead_<START>.jpg"
```

Read each JPEG. Expected: an empty table, no hands in frame. If any shows active work, the threshold is too high — lower it by 0.5 and go back to Step 1. Report to the user which regions were checked and what they showed.

- [ ] **Step 3: Map the five phases**

Extract a contact sheet to locate the phase boundaries and the hero moments:

```bash
for t in $(seq 30 60 1800); do \
  ffmpeg -v error -y -ss $t -i input/mini-pc.mp4 -frames:v 1 -vf "scale=200:-1" \
    "C:/Temp/claude/C--Users-opari-OneDrive-Desktop-claude-code-lazy-video/40ac1b9b-661a-457b-b39b-cf3c5e1f4b8a/scratchpad/sheet/t$t.jpg"; \
done
```

Read them and write down, in proxy-source seconds, the boundaries of: box arrives / first open, unwrap accessories, unscrew the case, RAM click-in and SSD seat, screw back and cable up. Also mark the **hero windows** — the 10-30s where something actually happens (lid comes off, RAM snaps in, SSD seats). Present this phase table to the user before continuing.

- [ ] **Step 4: Solve the speedup factors**

Create the scratchpad helper `plan_edl.py` (paths are absolute so it runs from anywhere; it imports the real `cut.py` functions so the EDL and the cutter can never disagree):

```python
"""Throwaway: solve speedup factors and convert caption times. Not part of the repo."""
import sys
sys.path.insert(0, r"C:\Users\opari\OneDrive\Desktop\claude-code\lazy-video")

from src.cut import keep_ranges, apply_speedups

SPAN = (0.0, 1816.373)
CUTS = []      # <- paste the reviewed regions from scratchpad/dead.json
# (start, end, relative speed). Must TILE the whole span with no gaps: a gap would
# stay at 1x and break the single-scalar solve below. Hero windows get 1, filler 12.
TIERS = []     # <- fill in from the Step 3 phase table


def solve(tiers, cuts, span, target):
    """Scale every tier by one k so the clip lands exactly on `target` seconds.

    local(k) = sum(len_i / (tier_i * k)) = raw / k, so k = raw / target -- one
    closed-form division, no search."""
    ranges = keep_ranges(span[0], span[1], cuts)
    speedups = [{"start": a, "end": b, "factor": f} for a, b, f in tiers]
    raw = sum((e - s) / sp for s, e, sp in apply_speedups(ranges, speedups))
    k = raw / target
    out = [{"start": a, "end": b, "factor": round(f * k, 4)} for a, b, f in tiers]
    assert all(z["factor"] > 1.0 for z in out), f"k={k}: some factor <= 1, validator will reject"
    return out, k


def clips_for(speedups, cuts, span):
    return apply_speedups(keep_ranges(span[0], span[1], cuts), speedups)


def source_time_for_local(local_t, clips):
    """Inverse of cut.remap_time: clip-local seconds -> source seconds."""
    for s, e, sp in clips:
        dur = (e - s) / sp
        if local_t <= dur + 1e-9:
            return round(s + local_t * sp, 3)
        local_t -= dur
    return clips[-1][1]


def card(text, local_start, local_end, clips):
    """A chapter card: every word shares the card's span, so the whole line shows
    at once instead of revealing word-by-word. There is no speech to sync to."""
    s = source_time_for_local(local_start, clips)
    e = source_time_for_local(local_end, clips)
    return {"start": s, "end": e, "text": text,
            "words": [{"w": w, "start": s, "end": e} for w in text.split()]}


BAR_A, BAR_B = 2.696629, 3.344948
for name, target, bar, cards in (
    ("circuit-rush", 48.539, BAR_A,
     [(0, 2), (4, 2), (9, 2), (13, 2), (17, 1)]),        # (start bar, length in bars)
    ("retrowave", 36.794, BAR_B,
     [(0, 1.5), (3, 1.5), (6, 1.5), (8, 1.5), (10, 1)]),
):
    speedups, k = solve(TIERS, CUTS, SPAN, target)
    clips = clips_for(speedups, CUTS, SPAN)
    texts = ["MINI PC SAMPAI", "BUKA CASING", "RAM 32GB", "SSD 1TB", "LINUX · CACHYOS"]
    caps = [card(t, b * bar, (b + n) * bar, clips) for t, (b, n) in zip(texts, cards)]
    print(name, "k=", round(k, 3))
    print("speedups:", speedups)
    print("captions:", caps)
```

Run it, iterate on `TIERS` until every factor is comfortably above 1 and the filler factor stays **at or below ~60x** — beyond that the timelapse strobes. If it exceeds 60x, either cut more dead time or shorten the hero windows; report the number to the user either way.

- [ ] **Step 5: Write the EDL**

Write `output/mini-pc/edl.json` using the solved values. Skeleton with every field this pipeline requires — fill `cuts_to_remove`, `speedups` and `captions` from Step 4's output:

```json
{
  "stage": "final",
  "source": "input/mini-pc.mp4",
  "segments": [
    {
      "index": 1,
      "title": "Mini PC Build — Circuit Rush",
      "filename_slug": "mini-pc-build-circuit-rush",
      "intensity": "medium",
      "start": 0.0,
      "end": 1816.373,
      "cuts_to_remove": [],
      "speedups": [],
      "captions": [],
      "bg_music": "input/Circuit Rush - The Mini Vandals.mp3",
      "bg_music_offset": 0.0,
      "cta_duration_sec": 2.697,
      "end_image": "input/mini-pc/final.jpg",
      "end_image_dur": 5.393
    },
    {
      "index": 2,
      "title": "Mini PC Build — Retrowave",
      "filename_slug": "mini-pc-build-retrowave",
      "intensity": "medium",
      "start": 0.0,
      "end": 1816.373,
      "cuts_to_remove": [],
      "speedups": [],
      "captions": [],
      "bg_music": "input/Land of the RetroOnes - RAGE.mp3",
      "bg_music_offset": 15.0,
      "cta_duration_sec": 3.345,
      "end_image": "input/mini-pc/final.jpg",
      "end_image_dur": 6.690
    }
  ]
}
```

Both segments carry the **same** `cuts_to_remove` and the same phase structure; only the solved `speedups` factors and the caption times differ, because the two targets and bar grids differ.

- [ ] **Step 6: Confirm the validator passed**

The PostToolUse hook runs `validate_edl` automatically on write. If it reported errors, fix the EDL and rewrite. Confirm explicitly:

```bash
uv run python -m src.validate_edl output/mini-pc/edl.json
```

Expected: `[validate_edl] output/mini-pc/edl.json OK`

- [ ] **Step 7: Show the user the EDL and get approval**

Per this repo's working style, the user approves the EDL **before** any cutting. Present: the phase table, the solved factors for both versions, the chapter card timings, and total dead time removed. Wait for approval.

- [ ] **Step 8: No commit — back the EDL up instead**

`.gitignore:20` (`/output/*`) covers `output/`, so the EDL is deliberately not version-controlled. Do **not** force-add it. It represents hours of judgement, so copy it somewhere it survives a `cut.py` rerun:

```bash
cp output/mini-pc/edl.json "C:/Temp/claude/C--Users-opari-OneDrive-Desktop-claude-code-lazy-video/40ac1b9b-661a-457b-b39b-cf3c5e1f4b8a/scratchpad/edl.approved.json"
```

---

### Task 7: Cut and draft-render

**Files:**
- Create: `output/mini-pc/clips/01_mini-pc-build-circuit-rush.mp4` + `.captions.json`
- Create: `output/mini-pc/clips/02_mini-pc-build-retrowave.mp4` + `.captions.json`
- Modify: `config.json`

**Interfaces:**
- Consumes: `output/mini-pc/edl.json` from Task 6; everything built in Tasks 1, 4 and 5.
- Produces: the two cut clips and their cues files, then two draft reels.

- [ ] **Step 1: Set the music level for a voiceless reel**

In `config.json`, under `brand`, the music is now the entire audio bed rather than something ducked under a voice:

```json
    "bg_music": "input/Circuit Rush - The Mini Vandals.mp3",
    "bg_music_volume": 0.7,
```

and set the CTA fallback to one bar of Circuit Rush (both segments override it anyway; this keeps the default coherent):

```json
      "duration_sec": 2.7,
```

- [ ] **Step 2: Cut both segments**

Run:

```bash
uv run python -m src.cut input/mini-pc.mp4
```

Expected: two `[cut] segment N ... -> M clip(s), M sped-up -> NN_slug.mp4` lines and no traceback.

- [ ] **Step 3: Verify the cut lengths against the plan**

Run:

```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 \
  "output/mini-pc/clips/01_mini-pc-build-circuit-rush.mp4"
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 \
  "output/mini-pc/clips/02_mini-pc-build-retrowave.mp4"
```

Expected: ≈ `48.5` and ≈ `36.8`, within about half a second. A large miss means the solve in Task 6 Step 4 used stale `CUTS` or `TIERS` that do not tile the span — fix there, not here.

- [ ] **Step 4: Draft-render the opening of reel A**

Run:

```bash
uv run python -m src.render input/mini-pc.mp4 --draft --frames 0-90 --concurrency 24
```

Watch the 3-second output. Expected: portrait framing, the box on the table, `MINI PC SAMPAI` readable, music audible and not clipping.

- [ ] **Step 5: Full draft render of both reels**

Run:

```bash
uv run python -m src.render input/mini-pc.mp4 --draft --concurrency 24
```

Watch both end to end. Check specifically:
- the photo beat appears and holds its full 2 bars — if the reel ends at the clip, `calculateMetadata` in Task 4 Step 3 was missed;
- the CTA is not truncated;
- reel B's music starts already in the groove, not in the silent intro — if it starts silent, `trimBefore` is not wired;
- chapter cards are readable and land on the beat;
- no fast-forward section strobes badly.

- [ ] **Step 6: Show the user both drafts and collect tweaks**

Present both. Expect iteration on wording, caption position, music volume and the ending buffer. Most tweaks are a `config.json` or EDL edit plus a render-only re-run — do not re-cut unless the cut ranges themselves change.

- [ ] **Step 7: Commit the config change**

```bash
git add config.json
git commit -m "chore: music becomes the full audio bed for voiceless reels"
```

---

### Task 8: Final render

**Files:**
- Create: `output/mini-pc/01_mini-pc-build-circuit-rush.mp4`
- Create: `output/mini-pc/02_mini-pc-build-retrowave.mp4`

**Interfaces:**
- Consumes: everything above.
- Produces: the two finished reels.

- [ ] **Step 1: Render at full resolution**

Close any media player holding a previous render open (`WinError 32` on Windows), then run:

```bash
uv run python -m src.render input/mini-pc.mp4
```

Expected: `[render] 2 reels -> output/mini-pc`

- [ ] **Step 2: Verify both outputs**

Run:

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height \
  -show_entries format=duration -of default=nw=1 "output/mini-pc/01_mini-pc-build-circuit-rush.mp4"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height \
  -show_entries format=duration -of default=nw=1 "output/mini-pc/02_mini-pc-build-retrowave.mp4"
```

Expected: `1080x1920` for both; durations ≈ `56.6` and ≈ `46.8`.

Durations that match the clip lengths (48.5 / 36.8) instead mean the photo beat and CTA were dropped from the composition length.

- [ ] **Step 3: Watch both reels end to end**

Required before calling this done — the repo has no automated way to catch a desynced caption, a truncated CTA, or a photo that never appears.

- [ ] **Step 4: Report**

Report both output paths, both durations, the total dead time cut, and the final speedup factors. State plainly anything that came out worse than planned rather than rounding it up to success.

---

## Self-Review

**Spec coverage** — every section maps to a task:

| Spec section | Task |
|---|---|
| Proxy build (Stage 0) | 3 |
| `src/motion.py` dead-frame detection | 2 |
| Hand-written `edl.json`, tiered speedups, chapter cards | 6 |
| Caption local→source inversion | 6 (Step 4 helper) |
| Per-segment music override + offset | 5 |
| `endImage` final photo beat | 4 |
| `cut_points_sec` bug | 1 |
| Validator asset-existence check | 5 |
| Config: music volume, CTA duration | 7 |
| Testing checklist | 2, 3, 7, 8 |

**Placeholder scan:** the only intentionally empty values are `CUTS` and `TIERS` in the Task 6 scratchpad helper and the matching EDL arrays — these are outputs of Steps 1-4 of that same task, which specify exactly how to derive them. No "TBD", no "add error handling", no "similar to Task N".

**Type consistency:** `stage_asset` (Task 5) is the single asset-staging path used for both music and end image; `end_image` / `end_image_dur` are named identically in the EDL, in `cut.py`'s cues, and as `endImage` / `endImageDur` in props; `bg_music_offset` → `bgMusicOffset` → `trimBefore` is the one conversion, done once in `Reel.tsx` at `Math.round(offset * fps)`. `cut_points_sec` accepts both 2- and 3-element ranges, so Task 1 does not break existing cues files.

**One gap found and fixed while reviewing:** Task 4 Step 4 originally passed `end_image_src` from `run()`, which Task 5 then rewrote to read from the cues. The step now explicitly says to leave the call site passing `""` until Task 5 wires it, so Task 4 is independently testable without a half-built interface.
