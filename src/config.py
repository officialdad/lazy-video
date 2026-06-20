"""Shared config + path helpers for the pipeline."""

from __future__ import annotations

import json
import os
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


def add_cuda_dll_dirs() -> None:
    """Make the nvidia pip-wheel CUDA DLLs discoverable on Windows.

    faster-whisper/ctranslate2 load cublas64_12.dll and cudnn at inference
    time, but Windows does not search site-packages/nvidia/*/bin by default.
    Register those dirs so the DLLs resolve. No-op off Windows / if absent.
    """
    if os.name != "nt":
        return
    try:
        import nvidia  # provided by the nvidia-* pip wheels
    except ImportError:
        return
    # `nvidia` is a namespace package: __file__ is None, use __path__.
    found: list[str] = []
    for root in map(Path, nvidia.__path__):
        for bindir in root.glob("*/bin"):
            found.append(str(bindir))
            try:
                os.add_dll_directory(str(bindir))
            except OSError:
                pass
    # add_dll_directory alone is not honored by ctranslate2's loader; also
    # prepend the dirs to PATH, which the DLL search does respect.
    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")


def slugify(text: str) -> str:
    """Lowercase ascii slug for filenames (BM/English titles -> kebab-case)."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "segment"
