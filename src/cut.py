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


def remap_time(t: float, seg_start: float, cuts: list[dict]) -> float:
    """Map an original-source timestamp onto the cut clip's local timeline."""
    removed = 0.0
    for c in sorted(cuts, key=lambda c: c["start"]):
        if t >= c["end"]:
            removed += c["end"] - c["start"]
        elif t > c["start"]:          # inside a cut -> clamp to its start
            t = c["start"]
            break
    return round(max(0.0, t - seg_start - removed), 3)


def remap_captions(captions: list[dict], seg_start: float, cuts: list[dict]) -> list[dict]:
    out = []
    for cap in captions:
        s = remap_time(cap["start"], seg_start, cuts)
        e = remap_time(cap["end"], seg_start, cuts)
        if e - s > 0.05:
            out.append({"start": s, "end": e, "text": cap["text"]})
    return out


def build_filter(ranges: list[tuple[float, float]]) -> str:
    """ffmpeg filter_complex: trim each keep-range, reset PTS, concat A/V."""
    parts, labels = [], []
    for i, (s, e) in enumerate(ranges):
        parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(ranges)}:v=1:a=1[v][a]")
    return ";".join(parts)


def cut_segment(video: Path, seg: dict, clips_dir: Path, cfg: dict) -> dict:
    ranges = keep_ranges(seg["start"], seg["end"], seg["cuts_to_remove"])
    if not ranges:
        sys.exit(f"[cut] segment {seg['index']} has no content after cuts")

    name = f"{seg['index']:02d}_{seg['filename_slug']}"
    clip_path = clips_dir / f"{name}.mp4"
    out = cfg["output"]

    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-filter_complex", build_filter(ranges),
        "-map", "[v]", "-map", "[a]",
        "-c:v", out["vcodec"], "-crf", str(out["crf"]), "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(out["fps"]),
        "-c:a", out["acodec"], "-b:a", "160k",
        str(clip_path),
    ]
    print(f"[cut] segment {seg['index']} '{seg['title']}' "
          f"-> {len(ranges)} keep-range(s) -> {clip_path.name}")
    subprocess.run(cmd, check=True, capture_output=True)

    captions = remap_captions(seg["captions"], seg["start"], seg["cuts_to_remove"])
    cues_path = clips_dir / f"{name}.captions.json"
    duration = round(sum(e - s for s, e in ranges), 3)
    cues_path.write_text(json.dumps({
        "clip": clip_path.name,
        "index": seg["index"],
        "title": seg["title"],
        "intensity": seg["intensity"],
        "duration": duration,
        "keep_ranges": ranges,          # source-time, for debugging punch-in points
        "captions": captions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"clip": str(clip_path), "duration": duration, "captions": len(captions)}


def run(video: Path, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    out_dir = output_dir_for(video)
    edl_path = out_dir / "edl.json"
    if not edl_path.exists():
        sys.exit(f"[cut] approved edl.json not found: {edl_path} (run stage 2 first)")
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    if edl.get("stage") != "final":
        print("[cut] WARNING: edl.json is not marked 'final' (not LLM-approved?)")

    clips_dir = out_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

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
