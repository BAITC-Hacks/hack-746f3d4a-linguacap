import math
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.jobs import TranscriptSegment, TranscriptionJobManager, merge_segment_text
from app.main import create_app


class FakeTranscriber:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, wav_path: Path) -> str:
        assert wav_path.is_file()
        self.calls += 1
        return "тестовая расшифровка"


def write_speech_like_wav(path: Path) -> None:
    sample_rate = 16_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(
            b"".join(
                int(10_000 * math.sin(2 * math.pi * 440 * index / sample_rate)).to_bytes(2, "little", signed=True)
                for index in range(sample_rate)
            )
        )


def job_settings(tmp_path: Path) -> Settings:
    return Settings.from_environment(
        {
            "ASR_DEVICE": "cpu",
            "ASR_RUNTIME_DIR": str(tmp_path / "runtime"),
            "ASR_MAX_UPLOAD_BYTES": "10000000",
            "ASR_MAX_AUDIO_DURATION_SECONDS": "30",
            "ASR_CHUNK_DURATION_SECONDS": "18",
            "ASR_CHUNK_OVERLAP_SECONDS": "1",
        }
    )


def test_manager_transcribes_and_removes_audio_workspace(tmp_path: Path):
    settings = job_settings(tmp_path)
    transcriber = FakeTranscriber()
    manager = TranscriptionJobManager(settings, transcriber)
    job = manager.create()
    source = job.workspace / "source.wav"
    write_speech_like_wav(source)

    manager.submit(job.job_id, source)
    assert job.future is not None
    job.future.result(timeout=10)

    result = manager.result_for(job.job_id)
    assert result.text == "тестовая расшифровка"
    assert len(result.segments) == 1
    assert transcriber.calls == 1
    assert not job.workspace.exists()
    assert manager.delete(job.job_id)
    manager.shutdown()


def test_transcription_api_exposes_status_result_and_deletion(tmp_path: Path):
    settings = job_settings(tmp_path)
    transcriber = FakeTranscriber()
    source = tmp_path / "meeting.wav"
    write_speech_like_wav(source)
    app = create_app(settings, transcriber)

    with TestClient(app) as client, source.open("rb") as audio_file:
        created = client.post("/transcribe", files={"file": ("meeting.wav", audio_file, "audio/wav")})
        assert created.status_code == 202
        job_id = created.json()["id"]
        app.state.jobs.get(job_id).future.result(timeout=10)

        status = client.get(f"/jobs/{job_id}")
        assert status.json()["status"] == "completed"
        result = client.get(f"/jobs/{job_id}/result")
        assert result.status_code == 200
        assert result.json()["segments"][0]["text"] == "тестовая расшифровка"
        deleted = client.delete(f"/jobs/{job_id}")
        assert deleted.status_code == 204

    app.state.jobs.shutdown()


def test_merge_segment_text_removes_overlap_only_at_the_boundary():
    segments = [
        TranscriptSegment("chunk-1", 0, 18, "подготовить отчёт до пятницы"),
        TranscriptSegment("chunk-2", 17, 30, "до пятницы и направить директору"),
    ]

    assert merge_segment_text(segments) == "подготовить отчёт до пятницы и направить директору"
