from io import BytesIO

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import _ollama_model_status, create_app


def test_health_reports_local_runtime_state(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.find_spec", lambda module: object() if module == "torch" else None)
    monkeypatch.setattr("app.main.shutil.which", lambda binary: None)
    models_dir = tmp_path / "models"
    rukk_dir = models_dir / "asr-rukk"
    rukk_dir.mkdir(parents=True)
    (rukk_dir / "model.pt").write_text("local weights marker")

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
        "ffprobe": "not_found",
        "dependencies": {"torch": "available", "pyannote": "not_found", "nemo": "not_found", "docx": "not_found", "reportlab": "not_found"},
        "ready": {"transcription": False, "diarization": False, "analysis": False, "export": False},
        "startup_error": None,
        "analysis_model": None,
        "models": {
            "asr_rukk": {"state": "not_downloaded", "path": str(rukk_dir)},
            "asr_nemo": {"state": "not_downloaded", "path": str(models_dir / "nemo")},
            "diarization": {"state": "not_downloaded", "path": str(models_dir / "diarization" / "pyannote-community-1")},
            "llm": {"state": "disabled", "path": str(models_dir / "llm")},
        },
    }


def test_invalid_device_is_rejected():
    try:
        Settings.from_environment({"ASR_DEVICE": "cuda"})
    except ValueError as error:
        assert "ASR_DEVICE" in str(error)
    else:
        raise AssertionError("An unsupported device must be rejected")


def test_ollama_requires_the_configured_model_not_just_a_model_directory(monkeypatch):
    settings = Settings.from_environment({
        "ASR_DEVICE": "cpu",
        "ASR_LOCAL_LLM_PROVIDER": "ollama",
        "ASR_LOCAL_LLM_MODEL": "qwen3:4b",
    })
    monkeypatch.setattr("app.main.urlopen", lambda url, timeout: BytesIO(b'{"models":[{"name":"other:latest"}]}'))
    assert _ollama_model_status(settings).state == "not_downloaded"

    monkeypatch.setattr("app.main.urlopen", lambda url, timeout: BytesIO(b'{"models":[{"name":"qwen3:4b"}]}'))
    assert _ollama_model_status(settings).state == "available"
