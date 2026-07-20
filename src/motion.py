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

    Index i is the tblend diff across the interval [i, i+1], not a snapshot of
    second i alone -- so a run of low values at indices a..b-1 means stillness
    over [a, b]. The reported `end` is therefore up to 1s short of the true still
    window (the final still second has no successor to prove it's still). That's
    deliberate: keep footage when in doubt -- deleting real content is the costly
    mistake, an extra second of stillness is not. A value exactly at the threshold
    counts as motion."""
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
