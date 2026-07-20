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
