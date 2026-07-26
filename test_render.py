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
