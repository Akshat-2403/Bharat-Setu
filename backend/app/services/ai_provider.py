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
    certificate_number: str | None = None
    registration_number: str | None = None
    registration_status: str | None = None
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
    kind: Literal[
        "MISSING_MANDATORY_DOCUMENT", "IDENTITY_MISMATCH", "VALUE_MISMATCH",
        "VALIDITY", "UNVERIFIED_CLAIM", "UNREADABLE", "OTHER",
    ] = "OTHER"
    description: str = Field(min_length=1, max_length=800)
    evidence_quote: str | None = Field(default=None, max_length=800)
    document_name: str | None = Field(default=None, max_length=240)
    recommended_action: str | None = Field(default=None, max_length=800)


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
            "Extract only facts visibly supported by this document: vendor/entity name, PAN, GSTIN, Udyam or "
            "establishment identifiers, certificate/registration numbers and status, address, financial values, "
            "experience, and validity or issue dates. Do not infer missing identifiers, names, status, or dates. "
            "Return null for fields that are not present or legible. Dates must use YYYY-MM-DD. "
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
            "Treat the supplied document inventory as the complete set of uploaded files for this bid. For an absent "
            "mandatory document, return FAIL and a MISSING_MANDATORY_DOCUMENT discrepancy with no document name "
            "and no evidence quote; the missing file itself is the evidence. For a present but unreadable, sparse, or "
            "ambiguous document, return WARNING and request officer review instead of inferring facts. A document "
            "marked extraction_warning is not sufficient evidence to pass a requirement. Use PASS only "
            "when visible document evidence supports the requirement. Use FAIL for a clear identity, value, validity, "
            "or other compliance conflict. Evidence quotes must be short, verbatim excerpts from the supplied files; "
            "omit the quote when the discrepancy is an absent document. Never invent a name, identifier, date, quote, "
            "or verification result. Return exactly one result per tender requirement, a 0-100 risk_score that reflects "
            "the severity and number of unresolved issues, specific discrepancies with actionable recommended actions, "
            "and a concise neutral officer_review_summary. Never recommend automatic approval or rejection.\n\n"
            f"Tender and requirements:\n{json.dumps(tender, ensure_ascii=False)}\n\n"
            f"Vendor profile and already extracted fields:\n{json.dumps(vendor, ensure_ascii=False)}\n\n"
            f"Mock external verification signals:\n{json.dumps(mock_verifications, ensure_ascii=False)}\n\n"
            "Complete uploaded document inventory and extracted fields are provided below. Read the attached bytes "
            "in the same order and use document_type for coverage checks:\n"
            + "\n".join(
                f"{doc['filename']} (type={doc.get('document_type', 'UNKNOWN')}): "
                f"{json.dumps(doc.get('fields', {}), ensure_ascii=False)}"
                for doc in documents
            )
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
        uploaded_types = {
            str(doc.get("document_type") or (doc.get("fields") or {}).get("document_type") or "").strip().upper()
            for doc in documents
        }
        documents_by_type: dict[str, list[dict]] = {}
        for document in documents:
            document_type = str(document.get("document_type") or (document.get("fields") or {}).get("document_type") or "").strip().upper()
            documents_by_type.setdefault(document_type, []).append(document)
        requirement_results = {
            result.document_type.strip().upper(): result
            for result in assessment.requirements
        }
        discrepancies = list(assessment.discrepancies)
        enforced_results = []
        missing_mandatory_count = 0
        unreadable_count = 0
        for requirement in tender.get("requirements", []):
            document_type = str(requirement["document_type"]).strip().upper()
            result = requirement_results[document_type]
            if requirement.get("mandatory", requirement.get("is_mandatory", False)) and document_type not in uploaded_types:
                missing_mandatory_count += 1
                action = f"Upload the required {document_type} document, then rerun verification."
                result = RequirementAssessment.model_validate({
                    **result.model_dump(),
                    "status": "FAIL",
                    "finding": f"The mandatory {document_type} document was not uploaded for this bid.",
                    "evidence_quote": None,
                    "recommended_action": action,
                })
                already_reported = any(
                    item.kind == "MISSING_MANDATORY_DOCUMENT"
                    and item.document_name is None
                    and document_type in item.description.upper()
                    for item in discrepancies
                )
                if not already_reported:
                    discrepancies.append(ComplianceDiscrepancy(
                        kind="MISSING_MANDATORY_DOCUMENT",
                        description=f"Mandatory {document_type} document is missing from the uploaded bid files.",
                        recommended_action=action,
                    ))
            elif documents_by_type.get(document_type) and all(
                document.get("extraction_warning") for document in documents_by_type[document_type]
            ):
                unreadable_count += 1
                action = f"Upload a clearer {document_type} file, then rerun verification."
                result = RequirementAssessment.model_validate({
                    **result.model_dump(),
                    "status": "WARNING",
                    "finding": f"The uploaded {document_type} file did not yield legible facts with sufficient confidence; officer review is required.",
                    "evidence_quote": None,
                    "recommended_action": action,
                })
                if not any(item.kind == "UNREADABLE" and document_type in item.description.upper() for item in discrepancies):
                    discrepancies.append(ComplianceDiscrepancy(
                        kind="UNREADABLE",
                        description=f"Uploaded {document_type} evidence is sparse or unreadable; its claims could not be confirmed.",
                        recommended_action=action,
                    ))
            enforced_results.append(result)
        return ComplianceAssessment.model_validate({
            **assessment.model_dump(),
            "risk_score": max(assessment.risk_score, min(100, missing_mandatory_count * 30), min(100, unreadable_count * 20)),
            "requirements": [result.model_dump() for result in enforced_results],
            "discrepancies": [item.model_dump() for item in discrepancies],
        })


def extracted_fields_for_document(result: DocumentExtraction) -> list[dict[str, str | float]]:
    doc_type = result.document_type.strip().upper()
    fields: dict[str, str | None] = {
        "document_type": result.document_type,
        "vendor_name": result.vendor_name,
        "pan": result.pan,
        "gstin": result.gstin,
        "certificate_number": result.certificate_number,
        "registration_number": result.registration_number,
        "registration_status": result.registration_status,
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
