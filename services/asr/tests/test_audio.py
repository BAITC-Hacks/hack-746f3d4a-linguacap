import math
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.audio import AudioValidationError, cleanup_workspace, extension_for_upload, prepare_audio
from app.config import Settings
from app.main import create_app


def write_speech_like_wav(path: Path) -> None:
    sample_rate = 16_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)

        silence = b"\x00\x00" * sample_rate
        output.writeframes(silence)
        output.writeframes(
            b"".join(
                int(10_000 * math.sin(2 * math.pi * 440 * index / sample_rate)).to_bytes(2, "little", signed=True)
                for index in range(sample_rate * 2)
            )
        )
        output.writeframes(silence)


def audio_settings(tmp_path: Path) -> Settings:
    return Settings.from_environment(
        {
            "ASR_DEVICE": "cpu",
            "ASR_RUNTIME_DIR": str(tmp_path / "runtime"),
            "ASR_MAX_UPLOAD_BYTES": "10000000",
            "ASR_MAX_AUDIO_DURATION_SECONDS": "30",
            "ASR_CHUNK_DURATION_SECONDS": "20",
            "ASR_CHUNK_OVERLAP_SECONDS": "1",
            "ASR_VAD_THRESHOLD_DB": "-45",
            "ASR_VAD_MIN_SPEECH_SECONDS": "0.3",
            "ASR_VAD_MIN_SILENCE_SECONDS": "0.5",
        }
    )


def test_prepare_audio_normalizes_and_splits_detected_speech(tmp_path: Path):
    source = tmp_path / "meeting.wav"
    write_speech_like_wav(source)
    settings = audio_settings(tmp_path)
    workspace = settings.runtime_dir / "manual-test"
    workspace.mkdir(parents=True)

    try:
        prepared = prepare_audio(source, workspace, settings)

        assert prepared.source.duration_seconds == pytest.approx(4, abs=0.1)
        assert prepared.normalized.sample_rate == 16_000
        assert prepared.normalized.channels == 1
        assert len(prepared.chunks) == 1
        assert prepared.chunks[0].start_seconds == pytest.approx(0.99, abs=0.1)
        assert prepared.chunks[0].end_seconds == pytest.approx(3.0, abs=0.1)
        assert prepared.chunks[0].path.is_file()
    finally:
        cleanup_workspace(workspace, settings)

    assert not workspace.exists()


def test_upload_extension_and_content_type_must_match():
    assert extension_for_upload("meeting.mp3", "audio/mpeg") == ".mp3"

    with pytest.raises(AudioValidationError, match="does not match"):
        extension_for_upload("meeting.mp3", "video/mp4")

    with pytest.raises(AudioValidationError, match="Supported formats"):
        extension_for_upload("meeting.ogg", "audio/ogg")


def test_prepare_audio_endpoint_returns_timestamps_and_cleans_up(tmp_path: Path):
    source = tmp_path / "meeting.wav"
    write_speech_like_wav(source)
    settings = audio_settings(tmp_path)

    with TestClient(create_app(settings)) as client, source.open("rb") as audio_file:
        response = client.post(
            "/prepare-audio",
            files={"file": ("meeting.wav", audio_file, "audio/wav")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["normalized"]["sample_rate"] == 16_000
    assert payload["normalized"]["channels"] == 1
    assert payload["chunks"][0]["start_seconds"] < payload["chunks"][0]["end_seconds"]
    assert not settings.runtime_dir.exists() or not any(settings.runtime_dir.iterdir())
