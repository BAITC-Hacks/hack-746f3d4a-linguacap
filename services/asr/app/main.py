"""HTTP entry point for the private, local-only ASR service."""

from __future__ import annotations

import logging
import shutil
import json
from importlib.util import find_spec
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.analysis import (
    ActionItem,
    DisabledProtocolAnalyzer,
    LocalModelUnavailableError,
    LocalOllamaProtocolAnalyzer,
    MeetingProtocol,
    ProtocolAnalysisError,
    ProtocolAnalyzer,
)
from app.audio import AudioProcessingError, AudioValidationError, cleanup_workspace, create_workspace, extension_for_upload, prepare_audio, store_upload
from app.config import Settings, get_settings
from app.diarization import LocalPyannoteDiarizer, PYANNOTE_CONFIG_FILENAME, PYANNOTE_MODEL_DIRECTORY
from app.jobs import Diarizer, Job, JobNotFoundError, Transcriber, TranscriptionJobManager
from app.protocol_export import ProtocolExportError, create_protocol_export
from app.schemas import (
    ActionItemResponse,
    AudioPreparationResponse,
    DeviceStatus,
    HealthResponse,
    JobEventResponse,
    JobResponse,
    MeetingProtocolResponse,
    ModelStatus,
    PreparedAudioChunk,
    PreparedAudioFormat,
    RenameSpeakerRequest,
    SpeakerResponse,
    TranscriptSegmentResponse,
    TranscriptionResultResponse,
    UpdateActionRequest,
    UpdateTranscriptSegmentRequest,
)
from app.transcription import LocalRukkTranscriber, TranscriptionError
from app.nemo_transcription import NEMO_FILENAME

logger = logging.getLogger("uvicorn.error")


def _model_status(path: Path, *required_files: str) -> ModelStatus:
    return ModelStatus(
        state="available" if all((path / filename).is_file() for filename in required_files) else "not_downloaded",
        path=str(path),
    )


def _ollama_model_status(settings: Settings) -> ModelStatus:
    if settings.local_llm_provider != "ollama" or not settings.local_llm_model:
        return ModelStatus(state="disabled", path=str(settings.llm_model_dir))
    try:
        with urlopen(f"{settings.local_llm_base_url.rstrip('/')}/api/tags", timeout=1) as response:  # noqa: S310 -- URL is validated as loopback in Settings.
            payload = json.load(response)
        models = payload.get("models", []) if isinstance(payload, dict) else []
        names = {entry.get("name") for entry in models if isinstance(entry, dict)}
        state = "available" if settings.local_llm_model in names else "not_downloaded"
    except (OSError, URLError, ValueError, TypeError):
        state = "unavailable"
    return ModelStatus(state=state, path=str(settings.llm_model_dir))


def _job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.job_id,
        status=job.state,
        error=job.error,
        stage=job.stage,
        progress_percent=job.progress_percent,
        events=[
            JobEventResponse(stage=event.stage, progress_percent=event.progress_percent, message=event.message)
            for event in job.events
        ],
    )


def create_app(
    settings: Settings | None = None,
    transcriber: Transcriber | None = None,
    diarizer: Diarizer | None = None,
    analyzer: ProtocolAnalyzer | None = None,
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
    analysis_engine = analyzer or (
        LocalOllamaProtocolAnalyzer(configured_settings)
        if configured_settings.local_llm_provider == "ollama"
        else DisabledProtocolAnalyzer()
    )
    app.state.jobs = TranscriptionJobManager(configured_settings, transcription_engine, diarization_engine, analysis_engine)
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
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        ffmpeg_available = shutil.which(configured_settings.ffmpeg_binary) is not None
        ffprobe_available = shutil.which(configured_settings.ffprobe_binary) is not None
        dependencies = {
            name: "available" if find_spec(module) is not None else "not_found"
            for name, module in (
                ("torch", "torch"), ("pyannote", "pyannote"), ("nemo", "nemo"),
                ("docx", "docx"), ("reportlab", "reportlab"),
            )
        }
        models = {
            "asr_rukk": _model_status(configured_settings.rukk_model_dir, "model.pt", "tokens.lst"),
            "asr_nemo": _model_status(configured_settings.nemo_model_dir, NEMO_FILENAME),
            "diarization": _model_status(
                configured_settings.diarization_model_dir / PYANNOTE_MODEL_DIRECTORY, PYANNOTE_CONFIG_FILENAME
            ),
            "llm": _ollama_model_status(configured_settings),
        }
        return HealthResponse(
            status="ok",
            service="local-asr",
            device=DeviceStatus(
                requested=configured_settings.requested_device,
                selected=configured_settings.selected_device,
                fallback_reason=configured_settings.device_fallback_reason,
            ),
            ffmpeg="available" if ffmpeg_available else "not_found",
            ffprobe="available" if ffprobe_available else "not_found",
            dependencies=dependencies,
            ready={
                "transcription": ffmpeg_available and ffprobe_available and dependencies["torch"] == "available"
                and models["asr_rukk"].state == "available" and app.state.asr_startup_error is None,
                "diarization": dependencies["pyannote"] == "available" and models["diarization"].state == "available",
                "analysis": models["llm"].state == "available",
                "export": dependencies["docx"] == "available" and dependencies["reportlab"] == "available",
            },
            startup_error=app.state.asr_startup_error,
            analysis_model=configured_settings.local_llm_model,
            models=models,
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
            return _job_response(job)
        except AudioValidationError as error:
            manager.discard(job.job_id)
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/jobs/{job_id}", response_model=JobResponse, tags=["transcription"])
    def get_job(job_id: str) -> JobResponse:
        try:
            job = app.state.jobs.get(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        return _job_response(job)

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

    @app.post("/jobs/{job_id}/analysis", response_model=MeetingProtocolResponse, tags=["analysis"])
    def analyze_transcript(job_id: str) -> MeetingProtocolResponse:
        try:
            protocol = app.state.jobs.analyze(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        except LocalModelUnavailableError as error:
            raise HTTPException(status_code=503, detail="Локальная LLM не настроена.") from error
        except ProtocolAnalysisError as error:
            raise HTTPException(status_code=422, detail="Локальная LLM вернула некорректный протокол.") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail="Расшифровка ещё не готова.") from error
        return _protocol_response(protocol)

    @app.get("/jobs/{job_id}/analysis", response_model=MeetingProtocolResponse, tags=["analysis"])
    def get_analysis(job_id: str) -> MeetingProtocolResponse:
        try:
            protocol = app.state.jobs.analysis_for(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail="Протокол ещё не сформирован.") from error
        return _protocol_response(protocol)

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

    @app.put("/jobs/{job_id}/segments/{segment_id}", response_model=TranscriptSegmentResponse, tags=["transcription"])
    def update_transcript_segment(job_id: str, segment_id: str, body: UpdateTranscriptSegmentRequest) -> TranscriptSegmentResponse:
        try:
            segment = app.state.jobs.update_segment(job_id, segment_id, body.text)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Сегмент не найден.") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail="Расшифровка ещё не готова.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return TranscriptSegmentResponse(
            id=segment.segment_id,
            start_seconds=round(segment.start_seconds, 3),
            end_seconds=round(segment.end_seconds, 3),
            text=segment.text,
            speaker_id=segment.speaker_id,
            speaker_name=segment.speaker_name,
        )

    @app.put("/jobs/{job_id}/actions/{action_index}", response_model=ActionItemResponse, tags=["analysis"])
    def update_action(job_id: str, action_index: int, body: UpdateActionRequest) -> ActionItemResponse:
        try:
            action = app.state.jobs.update_action(
                job_id,
                action_index,
                description=body.description,
                assignee=body.assignee,
                deadline_text=body.deadline_text,
                deadline=body.deadline,
            )
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Поручение не найдено.") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail="Протокол ещё не сформирован.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _action_response(action)

    @app.get("/jobs/{job_id}/export/{export_format}", tags=["export"])
    def export_protocol(job_id: str, export_format: str) -> Response:
        if export_format not in {"docx", "pdf"}:
            raise HTTPException(status_code=400, detail="Поддерживаются только форматы DOCX и PDF.")
        try:
            result = app.state.jobs.result_for(job_id)
            protocol = app.state.jobs.analysis_for(job_id)
            content = create_protocol_export(export_format, result, protocol)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Задание не найдено.") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail="Сначала сформируйте саммари и поручения.") from error
        except ProtocolExportError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if export_format == "docx" else "application/pdf"
        filename = f"protocol-{job_id[:8]}.{export_format}"
        logger.info("asr_protocol_exported id=%s format=%s", job_id, export_format)
        return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

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


def _protocol_response(protocol: MeetingProtocol) -> MeetingProtocolResponse:
    return MeetingProtocolResponse(
        title=protocol.title,
        summary=protocol.summary,
        key_points=list(protocol.key_points),
        action_items=[_action_response(item) for item in protocol.action_items],
    )


def _action_response(item: ActionItem) -> ActionItemResponse:
    return ActionItemResponse(
        description=item.description,
        assignee=item.assignee,
        deadline_text=item.deadline_text,
        deadline=item.deadline,
        source_segment_ids=list(item.source_segment_ids),
        confidence=item.confidence,
        status=item.status,
    )


app = create_app()
