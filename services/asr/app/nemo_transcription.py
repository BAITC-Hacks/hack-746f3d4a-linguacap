"""Optional local NVIDIA NeMo adapter for the Stage 4 comparison."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.config import Settings
from app.transcription import TranscriptionError

NEMO_FILENAME = "stt_kk_ru_fastconformer_hybrid_large.nemo"


class LocalNemoTranscriber:
    """Load the downloaded NeMo archive only; never call `from_pretrained`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: Any | None = None
        self._device = settings.selected_device

    @property
    def model_path(self) -> Path:
        return self._settings.nemo_model_dir / NEMO_FILENAME

    @property
    def is_installed(self) -> bool:
        return self.model_path.is_file()

    @property
    def device(self) -> str:
        return self._device

    def load(self) -> None:
        if self._model is not None:
            return
        if not self.is_installed:
            raise TranscriptionError("The local NVIDIA NeMo model weights are not installed.")
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        try:
            import nemo.collections.asr as nemo_asr
        except Exception as error:
            raise TranscriptionError("NVIDIA NeMo is not installed for the local ASR service.") from error
        self._model = self._load_for_device(nemo_asr, self._device)

    def _load_for_device(self, nemo_asr: Any, device: str) -> Any:
        try:
            model = nemo_asr.models.ASRModel.restore_from(str(self.model_path), map_location=device)
            return model.to(device).eval()
        except Exception as error:
            if device != "cpu":
                self._device = "cpu"
                return self._load_for_device(nemo_asr, "cpu")
            raise TranscriptionError("The local NVIDIA NeMo model could not be loaded.") from error

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        try:
            output = self._model.transcribe([str(wav_path)], batch_size=1)[0]
            return getattr(output, "text", str(output)).strip()
        except Exception as error:
            if self._device != "cpu":
                self._device = "cpu"
                self._model = None
                self.load()
                return self.transcribe(wav_path)
            raise TranscriptionError("The local NVIDIA NeMo model could not transcribe this chunk.") from error
