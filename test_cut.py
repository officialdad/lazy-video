"""Runnable check for the cut.py timeline math (cuts + speedups -> clip-local time).

    uv run python test_cut.py

The remap is sync-critical: if elapsed time inside a sped-up region isn't divided
by its speed, every caption after the fast-forward drifts out of sync. These asserts
fail loudly if that breaks.
"""

from src.cut import keep_ranges, apply_speedups, remap_time, atempo_chain, remap_captions


def approx(a, b, eps=0.01):
    return abs(a - b) <= eps


# --- keep_ranges: span minus cuts ---
assert keep_ranges(0, 10, [{"start": 2, "end": 3}]) == [(0, 2), (3, 10)]
assert keep_ranges(0, 10, []) == [(0, 10)]

# --- apply_speedups: tag + split a keep-range at speedup edges ---
clips = apply_speedups([(0, 10)], [{"start": 4, "end": 7, "factor": 3}])
assert clips == [(0, 4, 1.0), (4, 7, 3.0), (7, 10, 1.0)], clips

# no speedups -> everything speed 1.0
assert apply_speedups([(0, 5)], []) == [(0, 5, 1.0)]

# --- remap_time: local timeline accounts for cuts AND speed compression ---
# clip layout: [0-4 @1x][4-7 @3x][7-10 @1x]
#   4s -> 4.0 (end of first clip)
#   7s -> 4 + 3/3 = 5.0 (sped region compresses 3s -> 1s)
#  10s -> 5 + 3 = 8.0
assert approx(remap_time(4, clips), 4.0)
assert approx(remap_time(7, clips), 5.0)
assert approx(remap_time(10, clips), 8.0)
# a point INSIDE the sped region: 5.5s -> 4 + (5.5-4)/3 = 4.5
assert approx(remap_time(5.5, clips), 4.5)

# with a leading cut removed, local starts at 0 at the first kept content
c2 = apply_speedups(keep_ranges(0, 20, [{"start": 5, "end": 8}]),
                    [{"start": 10, "end": 16, "factor": 6}])
# kept: [0-5 @1x][8-10 @1x][10-16 @6x][16-20 @1x]  (5 and 8-10 merge in source but stay split by the cut)
# a caption word at 16s (end of fast-forward) -> 5 + 2 + 6/6 = 8.0
assert approx(remap_time(16, c2), 8.0), remap_time(16, c2)
# word at 20s -> 8 + 4 = 12.0
assert approx(remap_time(20, c2), 12.0), remap_time(20, c2)

# --- atempo_chain: any factor decomposes into <=2.0 stages ---
assert atempo_chain(2.0) == "atempo=2.0000"
assert atempo_chain(6.0) == "atempo=2.0,atempo=2.0,atempo=1.5000"  # 2*2*1.5 = 6
assert atempo_chain(8.0) == "atempo=2.0,atempo=2.0,atempo=2.0000"
# each stage stays within ffmpeg's [0.5, 2.0] atempo limit
for f in (3.0, 6.0, 8.0, 5.0):
    prod = 1.0
    for stage in atempo_chain(f).split(","):
        v = float(stage.split("=")[1]); assert 0.5 <= v <= 2.0; prod *= v
    assert approx(prod, f), (f, prod)

# --- remap_captions: the "icon" field (chapter-card icons) must survive the remap ---
# no cuts/speedups -> identity timeline, so times below are unchanged
identity_clips = apply_speedups([(0, 10)], [])
caps_in = [
    {"start": 0, "end": 3, "text": "BUKA CASING", "words": [{"w": "BUKA CASING", "start": 0, "end": 3}],
     "icon": "screwdriver"},
    {"start": 3, "end": 6, "text": "PASANG RAM", "words": [{"w": "PASANG RAM", "start": 3, "end": 6}]},
]
caps_out = remap_captions(caps_in, identity_clips)
assert caps_out[0]["icon"] == "screwdriver", caps_out[0]
# a caption with no icon still produces a valid dict, with icon defaulting to ""
assert caps_out[1]["icon"] == "", caps_out[1]
assert set(caps_out[1].keys()) == {"start", "end", "text", "words", "icon"}, caps_out[1]

print("cut.py timeline math OK")
