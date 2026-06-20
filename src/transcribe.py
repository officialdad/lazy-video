"""Stage 1 - Transcribe.

Run faster-whisper on a portrait recording and emit word-level timestamps.
Multilingual (mixed Bahasa Malaysia + English); never force-translate.

Usage:
    uv run python -m src.transcribe input/video.mp4
    uv run python -m src.transcribe input/video.mp4 --out output/video/transcript.json

Output JSON shape:
    {
      "source": "input/video.mp4",
      "language": "ms",           # auto-detected dominant language
      "duration": 612.3,
      "model": "large-v3",
      "device": "cuda",
      "segments": [ {"id": 0, "start": 0.0, "end": 4.2, "text": "..."} ],
      "words":    [ {"word": "Apa", "start": 0.40, "end": 0.61, "prob": 0.98} ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import add_cuda_dll_dirs, load_config, output_dir_for


def transcribe(video: Path, cfg: dict) -> dict:
    """Transcribe a video to word-level timestamps using faster-whisper."""
    add_cuda_dll_dirs()  # register nvidia wheel DLL dirs before CUDA loads
    from faster_whisper import WhisperModel

    model_name = cfg["whisper_model"]
    device = cfg["whisper_device"]
    compute_type = cfg["whisper_compute_type"]

    print(f"[transcribe] loading {model_name} on {device} ({compute_type}) ...")
    t0 = time.time()
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:  # pragma: no cover - hardware/runtime dependent
        if device != "cpu":
            print(f"[transcribe] {device} load failed ({exc}); falling back to cpu/int8")
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            device, compute_type = "cpu", "int8"
        else:
            raise
    print(f"[transcribe] model ready in {time.time() - t0:.1f}s")

    # language=None -> auto-detect; task='transcribe' -> never translate.
    # word_timestamps=True is the whole point of this stage.
    segments_iter, info = model.transcribe(
        str(video),
        language=None,
        task="transcribe",
        word_timestamps=True,
        vad_filter=False,
    )

    segments: list[dict] = []
    words: list[dict] = []
    print(f"[transcribe] detected language={info.language} "
          f"(p={info.language_probability:.2f}); transcribing ...")
    for seg in segments_iter:
        segments.append(
            {"id": seg.id, "start": round(seg.start, 3),
             "end": round(seg.end, 3), "text": seg.text.strip()}
        )
        for w in (seg.words or []):
            words.append(
                {"word": w.word.strip(), "start": round(w.start, 3),
                 "end": round(w.end, 3), "prob": round(w.probability, 3)}
            )
        # progress: print each segment as it streams in
        print(f"  [{seg.start:7.2f} -> {seg.end:7.2f}] {seg.text.strip()}")

    return {
        "source": str(video),
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 3),
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "segments": segments,
        "words": words,
    }


def run(video: Path, out: Path | None = None, cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    if not video.exists():
        sys.exit(f"[transcribe] input not found: {video}")
    if out is None:
        out = output_dir_for(video) / "transcript.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    result = transcribe(video, cfg)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[transcribe] {len(result['words'])} words, "
          f"{len(result['segments'])} segments -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 1 - transcribe to word timestamps")
    ap.add_argument("video", type=Path, help="input .mp4/.mov")
    ap.add_argument("--out", type=Path, default=None, help="output transcript.json path")
    args = ap.parse_args()
    run(args.video, args.out)


if __name__ == "__main__":
    main()
