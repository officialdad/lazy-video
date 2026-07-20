"""Stage 3 - Cut (ffmpeg).

Read the approved edl.json and slice the source video into one raw clip per
segment, removing the `cuts_to_remove` regions. Re-encode (not stream-copy) so
cuts are frame-accurate and clips concatenate cleanly.

For each segment also emit a clip-local caption file the Remotion renderer
(Stage 4) consumes -- caption times in the EDL are in ORIGINAL source time, so
here we remap them onto the cut clip's timeline.

Outputs:
    output/<name>/clips/NN_slug.mp4
    output/<name>/clips/NN_slug.captions.json   (title, intensity, clip-local cues)

Usage:
    uv run python -m src.cut input/video.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .config import load_config, output_dir_for
from .validate_edl import validate


def keep_ranges(start: float, end: float, cuts: list[dict]) -> list[tuple[float, float]]:
    """Segment span minus cut regions -> list of (start, end) ranges to keep."""
    cuts = sorted(cuts, key=lambda c: c["start"])
    ranges: list[tuple[float, float]] = []
    cur = start
    for c in cuts:
        cs, ce = max(c["start"], start), min(c["end"], end)
        if cs > cur:
            ranges.append((cur, cs))
        cur = max(cur, ce)
    if end > cur:
        ranges.append((cur, end))
    return [(s, e) for s, e in ranges if e - s > 0.02]


def apply_speedups(ranges: list[tuple[float, float]],
                   speedups: list[dict]) -> list[tuple[float, float, float]]:
    """Tag each keep-range with a playback speed, splitting where a speedup starts/ends.

    Returns ordered (start, end, speed) clips -- speed 1.0 = normal, >1.0 = fast-forward
    (e.g. the no-speech coding demo). Speedups must not overlap cuts (validator enforces)."""
    sp = sorted(speedups, key=lambda z: z["start"])
    clips: list[tuple[float, float, float]] = []
    for s, e in ranges:
        cur = s
        for z in sp:
            zs, ze = max(z["start"], cur), min(z["end"], e)
            if zs >= ze:               # no (remaining) overlap with this range
                continue
            if zs > cur:               # normal-speed lead-in before the speedup
                clips.append((cur, zs, 1.0))
            clips.append((zs, ze, float(z["factor"])))
            cur = ze
        if e > cur:
            clips.append((cur, e, 1.0))
    return clips


def atempo_chain(speed: float) -> str:
    """atempo only accepts 0.5-2.0 per instance; chain to reach any factor."""
    factors, r = [], speed
    while r > 2.0 + 1e-9:
        factors.append("atempo=2.0"); r /= 2.0
    while r < 0.5 - 1e-9:
        factors.append("atempo=0.5"); r /= 0.5
    factors.append(f"atempo={r:.4f}")
    return ",".join(factors)


def remap_time(t: float, clips: list[tuple[float, float, float]]) -> float:
    """Map an original-source timestamp onto the cut clip's local timeline.

    Elapsed time inside a sped-up clip is divided by its speed; time landing in a
    removed gap clamps to the local position where the gap was."""
    local = 0.0
    for s, e, speed in clips:
        if t >= e:
            local += (e - s) / speed
        elif t > s:                    # inside this clip
            return round(local + (t - s) / speed, 3)
        else:                          # t is before this clip -> it fell in a cut gap
            break
    return round(local, 3)


def remap_captions(captions: list[dict],
                   clips: list[tuple[float, float, float]]) -> list[dict]:
    out = []
    for cap in captions:
        s = remap_time(cap["start"], clips)
        e = remap_time(cap["end"], clips)
        if e - s <= 0.05:
            continue
        words = []
        for w in cap.get("words", []):
            ws = remap_time(w["start"], clips)
            we = remap_time(w["end"], clips)
            if we >= ws:
                words.append({"w": w["w"], "start": ws, "end": we})
        out.append({"start": s, "end": e, "text": cap["text"], "words": words})
    return out


def build_filter(clips: list[tuple[float, float, float]]) -> str:
    """ffmpeg filter_complex: trim each clip, reset PTS (speeding if tagged), concat A/V.

    A fast-forward clip's audio is compressed to match (atempo) then muted -- sped-up
    keyboard/ambient would otherwise read as chipmunk noise over the quiet music bed.
    ponytail: mute is the sensible default for fast-forward; add an opt-in flag if a
    future speedup ever wants pitch-corrected audible audio."""
    parts, labels = [], []
    for i, (s, e, speed) in enumerate(clips):
        if speed == 1.0:
            vpts, af = "PTS-STARTPTS", "asetpts=PTS-STARTPTS"
        else:
            vpts = f"(PTS-STARTPTS)/{speed}"
            af = f"asetpts=PTS-STARTPTS,{atempo_chain(speed)},volume=0"
        parts.append(f"[0:v]trim=start={s}:end={e},setpts={vpts}[v{i}]")
        parts.append(f"[0:a]atrim=start={s}:end={e},{af}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(clips)}:v=1:a=1[v][a]")
    return ";".join(parts)


def cut_segment(video: Path, seg: dict, clips_dir: Path, cfg: dict) -> dict:
    ranges = keep_ranges(seg["start"], seg["end"], seg["cuts_to_remove"])
    clips = apply_speedups(ranges, seg.get("speedups") or [])
    if not clips:
        sys.exit(f"[cut] segment {seg['index']} has no content after cuts")

    name = f"{seg['index']:02d}_{seg['filename_slug']}"
    clip_path = clips_dir / f"{name}.mp4"
    out = cfg["output"]

    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-filter_complex", build_filter(clips),
        "-map", "[v]", "-map", "[a]",
        "-c:v", out["vcodec"], "-crf", str(out["crf"]), "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(out["fps"]),
        "-c:a", out["acodec"], "-b:a", "160k",
        str(clip_path),
    ]
    n_ff = sum(1 for _, _, sp in clips if sp != 1.0)
    print(f"[cut] segment {seg['index']} '{seg['title']}' "
          f"-> {len(clips)} clip(s){f', {n_ff} sped-up' if n_ff else ''} -> {clip_path.name}")
    subprocess.run(cmd, check=True, capture_output=True)

    captions = remap_captions(seg["captions"], clips)
    # visual overlays (arrows/highlights) ride the same source->clip time remap
    overlays = []
    for o in seg.get("overlays") or []:
        s, e = remap_time(o["start"], clips), remap_time(o["end"], clips)
        if e - s > 0.05:
            overlays.append({**o, "start": s, "end": e})
    cues_path = clips_dir / f"{name}.captions.json"
    duration = round(sum((e - s) / speed for s, e, speed in clips), 3)
    cues_path.write_text(json.dumps({
        "clip": clip_path.name,
        "index": seg["index"],
        "title": seg["title"],
        "intensity": seg["intensity"],
        "duration": duration,
        "keep_ranges": clips,           # source-time (start, end, speed), for debugging
        "captions": captions,
        "overlays": overlays,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"clip": str(clip_path), "duration": duration, "captions": len(captions)}


def run(video: Path, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    out_dir = output_dir_for(video)
    edl_path = out_dir / "edl.json"
    if not edl_path.exists():
        sys.exit(f"[cut] approved edl.json not found: {edl_path} (run stage 2 first)")
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    errs = validate(edl)
    if errs:
        sys.exit("[cut] edl.json failed validation:\n" + "\n".join(f"  - {e}" for e in errs))

    clips_dir = out_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    # clear stale clips so output reflects the CURRENT edl (segment count can change)
    for old in [*clips_dir.glob("*.mp4"), *clips_dir.glob("*.captions.json")]:
        old.unlink()

    results = [cut_segment(video, seg, clips_dir, cfg) for seg in edl["segments"]]
    print(f"[cut] {len(results)} clips -> {clips_dir}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 3 - cut clips from approved EDL")
    ap.add_argument("video", type=Path, help="input video")
    args = ap.parse_args()
    run(args.video)


if __name__ == "__main__":
    main()
