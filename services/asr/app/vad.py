"""A deterministic, local baseline voice-activity detector.

It intentionally has no network or model dependency. The Stage 3 ASR pipeline
can replace it with a model-backed detector while retaining these time spans.
"""

from __future__ import annotations

import math
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpeechSegment:
    start_seconds: float
    end_seconds: float


def _rms_dbfs(frame: bytes) -> float:
    samples = array("h")
    samples.frombytes(frame)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return -120.0

    mean_square = sum(sample * sample for sample in samples) / len(samples)
    if mean_square <= 0:
        return -120.0
    return 20 * math.log10(math.sqrt(mean_square) / 32768)


def detect_speech_segments(
    wav_path: Path,
    *,
    threshold_db: float,
    min_speech_seconds: float,
    min_silence_seconds: float,
    frame_ms: int = 30,
) -> list[SpeechSegment]:
    """Find speech-like intervals in the normalized 16-bit mono WAV file."""
    with wave.open(str(wav_path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError("VAD accepts only 16-bit mono WAV files.")

        sample_rate = source.getframerate()
        frame_samples = max(1, round(sample_rate * frame_ms / 1_000))
        frame_duration = frame_samples / sample_rate
        voiced_ranges: list[SpeechSegment] = []
        frame_index = 0

        while frame := source.readframes(frame_samples):
            start_seconds = frame_index * frame_duration
            end_seconds = start_seconds + len(frame) / (source.getsampwidth() * source.getnchannels() * sample_rate)
            if _rms_dbfs(frame) >= threshold_db:
                voiced_ranges.append(SpeechSegment(start_seconds, end_seconds))
            frame_index += 1

    if not voiced_ranges:
        return []

    merged: list[SpeechSegment] = []
    current = voiced_ranges[0]
    for segment in voiced_ranges[1:]:
        if segment.start_seconds - current.end_seconds <= min_silence_seconds:
            current = SpeechSegment(current.start_seconds, segment.end_seconds)
        else:
            if current.end_seconds - current.start_seconds >= min_speech_seconds:
                merged.append(current)
            current = segment

    if current.end_seconds - current.start_seconds >= min_speech_seconds:
        merged.append(current)
    return merged
