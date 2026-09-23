"""Private audio validation, FFmpeg normalization, VAD, and chunking."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import Settings
from app.vad import SpeechSegment, detect_speech_segments

SUPPORTED_AUDIO_TYPES: dict[str, frozenset[str]] = {
    ".mp3": frozenset({"audio/mpeg", "audio/mp3"}),
    ".wav": frozenset({"audio/wav", "audio/x-wav", "audio/wave"}),
    ".m4a": frozenset({"audio/mp4", "audio/x-m4a"}),
    ".mp4": frozenset({"video/mp4", "audio/mp4", "application/mp4"}),
}


class AudioValidationError(ValueError):
    """Input is not eligible for local audio preparation."""


class AudioProcessingError(RuntimeError):
    """A local decoder or conversion step could not process the recording."""


@dataclass(frozen=True)
class AudioProperties:
    duration_seconds: float
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class AudioChunk:
    chunk_id: str
    start_seconds: float
    end_seconds: float
    path: Path


@dataclass(frozen=True)
class PreparedAudio:
    source: AudioProperties
    normalized: AudioProperties
    normalized_path: Path
    chunks: tuple[AudioChunk, ...]


def _run(command: list[str], *, timeout_seconds: int = 300) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        raise AudioProcessingError("FFmpeg or FFprobe was not found in PATH.") from error
    except subprocess.TimeoutExpired as error:
        raise AudioProcessingError("Audio preparation exceeded the time limit.") from error

    if completed.returncode != 0:
        raise AudioProcessingError("FFmpeg could not process the supplied recording.")
    return completed.stdout


def extension_for_upload(filename: str | None, content_type: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    allowed_types = SUPPORTED_AUDIO_TYPES.get(extension)
    if allowed_types is None:
        raise AudioValidationError("Supported formats are MP3, WAV, M4A, and MP4.")

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type and normalized_content_type not in allowed_types:
        raise AudioValidationError("The file type does not match its filename extension.")
    return extension


async def store_upload(upload: UploadFile, destination: Path, *, max_bytes: int) -> Path:
    """Stream the upload to disk, enforcing the limit before excess data persists."""
    extension_for_upload(upload.filename, upload.content_type)
    total_bytes = 0
    chunk_size = 1_048_576

    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(chunk_size):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise AudioValidationError("The recording exceeds the configured size limit.")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if total_bytes == 0:
        destination.unlink(missing_ok=True)
        raise AudioValidationError("The uploaded recording is empty.")
    return destination


def probe_audio(source_path: Path, settings: Settings) -> AudioProperties:
    raw_result = _run(
        [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,sample_rate,channels",
            "-of",
            "json",
            str(source_path),
        ]
    )
    try:
        payload = json.loads(raw_result)
        duration_seconds = float(payload["format"]["duration"])
        audio_stream = next(stream for stream in payload.get("streams", []) if stream.get("codec_type") == "audio")
        sample_rate = int(audio_stream["sample_rate"])
        channels = int(audio_stream["channels"])
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AudioValidationError("The uploaded file does not contain a readable audio stream.") from error

    if duration_seconds <= 0:
        raise AudioValidationError("The uploaded recording has no audio duration.")
    if duration_seconds > settings.max_audio_duration_seconds:
        raise AudioValidationError("The recording exceeds the configured duration limit.")
    return AudioProperties(duration_seconds, sample_rate, channels)


def wav_properties(path: Path) -> AudioProperties:
    with wave.open(str(path), "rb") as source:
        sample_rate = source.getframerate()
        channels = source.getnchannels()
        duration_seconds = source.getnframes() / sample_rate if sample_rate else 0
        sample_width = source.getsampwidth()

    if sample_rate != 16_000 or channels != 1 or sample_width != 2:
        raise AudioProcessingError("FFmpeg did not produce 16 kHz, mono, 16-bit WAV audio.")
    return AudioProperties(duration_seconds, sample_rate, channels)


def normalize_audio(source_path: Path, destination: Path, settings: Settings) -> AudioProperties:
    _run(
        [
            settings.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
    )
    return wav_properties(destination)


def _chunk_ranges(
    segments: list[SpeechSegment], *, chunk_duration_seconds: float, chunk_overlap_seconds: float
) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for segment in segments:
        start_seconds = segment.start_seconds
        while start_seconds < segment.end_seconds:
            end_seconds = min(start_seconds + chunk_duration_seconds, segment.end_seconds)
            ranges.append((start_seconds, end_seconds))
            if end_seconds >= segment.end_seconds:
                break
            start_seconds = end_seconds - chunk_overlap_seconds
    return ranges


def extract_chunks(normalized_path: Path, chunks_dir: Path, settings: Settings) -> tuple[AudioChunk, ...]:
    segments = detect_speech_segments(
        normalized_path,
        threshold_db=settings.vad_threshold_db,
        min_speech_seconds=settings.vad_min_speech_seconds,
        min_silence_seconds=settings.vad_min_silence_seconds,
    )
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[AudioChunk] = []
    for index, (start_seconds, end_seconds) in enumerate(
        _chunk_ranges(
            segments,
            chunk_duration_seconds=settings.chunk_duration_seconds,
            chunk_overlap_seconds=settings.chunk_overlap_seconds,
        ),
        start=1,
    ):
        destination = chunks_dir / f"chunk-{index:04d}.wav"
        _run(
            [
                settings.ffmpeg_binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(normalized_path),
                "-t",
                f"{end_seconds - start_seconds:.3f}",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ]
        )
        chunks.append(AudioChunk(f"chunk-{index:04d}", start_seconds, end_seconds, destination))
    return tuple(chunks)


def prepare_audio(source_path: Path, workspace: Path, settings: Settings) -> PreparedAudio:
    """Normalize one local recording and return speech chunks with original times."""
    source = probe_audio(source_path, settings)
    normalized_path = workspace / "normalized.wav"
    normalized = normalize_audio(source_path, normalized_path, settings)
    chunks = extract_chunks(normalized_path, workspace / "chunks", settings)
    return PreparedAudio(source, normalized, normalized_path, chunks)


def create_workspace(settings: Settings) -> Path:
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"prepare-{uuid4().hex}-", dir=settings.runtime_dir))


def cleanup_workspace(workspace: Path, settings: Settings) -> None:
    runtime_dir = settings.runtime_dir.resolve()
    resolved_workspace = workspace.resolve()
    if runtime_dir not in resolved_workspace.parents:
        raise ValueError("Refusing to delete a workspace outside ASR_RUNTIME_DIR.")
    shutil.rmtree(resolved_workspace, ignore_errors=True)
