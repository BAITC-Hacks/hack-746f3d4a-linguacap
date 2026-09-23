"""Response schemas shared by the service endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


JobStage = Literal["queued", "preparing", "diarizing", "transcribing", "completed", "failed"]


class ModelStatus(BaseModel):
    state: Literal["available", "not_downloaded", "disabled", "unavailable"]
    path: str


class DeviceStatus(BaseModel):
    requested: Literal["auto", "mps", "cpu"]
    selected: Literal["mps", "cpu"]
    fallback_reason: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["local-asr"]
    device: DeviceStatus
    ffmpeg: Literal["available", "not_found"]
    ffprobe: Literal["available", "not_found"]
    dependencies: dict[str, Literal["available", "not_found"]]
    ready: dict[str, bool]
    startup_error: str | None = None
    analysis_model: str | None = None
    models: dict[str, ModelStatus]


class PreparedAudioFormat(BaseModel):
    duration_seconds: float
    sample_rate: int
    channels: int


class PreparedAudioChunk(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float


class AudioPreparationResponse(BaseModel):
    status: Literal["ready"]
    source: PreparedAudioFormat
    normalized: PreparedAudioFormat
    chunks: list[PreparedAudioChunk]


class JobResponse(BaseModel):
    id: str
    status: Literal["queued", "processing", "completed", "failed", "deleting"]
    error: str | None = None
    stage: JobStage
    progress_percent: int
    events: list["JobEventResponse"]


class JobEventResponse(BaseModel):
    stage: JobStage
    progress_percent: int
    message: str


class TranscriptSegmentResponse(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float
    text: str
    speaker_id: str | None = None
    speaker_name: str | None = None


class SpeakerResponse(BaseModel):
    id: str
    display_name: str


class RenameSpeakerRequest(BaseModel):
    display_name: str


class UpdateTranscriptSegmentRequest(BaseModel):
    text: str


class UpdateActionRequest(BaseModel):
    description: str
    assignee: str | None = None
    deadline_text: str | None = None
    deadline: date | None = None


class TranscriptionResultResponse(BaseModel):
    text: str
    segments: list[TranscriptSegmentResponse]
    speakers: list[SpeakerResponse]


class ActionItemResponse(BaseModel):
    description: str
    assignee: str | None
    deadline_text: str | None
    deadline: date | None
    source_segment_ids: list[str]
    confidence: float
    status: Literal["new"]


class MeetingProtocolResponse(BaseModel):
    title: str
    summary: str
    key_points: list[str]
    action_items: list[ActionItemResponse]
