"""Configuration for the local-only ASR service."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

SUPPORTED_DEVICES = frozenset({"auto", "mps", "cpu"})
SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _path_from_env(value: str, *, base_dir: Path) -> Path:
    """Resolve a configured path without requiring the directory to exist."""
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (base_dir / candidate).resolve()


def _mps_is_available() -> tuple[bool, str | None]:
    """Return MPS availability without making PyTorch a Stage 1 dependency."""
    if platform.system() != "Darwin":
        return False, "MPS is available only on macOS."

    try:
        import torch  # type: ignore[import-not-found]
    except Exception:
        return False, "PyTorch is not installed yet."

    try:
        available = torch.backends.mps.is_available()
        built = torch.backends.mps.is_built()
    except Exception:
        return False, "PyTorch could not inspect MPS support."

    if available and built:
        return True, None
    if not built:
        return False, "Installed PyTorch was built without MPS support."
    return False, "MPS is not available on this host."


def _positive_int(value: str, *, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return parsed


def _positive_float(value: str, *, name: str, allow_zero: bool = False) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number.") from error
    if parsed < 0 or (parsed == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'zero or greater' if allow_zero else 'greater than zero'}.")
    return parsed


def resolve_device(requested_device: str) -> tuple[str, str | None]:
    """Select the safe device and explain an automatic fallback, if any."""
    if requested_device == "cpu":
        return "cpu", None

    mps_available, reason = _mps_is_available()
    if mps_available:
        return "mps", None

    return "cpu", reason


@dataclass(frozen=True)
class Settings:
    """Immutable service configuration sourced from environment variables."""

    service_root: Path
    models_dir: Path
    rukk_model_dir: Path
    diarization_model_dir: Path
    llm_model_dir: Path
    requested_device: str
    selected_device: str
    device_fallback_reason: str | None
    ffmpeg_binary: str
    allowed_origins: tuple[str, ...]
    ffprobe_binary: str = "ffprobe"
    runtime_dir: Path = SERVICE_ROOT / "runtime"
    max_upload_bytes: int = 1_073_741_824
    max_audio_duration_seconds: int = 14_400
    chunk_duration_seconds: float = 18.0
    chunk_overlap_seconds: float = 1.0
    vad_threshold_db: float = -45.0
    vad_min_speech_seconds: float = 0.3
    vad_min_silence_seconds: float = 0.5

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        requested_device = env.get("ASR_DEVICE", "auto").strip().lower()
        if requested_device not in SUPPORTED_DEVICES:
            accepted = ", ".join(sorted(SUPPORTED_DEVICES))
            raise ValueError(f"ASR_DEVICE must be one of: {accepted}.")

        models_dir = _path_from_env(env.get("ASR_MODELS_DIR", "models"), base_dir=SERVICE_ROOT)
        selected_device, fallback_reason = resolve_device(requested_device)
        chunk_duration_seconds = _positive_float(env.get("ASR_CHUNK_DURATION_SECONDS", "18"), name="ASR_CHUNK_DURATION_SECONDS")
        chunk_overlap_seconds = _positive_float(
            env.get("ASR_CHUNK_OVERLAP_SECONDS", "1"), name="ASR_CHUNK_OVERLAP_SECONDS", allow_zero=True
        )
        if chunk_overlap_seconds >= chunk_duration_seconds:
            raise ValueError("ASR_CHUNK_OVERLAP_SECONDS must be smaller than ASR_CHUNK_DURATION_SECONDS.")
        allowed_origins = tuple(
            origin.strip()
            for origin in env.get("ASR_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        )

        return cls(
            service_root=SERVICE_ROOT,
            models_dir=models_dir,
            rukk_model_dir=_path_from_env(env.get("ASR_RUKK_MODEL_DIR", str(models_dir / "asr" / "rukk")), base_dir=SERVICE_ROOT),
            diarization_model_dir=_path_from_env(env.get("ASR_DIARIZATION_MODEL_DIR", str(models_dir / "diarization")), base_dir=SERVICE_ROOT),
            llm_model_dir=_path_from_env(env.get("ASR_LLM_MODEL_DIR", str(models_dir / "llm")), base_dir=SERVICE_ROOT),
            requested_device=requested_device,
            selected_device=selected_device,
            device_fallback_reason=fallback_reason,
            ffmpeg_binary=env.get("ASR_FFMPEG_BINARY", "ffmpeg").strip() or "ffmpeg",
            allowed_origins=allowed_origins,
            ffprobe_binary=env.get("ASR_FFPROBE_BINARY", "ffprobe").strip() or "ffprobe",
            runtime_dir=_path_from_env(env.get("ASR_RUNTIME_DIR", "runtime"), base_dir=SERVICE_ROOT),
            max_upload_bytes=_positive_int(env.get("ASR_MAX_UPLOAD_BYTES", "1073741824"), name="ASR_MAX_UPLOAD_BYTES"),
            max_audio_duration_seconds=_positive_int(
                env.get("ASR_MAX_AUDIO_DURATION_SECONDS", "14400"), name="ASR_MAX_AUDIO_DURATION_SECONDS"
            ),
            chunk_duration_seconds=chunk_duration_seconds,
            chunk_overlap_seconds=chunk_overlap_seconds,
            vad_threshold_db=float(env.get("ASR_VAD_THRESHOLD_DB", "-45")),
            vad_min_speech_seconds=_positive_float(
                env.get("ASR_VAD_MIN_SPEECH_SECONDS", "0.3"), name="ASR_VAD_MIN_SPEECH_SECONDS"
            ),
            vad_min_silence_seconds=_positive_float(
                env.get("ASR_VAD_MIN_SILENCE_SECONDS", "0.5"), name="ASR_VAD_MIN_SILENCE_SECONDS"
            ),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_environment()
