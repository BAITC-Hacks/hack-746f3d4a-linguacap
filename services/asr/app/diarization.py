"""Local-only pyannote adapter and timestamp alignment for speaker diarization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings
import wave
from typing import Any, Iterable

from app.config import Settings

PYANNOTE_MODEL_DIRECTORY = "pyannote-community-1"
PYANNOTE_CONFIG_FILENAME = "config.yaml"


class DiarizationError(RuntimeError):
    """A local diarization runtime or its explicitly downloaded model failed."""


@dataclass(frozen=True)
class SpeakerTurn:
    speaker_id: str
    start_seconds: float
    end_seconds: float


class LocalPyannoteDiarizer:
    """Load a pre-downloaded pyannote pipeline without a token or network call."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pipeline: Any | None = None

    @property
    def model_path(self) -> Path:
        return self._settings.diarization_model_dir / PYANNOTE_MODEL_DIRECTORY

    @property
    def is_installed(self) -> bool:
        return (self.model_path / PYANNOTE_CONFIG_FILENAME).is_file()

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        if not self.is_installed:
            raise DiarizationError("Локальная модель диаризации не установлена.")
        try:
            # The pipeline receives an in-memory waveform below, so it does not
            # call TorchCodec to decode the audio path.
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=r"(?s).*torchcodec.*")
                from pyannote.audio import Pipeline
                self._pipeline = Pipeline.from_pretrained(str(self.model_path))
        except Exception as error:
            raise DiarizationError("Локальная модель диаризации не загрузилась.") from error

    @staticmethod
    def _waveform(wav_path: Path) -> Any:
        try:
            with wave.open(str(wav_path), "rb") as source:
                if source.getnchannels() != 1 or source.getframerate() != 16_000 or source.getsampwidth() != 2:
                    raise DiarizationError("Диаризация принимает только WAV 16 kHz mono PCM 16-bit.")
                frames = source.readframes(source.getnframes())
        except (OSError, wave.Error) as error:
            raise DiarizationError("Не удалось прочитать подготовленный WAV для диаризации.") from error

        try:
            import torch

            # A mutable buffer avoids PyTorch's non-writable-buffer warning.
            samples = torch.frombuffer(bytearray(frames), dtype=torch.int16).to(dtype=torch.float32)
            return samples.unsqueeze(0).div_(32768.0)
        except Exception as error:
            raise DiarizationError("Локальный PyTorch не подготовил аудио для диаризации.") from error

    def diarize(self, wav_path: Path) -> tuple[SpeakerTurn, ...]:
        self._load()
        try:
            output = self._pipeline({"waveform": self._waveform(wav_path), "sample_rate": 16_000})
            annotation = getattr(output, "exclusive_speaker_diarization", output)
            raw_turns = [
                SpeakerTurn(str(label), float(turn.start), float(turn.end))
                for turn, _, label in annotation.itertracks(yield_label=True)
                if turn.end > turn.start
            ]
            return normalize_speaker_turns(raw_turns)
        except DiarizationError:
            raise
        except Exception as error:
            raise DiarizationError("Локальная диаризация не завершилась.") from error


def normalize_speaker_turns(turns: Iterable[SpeakerTurn], *, merge_gap_seconds: float = 0.2) -> tuple[SpeakerTurn, ...]:
    """Stabilize local labels into SPEAKER_01… and merge short same-speaker gaps."""
    ordered = sorted(turns, key=lambda turn: (turn.start_seconds, turn.end_seconds, turn.speaker_id))
    labels: dict[str, str] = {}
    normalized: list[SpeakerTurn] = []
    for turn in ordered:
        speaker_id = labels.setdefault(turn.speaker_id, f"SPEAKER_{len(labels) + 1:02d}")
        candidate = SpeakerTurn(speaker_id, round(turn.start_seconds, 3), round(turn.end_seconds, 3))
        if normalized and normalized[-1].speaker_id == candidate.speaker_id and candidate.start_seconds <= normalized[-1].end_seconds + merge_gap_seconds:
            previous = normalized[-1]
            normalized[-1] = SpeakerTurn(previous.speaker_id, previous.start_seconds, max(previous.end_seconds, candidate.end_seconds))
        else:
            normalized.append(candidate)
    return tuple(normalized)


def speaker_for_interval(start_seconds: float, end_seconds: float, turns: Iterable[SpeakerTurn]) -> str | None:
    """Choose the speaker whose turn overlaps a transcript interval the longest."""
    best_speaker: str | None = None
    best_overlap = 0.0
    for turn in turns:
        overlap = min(end_seconds, turn.end_seconds) - max(start_seconds, turn.start_seconds)
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = turn.speaker_id
    return best_speaker
