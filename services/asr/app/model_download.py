"""Download only the required public rukk model files into the local model store."""

from __future__ import annotations

from huggingface_hub import hf_hub_download

from app.config import get_settings

REPOSITORY_ID = "alibiserikbay/kazakh-russian-mixed-stt"
RUKK_FILES = ("asr/rukk/model.pt", "asr/rukk/tokens.lst")


def download_rukk_model() -> None:
    settings = get_settings()
    for filename in RUKK_FILES:
        local_path = hf_hub_download(
            repo_id=REPOSITORY_ID,
            filename=filename,
            local_dir=settings.models_dir,
        )
        print(local_path)


if __name__ == "__main__":
    download_rukk_model()
