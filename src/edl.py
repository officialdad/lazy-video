"""Stage 2 - Edit Decision List (mechanical draft).

This module does ONLY the mechanical pass. It reads transcript.json and emits
a DRAFT edl.json:

  - segment by marker phrases  (each marker = boundary; N markers -> N+1 reels)
  - detect flub regions        (flub word -> cut back to start of its sentence)
  - detect silence regions      (inter-segment gaps > threshold; never mid-sentence)
  - copy raw captions per segment (whisper segment text, in source time)

It deliberately does NOT write hook titles, clean captions, or restore technical
terms -- that is the LLM final pass (done in-session), which rewrites the draft
into the approved edl.json. See CLAUDE.md.

Caption timestamps in the EDL are in ORIGINAL SOURCE time. Stage 3 (cut.py)
remaps them to clip-local time after removing cut regions.

Usage:
    uv run python -m src.edl input/video.mp4
    uv run python -m src.edl input/video.mp4 --out output/video/edl.draft.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .config import load_config, output_dir_for, slugify


def _norm(token: str) -> str:
    """Lowercase, strip surrounding punctuation, for phrase matching."""
    return re.sub(r"[^\w]", "", token.lower())


def find_phrase_hits(words: list[dict], phrase: str) -> list[tuple[int, int]]:
    """Return [(start_idx, end_idx_inclusive)] word-index spans matching phrase."""
    tokens = [_norm(t) for t in phrase.split() if _norm(t)]
    if not tokens:
        return []
    norm_words = [_norm(w["word"]) for w in words]
    hits: list[tuple[int, int]] = []
    i = 0
    n, m = len(norm_words), len(tokens)
    while i <= n - m:
        if norm_words[i:i + m] == tokens:
            hits.append((i, i + m - 1))
            i += m
        else:
            i += 1
    return hits


def segment_by_markers(words: list[dict], marker_phrases: list[str],
                       keep_in_segment: bool = False) -> list[dict]:
    """Split words into segments at marker phrases.

    keep_in_segment=False: marker phrase is dropped (old behavior).
    keep_in_segment=True : marker phrase stays as the segment's spoken lead-out,
                           so the boundary is the END of the phrase ("...adalah")
                           and the next segment starts at the following word.
    """
    spans: list[tuple[int, int]] = []
    for ph in marker_phrases:
        spans.extend(find_phrase_hits(words, ph))
    spans.sort()

    segments: list[dict] = []
    cursor = 0
    bounds = spans + [(len(words), len(words))]  # sentinel tail
    for (m_start, m_end) in bounds:
        last = len(words) - 1 if m_start == len(words) else (m_end if keep_in_segment else m_start - 1)
        content = words[cursor:last + 1]
        if content:
            ends_on_marker = m_start != len(words)
            segments.append({
                "word_start_idx": cursor,
                "word_end_idx": last,
                "start": content[0]["start"],
                "end": content[-1]["end"],
                "ends_on_marker": ends_on_marker,
            })
        cursor = m_end + 1
    return segments


def detect_flubs(words: list[dict], segs_text: list[dict], flub_word: str) -> list[dict]:
    """flub word -> cut from start of the whisper sentence it sits in, through the flub."""
    target = _norm(flub_word)
    cuts: list[dict] = []
    for i, w in enumerate(words):
        if _norm(w["word"]) != target:
            continue
        # sentence start = start of the whisper segment containing this word's time
        sent_start = w["start"]
        for s in segs_text:
            if s["start"] <= w["start"] <= s["end"]:
                sent_start = s["start"]
                break
        cuts.append({"start": round(sent_start, 3), "end": round(w["end"], 3),
                     "reason": "flub"})
    return cuts


def detect_silences(segs_text: list[dict], threshold: float, pad: float = 0.15) -> list[dict]:
    """Inter-segment gaps longer than threshold -> trim, leaving a small breathing pad.

    Only trims gaps BETWEEN whisper segments, never inside one, so sentences keep
    their natural rhythm (gentle pacing for beginner content)."""
    cuts: list[dict] = []
    for a, b in zip(segs_text, segs_text[1:]):
        gap = b["start"] - a["end"]
        if gap > threshold:
            start = a["end"] + pad
            end = b["start"] - pad
            if end - start > 0.05:
                cuts.append({"start": round(start, 3), "end": round(end, 3),
                             "reason": "silence"})
    return cuts


def words_in_range(words: list[dict], start: float, end: float) -> list[dict]:
    """Words whose midpoint falls within [start, end] (source time)."""
    out = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        if start <= mid <= end:
            out.append({"w": w["word"], "start": w["start"], "end": w["end"]})
    return out


def captions_in_range(segs_text: list[dict], words: list[dict],
                      start: float, end: float) -> list[dict]:
    """Whisper captions whose midpoint falls within [start, end], each carrying the
    per-word timings (source time) that drive the karaoke reveal."""
    out = []
    for s in segs_text:
        mid = (s["start"] + s["end"]) / 2
        if start <= mid <= end:
            ws = words_in_range(words, s["start"], s["end"])
            out.append({"start": s["start"], "end": s["end"],
                        "text": s["text"], "words": ws})
    return out


def build_draft(transcript: dict, cfg: dict) -> dict:
    words = transcript["words"]
    segs_text = transcript["segments"]
    if not words:
        sys.exit("[edl] transcript has no words")

    marker_segments = segment_by_markers(
        words, cfg["marker_phrases"], cfg.get("marker_keep_in_segment", False))
    flub_cuts = detect_flubs(words, segs_text, cfg["flub_word"])
    silence_cuts = detect_silences(segs_text, cfg["silence_threshold_sec"])
    all_cuts = sorted(flub_cuts + silence_cuts, key=lambda c: c["start"])

    # every reel ends with the swipe-left CTA card (it replaces the outro sting)
    segments_out: list[dict] = []
    for idx, seg in enumerate(marker_segments, start=1):
        s, e = seg["start"], seg["end"]
        seg_cuts = [c for c in all_cuts if c["start"] >= s and c["end"] <= e]
        caps = captions_in_range(segs_text, words, s, e)
        first_text = caps[0]["text"] if caps else f"segment-{idx}"
        segments_out.append({
            "index": idx,
            "title": "",                     # LLM fills (hook title)
            "filename_slug": slugify(first_text)[:40],  # LLM may refine
            "start": round(s, 3),
            "end": round(e, 3),
            "cuts_to_remove": seg_cuts,
            "end_transition": "swipe_cta",
            "captions": caps,                # text + per-word timing; LLM cleans text
            "intensity": cfg["default_intensity"],
        })

    return {
        "source": transcript["source"],
        "stage": "draft",                    # LLM pass flips this to "final"
        "segments": segments_out,
    }


def run(video: Path, out: Path | None = None, cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    out_dir = output_dir_for(video)
    transcript_path = out_dir / "transcript.json"
    if not transcript_path.exists():
        sys.exit(f"[edl] transcript not found: {transcript_path} (run stage 1 first)")
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

    draft = build_draft(transcript, cfg)
    if out is None:
        out = out_dir / "edl.draft.json"
    out.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

    nflub = sum(len([c for c in s["cuts_to_remove"] if c["reason"] == "flub"])
                for s in draft["segments"])
    nsil = sum(len([c for c in s["cuts_to_remove"] if c["reason"] == "silence"])
               for s in draft["segments"])
    print(f"[edl] {len(draft['segments'])} segments, "
          f"{nflub} flub cuts, {nsil} silence cuts -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 2 - EDL mechanical draft")
    ap.add_argument("video", type=Path, help="input video (used to locate output dir)")
    ap.add_argument("--out", type=Path, default=None, help="output edl.draft.json path")
    args = ap.parse_args()
    run(args.video, args.out)


if __name__ == "__main__":
    main()
