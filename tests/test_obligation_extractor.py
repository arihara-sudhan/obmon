from types import SimpleNamespace

import pytest

from app.schemas import Obligation, ObligationExtractionResult, ParsedDocument, ParsedPage
from app.services import obligation_extractor


def _document() -> ParsedDocument:
    return ParsedDocument(
        filename="contract.pdf",
        total_pages=2,
        pages=[
            ParsedPage(
                page_number=1,
                text="The supplier must deliver the report within 10 days.",
            ),
            ParsedPage(page_number=2, text="The customer may request changes."),
        ],
    )


def _llm_result() -> ObligationExtractionResult:
    return ObligationExtractionResult(
        has_obligations=True,
        obligations=[
            {
                "obligation_type": "delivery",
                "trigger_type": "contract_execution",
                "required_action": "Deliver the report",
                "time_constraint_type": "relative_deadline",
                "time_value": 10,
                "time_unit": "days",
                "fixed_deadline": None,
                "evidence_text": "The supplier must deliver the report within 10 days.",
                "page_number": 1,
                "confidence": 0.98,
                "requires_human_review": False,
            }
        ],
    )


def _fake_gemini(result: ObligationExtractionResult, captured: dict[str, object]):
    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=result.model_dump_json())

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.models = FakeModels()

    return FakeClient


def _patch_gemini(monkeypatch, fake_client) -> None:
    class FakeConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(
        obligation_extractor,
        "genai",
        SimpleNamespace(Client=fake_client),
    )
    monkeypatch.setattr(
        obligation_extractor,
        "types",
        SimpleNamespace(GenerateContentConfig=FakeConfig),
    )


def test_extract_obligations_uses_gemini_structured_output(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fake_client = _fake_gemini(_llm_result(), captured)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _patch_gemini(monkeypatch, fake_client)

    result = obligation_extractor.extract_obligations(_document())

    assert result.has_obligations is True
    assert result.obligations[0].page_number == 1
    assert captured["client_kwargs"] == {"api_key": "test-key"}
    assert captured["model"] == "gemini-3.8-flash"
    assert "--- PAGE 1 ---" in captured["contents"]
    assert "--- PAGE 2 ---" in captured["contents"]
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_schema is ObligationExtractionResult


def test_ambiguous_deadline_requires_human_review(monkeypatch) -> None:
    result = _llm_result()
    result.obligations[0].time_constraint_type = "ambiguous"
    result.obligations[0].requires_human_review = False
    captured: dict[str, object] = {}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _patch_gemini(monkeypatch, _fake_gemini(result, captured))

    extracted = obligation_extractor.extract_obligations(_document())

    assert extracted.obligations[0].requires_human_review is True


def test_extract_obligations_returns_empty_result(monkeypatch) -> None:
    empty_result = ObligationExtractionResult(has_obligations=False, obligations=[])
    captured: dict[str, object] = {}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _patch_gemini(monkeypatch, _fake_gemini(empty_result, captured))

    extracted = obligation_extractor.extract_obligations(_document())

    assert extracted == empty_result


def test_obligation_rejects_blank_evidence() -> None:
    with pytest.raises(ValueError):
        Obligation(
            obligation_type="notification",
            trigger_type="security_incident",
            required_action="Notify the customer",
            time_constraint_type="none",
            evidence_text="   ",
            page_number=1,
            confidence=0.9,
            requires_human_review=False,
        )


def test_obligation_rejects_generic_trigger() -> None:
    with pytest.raises(ValueError):
        Obligation(
            obligation_type="notification",
            trigger_type="event",
            required_action="Notify the customer",
            time_constraint_type="none",
            evidence_text="The supplier must notify the customer.",
            page_number=1,
            confidence=0.9,
            requires_human_review=False,
        )
