"""Shared config + path helpers for the pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path

# repo root = parent of src/
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_ROOT = ROOT / "output"


def load_config(path: Path | None = None) -> dict:
    """Load config.json from the repo root (or an explicit path)."""
    path = path or CONFIG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def video_name(video: Path) -> str:
    """Stem used to name the per-video output folder."""
    return video.stem


def output_dir_for(video: Path) -> Path:
    """output/<video-name>/, created on demand."""
    d = OUTPUT_ROOT / video_name(video)
    d.mkdir(parents=True, exist_ok=True)
    return d


def slugify(text: str) -> str:
    """Lowercase ascii slug for filenames (BM/English titles -> kebab-case)."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "segment"
