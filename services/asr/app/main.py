"""HTTP entry point for the private, local-only ASR service."""

from __future__ import annotations

import shutil

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.audio import AudioProcessingError, AudioValidationError, cleanup_workspace, create_workspace, extension_for_upload, prepare_audio, store_upload
from app.config import Settings, get_settings
from app.diarization import LocalPyannoteDiarizer
from app.jobs import Diarizer, JobNotFoundError, Transcriber, TranscriptionJobManager
from app.schemas import (
    AudioPreparationResponse,
    DeviceStatus,
    HealthResponse,
    JobResponse,
    ModelStatus,
    PreparedAudioChunk,
    PreparedAudioFormat,
    RenameSpeakerRequest,
    SpeakerResponse,
    TranscriptSegmentResponse,
    TranscriptionResultResponse,
)
from app.transcription import LocalRukkTranscriber, TranscriptionError


def _model_status(path: str) -> ModelStatus:
    from pathlib import Path

    model_path = Path(path)
    return ModelStatus(
        state="available" if model_path.is_dir() and any(model_path.iterdir()) else "not_downloaded",
        path=str(model_path),
    )


def _job_response(job_id: str, state: str, error: str | None) -> JobResponse:
    return JobResponse(id=job_id, status=state, error=error)


def create_app(
    settings: Settings | None = None, transcriber: Transcriber | None = None, diarizer: Diarizer | None = None
) -> FastAPI:
    """Build an app instance; injectable settings keep tests isolated."""
    configured_settings = settings or get_settings()
    app = FastAPI(
        title="HackAlem Local ASR Service",
        version="0.1.0",
        description="Local-only speech-processing service. No audio leaves the host.",
    )
    app.state.settings = configured_settings
    transcription_engine = transcriber or LocalRukkTranscriber(configured_settings)
    diarization_engine = diarizer or LocalPyannoteDiarizer(configured_settings)
    app.state.jobs = TranscriptionJobManager(configured_settings, transcription_engine, diarization_engine)
    app.state.asr_startup_error = None
    if isinstance(transcription_engine, LocalRukkTranscriber) and transcription_engine.is_installed:
        try:
            transcription_engine.load()
        except TranscriptionError:
            app.state.asr_startup_error = "Локальная ASR-модель не загрузилась."
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="local-asr",
            device=DeviceStatus(
                requested=configured_settings.requested_device,
                selected=configured_settings.selected_device,
                fallback_reason=configured_settings.device_fallback_reason,
            ),
            ffmpeg="available" if shutil.which(configured_settings.ffmpeg_binary) else "not_found",
            models={
                "asr_rukk": _model_status(str(configured_settings.rukk_model_dir)),
                "asr_nemo": _model_status(str(configured_settings.nemo_model_dir)),
                "diarization": _model_status(str(configured_settings.diarization_model_dir)),
                "llm": _model_status(str(configured_settings.llm_model_dir)),
            },
        )

    @app.post("/prepare-audio", response_model=AudioPreparationResponse, tags=["audio"])
    async def prepare_uploaded_audio(file: UploadFile = File(...)) -> AudioPreparationResponse:
        """Validate and prepare one recording without retaining its contents."""
        try:
            extension = extension_for_upload(file.filename, file.content_type)
        except AudioValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        workspace = create_workspace(configured_settings)
        try:
            source_path = workspace / f"source{extension}"
            await store_upload(file, source_path, max_bytes=configured_settings.max_upload_bytes)
            prepared = prepare_audio(source_path, workspace, configured_settings)
            return AudioPreparationResponse(
                status="ready",
                source=PreparedAudioFormat(**prepared.source.__dict__),
                normalized=PreparedAudioFormat(**prepared.normalized.__dict__),
                chunks=[
                    PreparedAudioChunk(
                        id=chunk.chunk_id,
                        start_seconds=round(chunk.start_seconds, 3),
                        end_seconds=round(chunk.end_seconds, 3),
                    )
                    for chunk in prepared.chunks
                ],
            )
        except AudioValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except AudioProcessingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        finally:
            cleanup_workspace(workspace, configured_settings)

    @app.post("/transcribe", response_model=JobResponse, status_code=202, tags=["transcription"])
    async def create_transcription_job(file: UploadFile = File(...)) -> JobResponse:
        """Queue one private ASR job; exactly one job transcribes at a time."""
        try:
            extension = extension_for_upload(file.filename, file.content_type)
        except AudioValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        manager: TranscriptionJobManager = app.state.jobs
        job = manager.create()
        try:
            await store_upload(file, job.workspace / f"source{extension}", max_bytes=configured_settings.max_upload_bytes)
            manager.submit(job.job_id, job.workspace / f"source{extension}")
            return _job_response(job.job_id, job.state, job.error)
        except AudioValidationError as error:
            manager.discard(job.job_id)
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/jobs/{job_id}", response_model=JobResponse, tags=["transcription"])
    def get_job(job_id: str) -> JobResponse:
        try:
            job = app.state.jobs.get(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        return _job_response(job.job_id, job.state, job.error)

    @app.get("/jobs/{job_id}/result", response_model=TranscriptionResultResponse, tags=["transcription"])
    def get_result(job_id: str) -> TranscriptionResultResponse:
        try:
            result = app.state.jobs.result_for(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail="Результат ещё не готов.") from error
        return TranscriptionResultResponse(
            text=result.text,
            segments=[
                TranscriptSegmentResponse(
                    id=segment.segment_id,
                    start_seconds=round(segment.start_seconds, 3),
                    end_seconds=round(segment.end_seconds, 3),
                    text=segment.text,
                    speaker_id=segment.speaker_id,
                    speaker_name=segment.speaker_name,
                )
                for segment in result.segments
            ],
            speakers=[SpeakerResponse(id=speaker.speaker_id, display_name=speaker.display_name) for speaker in result.speakers],
        )

    @app.post("/jobs/{job_id}/speakers/{speaker_id}", response_model=SpeakerResponse, tags=["diarization"])
    def rename_speaker(job_id: str, speaker_id: str, body: RenameSpeakerRequest) -> SpeakerResponse:
        try:
            speaker = app.state.jobs.rename_speaker(job_id, speaker_id, body.display_name)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Спикер не найден.") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail="Результат ещё не готов.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return SpeakerResponse(id=speaker.speaker_id, display_name=speaker.display_name)

    @app.delete("/jobs/{job_id}", status_code=204, tags=["transcription"])
    def delete_job(job_id: str) -> Response:
        try:
            removed = app.state.jobs.delete(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        if not removed:
            return Response(status_code=202, headers={"Retry-After": "1"})
        return Response(status_code=204)

    return app


app = create_app()
