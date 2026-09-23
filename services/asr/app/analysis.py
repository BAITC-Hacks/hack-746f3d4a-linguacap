"""Strictly local meeting-protocol analysis and JSON validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any, Iterable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings


class ProtocolAnalysisError(RuntimeError):
    """A local protocol analysis cannot safely produce a validated result."""


class LocalModelUnavailableError(ProtocolAnalysisError):
    """No configured local LLM runtime can process the transcript."""


@dataclass(frozen=True)
class ProtocolSourceSegment:
    """The only transcript data that is sent to the configured local runtime."""

    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    speaker_name: str | None


@dataclass(frozen=True)
class ActionItem:
    description: str
    assignee: str | None
    deadline_text: str | None
    deadline: date | None
    source_segment_ids: tuple[str, ...]
    confidence: float
    status: str = "new"


@dataclass(frozen=True)
class MeetingProtocol:
    title: str
    summary: str
    key_points: tuple[str, ...]
    action_items: tuple[ActionItem, ...]


class ProtocolAnalyzer(Protocol):
    @property
    def is_configured(self) -> bool: ...

    def analyze(self, segments: tuple[ProtocolSourceSegment, ...]) -> MeetingProtocol: ...


class DisabledProtocolAnalyzer:
    """Safe default: no transcript leaves the process until a local model is configured."""

    @property
    def is_configured(self) -> bool:
        return False

    def analyze(self, segments: tuple[ProtocolSourceSegment, ...]) -> MeetingProtocol:
        raise LocalModelUnavailableError("Локальная LLM пока не настроена.")


class LocalOllamaProtocolAnalyzer:
    """Call only a loopback Ollama server and accept only the protocol schema."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.local_llm_model)

    def analyze(self, segments: tuple[ProtocolSourceSegment, ...]) -> MeetingProtocol:
        if not self.is_configured:
            raise LocalModelUnavailableError("Укажите ASR_LOCAL_LLM_MODEL для локальной Ollama-модели.")
        if not segments:
            raise ProtocolAnalysisError("Невозможно подготовить протокол без сегментов транскрипта.")

        request_payload = {
            "model": self._settings.local_llm_model,
            "stream": False,
            "think": False,
            "format": _PROTOCOL_JSON_SCHEMA,
            "options": {"temperature": 0.1, "num_predict": 1_200},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_transcript_prompt(segments)},
            ],
        }
        request = Request(
            f"{self._settings.local_llm_base_url.rstrip('/')}/api/chat",
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._settings.local_llm_timeout_seconds) as response:  # noqa: S310 -- origin is validated as loopback in Settings.
                response_payload = json.loads(response.read().decode("utf-8"))
            content = response_payload["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Ollama message content is not text.")
            parsed = json.loads(content)
        except (HTTPError, URLError, OSError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProtocolAnalysisError("Локальная LLM не вернула корректный JSON протокола.") from error

        return protocol_from_payload(parsed, source_segment_ids={segment.segment_id for segment in segments})


_SYSTEM_PROMPT = """Ты формируешь протокол совещания только из переданных сегментов транскрипта.
Верни ровно JSON без Markdown. Не выдумывай факты, ответственных или сроки. Если
ответственный или срок не назван явно, верни null. В каждом поручении укажи один
или несколько идентификаторов исходных сегментов из списка. deadline заполняй
только полной ISO-датой YYYY-MM-DD, иначе null; исходную формулировку срока
сохрани в deadline_text. status всегда \"new\"."""

_PROTOCOL_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "summary", "key_points", "action_items"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["description", "assignee", "deadline_text", "deadline", "source_segment_ids", "confidence", "status"],
                "properties": {
                    "description": {"type": "string"},
                    "assignee": {"type": ["string", "null"]},
                    "deadline_text": {"type": ["string", "null"]},
                    "deadline": {"type": ["string", "null"]},
                    "source_segment_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "status": {"type": "string", "enum": ["new"]},
                },
            },
        },
    },
}


def _build_transcript_prompt(segments: Iterable[ProtocolSourceSegment]) -> str:
    payload = [
        {
            "id": segment.segment_id,
            "start_seconds": segment.start_seconds,
            "end_seconds": segment.end_seconds,
            "speaker": segment.speaker_name,
            "text": segment.text,
        }
        for segment in segments
    ]
    return (
        "Сформируй JSON со схемой: title (string), summary (string), key_points "
        "(string[]), action_items ({description, assignee, deadline_text, deadline, "
        "source_segment_ids, confidence, status}[]). Транскрипт:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def protocol_from_payload(payload: Any, *, source_segment_ids: set[str]) -> MeetingProtocol:
    """Validate untrusted model JSON and preserve only grounded action items."""
    if not isinstance(payload, Mapping):
        raise ProtocolAnalysisError("Локальная LLM вернула протокол не в виде JSON-объекта.")

    title = _required_text(payload, "title", max_length=300)
    summary = _required_text(payload, "summary", max_length=6_000)
    raw_key_points = payload.get("key_points")
    if not isinstance(raw_key_points, list) or len(raw_key_points) > 30:
        raise ProtocolAnalysisError("Поле key_points имеет недопустимый формат.")
    key_points = tuple(_text(value, "key_points", max_length=1_000) for value in raw_key_points)

    raw_items = payload.get("action_items")
    if not isinstance(raw_items, list) or len(raw_items) > 100:
        raise ProtocolAnalysisError("Поле action_items имеет недопустимый формат.")
    action_items = tuple(_action_item(item, source_segment_ids) for item in raw_items)
    return MeetingProtocol(title, summary, key_points, action_items)


def _action_item(raw_item: Any, source_segment_ids: set[str]) -> ActionItem:
    if not isinstance(raw_item, Mapping):
        raise ProtocolAnalysisError("Поручение должно быть JSON-объектом.")
    source_ids = raw_item.get("source_segment_ids")
    if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 20 or not all(isinstance(item, str) for item in source_ids):
        raise ProtocolAnalysisError("У поручения должны быть идентификаторы исходных сегментов.")
    if len(set(source_ids)) != len(source_ids) or not set(source_ids).issubset(source_segment_ids):
        raise ProtocolAnalysisError("Поручение ссылается на неизвестный сегмент транскрипта.")

    raw_confidence = raw_item.get("confidence")
    if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)) or not 0 <= raw_confidence <= 1:
        raise ProtocolAnalysisError("confidence поручения должно находиться в диапазоне от 0 до 1.")
    status = raw_item.get("status")
    if status != "new":
        raise ProtocolAnalysisError("status поручения должен быть равен new.")
    raw_deadline = raw_item.get("deadline")
    if raw_deadline is None:
        deadline = None
    elif isinstance(raw_deadline, str):
        try:
            deadline = date.fromisoformat(raw_deadline)
        except ValueError as error:
            raise ProtocolAnalysisError("deadline должен быть ISO-датой YYYY-MM-DD или null.") from error
    else:
        raise ProtocolAnalysisError("deadline должен быть ISO-датой YYYY-MM-DD или null.")

    return ActionItem(
        description=_required_text(raw_item, "description", max_length=2_000),
        assignee=_optional_text(raw_item.get("assignee"), "assignee", max_length=300),
        deadline_text=_optional_text(raw_item.get("deadline_text"), "deadline_text", max_length=300),
        deadline=deadline,
        source_segment_ids=tuple(source_ids),
        confidence=float(raw_confidence),
        status=status,
    )


def _required_text(payload: Mapping[str, Any], field: str, *, max_length: int) -> str:
    return _text(payload.get(field), field, max_length=max_length)


def _optional_text(value: Any, field: str, *, max_length: int) -> str | None:
    return None if value is None else _text(value, field, max_length=max_length)


def _text(value: Any, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not (cleaned := value.strip()) or len(cleaned) > max_length:
        raise ProtocolAnalysisError(f"Поле {field} содержит недопустимый текст.")
    return cleaned
