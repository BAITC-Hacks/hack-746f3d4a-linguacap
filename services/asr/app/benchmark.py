"""Run a privacy-preserving timing comparison on the same local VAD chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
from time import perf_counter

from app.audio import cleanup_workspace, create_workspace, prepare_audio
from app.config import get_settings
from app.nemo_transcription import LocalNemoTranscriber
from app.transcription import LocalRukkTranscriber


def _peak_memory_mb() -> float:
    """Return the current process peak RSS in MiB on macOS and Linux."""
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(peak_rss / divisor, 1)


def benchmark(recording: Path, engine_name: str) -> dict[str, object]:
    settings = get_settings()
    engine = LocalRukkTranscriber(settings) if engine_name == "rukk" else LocalNemoTranscriber(settings)
    workspace = create_workspace(settings)
    try:
        prepared = prepare_audio(recording, workspace, settings)
        started_at = perf_counter()
        texts = [engine.transcribe(chunk.path) for chunk in prepared.chunks]
        elapsed_seconds = perf_counter() - started_at
        return {
            "engine": engine_name,
            "device": engine.device,
            "source_duration_seconds": round(prepared.source.duration_seconds, 3),
            "chunk_count": len(prepared.chunks),
            "transcription_seconds": round(elapsed_seconds, 3),
            "realtime_factor": round(elapsed_seconds / prepared.source.duration_seconds, 3)
            if prepared.source.duration_seconds
            else None,
            "speed_x_realtime": round(prepared.source.duration_seconds / elapsed_seconds, 3) if elapsed_seconds else None,
            "nonempty_segments": sum(bool(text) for text in texts),
            "peak_process_memory_mb": _peak_memory_mb(),
        }
    finally:
        cleanup_workspace(workspace, settings)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark a local ASR engine without printing transcript text.")
    parser.add_argument("engine", choices=("rukk", "nemo"))
    parser.add_argument("recording", type=Path)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.recording, args.engine), ensure_ascii=False))
