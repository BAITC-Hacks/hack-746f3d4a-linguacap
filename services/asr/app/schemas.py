"""Response schemas shared by the service endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ModelStatus(BaseModel):
    state: Literal["available", "not_downloaded"]
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


class TranscriptSegmentResponse(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float
    text: str


class TranscriptionResultResponse(BaseModel):
    text: str
    segments: list[TranscriptSegmentResponse]
