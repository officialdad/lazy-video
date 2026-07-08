"""Stage 4 - Render branded reels (Remotion).

For each cut clip + its captions.json, build Remotion props and render one
finished reel: intro sting -> content (gentle drift + punch-in + captions +
progress bar) -> outro CTA, at the configured resolution/fps.

Remotion's public dir is the repo root, so props reference repo-relative paths
(clips in output/, brand assets in assets/) via staticFile().

Outputs:
    output/<name>/NN_slug.mp4

Usage:
    uv run python -m src.render input/video.mp4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .config import ROOT, load_config, output_dir_for


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def ffprobe_dims(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        check=True, capture_output=True, text=True,
    )
    w, h = out.stdout.strip().split("x")[:2]
    return int(w), int(h)


def cut_points_sec(keep_ranges: list[list[float]]) -> list[float]:
    """Clip-local times where shots join (punch-in points), plus 0 for the opening."""
    points = [0.0]
    cum = 0.0
    for r in keep_ranges[:-1]:
        cum += r[1] - r[0]
        points.append(round(cum, 3))
    return points


def render_clip(cues_path: Path, cfg: cfg_t, public_dir: Path,
                intro_src: str, intro_dur: float, out_dir: Path,
                bg_music_src: str = "", bg_music_vol: float = 0.0,
                extra_flags: list[str] | None = None) -> Path:
    """Render one reel. Media is staged in public_dir; props use basenames."""
    cues = json.loads(cues_path.read_text(encoding="utf-8"))
    clip_path = cues_path.with_name(cues["clip"])
    name = clip_path.stem
    out_path = out_dir / f"{name}.mp4"

    # stage the clip into the (small) public dir so staticFile() can reach it
    shutil.copy2(clip_path, public_dir / clip_path.name)

    # blurred cover bg is only needed when the clip aspect != output aspect
    # (a matched-aspect clip fills the frame, so skipping it saves a decode/frame)
    cw, ch = ffprobe_dims(clip_path)
    out_ar = cfg["output"]["width"] / cfg["output"]["height"]
    cover_bg = abs(cw / ch - out_ar) > 0.01

    brand = dict(cfg["brand"])
    brand.setdefault("bg_color", "#0B132B")
    cta = brand.get("cta", {"text": "FOLLOW & STAY TUNED", "duration_sec": 1.6})

    props = {
        "clipSrc": clip_path.name,        # basename; public dir = staging dir
        "introSrc": intro_src,            # "" when intro disabled (reel starts cold)
        "introDur": intro_dur,
        "clipDur": cues["duration"],
        "title": cues["title"],
        "intensity": cues["intensity"],
        "captions": cues["captions"],     # each caption carries per-word timing
        "cutPointsSec": cut_points_sec(cues["keep_ranges"]),
        "cta": {"text": cta["text"], "durationSec": cta.get("duration_sec", 1.6)},
        "brand": brand,
        "bgMusic": bg_music_src,
        "bgMusicVolume": bg_music_vol,
        "coverBg": cover_bg,
    }
    props_path = public_dir / f"{name}.props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    print(f"[render] {name}  ({cues['duration']}s content) -> {out_path.name}")
    subprocess.run(
        ["npx", "remotion", "render", "Reel", str(out_path.resolve()),
         f"--props={props_path.resolve()}", f"--public-dir={public_dir.resolve()}",
         *(extra_flags or [])],
        check=True, cwd=ROOT / "remotion", shell=(sys.platform == "win32"),
    )
    return out_path


cfg_t = dict  # alias for readability


def run(video: Path, cfg: dict | None = None, *,
        draft: bool = False, concurrency: int | None = None,
        frames: str | None = None, gl: str | None = None,
        hwaccel: str = "disable", binaries_dir: str | None = None) -> list[Path]:
    cfg = cfg or load_config()

    # speed flags for iterative editing (final render passes none of these)
    extra_flags: list[str] = []
    if draft:
        extra_flags.append("--scale=0.5")      # 1/4 the pixels -> ~3-4x faster preview
    if concurrency:
        extra_flags.append(f"--concurrency={concurrency}")
    if frames:
        extra_flags.append(f"--frames={frames}")  # e.g. "0-90" to preview just the opening
    if gl:
        extra_flags.append(f"--gl={gl}")          # "angle" = GPU-accelerate the blur
    if hwaccel and hwaccel != "disable":
        # NVENC (Windows/Linux) or VideoToolbox (macOS) encode; falls back to CPU
        # with "if-possible". Only speeds the encode stage, not the frame decode.
        extra_flags.append(f"--hardware-acceleration={hwaccel}")
    # Windows: Remotion's bundled ffmpeg lacks NVENC -- point it at an external
    # nvenc-capable ffmpeg (dir must hold ffmpeg.exe + ffprobe.exe) for hw encode.
    binaries_dir = binaries_dir or cfg.get("render_binaries_dir") or None
    if binaries_dir and hwaccel not in (None, "disable"):
        extra_flags.append(f"--binaries-directory={binaries_dir}")
    if extra_flags:
        print(f"[render] speed flags: {' '.join(extra_flags)}")
    out_dir = output_dir_for(video)
    clips_dir = out_dir / "clips"
    cue_files = sorted(clips_dir.glob("*.captions.json"))
    if not cue_files:
        sys.exit(f"[render] no clip captions in {clips_dir} (run stage 3 first)")

    # clear stale rendered reels so output matches the current clip set
    for old in out_dir.glob("[0-9][0-9]_*.mp4"):
        old.unlink()

    # small staging dir so Remotion isn't copying the whole repo (node_modules)
    public_dir = out_dir / "_render_public"
    public_dir.mkdir(parents=True, exist_ok=True)

    # intro is off by default -- reels start cold on content (the hook).
    if cfg["brand"].get("show_intro", False):
        intro = ROOT / cfg["brand"]["intro_asset"]
        shutil.copy2(intro, public_dir / "intro.mp4")
        intro_src, intro_dur = "intro.mp4", ffprobe_duration(intro)
    else:
        intro_src, intro_dur = "", 0.0

    # stage optional background music into the public dir (referenced by basename)
    bg_music = cfg["brand"].get("bg_music", "")
    if bg_music:
        bgm_ext = Path(bg_music).suffix or ".mp3"
        shutil.copy2(ROOT / bg_music, public_dir / f"bgm{bgm_ext}")
        bg_src, bg_vol = f"bgm{bgm_ext}", cfg["brand"].get("bg_music_volume", 0.15)
    else:
        bg_src, bg_vol = "", 0.0

    try:
        outputs = [render_clip(cf, cfg, public_dir, intro_src, intro_dur, out_dir,
                               bg_src, bg_vol, extra_flags)
                   for cf in cue_files]
    finally:
        shutil.rmtree(public_dir, ignore_errors=True)
    print(f"[render] {len(outputs)} reels -> {out_dir}")
    return outputs


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 4 - render branded reels")
    ap.add_argument("video", type=Path, help="input video")
    ap.add_argument("--draft", action="store_true",
                    help="half-scale preview (~3-4x faster); re-run without for final")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="parallel render threads (default ~half your cores)")
    ap.add_argument("--frames", default=None,
                    help="render only a frame range, e.g. 0-90 for the first 3s at 30fps")
    ap.add_argument("--gl", default=None,
                    help="GL backend; 'angle' GPU-accelerates the blur")
    ap.add_argument("--hwaccel", default="disable",
                    choices=["disable", "if-possible", "required"],
                    help="hardware (NVENC) encode; needs --binaries-directory on Windows")
    ap.add_argument("--binaries-directory", dest="binaries_dir", default=None,
                    help="dir with an ffmpeg that has BOTH h264_nvenc AND libfdk_aac (Windows NVENC)")
    args = ap.parse_args()
    run(args.video, draft=args.draft, concurrency=args.concurrency,
        frames=args.frames, gl=args.gl, hwaccel=args.hwaccel,
        binaries_dir=args.binaries_dir)


if __name__ == "__main__":
    main()
