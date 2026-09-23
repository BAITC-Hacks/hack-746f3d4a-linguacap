from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_local_runtime_state(tmp_path):
    models_dir = tmp_path / "models"
    rukk_dir = models_dir / "asr-rukk"
    rukk_dir.mkdir(parents=True)
    (rukk_dir / "model.bin").write_text("local weights marker")

    settings = Settings(
        service_root=tmp_path,
        models_dir=models_dir,
        rukk_model_dir=rukk_dir,
        nemo_model_dir=models_dir / "nemo",
        diarization_model_dir=models_dir / "diarization",
        llm_model_dir=models_dir / "llm",
        requested_device="cpu",
        selected_device="cpu",
        device_fallback_reason=None,
        ffmpeg_binary="missing-ffmpeg-for-test",
        allowed_origins=("http://localhost:3000",),
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "local-asr",
        "device": {"requested": "cpu", "selected": "cpu", "fallback_reason": None},
        "ffmpeg": "not_found",
        "models": {
            "asr_rukk": {"state": "available", "path": str(rukk_dir)},
            "asr_nemo": {"state": "not_downloaded", "path": str(models_dir / "nemo")},
            "diarization": {"state": "not_downloaded", "path": str(models_dir / "diarization")},
            "llm": {"state": "not_downloaded", "path": str(models_dir / "llm")},
        },
    }


def test_invalid_device_is_rejected():
    try:
        Settings.from_environment({"ASR_DEVICE": "cuda"})
    except ValueError as error:
        assert "ASR_DEVICE" in str(error)
    else:
        raise AssertionError("An unsupported device must be rejected")
