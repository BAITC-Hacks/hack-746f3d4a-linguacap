from datetime import date
import json

import pytest

from app.analysis import LocalOllamaProtocolAnalyzer, ProtocolAnalysisError, ProtocolSourceSegment, protocol_from_payload
from app.config import Settings


def valid_payload() -> dict[str, object]:
    return {
        "title": "Планирование",
        "summary": "Обсудили отчёт.",
        "key_points": ["Отчёт нужно подготовить."],
        "action_items": [
            {
                "description": "Подготовить отчёт",
                "assignee": None,
                "deadline_text": "до пятницы",
                "deadline": None,
                "source_segment_ids": ["chunk-0001"],
                "confidence": 0.8,
                "status": "new",
            }
        ],
    }


def test_protocol_rejects_action_item_without_a_real_transcript_source():
    payload = valid_payload()
    payload["action_items"][0]["source_segment_ids"] = ["unknown"]  # type: ignore[index]

    with pytest.raises(ProtocolAnalysisError, match="неизвестный сегмент"):
        protocol_from_payload(payload, source_segment_ids={"chunk-0001"})


def test_protocol_keeps_unknown_assignee_and_relative_deadline_empty_or_verbatim():
    protocol = protocol_from_payload(valid_payload(), source_segment_ids={"chunk-0001"})

    item = protocol.action_items[0]
    assert item.assignee is None
    assert item.deadline_text == "до пятницы"
    assert item.deadline is None


def test_protocol_accepts_only_an_iso_deadline_when_one_is_explicit():
    payload = valid_payload()
    payload["action_items"][0]["deadline"] = "2026-09-25"  # type: ignore[index]

    protocol = protocol_from_payload(payload, source_segment_ids={"chunk-0001"})
    assert protocol.action_items[0].deadline == date(2026, 9, 25)


def test_ollama_client_posts_only_to_loopback_and_validates_the_reply(monkeypatch):
    settings = Settings.from_environment(
        {
            "ASR_DEVICE": "cpu",
            "ASR_LOCAL_LLM_PROVIDER": "ollama",
            "ASR_LOCAL_LLM_MODEL": "local-model",
            "ASR_LOCAL_LLM_BASE_URL": "http://127.0.0.1:11434",
        }
    )
    observed: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps({"message": {"content": json.dumps(valid_payload())}}).encode()

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["timeout"] = timeout
        observed["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("app.analysis.urlopen", fake_urlopen)
    result = LocalOllamaProtocolAnalyzer(settings).analyze(
        (ProtocolSourceSegment("chunk-0001", 0, 1, "Подготовить отчёт до пятницы", "Спикер 1"),)
    )

    assert observed["url"] == "http://127.0.0.1:11434/api/chat"
    assert observed["payload"]["think"] is False  # type: ignore[index]
    assert observed["payload"]["options"] == {"temperature": 0, "num_predict": 2_048, "seed": 0}  # type: ignore[index]
    assert observed["payload"]["format"]["type"] == "object"  # type: ignore[index]
    assert result.action_items[0].deadline_text == "до пятницы"


def test_external_local_llm_endpoint_is_rejected_by_settings():
    with pytest.raises(ValueError, match="loopback"):
        Settings.from_environment({"ASR_LOCAL_LLM_BASE_URL": "https://example.com"})
