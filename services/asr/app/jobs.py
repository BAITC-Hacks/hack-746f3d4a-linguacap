"""A single-worker in-memory queue that protects a 16 GB local machine."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
import logging
from pathlib import Path
from threading import RLock
from time import time
from typing import Protocol
from uuid import uuid4

from app.audio import AudioProcessingError, cleanup_workspace, prepare_audio
from app.config import Settings
from app.diarization import DiarizationError, LocalPyannoteDiarizer, SpeakerTurn, speaker_for_interval
from app.transcription import LocalRukkTranscriber, TranscriptionError

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    def transcribe(self, wav_path: Path) -> str: ...


class Diarizer(Protocol):
    @property
    def is_installed(self) -> bool: ...

    def diarize(self, wav_path: Path) -> tuple[SpeakerTurn, ...]: ...


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    speaker_id: str | None = None
    speaker_name: str | None = None


@dataclass(frozen=True)
class Speaker:
    speaker_id: str
    display_name: str


@dataclass(frozen=True)
class TranscriptionResult:
    segments: tuple[TranscriptSegment, ...]
    text: str
    speakers: tuple[Speaker, ...] = ()


@dataclass
class Job:
    job_id: str
    workspace: Path
    state: str = "queued"
    created_at: float = field(default_factory=time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result: TranscriptionResult | None = None
    cancel_requested: bool = False
    future: Future[None] | None = None


class JobNotFoundError(KeyError):
    pass


class TranscriptionJobManager:
    def __init__(self, settings: Settings, transcriber: Transcriber | None = None, diarizer: Diarizer | None = None) -> None:
        self._settings = settings
        self._transcriber = transcriber or LocalRukkTranscriber(settings)
        self._diarizer = diarizer
        self._jobs: dict[str, Job] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-asr")

    def create(self) -> Job:
        job_id = uuid4().hex
        workspace = self._settings.runtime_dir / "jobs" / job_id
        workspace.mkdir(parents=True, exist_ok=False)
        job = Job(job_id=job_id, workspace=workspace)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def submit(self, job_id: str, source_path: Path) -> None:
        with self._lock:
            job = self._get(job_id)
            job.future = self._executor.submit(self._process, job_id, source_path)

    def get(self, job_id: str) -> Job:
        with self._lock:
            return self._get(job_id)

    def result_for(self, job_id: str) -> TranscriptionResult:
        with self._lock:
            job = self._get(job_id)
            if job.state != "completed" or job.result is None:
                raise RuntimeError("The job has not completed.")
            return job.result

    def rename_speaker(self, job_id: str, speaker_id: str, display_name: str) -> Speaker:
        cleaned_name = display_name.strip()
        if not cleaned_name or len(cleaned_name) > 100:
            raise ValueError("Имя спикера должно содержать от 1 до 100 символов.")
        with self._lock:
            job = self._get(job_id)
            if job.state != "completed" or job.result is None:
                raise RuntimeError("The job has not completed.")
            matching = next((speaker for speaker in job.result.speakers if speaker.speaker_id == speaker_id), None)
            if matching is None:
                raise KeyError(speaker_id)
            renamed = Speaker(speaker_id, cleaned_name)
            job.result = TranscriptionResult(
                segments=tuple(
                    replace(segment, speaker_name=cleaned_name) if segment.speaker_id == speaker_id else segment
                    for segment in job.result.segments
                ),
                text=job.result.text,
                speakers=tuple(renamed if speaker.speaker_id == speaker_id else speaker for speaker in job.result.speakers),
            )
            return renamed

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._get(job_id)
            if job.state == "queued" and job.future and job.future.cancel():
                job.state = "deleted"
                self._jobs.pop(job_id, None)
                cleanup_workspace(job.workspace, self._settings)
                return True
            if job.state in {"queued", "processing"}:
                job.cancel_requested = True
                job.state = "deleting"
                return False
            self._jobs.pop(job_id, None)
        cleanup_workspace(job.workspace, self._settings)
        return True

    def discard(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is not None:
            cleanup_workspace(job.workspace, self._settings)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as error:
            raise JobNotFoundError(job_id) from error

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return self._get(job_id).cancel_requested

    def _process(self, job_id: str, source_path: Path) -> None:
        with self._lock:
            job = self._get(job_id)
            if job.cancel_requested:
                return
            job.state = "processing"
            job.started_at = time()
        logger.info("asr_job_started id=%s", job_id)

        try:
            prepared = prepare_audio(source_path, job.workspace, self._settings)
            turns = self._diarizer.diarize(prepared.normalized_path) if self._diarizer and self._diarizer.is_installed else ()
            speakers = tuple(Speaker(turn.speaker_id, f"Спикер {index}") for index, turn in enumerate(_first_turns(turns), start=1))
            speaker_names = {speaker.speaker_id: speaker.display_name for speaker in speakers}
            segments: list[TranscriptSegment] = []
            for chunk in prepared.chunks:
                if self._is_cancelled(job_id):
                    return
                text = self._transcriber.transcribe(chunk.path)
                speaker_id = speaker_for_interval(chunk.start_seconds, chunk.end_seconds, turns)
                segments.append(
                    TranscriptSegment(
                        chunk.chunk_id,
                        chunk.start_seconds,
                        chunk.end_seconds,
                        text,
                        speaker_id=speaker_id,
                        speaker_name=speaker_names.get(speaker_id),
                    )
                )
            result = TranscriptionResult(tuple(segments), merge_segment_text(segments), speakers)
            with self._lock:
                job = self._get(job_id)
                if not job.cancel_requested:
                    job.result = result
                    job.state = "completed"
                    logger.info(
                        "asr_job_completed id=%s duration_ms=%d chunks=%d",
                        job_id,
                        round((time() - job.started_at) * 1_000) if job.started_at else 0,
                        len(segments),
                    )
        except (AudioProcessingError, DiarizationError, TranscriptionError):
            with self._lock:
                job = self._get(job_id)
                if not job.cancel_requested:
                    job.error = "Локальное распознавание не удалось завершить."
                    job.state = "failed"
                    logger.warning("asr_job_failed id=%s", job_id)
        finally:
            cleanup_workspace(job.workspace, self._settings)
            with self._lock:
                job = self._get(job_id)
                job.finished_at = time()
                if job.cancel_requested:
                    job.state = "deleted"
                    self._jobs.pop(job_id, None)
                    logger.info("asr_job_deleted id=%s", job_id)


def merge_segment_text(segments: list[TranscriptSegment]) -> str:
    """Remove exact word repetition introduced by adjacent chunk overlap."""
    merged_words: list[str] = []
    for segment in segments:
        words = segment.text.split()
        max_overlap = min(len(merged_words), len(words), 40)
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if [word.casefold() for word in merged_words[-size:]] == [word.casefold() for word in words[:size]]:
                overlap = size
                break
        merged_words.extend(words[overlap:])
    return " ".join(merged_words)


def _first_turns(turns: tuple[SpeakerTurn, ...]) -> tuple[SpeakerTurn, ...]:
    """Keep one chronology-defining turn per normalized speaker."""
    first_turns: dict[str, SpeakerTurn] = {}
    for turn in turns:
        first_turns.setdefault(turn.speaker_id, turn)
    return tuple(first_turns.values())
