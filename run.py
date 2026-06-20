"""Single entrypoint - chain all four pipeline stages.

Stage 2 pauses for approval: the mechanical draft EDL is written, then Claude
(in-session) does the final pass into edl.json and the user approves it. Only
once edl.json is marked "final" do cut + render run.

Flow:
    uv run python run.py input/video.mp4
      -> Stage 1 transcribe (if transcript.json missing)
      -> Stage 2 draft EDL, then STOP for the LLM final pass + user approval
    # Claude rewrites edl.draft.json -> edl.json (stage: "final"); user approves
    uv run python run.py input/video.mp4
      -> sees approved edl.json -> Stage 3 cut -> Stage 4 render -> reels

Force a specific stage with --stage {transcribe,edl,cut,render,all}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src import cut, edl, render, transcribe
from src.config import load_config, output_dir_for


def _edl_is_final(out_dir: Path) -> bool:
    p = out_dir / "edl.json"
    if not p.exists():
        return False
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("stage") == "final"
    except json.JSONDecodeError:
        return False


PAUSE_MSG = """
================================================================================
 STAGE 2 PAUSED FOR APPROVAL
================================================================================
 Draft EDL written:   {draft}

 Next (in your Claude Code session):
   1. Claude reads transcript.json + edl.draft.json and writes the FINAL EDL to
      {final}
      - fix transcription errors, restore terms (cloud code -> Claude Code)
      - preserve the BM/English mix (never translate)
      - write hook titles + filename slugs, sanity-check cut regions
      - set  "stage": "final"
   2. You review and approve edl.json.
   3. Re-run the same command to cut + render:
        uv run python run.py {video}
================================================================================
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the reel pipeline end to end")
    ap.add_argument("video", type=Path)
    ap.add_argument("--stage", choices=["transcribe", "edl", "cut", "render", "all"],
                    default="all")
    args = ap.parse_args()

    video: Path = args.video
    if not video.exists():
        sys.exit(f"[run] input not found: {video}")
    cfg = load_config()
    out_dir = output_dir_for(video)
    transcript = out_dir / "transcript.json"

    only = args.stage

    if only in ("transcribe", "all") and (only == "transcribe" or not transcript.exists()):
        transcribe.run(video, cfg=cfg)
    if only == "transcribe":
        return

    if only in ("edl", "all"):
        if only == "edl" or not _edl_is_final(out_dir):
            draft = edl.run(video, cfg=cfg)
            print(PAUSE_MSG.format(
                draft=draft, final=out_dir / "edl.json", video=video))
            return  # wait for the LLM final pass + user approval

    if only in ("cut", "all"):
        if not _edl_is_final(out_dir):
            sys.exit(f"[run] {out_dir / 'edl.json'} not approved (stage != final)")
        cut.run(video, cfg=cfg)
    if only == "cut":
        return

    if only in ("render", "all"):
        outputs = render.run(video, cfg=cfg)
        print(f"\n[run] DONE - {len(outputs)} reels in {out_dir}")


if __name__ == "__main__":
    main()
