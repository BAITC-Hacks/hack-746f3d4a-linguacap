from pathlib import Path

from app.config import Settings
from app.diarization import PYANNOTE_MODEL_DIRECTORY
from app import model_download


def test_pyannote_download_uses_the_explicit_local_offline_directory(monkeypatch, tmp_path: Path):
    settings = Settings.from_environment(
        {
            "ASR_DEVICE": "cpu",
            "ASR_MODELS_DIR": str(tmp_path / "models"),
        }
    )
    call: dict[str, object] = {}

    def fake_snapshot_download(**kwargs):
        call.update(kwargs)
        return str(kwargs["local_dir"])

    monkeypatch.setattr(model_download, "get_settings", lambda: settings)
    monkeypatch.setattr(model_download, "snapshot_download", fake_snapshot_download)

    model_download.download_pyannote_model()

    assert call == {
        "repo_id": model_download.PYANNOTE_REPOSITORY_ID,
        "local_dir": settings.diarization_model_dir / PYANNOTE_MODEL_DIRECTORY,
    }
