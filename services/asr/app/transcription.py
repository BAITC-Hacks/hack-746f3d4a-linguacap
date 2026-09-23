"""Offline greedy CTC inference for the local rukk TorchScript model."""

from __future__ import annotations

import re
import sys
import wave
from array import array
from pathlib import Path
from typing import Any

from app.config import Settings


class TranscriptionError(RuntimeError):
    """The local ASR model cannot transcribe a chunk."""


class LocalRukkTranscriber:
    """Loads `asr/rukk` once and transcribes 16 kHz mono WAV chunks locally."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._torch: Any | None = None
        self._model: Any | None = None
        self._tokens: dict[int, str] = {}
        self._blank_id: int | None = None
        self._device = settings.selected_device

    @property
    def model_path(self) -> Path:
        return self._settings.rukk_model_dir / "model.pt"

    @property
    def tokens_path(self) -> Path:
        return self._settings.rukk_model_dir / "tokens.lst"

    @property
    def is_installed(self) -> bool:
        return self.model_path.is_file() and self.tokens_path.is_file()

    @property
    def device(self) -> str:
        return self._device

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        if not self.is_installed:
            raise TranscriptionError("The local rukk model weights are not installed.")

        try:
            import torch
        except Exception as error:
            raise TranscriptionError("PyTorch is not installed for the local ASR service.") from error

        self._torch = torch
        self._tokens = self._read_tokens()
        self._blank_id = max(self._tokens) + 1
        self._model = self._load_for_device(self._device)

    def _read_tokens(self) -> dict[int, str]:
        tokens: dict[int, str] = {}
        try:
            for line in self.tokens_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    symbol, index = line.split("\t", 1)
                    tokens[int(index)] = symbol
        except (OSError, ValueError) as error:
            raise TranscriptionError("The local rukk token list is invalid.") from error
        if not tokens:
            raise TranscriptionError("The local rukk token list is empty.")
        return tokens

    def _load_for_device(self, device: str) -> Any:
        assert self._torch is not None
        try:
            model = self._torch.jit.load(str(self.model_path), map_location="cpu").eval()
            return model.to(device).eval()
        except Exception as error:
            if device != "cpu":
                self._device = "cpu"
                return self._load_for_device("cpu")
            raise TranscriptionError("The local rukk model could not be loaded.") from error

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        waveform = self._load_waveform(wav_path)
        try:
            return self._forward_and_decode(waveform)
        except Exception as error:
            if self._device != "cpu":
                self._device = "cpu"
                self._model = self._load_for_device("cpu")
                return self._forward_and_decode(waveform)
            raise TranscriptionError("The local rukk model could not transcribe this chunk.") from error

    def _load_waveform(self, wav_path: Path) -> Any:
        assert self._torch is not None
        try:
            with wave.open(str(wav_path), "rb") as source:
                if source.getframerate() != 16_000 or source.getnchannels() != 1 or source.getsampwidth() != 2:
                    raise TranscriptionError("ASR accepts only normalized 16 kHz mono WAV chunks.")
                samples = array("h")
                samples.frombytes(source.readframes(source.getnframes()))
        except wave.Error as error:
            raise TranscriptionError("The normalized audio chunk could not be read.") from error
        if sys.byteorder != "little":
            samples.byteswap()
        return self._torch.tensor(samples, dtype=self._torch.float32, device=self._device) / 32768.0

    def _forward_and_decode(self, waveform: Any) -> str:
        assert self._torch is not None and self._model is not None and self._blank_id is not None
        with self._torch.inference_mode():
            logits = self._model(waveform.unsqueeze(0))[0]
            token_ids = logits[0].argmax(dim=-1).tolist()

        decoded: list[str] = []
        previous: int | None = None
        for token_id in token_ids:
            if token_id != previous and token_id != self._blank_id:
                decoded.append(self._tokens.get(token_id, ""))
            previous = token_id
        return re.sub(r"\s+", " ", "".join(decoded).replace("|", " ").replace("_", " ")).strip()
