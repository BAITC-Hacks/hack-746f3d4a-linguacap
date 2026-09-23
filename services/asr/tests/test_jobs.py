import math
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.analysis import ActionItem, MeetingProtocol, ProtocolSourceSegment
from app.config import Settings
from app.diarization import SpeakerTurn
from app.jobs import TranscriptSegment, TranscriptionJobManager, merge_segment_text
from app.main import create_app


class FakeTranscriber:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, wav_path: Path) -> str:
        assert wav_path.is_file()
        self.calls += 1
        return "тестовая расшифровка"


class FakeDiarizer:
    @property
    def is_installed(self) -> bool:
        return True

    def diarize(self, wav_path: Path) -> tuple[SpeakerTurn, ...]:
        assert wav_path.is_file()
        return (SpeakerTurn("SPEAKER_01", 0, 2),)


class FakeAnalyzer:
    @property
    def is_configured(self) -> bool:
        return True

    def analyze(self, segments: tuple[ProtocolSourceSegment, ...]) -> MeetingProtocol:
        assert segments[0].segment_id == "chunk-0001"
        assert segments[0].speaker_name == "Спикер 1"
        return MeetingProtocol(
            title="Планирование",
            summary="Обсудили план.",
            key_points=("Нужен отчёт.",),
            action_items=(
                ActionItem(
                    description="Подготовить отчёт",
                    assignee=None,
                    deadline_text="до пятницы",
                    deadline=None,
                    source_segment_ids=("chunk-0001",),
                    confidence=0.8,
                ),
            ),
        )


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
    app = create_app(settings, transcriber, FakeDiarizer())

    with TestClient(app) as client, source.open("rb") as audio_file:
        created = client.post("/transcribe", files={"file": ("meeting.wav", audio_file, "audio/wav")})
        assert created.status_code == 202
        job_id = created.json()["id"]
        app.state.jobs.get(job_id).future.result(timeout=10)

        status = client.get(f"/jobs/{job_id}")
        assert status.json()["status"] == "completed"
        assert status.json()["stage"] == "completed"
        assert status.json()["progress_percent"] == 100
        assert status.json()["events"][0]["stage"] == "queued"
        assert {event["stage"] for event in status.json()["events"]} >= {"preparing", "diarizing", "transcribing", "completed"}
        assert all("тестовая расшифровка" not in event["message"] for event in status.json()["events"])
        result = client.get(f"/jobs/{job_id}/result")
        assert result.status_code == 200
        assert result.json()["segments"][0]["text"] == "тестовая расшифровка"
        assert result.json()["speakers"] == [{"id": "SPEAKER_01", "display_name": "Спикер 1"}]
        renamed = client.post(f"/jobs/{job_id}/speakers/SPEAKER_01", json={"display_name": "Алия"})
        assert renamed.status_code == 200
        assert renamed.json() == {"id": "SPEAKER_01", "display_name": "Алия"}
        deleted = client.delete(f"/jobs/{job_id}")
        assert deleted.status_code == 204

    app.state.jobs.shutdown()


def test_merge_segment_text_removes_overlap_only_at_the_boundary():
    segments = [
        TranscriptSegment("chunk-1", 0, 18, "подготовить отчёт до пятницы"),
        TranscriptSegment("chunk-2", 17, 30, "до пятницы и направить директору"),
    ]

    assert merge_segment_text(segments) == "подготовить отчёт до пятницы и направить директору"


def test_diarization_speaker_is_attached_and_can_be_renamed(tmp_path: Path):
    settings = job_settings(tmp_path)
    manager = TranscriptionJobManager(settings, FakeTranscriber(), FakeDiarizer())
    job = manager.create()
    source = job.workspace / "source.wav"
    write_speech_like_wav(source)

    manager.submit(job.job_id, source)
    assert job.future is not None
    job.future.result(timeout=10)

    result = manager.result_for(job.job_id)
    assert result.speakers[0].display_name == "Спикер 1"
    assert result.segments[0].speaker_id == "SPEAKER_01"

    speaker = manager.rename_speaker(job.job_id, "SPEAKER_01", "Ерлан")
    assert speaker.display_name == "Ерлан"
    assert manager.result_for(job.job_id).segments[0].speaker_name == "Ерлан"
    manager.delete(job.job_id)
    manager.shutdown()


def test_completed_transcript_can_be_analyzed_with_source_segment_links(tmp_path: Path):
    settings = job_settings(tmp_path)
    manager = TranscriptionJobManager(settings, FakeTranscriber(), FakeDiarizer(), FakeAnalyzer())
    job = manager.create()
    source = job.workspace / "source.wav"
    write_speech_like_wav(source)

    manager.submit(job.job_id, source)
    assert job.future is not None
    job.future.result(timeout=10)

    protocol = manager.analyze(job.job_id)
    assert protocol.action_items[0].source_segment_ids == ("chunk-0001",)
    assert manager.analysis_for(job.job_id) == protocol
    manager.delete(job.job_id)
    manager.shutdown()


def test_analysis_api_returns_only_validated_protocol_data(tmp_path: Path):
    settings = job_settings(tmp_path)
    source = tmp_path / "meeting.wav"
    write_speech_like_wav(source)
    app = create_app(settings, FakeTranscriber(), FakeDiarizer(), FakeAnalyzer())

    with TestClient(app) as client, source.open("rb") as audio_file:
        created = client.post("/transcribe", files={"file": ("meeting.wav", audio_file, "audio/wav")})
        job_id = created.json()["id"]
        app.state.jobs.get(job_id).future.result(timeout=10)

        analysis = client.post(f"/jobs/{job_id}/analysis")
        assert analysis.status_code == 200
        assert analysis.json()["action_items"][0]["source_segment_ids"] == ["chunk-0001"]
        assert client.get(f"/jobs/{job_id}/analysis").json() == analysis.json()

    app.state.jobs.shutdown()


def test_analysis_api_does_not_send_a_transcript_when_no_local_model_is_configured(tmp_path: Path):
    settings = job_settings(tmp_path)
    source = tmp_path / "meeting.wav"
    write_speech_like_wav(source)
    app = create_app(settings, FakeTranscriber(), FakeDiarizer())

    with TestClient(app) as client, source.open("rb") as audio_file:
        created = client.post("/transcribe", files={"file": ("meeting.wav", audio_file, "audio/wav")})
        job_id = created.json()["id"]
        app.state.jobs.get(job_id).future.result(timeout=10)

        analysis = client.post(f"/jobs/{job_id}/analysis")
        assert analysis.status_code == 503
        assert analysis.json()["detail"] == "Локальная LLM не настроена."

    app.state.jobs.shutdown()
