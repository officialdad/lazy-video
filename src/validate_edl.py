"""Deterministic contract check for an approved edl.json.

Every skill invocation ends with Claude hand-writing edl.json; this enforces the
invariants that keep Stage 3/4 correct, the same way every time:
  - stage == "final", non-empty segments
  - kebab-case filename_slug, start < end
  - cuts_to_remove sorted, non-overlapping, inside the segment span
  - every caption has non-empty karaoke `words`, each with sane timing
  - caption `text` matches its joined `words` (karaoke renders words, not text)

Used two ways:
  - PostToolUse hook (.claude/settings.json): exit 2 + stderr feeds errors back
    to Claude the moment it writes a bad edl.json.
  - src/cut.py: validates before cutting, so script-written EDLs are gated too.

Usage: uv run python -m src.validate_edl output/<name>/edl.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .config import ROOT

EPS = 0.05  # tolerance for float timing comparisons
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def validate(edl: dict) -> list[str]:
    errs: list[str] = []
    if edl.get("stage") != "final":
        errs.append(f'stage must be "final", got {edl.get("stage")!r}')
    segments = edl.get("segments") or []
    if not segments:
        errs.append("segments is empty")

    for seg in segments:
        tag = f"segment {seg.get('index', '?')}"
        start, end = seg.get("start"), seg.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start >= end:
            errs.append(f"{tag}: bad span start={start} end={end}")
            continue
        if not SLUG_RE.match(seg.get("filename_slug") or ""):
            errs.append(f"{tag}: filename_slug {seg.get('filename_slug')!r} is not kebab-case")
        if seg.get("intensity") not in ("gentle", "medium", "hype"):
            errs.append(f"{tag}: intensity {seg.get('intensity')!r} invalid")

        cuts = sorted(seg.get("cuts_to_remove") or [], key=lambda c: c["start"])
        prev_end = None
        for c in cuts:
            cs, ce = c.get("start"), c.get("end")
            if cs is None or ce is None or cs >= ce:
                errs.append(f"{tag}: cut {cs}-{ce} has non-positive length")
                continue
            if cs < start - EPS or ce > end + EPS:
                errs.append(f"{tag}: cut {cs}-{ce} outside segment span {start}-{end}")
            if prev_end is not None and cs < prev_end - EPS:
                errs.append(f"{tag}: cut {cs}-{ce} overlaps previous cut ending {prev_end}")
            prev_end = ce

        # speedups (optional): fast-forward regions, e.g. a no-speech coding demo.
        # factor > 1, inside span, must not overlap a cut (cut wins -> ambiguous).
        for z in sorted(seg.get("speedups") or [], key=lambda z: z["start"]):
            zs, ze, f = z.get("start"), z.get("end"), z.get("factor")
            if zs is None or ze is None or zs >= ze:
                errs.append(f"{tag}: speedup {zs}-{ze} has non-positive length")
                continue
            if not isinstance(f, (int, float)) or f <= 1.0:
                errs.append(f"{tag}: speedup {zs}-{ze} factor {f!r} must be > 1")
            if zs < start - EPS or ze > end + EPS:
                errs.append(f"{tag}: speedup {zs}-{ze} outside segment span {start}-{end}")
            for c in cuts:
                if zs < c["end"] - EPS and c["start"] < ze - EPS:
                    errs.append(f"{tag}: speedup {zs}-{ze} overlaps cut {c['start']}-{c['end']}")

        # optional per-segment overrides: a music track, its start offset, the payoff
        # photo and the CTA length. Assets are checked here because discovering a bad
        # path during a render wastes the whole cut that preceded it.
        for key in ("bg_music", "end_image"):
            rel = seg.get(key)
            if rel and not (ROOT / rel).exists():
                errs.append(f"{tag}: {key} {rel!r} does not exist")
        for key in ("end_image_dur", "cta_duration_sec"):
            v = seg.get(key)
            if v is not None and (not isinstance(v, (int, float)) or v <= 0):
                errs.append(f"{tag}: {key} {v!r} must be a positive number")
        off = seg.get("bg_music_offset")
        if off is not None and (not isinstance(off, (int, float)) or off < 0):
            errs.append(f"{tag}: bg_music_offset {off!r} must be >= 0")

        # end_card (optional): title + icon/label payoff list over the end photo.
        end_card = seg.get("end_card")
        if end_card is not None:
            if not isinstance(end_card, dict):
                errs.append(f"{tag}: end_card must be an object")
            else:
                if not (end_card.get("title") or "").strip():
                    errs.append(f"{tag}: end_card.title is empty")
                items = end_card.get("items")
                if not items:
                    errs.append(f"{tag}: end_card.items is empty")
                else:
                    for i, item in enumerate(items):
                        if not isinstance(item, dict) or not (item.get("label") or "").strip():
                            errs.append(f"{tag}: end_card.items[{i}] has an empty label")

        for cap in seg.get("captions") or []:
            ctag = f"{tag} caption {cap.get('start')}s {cap.get('text', '')[:30]!r}"
            if not (cap.get("text") or "").strip():
                errs.append(f"{ctag}: empty text")
            if not isinstance(cap.get("start"), (int, float)) or cap["start"] >= cap.get("end", -1):
                errs.append(f"{ctag}: bad cue span")
            words = cap.get("words") or []
            if not words:
                errs.append(f"{ctag}: empty words[] (karaoke reveal has no timing)")
                continue
            for w in words:
                if not (w.get("w") or "").strip() or w.get("start") is None or w.get("end") is None \
                        or w["end"] < w["start"]:
                    errs.append(f"{ctag}: bad word entry {w!r}")
            joined = " ".join(w.get("w", "") for w in words)
            if " ".join(joined.split()) != " ".join((cap.get("text") or "").split()):
                errs.append(f"{ctag}: text != joined words ({joined!r})")
    return errs


def main() -> None:
    if sys.argv[1:] == ["--hook"]:
        # PostToolUse hook mode: hook JSON on stdin; no-op unless an edl.json was written
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError:
            return
        fp = (payload.get("tool_input") or {}).get("file_path") or ""
        if not fp.replace("\\", "/").endswith("edl.json") or not Path(fp).exists():
            return
        sys.argv[1:] = [fp]
    path = Path(sys.argv[1])
    try:
        edl = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[validate_edl] {path}: unreadable/invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    errs = validate(edl)
    if errs:
        print(f"[validate_edl] {path} FAILED ({len(errs)} error(s)):", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2)
    print(f"[validate_edl] {path} OK")


if __name__ == "__main__":
    main()
