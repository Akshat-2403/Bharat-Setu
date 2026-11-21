import json
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.ai_provider import (
    ComplianceAssessment,
    DocumentExtraction,
    GeminiAIProvider,
    GeminiProviderError,
)


class FakeTypes:
    class Part:
        @staticmethod
        def from_bytes(data, mime_type):
            return {"inline_data": {"data": data, "mime_type": mime_type}}

    @staticmethod
    def GenerateContentConfig(**kwargs):
        return kwargs


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None

    def generate_content(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response, error)


def make_provider(payload=None, error=None):
    response = SimpleNamespace(
        text=json.dumps(payload) if payload is not None else None,
        usage_metadata=SimpleNamespace(prompt_token_count=25, candidates_token_count=18),
    )
    client = FakeClient(response=response, error=error)
    return GeminiAIProvider(client=client, model="test-model", sdk_types=FakeTypes), client


def test_gemini_extracts_structured_document_fields_from_inline_bytes():
    provider, client = make_provider({
        "vendor_name": "Bharat Components Ltd",
        "pan": "ABCDE1234F",
        "gstin": "27ABCDE1234F1Z5",
        "valid_from": "2025-04-01",
        "valid_until": "2026-03-31",
        "document_type": "GST",
        "confidence_score": 96.5,
        "registered_address": "Mumbai",
    })

    result = provider.extract_document(b"%PDF-1.7 raw bytes", "application/pdf", "GST")

    assert isinstance(result, DocumentExtraction)
    assert result.vendor_name == "Bharat Components Ltd"
    assert result.valid_until == "2026-03-31"
    assert client.models.request["model"] == "test-model"
    assert client.models.request["contents"][1]["inline_data"]["data"] == b"%PDF-1.7 raw bytes"
    assert client.models.request["config"]["response_schema"] is DocumentExtraction


@pytest.mark.parametrize(
    "payload",
    [
        {"document_type": "GST", "confidence_score": 105},
        {"document_type": "GST", "confidence_score": 85, "unexpected": "value"},
        {"document_type": "GST", "confidence_score": 80, "valid_until": "not-a-date"},
    ],
)
def test_gemini_rejects_invalid_structured_response(payload):
    provider, _ = make_provider(payload)
    with pytest.raises(GeminiProviderError) as error:
        provider.extract_document(b"pdf", "application/pdf")
    assert error.value.code == "invalid_response"


def test_gemini_timeout_returns_retryable_provider_error():
    provider, _ = make_provider(error=TimeoutError("request timeout"))
    with pytest.raises(GeminiProviderError, match="timed out") as error:
        provider.extract_document(b"pdf", "application/pdf")
    assert error.value.code == "timeout"


def test_gemini_returns_valid_compliance_assessment_for_each_requirement():
    provider, client = make_provider({
        "requirements": [{
            "requirement": "Active GST registration",
            "document_type": "GST",
            "status": "PASS",
            "finding": "The uploaded certificate shows an active registration.",
            "evidence_quote": "Status: Active",
            "recommended_action": "Officer should confirm the current registration.",
        }],
        "risk_score": 12,
        "discrepancies": [],
        "officer_review_summary": "GST evidence is present; confirm the certificate during officer review.",
    })
    assessment = provider.assess_compliance(
        {"requirements": [{"document_type": "GST", "mandatory": True, "description": "Active GST registration"}]},
        [{"filename": "gst.pdf", "mime_type": "application/pdf", "bytes": b"pdf", "fields": {"gstin": "27ABCDE1234F1Z5"}}],
        {"name": "Bharat Components Ltd"},
        [],
    )
    assert isinstance(assessment, ComplianceAssessment)
    assert assessment.risk_score == 12
    assert client.models.request["contents"][1]["inline_data"]["mime_type"] == "application/pdf"


def test_gemini_rejects_assessment_missing_tender_requirement():
    provider, _ = make_provider({
        "requirements": [], "risk_score": 0, "discrepancies": [],
        "officer_review_summary": "No result.",
    })
    with pytest.raises(GeminiProviderError, match="every tender requirement"):
        provider.assess_compliance(
            {"requirements": [{"document_type": "PAN", "mandatory": True}]}, [], {}, []
        )


def test_gemini_mode_requires_an_api_key():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="")
