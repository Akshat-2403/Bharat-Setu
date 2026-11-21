"""Structured multimodal Gemini provider for document and compliance analysis."""
import json
import logging
import time
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import settings

logger = logging.getLogger(__name__)


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DocumentExtraction(StrictOutput):
    vendor_name: str | None = None
    pan: str | None = None
    gstin: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    document_type: str = Field(min_length=1, max_length=80)
    confidence_score: float = Field(ge=0, le=100)
    udyam_number: str | None = None
    establishment_code: str | None = None
    registered_address: str | None = None
    turnover_inr: str | None = None
    years_experience: str | None = None

    @field_validator("valid_from", "valid_until")
    @classmethod
    def validate_iso_date(cls, value: str | None) -> str | None:
        if value:
            date.fromisoformat(value)
        return value


class RequirementAssessment(StrictOutput):
    requirement: str = Field(min_length=1, max_length=240)
    document_type: str = Field(min_length=1, max_length=80)
    status: Literal["PASS", "FAIL", "WARNING"]
    finding: str = Field(min_length=1, max_length=1200)
    evidence_quote: str | None = Field(default=None, max_length=800)
    recommended_action: str | None = Field(default=None, max_length=800)


class ComplianceDiscrepancy(StrictOutput):
    description: str = Field(min_length=1, max_length=800)
    evidence_quote: str = Field(min_length=1, max_length=800)
    document_name: str = Field(min_length=1, max_length=240)


class ComplianceAssessment(StrictOutput):
    requirements: list[RequirementAssessment]
    risk_score: int = Field(ge=0, le=100)
    discrepancies: list[ComplianceDiscrepancy]
    officer_review_summary: str = Field(min_length=1, max_length=1600)


class GeminiProviderError(RuntimeError):
    """Safe-to-display provider error with a stable failure code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GeminiAIProvider:
    def __init__(self, client=None, model: str | None = None, sdk_types=None):
        self.model = model or settings.GEMINI_MODEL
        self.sdk_types = sdk_types
        if client is None:
            if not settings.GEMINI_API_KEY:
                raise GeminiProviderError("configuration", "Gemini API key is not configured.")
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:
                raise GeminiProviderError("configuration", "The google-genai SDK is not installed.") from exc
            self.sdk_types = types
            client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000)),
            )
        self.client = client

    def _get_sdk_types(self):
        if self.sdk_types is None:
            try:
                from google.genai import types
            except ImportError as exc:
                raise GeminiProviderError("configuration", "The google-genai SDK is not installed.") from exc
            self.sdk_types = types
        return self.sdk_types

    def _file_part(self, file_bytes: bytes, mime_type: str):
        return self._get_sdk_types().Part.from_bytes(data=file_bytes, mime_type=mime_type)

    @staticmethod
    def _log_result(operation: str, started: float, response=None, error_code: str | None = None) -> None:
        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "Gemini request completed",
            extra={
                "provider": "gemini",
                "operation": operation,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "input_tokens": getattr(usage, "prompt_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
                "error_code": error_code,
            },
        )

    def _generate(self, operation: str, prompt: str, schema: type[BaseModel], parts: list | None = None) -> BaseModel:
        started = time.perf_counter()
        response = None
        try:
            types = self._get_sdk_types()
            contents = [prompt, *(parts or [])]
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
            response_text = getattr(response, "text", None)
            if not response_text:
                raise GeminiProviderError("invalid_response", "Gemini returned an empty structured response.")
            try:
                parsed = schema.model_validate(json.loads(response_text))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                raise GeminiProviderError("invalid_response", "Gemini returned data that did not match the required schema.") from exc
            self._log_result(operation, started, response)
            return parsed
        except GeminiProviderError as exc:
            self._log_result(operation, started, response, exc.code)
            raise
        except Exception as exc:
            error_name = type(exc).__name__.lower()
            is_timeout = isinstance(exc, TimeoutError) or "timeout" in error_name or "timeout" in str(exc).lower()
            code = "timeout" if is_timeout else "provider_error"
            message = "Gemini request timed out. Retry processing." if is_timeout else "Gemini could not process this request. Retry processing."
            self._log_result(operation, started, response, code)
            raise GeminiProviderError(code, message) from exc

    def extract_document(self, file_bytes: bytes, mime_type: str, expected_document_type: str | None = None) -> DocumentExtraction:
        prompt = (
            "Extract only facts visibly supported by this document. Do not infer missing identifiers, names, "
            "or dates. Return null for fields that are not present or legible. Dates must use YYYY-MM-DD. "
            "confidence_score is 0 to 100 and reflects the overall extraction certainty. "
            f"If supplied, use this requested document category as a hint, not as evidence: {expected_document_type or 'none'}."
        )
        return self._generate(
            "document_extraction", prompt, DocumentExtraction,
            [self._file_part(file_bytes, mime_type)],
        )

    def assess_compliance(self, tender: dict, documents: list[dict], vendor: dict, mock_verifications: list[dict]) -> ComplianceAssessment:
        prompt = (
            "Assess the attached bidder documents against every listed tender requirement. The supplied government "
            "verification results are MOCK signals, not authoritative evidence; do not claim they are live checks. "
            "Use PASS only when the document evidence supports the requirement, FAIL only when evidence clearly "
            "shows non-compliance, and WARNING when evidence is absent, unreadable, ambiguous, or needs officer review. "
            "Evidence quotes must be short verbatim excerpts from an attached document. Do not invent quotes. "
            "Return one requirement result for each requirement, a 0-100 risk_score, specific discrepancies with "
            "document names and quotes, and a concise neutral officer_review_summary. Never recommend automatic approval or rejection.\n\n"
            f"Tender and requirements:\n{json.dumps(tender, ensure_ascii=False)}\n\n"
            f"Vendor profile and already extracted fields:\n{json.dumps(vendor, ensure_ascii=False)}\n\n"
            f"Mock external verification signals:\n{json.dumps(mock_verifications, ensure_ascii=False)}\n\n"
            "Attached document labels and extracted fields are provided in order:\n"
            + "\n".join(f"{doc['filename']}: {json.dumps(doc.get('fields', {}), ensure_ascii=False)}" for doc in documents)
        )
        parts = []
        for doc in documents:
            parts.append(self._file_part(doc["bytes"], doc["mime_type"]))
        assessment = self._generate("compliance_assessment", prompt, ComplianceAssessment, parts)
        expected = sorted(str(item["document_type"]).strip().upper() for item in tender.get("requirements", []))
        actual = sorted(item.document_type.strip().upper() for item in assessment.requirements)
        if expected != actual:
            raise GeminiProviderError(
                "invalid_response",
                "Gemini did not return exactly one assessment for every tender requirement.",
            )
        return assessment


def extracted_fields_for_document(result: DocumentExtraction) -> list[dict[str, str | float]]:
    doc_type = result.document_type.strip().upper()
    fields: dict[str, str | None] = {
        "document_type": result.document_type,
        "vendor_name": result.vendor_name,
        "pan": result.pan,
        "gstin": result.gstin,
        "valid_from": result.valid_from,
        "valid_until": result.valid_until,
        "udyam_number": result.udyam_number,
        "establishment_code": result.establishment_code,
        "address": result.registered_address,
        "annual_turnover": result.turnover_inr,
        "experience_years": result.years_experience,
    }
    name_field = {"GST": "legal_name", "PAN": "entity_name", "UDYAM": "enterprise_name"}.get(doc_type, "vendor_name")
    if result.vendor_name:
        fields[name_field] = result.vendor_name
    if result.confidence_score is not None:
        fields["extraction_confidence"] = str(result.confidence_score)
    return [
        {"field_name": key, "field_value": value, "confidence": result.confidence_score,
         "validation_status": "VALID" if value else "UNCERTAIN"}
        for key, value in fields.items() if value is not None
    ]
