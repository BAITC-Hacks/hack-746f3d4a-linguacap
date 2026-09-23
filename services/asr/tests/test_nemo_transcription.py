from app.config import Settings
from app.nemo_transcription import LocalNemoTranscriber, NEMO_FILENAME


def test_nemo_adapter_only_accepts_the_explicit_local_archive(tmp_path):
    models_dir = tmp_path / "models"
    model_dir = models_dir / "nemo"
    settings = Settings(
        service_root=tmp_path,
        models_dir=models_dir,
        rukk_model_dir=models_dir / "rukk",
        nemo_model_dir=model_dir,
        diarization_model_dir=models_dir / "diarization",
        llm_model_dir=models_dir / "llm",
        requested_device="cpu",
        selected_device="cpu",
        device_fallback_reason=None,
        ffmpeg_binary="ffmpeg",
        allowed_origins=("http://localhost:3000",),
    )
    transcriber = LocalNemoTranscriber(settings)

    assert transcriber.model_path == model_dir / NEMO_FILENAME
    assert not transcriber.is_installed

    model_dir.mkdir(parents=True)
    transcriber.model_path.write_bytes(b"local weights marker")

    assert transcriber.is_installed
