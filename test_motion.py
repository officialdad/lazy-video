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
