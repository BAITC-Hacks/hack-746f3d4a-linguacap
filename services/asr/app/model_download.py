"""Download only the required public rukk model files into the local model store."""

from __future__ import annotations

import argparse

from huggingface_hub import hf_hub_download, snapshot_download

from app.config import get_settings
from app.diarization import PYANNOTE_MODEL_DIRECTORY

REPOSITORY_ID = "alibiserikbay/kazakh-russian-mixed-stt"
RUKK_FILES = ("asr/rukk/model.pt", "asr/rukk/tokens.lst")
NEMO_REPOSITORY_ID = "nvidia/stt_kk_ru_fastconformer_hybrid_large"
NEMO_FILENAME = "stt_kk_ru_fastconformer_hybrid_large.nemo"
PYANNOTE_REPOSITORY_ID = "pyannote/speaker-diarization-community-1"


def download_rukk_model() -> None:
    settings = get_settings()
    for filename in RUKK_FILES:
        local_path = hf_hub_download(
            repo_id=REPOSITORY_ID,
            filename=filename,
            local_dir=settings.models_dir,
        )
        print(local_path)


def download_nemo_model() -> None:
    settings = get_settings()
    local_path = hf_hub_download(
        repo_id=NEMO_REPOSITORY_ID,
        filename=NEMO_FILENAME,
        local_dir=settings.nemo_model_dir,
    )
    print(local_path)


def download_pyannote_model() -> None:
    """Copy every gated pyannote pipeline file into the local model store.

    Hugging Face authentication is resolved by ``huggingface_hub`` itself.  The
    service never receives or persists a token; it loads this folder offline.
    """
    settings = get_settings()
    local_path = snapshot_download(
        repo_id=PYANNOTE_REPOSITORY_ID,
        local_dir=settings.diarization_model_dir / PYANNOTE_MODEL_DIRECTORY,
    )
    print(local_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download one explicitly selected local model.")
    parser.add_argument("model", choices=("rukk", "nemo", "pyannote"), nargs="?", default="rukk")
    selected_model = parser.parse_args().model
    if selected_model == "rukk":
        download_rukk_model()
    elif selected_model == "nemo":
        download_nemo_model()
    else:
        download_pyannote_model()
