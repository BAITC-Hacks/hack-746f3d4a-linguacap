"""A single-worker in-memory queue that protects a 16 GB local machine."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import date
import logging
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Protocol
from uuid import uuid4

from app.analysis import (
    ActionItem,
    DisabledProtocolAnalyzer,
    MeetingProtocol,
    ProtocolAnalyzer,
    ProtocolSourceSegment,
)
from app.audio import AudioProcessingError, cleanup_workspace, prepare_audio
from app.config import Settings
from app.diarization import DiarizationError, LocalPyannoteDiarizer, SpeakerTurn, speaker_for_interval
from app.storage import LocalProtocolStore
from app.transcription import LocalRukkTranscriber, TranscriptionError

logger = logging.getLogger("uvicorn.error")

_STAGE_MESSAGES = {
    "queued": "Запись принята и ожидает свободный локальный слот.",
    "preparing": "Проверяем и подготавливаем аудио.",
    "diarizing": "Определяем реплики и спикеров.",
    "transcribing": "Распознаём речевые фрагменты локальной ASR-моделью.",
    "completed": "Транскрибация и диаризация завершены.",
    "failed": "Локальная обработка не завершилась.",
}


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


@dataclass(frozen=True)
class JobEvent:
    stage: str
    progress_percent: int
    message: str


@dataclass
class Job:
    job_id: str
    workspace: Path
    state: str = "queued"
    stage: str = "queued"
    progress_percent: int = 0
    events: list[JobEvent] = field(default_factory=lambda: [JobEvent("queued", 0, _STAGE_MESSAGES["queued"])])
    created_at: float = field(default_factory=time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result: TranscriptionResult | None = None
    analysis: MeetingProtocol | None = None
    cancel_requested: bool = False
    future: Future[None] | None = None


class JobNotFoundError(KeyError):
    pass


class TranscriptionJobManager:
    def __init__(
        self,
        settings: Settings,
        transcriber: Transcriber | None = None,
        diarizer: Diarizer | None = None,
        analyzer: ProtocolAnalyzer | None = None,
    ) -> None:
        self._settings = settings
        self._transcriber = transcriber or LocalRukkTranscriber(settings)
        self._diarizer = diarizer
        self._analyzer = analyzer or DisabledProtocolAnalyzer()
        self._store = LocalProtocolStore(settings.protocol_store_path)
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
        logger.info("asr_job_queued id=%s stage=queued progress_percent=0", job_id)
        return job

    def submit(self, job_id: str, source_path: Path) -> None:
        with self._lock:
            job = self._get(job_id)
            job.future = self._executor.submit(self._process, job_id, source_path)

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        return job if job is not None else self._persisted_job(job_id)

    def result_for(self, job_id: str) -> TranscriptionResult:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.state != "completed" or job.result is None:
                    raise RuntimeError("The job has not completed.")
                return job.result
        payload = self._store.result_for(job_id)
        if payload is None:
            raise JobNotFoundError(job_id)
        return _result_from_payload(payload)

    def analyze(self, job_id: str) -> MeetingProtocol:
        """Analyze only a completed in-memory transcript using a local analyzer."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.analysis is not None:
                return job.analysis
        stored_analysis = self._store.analysis_for(job_id)
        if stored_analysis is not None:
            return _protocol_from_payload(stored_analysis)

        result = self.result_for(job_id)
        segments = tuple(
            ProtocolSourceSegment(
                segment_id=segment.segment_id,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                speaker_name=segment.speaker_name,
            )
            for segment in result.segments
        )

        logger.info("asr_protocol_analysis_started id=%s segments=%d", job_id, len(segments))
        try:
            protocol = self._analyzer.analyze(segments)
        except Exception:
            logger.warning("asr_protocol_analysis_failed id=%s", job_id)
            raise
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.state != "completed" or job.result is None:
                    raise RuntimeError("The job is no longer available.")
                job.analysis = protocol
        self._store.save_analysis(job_id, _protocol_payload(protocol))
        logger.info("asr_protocol_analysis_completed id=%s action_items=%d", job_id, len(protocol.action_items))
        return protocol

    def analysis_for(self, job_id: str) -> MeetingProtocol:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.analysis is not None:
                return job.analysis
        payload = self._store.analysis_for(job_id)
        if payload is not None:
            return _protocol_from_payload(payload)
        if self._store.has(job_id):
            raise RuntimeError("The analysis has not completed.")
        raise JobNotFoundError(job_id)

    def rename_speaker(self, job_id: str, speaker_id: str, display_name: str) -> Speaker:
        cleaned_name = display_name.strip()
        if not cleaned_name or len(cleaned_name) > 100:
            raise ValueError("Имя спикера должно содержать от 1 до 100 символов.")
        result = self.result_for(job_id)
        matching = next((speaker for speaker in result.speakers if speaker.speaker_id == speaker_id), None)
        if matching is None:
            raise KeyError(speaker_id)
        renamed = Speaker(speaker_id, cleaned_name)
        updated = TranscriptionResult(
            segments=tuple(
                replace(segment, speaker_name=cleaned_name) if segment.speaker_id == speaker_id else segment
                for segment in result.segments
            ),
            text=result.text,
            speakers=tuple(renamed if speaker.speaker_id == speaker_id else speaker for speaker in result.speakers),
        )
        self._replace_result(job_id, updated)
        return renamed

    def update_segment(self, job_id: str, segment_id: str, text: str) -> TranscriptSegment:
        cleaned_text = text.strip()
        if not cleaned_text or len(cleaned_text) > 10_000:
            raise ValueError("Текст реплики должен содержать от 1 до 10000 символов.")
        result = self.result_for(job_id)
        matching = next((segment for segment in result.segments if segment.segment_id == segment_id), None)
        if matching is None:
            raise KeyError(segment_id)
        updated_segment = replace(matching, text=cleaned_text)
        updated_segments = tuple(
            updated_segment if segment.segment_id == segment_id else segment for segment in result.segments
        )
        updated = TranscriptionResult(
            segments=updated_segments,
            text=merge_segment_text(list(updated_segments)),
            speakers=result.speakers,
        )
        self._replace_result(job_id, updated)
        return updated_segment

    def update_action(
        self,
        job_id: str,
        action_index: int,
        *,
        description: str,
        assignee: str | None,
        deadline_text: str | None,
        deadline: date | None,
    ) -> ActionItem:
        protocol = self.analysis_for(job_id)
        if not 0 <= action_index < len(protocol.action_items):
            raise KeyError(action_index)
        cleaned_description = description.strip()
        if not cleaned_description or len(cleaned_description) > 2_000:
            raise ValueError("Описание поручения должно содержать от 1 до 2000 символов.")
        cleaned_assignee = _optional_edit_text(assignee, "Ответственный")
        cleaned_deadline_text = _optional_edit_text(deadline_text, "Срок")
        current = protocol.action_items[action_index]
        updated_action = replace(
            current,
            description=cleaned_description,
            assignee=cleaned_assignee,
            deadline_text=cleaned_deadline_text,
            deadline=deadline,
        )
        updated_protocol = replace(
            protocol,
            action_items=tuple(updated_action if index == action_index else item for index, item in enumerate(protocol.action_items)),
        )
        self._replace_protocol(job_id, updated_protocol)
        return updated_action

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                if self._store.delete(job_id):
                    logger.info("asr_job_deleted id=%s", job_id)
                    return True
                raise JobNotFoundError(job_id)
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
        self._store.delete(job_id)
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

    def _persisted_job(self, job_id: str) -> Job:
        result_payload = self._store.result_for(job_id)
        if result_payload is None:
            raise JobNotFoundError(job_id)
        analysis_payload = self._store.analysis_for(job_id)
        return Job(
            job_id=job_id,
            workspace=self._settings.runtime_dir / "jobs" / job_id,
            state="completed",
            stage="completed",
            progress_percent=100,
            events=[JobEvent("completed", 100, _STAGE_MESSAGES["completed"])],
            result=_result_from_payload(result_payload),
            analysis=_protocol_from_payload(analysis_payload) if analysis_payload is not None else None,
        )

    def _replace_result(self, job_id: str, result: TranscriptionResult) -> None:
        self._store.save_result(job_id, _result_payload(result))
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.result = result
                job.analysis = None

    def _replace_protocol(self, job_id: str, protocol: MeetingProtocol) -> None:
        self._store.save_analysis(job_id, _protocol_payload(protocol))
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.analysis = protocol

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return self._get(job_id).cancel_requested

    def _set_progress(self, job_id: str, stage: str, progress_percent: int) -> None:
        """Store safe, user-visible milestones without logging recording content."""
        with self._lock:
            job = self._get(job_id)
            if job.cancel_requested:
                return
            if job.stage == stage and job.progress_percent == progress_percent:
                return
            job.stage = stage
            job.progress_percent = progress_percent
            job.events.append(JobEvent(stage, progress_percent, _STAGE_MESSAGES[stage]))
        logger.info("asr_job_progress id=%s stage=%s progress_percent=%d", job_id, stage, progress_percent)

    def _process(self, job_id: str, source_path: Path) -> None:
        with self._lock:
            job = self._get(job_id)
            if job.cancel_requested:
                return
            job.state = "processing"
            job.started_at = time()
        logger.info("asr_job_started id=%s", job_id)

        try:
            self._set_progress(job_id, "preparing", 5)
            prepared = prepare_audio(source_path, job.workspace, self._settings)
            if self._is_cancelled(job_id):
                return
            self._set_progress(job_id, "diarizing", 25)
            turns = self._diarizer.diarize(prepared.normalized_path) if self._diarizer and self._diarizer.is_installed else ()
            if self._is_cancelled(job_id):
                return
            speakers = tuple(Speaker(turn.speaker_id, f"Спикер {index}") for index, turn in enumerate(_first_turns(turns), start=1))
            speaker_names = {speaker.speaker_id: speaker.display_name for speaker in speakers}
            segments: list[TranscriptSegment] = []
            chunk_count = len(prepared.chunks)
            self._set_progress(job_id, "transcribing", 50)
            for index, chunk in enumerate(prepared.chunks, start=1):
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
                self._set_progress(job_id, "transcribing", 50 + round(index / max(chunk_count, 1) * 45))
            result = TranscriptionResult(tuple(segments), merge_segment_text(segments), speakers)
            if not self._is_cancelled(job_id):
                self._store.save_result(job_id, _result_payload(result))
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
            self._set_progress(job_id, "completed", 100)
        except (AudioProcessingError, DiarizationError, TranscriptionError):
            with self._lock:
                job = self._get(job_id)
                if not job.cancel_requested:
                    job.error = "Локальное распознавание не удалось завершить."
                    job.state = "failed"
                    logger.warning("asr_job_failed id=%s", job_id)
            self._set_progress(job_id, "failed", 100)
        finally:
            cleanup_workspace(job.workspace, self._settings)
            with self._lock:
                job = self._get(job_id)
                job.finished_at = time()
                if job.cancel_requested:
                    job.state = "deleted"
                    self._jobs.pop(job_id, None)
                    self._store.delete(job_id)
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


def _result_payload(result: TranscriptionResult) -> dict[str, Any]:
    return {
        "text": result.text,
        "segments": [
            {
                "id": segment.segment_id,
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
                "speaker_id": segment.speaker_id,
                "speaker_name": segment.speaker_name,
            }
            for segment in result.segments
        ],
        "speakers": [{"id": speaker.speaker_id, "display_name": speaker.display_name} for speaker in result.speakers],
    }


def _result_from_payload(payload: dict[str, Any]) -> TranscriptionResult:
    try:
        segments = tuple(
            TranscriptSegment(
                segment_id=str(item["id"]),
                start_seconds=float(item["start_seconds"]),
                end_seconds=float(item["end_seconds"]),
                text=str(item["text"]),
                speaker_id=item.get("speaker_id"),
                speaker_name=item.get("speaker_name"),
            )
            for item in payload["segments"]
        )
        speakers = tuple(Speaker(str(item["id"]), str(item["display_name"])) for item in payload["speakers"])
        return TranscriptionResult(segments=segments, text=str(payload["text"]), speakers=speakers)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Local protocol storage contains an invalid transcript.") from error


def _protocol_payload(protocol: MeetingProtocol) -> dict[str, Any]:
    return {
        "title": protocol.title,
        "summary": protocol.summary,
        "key_points": list(protocol.key_points),
        "action_items": [
            {
                "description": item.description,
                "assignee": item.assignee,
                "deadline_text": item.deadline_text,
                "deadline": item.deadline.isoformat() if item.deadline else None,
                "source_segment_ids": list(item.source_segment_ids),
                "confidence": item.confidence,
                "status": item.status,
            }
            for item in protocol.action_items
        ],
    }


def _protocol_from_payload(payload: dict[str, Any]) -> MeetingProtocol:
    try:
        return MeetingProtocol(
            title=str(payload["title"]),
            summary=str(payload["summary"]),
            key_points=tuple(str(item) for item in payload["key_points"]),
            action_items=tuple(
                ActionItem(
                    description=str(item["description"]),
                    assignee=item.get("assignee"),
                    deadline_text=item.get("deadline_text"),
                    deadline=date.fromisoformat(item["deadline"]) if item.get("deadline") else None,
                    source_segment_ids=tuple(str(source_id) for source_id in item["source_segment_ids"]),
                    confidence=float(item["confidence"]),
                    status=str(item["status"]),
                )
                for item in payload["action_items"]
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Local protocol storage contains an invalid analysis.") from error


def _optional_edit_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if len(cleaned) > 300:
        raise ValueError(f"{label} не должен превышать 300 символов.")
    return cleaned or None
