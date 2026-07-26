"""Runnable check for the motion.py dead-region detector.

    uv run python test_motion.py

static_runs turns a per-second motion series into cuts_to_remove entries. The
run-boundary math is what decides whether real footage gets deleted, so the
edge cases (run at the very end, run one second too short) are asserted here.
"""

import subprocess
import tempfile
from pathlib import Path

from src.motion import static_runs, yavg_per_second

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

# --- smoke test: yavg_per_second against real ffmpeg output ---
# Everything above tests static_runs, a pure function -- it never touches ffmpeg.
# yavg_per_second shells out to ffmpeg and parses signalstats' metadata text with
# a regex; if a future ffmpeg changes that output format, the regex silently stops
# matching and yavg_per_second returns [] while every assert above keeps passing.
# This builds a real clip with a known static window and runs the actual filter
# chain, so that failure mode gets caught here instead of downstream as a
# confusing "no static runs found" from src.motion's CLI.
with tempfile.TemporaryDirectory() as tmp:
    fixture = Path(tmp) / "static_fixture.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=5",
        "-f", "lavfi", "-i", "color=c=navy:size=320x240:rate=10:duration=6",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=5",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
        str(fixture),
    ], check=True)

    yavg = yavg_per_second(fixture)
    # non-empty first: if the regex breaks, fail here with a clear message instead
    # of a mysterious empty-region result from static_runs below.
    assert yavg, "yavg_per_second returned no samples -- did ffmpeg's metadata format change?"

    runs = static_runs(yavg, 1.5, 3.0)
    # end is 10.0, not 11.0: the still window is t=5..11, but the last still second
    # (10->11) has no successor frame to diff against, so static_runs conservatively
    # excludes it -- this is the documented behavior in static_runs, not a bug.
    assert runs == [{"start": 5.0, "end": 10.0}], runs

print("motion.py ffmpeg filter chain OK")
