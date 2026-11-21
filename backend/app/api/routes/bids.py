import random
import uuid
import mimetypes
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query, Form
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.models import (
    Bid, Vendor, Tender, Document, ExtractedField, Verification,
    RuleResult, CrossCheck, RiskAssessment, AuditEvent, User, Notification
)
from app.schemas.schemas import BidCreate, BidResponse, DocumentResponse, DocumentListResponse
from app.core.config import settings
from app.core.security import get_current_user, require_role
from app.core.tender_rules import MIN_TENDER_VALUE_INR, format_inr, tender_value_is_eligible
from app.services.ocr.ocr_service import OCRService
from app.services.classification.classifier import DocumentClassifier
from app.services.extraction.extractor import FieldExtractor
from app.services.cross_check.cross_check_engine import CrossCheckEngine
from app.services.compliance.rule_engine import ComplianceRuleEngine
from app.services.risk.risk_engine import RiskEngine
from app.services.ai.explanation_engine import AIExplanationEngine
from app.services.ai_provider import (
    GeminiAIProvider, GeminiProviderError, extracted_fields_for_document,
)
from app.services.audit.audit_logger import AuditLogger
from app.services.storage import get_storage_backend, validate_upload
from app.services.validation.validators import (
    compare_names,
    parse_bid_amount,
    validate_entity_name,
    validate_gstin,
    validate_pan,
    validate_udyam,
    validate_epfo,
)
from app.providers.government.base import (
    MockGSTProvider, MockUdyamProvider, MockPANProvider, MockEPFOProvider,
    MockESICProvider, MockMCAProvider, MockStartupProvider, MockNSICProvider,
    MockDigiLockerProvider, MockDebarmentProvider
)
from app.services.notifications.notification_service import notify_bid_event

router = APIRouter(prefix="/bids", tags=["Bids"])
logger = logging.getLogger(__name__)


def _extract_with_gemini(db: Session, document: Document, mime_type: str):
    stored_bytes = get_storage_backend().download_bytes(document.storage_key)
    result = GeminiAIProvider().extract_document(
        stored_bytes, mime_type, document.document_type if document.document_type != "OTHER" else None
    )
    document.document_type = document.document_type if document.document_type != "OTHER" else result.document_type.strip().upper()
    document.extracted_text = None
    document.ocr_confidence = result.confidence_score
    document.source = f"Gemini ({settings.GEMINI_MODEL})"
    db.query(ExtractedField).filter(ExtractedField.document_id == document.id).delete(synchronize_session=False)
    fields = extracted_fields_for_document(result)
    for field in fields:
        db.add(ExtractedField(document_id=document.id, **field))
    document.document_status = "UPLOADED"
    document.verification_status = "PENDING"
    document.detail = f"Gemini extracted {len(fields)} structured fields ({result.confidence_score:.0f}% confidence)."
    return result


def _mark_ai_processing_failed(db: Session, bid: Bid, reason: str) -> None:
    safe_reason = reason[:1000]
    bid.status = "PROCESSING_FAILED"
    bid.ai_assessment = None
    bid.ai_recommendation = "AI processing did not complete. Retry verification; an officer must review the result."
    bid.ai_summary = f"Processing failed: {safe_reason}"
    for document in bid.documents:
        document.document_status = "PROCESSING_FAILED"
        document.verification_status = "PROCESSING_FAILED"
        document.detail = safe_reason
    db.commit()


def _gemini_rule_results(assessment) -> list[dict]:
    results = []
    for index, item in enumerate(assessment.requirements, start=1):
        finding = item.finding
        if item.evidence_quote:
            finding = f"{finding} Evidence: \"{item.evidence_quote}\""
        results.append({
            "rule_id": f"GEMINI_REQUIREMENT_{index:03d}",
            "document_type": (item.document_type or "GENERAL").upper(),
            "result": item.status,
            "finding": finding,
            "impact": "HIGH" if item.status == "FAIL" else "MEDIUM" if item.status == "WARNING" else "LOW",
            "recommended_action": item.recommended_action or "Officer review as appropriate.",
        })
    return results

def execute_bid_verification_pipeline(bid_id: str, db: Session):
    bid = db.query(Bid).filter(Bid.id == bid_id).first()
    if not bid:
        return

    if settings.LLM_PROVIDER == "gemini":
        for document in bid.documents:
            if document.document_status == "PROCESSING_FAILED" and not document.extracted_fields:
                mime_type = mimetypes.guess_type(document.filename)[0] or "application/octet-stream"
                try:
                    _extract_with_gemini(db, document, mime_type)
                except GeminiProviderError as exc:
                    _mark_ai_processing_failed(db, bid, str(exc))
                    return
                except Exception:
                    _mark_ai_processing_failed(db, bid, "Stored document could not be read or parsed. Retry verification.")
                    return
        db.commit()

    # Update processing state
    bid.status = "PROCESSING"
    bid.ai_assessment = None
    bid.ai_summary = "Document and compliance analysis is in progress."
    db.commit()

    AuditLogger.log_event(db, "VERIFICATION_STARTED", "Verification Engine", "Started automated verification pipeline", bid_id=bid.id, vendor_name=bid.vendor.name if bid.vendor else "", status="checking")

    # 1. Load Tender and Requirements from DB
    tender = db.query(Tender).filter(Tender.id == bid.tender_id).first()
    tender_reqs = tender.requirements if tender else []
    required_doc_types = [r.document_type.upper() for r in tender_reqs if r.is_mandatory]

    # 2. Gather Extracted Fields from database and build document map
    extracted_fields_map = {}
    uploaded_doc_types = []
    docs_by_type = {}
    for doc in bid.documents:
        doc_type_upper = doc.document_type.upper()
        if doc_type_upper not in uploaded_doc_types:
            uploaded_doc_types.append(doc_type_upper)
            
        if doc_type_upper not in docs_by_type:
            docs_by_type[doc_type_upper] = []
        docs_by_type[doc_type_upper].append(doc)
        
        for ef in doc.extracted_fields:
            extracted_fields_map[ef.field_name] = ef.field_value

    # 3. Call Government Verification Providers and persist Verification DB records
    doc_verifications = []
    doc_checks = []
    verification_ids_by_type = {}

    vendor = bid.vendor
    vendor_name = extracted_fields_map.get("legal_name") or extracted_fields_map.get("enterprise_name") or (vendor.name if vendor else "")

    # Clean old verifications for re-run
    db.query(Verification).filter(Verification.bid_id == bid.id).delete()
    db.query(RuleResult).filter(RuleResult.bid_id == bid.id).delete()
    db.query(CrossCheck).filter(CrossCheck.bid_id == bid.id).delete()
    db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid.id).delete()
    db.commit()

    # Mark every document as PROCESSING before providers run.
    # This ensures that if the pipeline is interrupted, documents do not remain
    # in UPLOADED state indefinitely — they will be in PROCESSING, which signals
    # an incomplete verification run that can be retried.
    for doc in bid.documents:
        doc.document_status = "PROCESSING"
        doc.verification_status = "IN_PROGRESS"
    db.commit()

    pan_res, gst_res = {}, {}

    # Provider 1: GST
    for doc in docs_by_type.get("GST", []):
        doc_fields = {ef.field_name: ef.field_value for ef in doc.extracted_fields}
        doc_gstin = doc_fields.get("gstin")
        doc_id = doc.id
        
        if not doc_gstin:
            current_gst_res = {"verified": False, "status": "INVALID_DOCUMENT", "source": "OCR Extraction", "detail": "GSTIN could not be extracted from the uploaded document."}
        elif vendor and vendor.gstin and doc_gstin != vendor.gstin:
            current_gst_res = {"verified": False, "status": "IDENTITY_MISMATCH", "source": "System Cross-Check", "detail": f"Uploaded GSTIN ({doc_gstin}) does not match vendor profile."}
        else:
            current_gst_res = MockGSTProvider().verify(doc_gstin, {"vendor_name": vendor_name, "address": vendor.address if vendor else ""})
            
        v_gst = Verification(bid_id=bid.id, document_id=doc_id, document_type="GST", source=current_gst_res["source"], is_simulated=True, provider_mode=current_gst_res.get("provider_mode", "MOCK"), verified=current_gst_res["verified"], status=current_gst_res["status"], reference_id=current_gst_res.get("reference_id"), raw_response=current_gst_res)
        db.add(v_gst)
        db.flush()
        verification_ids_by_type.setdefault("GST", []).append(v_gst.id)
        doc_verifications.append(current_gst_res)
        doc_checks.append({"name": "GST", "status": "verified" if current_gst_res["verified"] else "failed", "source": current_gst_res["source"], "detail": current_gst_res["detail"]})
        
        if not current_gst_res["verified"]:
            doc.document_status = "FAILED"
        elif doc.document_status != "FAILED":
            doc.document_status = "VERIFIED"
        doc.detail = current_gst_res["detail"]
        doc.source = current_gst_res["source"]
        doc.verification_status = "COMPLETED"
        gst_res = current_gst_res  # save last for cross checks

    # Provider 2: PAN
    for doc in docs_by_type.get("PAN", []):
        doc_fields = {ef.field_name: ef.field_value for ef in doc.extracted_fields}
        doc_pan = doc_fields.get("pan")
        doc_id = doc.id
        
        if not doc_pan:
            current_pan_res = {"verified": False, "status": "INVALID_DOCUMENT", "source": "OCR Extraction", "detail": "PAN could not be extracted from the uploaded document."}
        elif vendor and vendor.pan and doc_pan != vendor.pan:
            current_pan_res = {"verified": False, "status": "IDENTITY_MISMATCH", "source": "System Cross-Check", "detail": f"Uploaded PAN ({doc_pan}) does not match vendor profile."}
        else:
            current_pan_res = MockPANProvider().verify(doc_pan, {"vendor_name": vendor_name})
            
        v_pan = Verification(bid_id=bid.id, document_id=doc_id, document_type="PAN", source=current_pan_res["source"], is_simulated=True, provider_mode=current_pan_res.get("provider_mode", "MOCK"), verified=current_pan_res["verified"], status=current_pan_res["status"], reference_id=current_pan_res.get("reference_id"), raw_response=current_pan_res)
        db.add(v_pan)
        db.flush()
        verification_ids_by_type.setdefault("PAN", []).append(v_pan.id)
        doc_verifications.append(current_pan_res)
        doc_checks.append({"name": "PAN", "status": "verified" if current_pan_res["verified"] else "failed", "source": current_pan_res["source"], "detail": current_pan_res["detail"]})
        
        if not current_pan_res["verified"]:
            doc.document_status = "FAILED"
        elif doc.document_status != "FAILED":
            doc.document_status = "VERIFIED"
        doc.detail = current_pan_res["detail"]
        doc.source = current_pan_res["source"]
        doc.verification_status = "COMPLETED"
        pan_res = current_pan_res

    # Provider 3: Udyam
    for doc in docs_by_type.get("UDYAM", []):
        doc_fields = {ef.field_name: ef.field_value for ef in doc.extracted_fields}
        doc_udyam = doc_fields.get("udyam_number")
        doc_id = doc.id
        
        if not doc_udyam:
            udyam_res = {"verified": False, "status": "INVALID_DOCUMENT", "source": "OCR Extraction", "detail": "Udyam Number could not be extracted from the uploaded document."}
        elif vendor and vendor.udyam and doc_udyam != vendor.udyam:
            udyam_res = {"verified": False, "status": "IDENTITY_MISMATCH", "source": "System Cross-Check", "detail": f"Uploaded Udyam ({doc_udyam}) does not match vendor profile."}
        else:
            udyam_res = MockUdyamProvider().verify(doc_udyam, {"vendor_name": vendor_name})
            
        v_udyam = Verification(bid_id=bid.id, document_id=doc_id, document_type="UDYAM", source=udyam_res["source"], is_simulated=True, provider_mode=udyam_res.get("provider_mode", "MOCK"), verified=udyam_res["verified"], status=udyam_res["status"], reference_id=udyam_res.get("reference_id"), raw_response=udyam_res)
        db.add(v_udyam)
        db.flush()
        verification_ids_by_type.setdefault("UDYAM", []).append(v_udyam.id)
        doc_verifications.append(udyam_res)
        doc_checks.append({"name": "Udyam", "status": "verified" if udyam_res["verified"] else "failed", "source": udyam_res["source"], "detail": udyam_res["detail"]})
        
        if not udyam_res["verified"]:
            doc.document_status = "FAILED"
        elif doc.document_status != "FAILED":
            doc.document_status = "VERIFIED"
        doc.detail = udyam_res["detail"]
        doc.source = udyam_res["source"]
        doc.verification_status = "COMPLETED"

    # Provider 4: EPFO
    for doc in docs_by_type.get("EPFO", []):
        doc_fields = {ef.field_name: ef.field_value for ef in doc.extracted_fields}
        doc_epfo = doc_fields.get("establishment_code")
        doc_id = doc.id
        
        if not doc_epfo:
            epfo_res = {"verified": False, "status": "INVALID_DOCUMENT", "source": "OCR Extraction", "detail": "EPFO Establishment Code could not be extracted from the uploaded document."}
        elif vendor and vendor.epfo_code and doc_epfo != vendor.epfo_code:
            epfo_res = {"verified": False, "status": "IDENTITY_MISMATCH", "source": "System Cross-Check", "detail": f"Uploaded EPFO Code ({doc_epfo}) does not match vendor profile."}
        else:
            epfo_res = MockEPFOProvider().verify(doc_epfo, {"vendor_name": vendor_name})
            
        v_epfo = Verification(bid_id=bid.id, document_id=doc_id, document_type="EPFO", source=epfo_res["source"], is_simulated=True, provider_mode=epfo_res.get("provider_mode", "MOCK"), verified=epfo_res["verified"], status=epfo_res["status"], reference_id=epfo_res.get("reference_id"), raw_response=epfo_res)
        db.add(v_epfo)
        db.flush()
        verification_ids_by_type.setdefault("EPFO", []).append(v_epfo.id)
        doc_verifications.append(epfo_res)
        doc_checks.append({"name": "EPFO", "status": "verified" if epfo_res["verified"] else "failed", "source": epfo_res["source"], "detail": epfo_res["detail"]})
        
        if not epfo_res["verified"]:
            doc.document_status = "FAILED"
        elif doc.document_status != "FAILED":
            doc.document_status = "VERIFIED"
        doc.detail = epfo_res["detail"]
        doc.source = epfo_res["source"]
        doc.verification_status = "COMPLETED"

    # Provider 5: Debarment (always run as a global compliance check)
    debar_res = MockDebarmentProvider().verify(vendor_name)
    v_debar = Verification(bid_id=bid.id, document_id=None, document_type="DEBARMENT", source=debar_res["source"], is_simulated=True, provider_mode=debar_res.get("provider_mode", "MOCK"), verified=debar_res["verified"], status=debar_res["status"], reference_id=debar_res.get("reference_id"), raw_response=debar_res)
    db.add(v_debar)
    doc_verifications.append(debar_res)

    # Every uploaded document must end in an explicit terminal outcome. A
    # content-unknown document is never verified by filename or OCR confidence.
    for doc in bid.documents:
        if doc.document_type.upper() == "OTHER":
            review = Verification(
                bid_id=bid.id,
                document_id=doc.id,
                document_type="OTHER",
                source="Document Classifier",
                is_simulated=True,
                provider_mode="MOCK",
                verified=False,
                status="MANUAL_REVIEW_REQUIRED",
                raw_response={"detail": "Document content did not match a supported compliance category."},
            )
            db.add(review)
            db.flush()
            verification_ids_by_type.setdefault("OTHER", []).append(review.id)
            doc.document_status = "MANUAL_REVIEW_REQUIRED"
            doc.verification_status = "COMPLETED"
            doc.detail = "Content did not identify a supported compliance document; manual review required."
            doc.source = "Document Classifier"

    # 4. Perform Cross-Document Comparisons and persist CrossCheck records
    cross_checks = []
    
    # Name match (Only if PAN provider ran)
    if "PAN" in uploaded_doc_types and pan_res:
        pan_name = pan_res.get("pan_holder_name", vendor_name)
        name_score, name_status = CrossCheckEngine.compare_names(vendor_name, pan_name)
        cc_name = CrossCheck(bid_id=bid.id, check_type="NAME_MATCH", field_a="vendor_name", value_a=vendor_name, field_b="pan_holder_name", value_b=pan_name, match_score=name_score, status=name_status, explanation=f"Comparison: '{vendor_name}' vs '{pan_name}'")
        db.add(cc_name)
        if name_status != "MATCH":
            cross_checks.append({"check_type": "NAME_MATCH", "status": name_status, "explanation": f"Submitted name '{vendor_name}' vs PAN name '{pan_name}'"})

    # Address match (Only if GST provider ran)
    if "GST" in uploaded_doc_types and gst_res:
        gst_addr = gst_res.get("registered_address", "")
        udyam_addr = extracted_fields_map.get("address") or (vendor.address if vendor else "")
        if gst_addr and udyam_addr:
            addr_score, addr_status = CrossCheckEngine.compare_addresses(gst_addr, udyam_addr)
            cc_addr = CrossCheck(bid_id=bid.id, check_type="ADDRESS_MATCH", field_a="gst_address", value_a=gst_addr, field_b="udyam_address", value_b=udyam_addr, match_score=addr_score, status=addr_status, explanation=f"Comparison: '{gst_addr}' vs '{udyam_addr}'")
            db.add(cc_addr)
            if addr_status != "MATCH":
                cross_checks.append({"check_type": "ADDRESS_MATCH", "status": addr_status, "explanation": f"GST address '{gst_addr}' vs Udyam address '{udyam_addr}'"})

    # 5. Evaluate Rules against Tender Requirements and persist RuleResult records
    tender_data_dict = {
        "required_documents": required_doc_types,
        "minimum_turnover_inr": tender.minimum_turnover_inr if tender else 0.0,
        "minimum_experience_years": tender.minimum_experience_years if tender else 0
    }

    ai_assessment = None
    if settings.LLM_PROVIDER == "gemini":
        try:
            ai_documents = []
            storage = get_storage_backend()
            for document in bid.documents:
                mime_type = mimetypes.guess_type(document.filename)[0] or "application/octet-stream"
                ai_documents.append({
                    "filename": document.filename,
                    "document_type": document.document_type,
                    "extraction_warning": document.document_status.upper() == "WARNING",
                    "mime_type": mime_type,
                    "bytes": storage.download_bytes(document.storage_key),
                    "fields": {field.field_name: field.field_value for field in document.extracted_fields},
                })
            tender_payload = {
                "title": tender.title if tender else "",
                "requirements": [
                    {"document_type": item.document_type, "mandatory": item.is_mandatory, "description": item.description}
                    for item in tender_reqs
                ],
                "minimum_turnover_inr": tender.minimum_turnover_inr if tender else 0,
                "minimum_experience_years": tender.minimum_experience_years if tender else 0,
            }
            vendor_payload = {
                "name": vendor.name if vendor else "",
                "pan": vendor.pan if vendor else None,
                "gstin": vendor.gstin if vendor else None,
                "extracted_fields": extracted_fields_map,
            }
            ai_assessment = GeminiAIProvider().assess_compliance(
                tender_payload, ai_documents, vendor_payload, doc_verifications
            )
            rule_results_list = _gemini_rule_results(ai_assessment)
        except GeminiProviderError as exc:
            _mark_ai_processing_failed(db, bid, str(exc))
            return
        except Exception:
            logger.exception("Could not prepare Gemini compliance assessment for bid %s", bid.id)
            _mark_ai_processing_failed(db, bid, "Documents or tender data could not be prepared for Gemini assessment.")
            return
    else:
        rule_results_list = ComplianceRuleEngine.evaluate_tender_rules(
            tender_data_dict, extracted_fields_map, doc_verifications, cross_checks, uploaded_doc_types
        )

    for rr in rule_results_list:
        db_rr = RuleResult(
            bid_id=bid.id,
            verification_id=(
                verification_ids_by_type.get(rr["document_type"].upper(), [None])[0]
                if rr.get("document_type")
                else None
            ),
            rule_id=rr["rule_id"],
            document_type=rr["document_type"],
            result=rr["result"],
            finding=rr["finding"],
            impact=rr.get("impact", "HIGH"),
            recommended_action=rr.get("recommended_action")
        )
        db.add(db_rr)

    # 6. Calculate Risk and Compliance Scores
    if ai_assessment is not None:
        risk_score = ai_assessment.risk_score
        risk_level = "LOW" if risk_score <= 25 else "MEDIUM" if risk_score <= 60 else "HIGH"
        total_assessed = len(ai_assessment.requirements)
        compliance_points = sum(
            1.0 if item.status == "PASS" else 0.5 if item.status == "WARNING" else 0.0
            for item in ai_assessment.requirements
        )
        compliance_score = round(compliance_points / total_assessed * 100, 1) if total_assessed else 0.0
        risk_factors = [item.finding for item in ai_assessment.requirements if item.status in {"FAIL", "WARNING"}]
        risk_factors.extend(item.description for item in ai_assessment.discrepancies)
        risk_factors = list(dict.fromkeys(risk_factors))
    else:
        risk_score, risk_level, compliance_score, risk_factors = RiskEngine.calculate_scores(
            rule_results_list, doc_checks, cross_checks
        )

    # 7. Generate Explainable AI Summary (strictly fact-grounded)
    if ai_assessment is not None:
        rec = "AI compliance analysis is complete. An authorized procurement officer must review the evidence and make the final decision."
        summary = ai_assessment.officer_review_summary
        confidence_values = [doc.ocr_confidence for doc in bid.documents if doc.ocr_confidence is not None]
        confidence = round(sum(confidence_values) / len(confidence_values)) if confidence_values else 0
    else:
        rec, summary, confidence = AIExplanationEngine.generate_explanation(
            vendor_name, risk_level, risk_score, compliance_score, risk_factors, doc_checks
        )

    # Persist RiskAssessment
    risk_assess = RiskAssessment(
        bid_id=bid.id,
        risk_score=risk_score,
        risk_level=risk_level,
        compliance_score=compliance_score,
        risk_factors=risk_factors
    )
    db.add(risk_assess)

    # Update Bid status
    bid.risk_score = risk_score
    bid.risk_level = risk_level
    bid.compliance_score = compliance_score
    bid.ai_confidence = confidence
    bid.ai_recommendation = rec
    bid.ai_summary = summary
    bid.ai_assessment = ai_assessment.model_dump(mode="json") if ai_assessment is not None else None
    bid.status = "FLAGGED" if risk_level == "HIGH" else "PENDING_REVIEW"

    db.commit()

    AuditLogger.log_event(
        db, "RISK_CALCULATED", "AI Engine",
        f"Verification complete: Risk Score {risk_score} ({risk_level}), Compliance {compliance_score}%",
        bid_id=bid.id, vendor_name=vendor_name, status="pass" if risk_level != "HIGH" else "fail"
    )

    notify_bid_event(
        db,
        bid,
        "BID_FLAGGED" if risk_level == "HIGH" else "BID_STATUS_CHANGED",
        event_id=f"verification:{bid.id}:{bid.risk_score}:{bid.compliance_score}",
    )

    # Get the users who own this bid to generate persistent alerts
    bidder_users = db.query(User).filter(User.vendor_id == bid.vendor_id).all()
    for bidder_user in bidder_users:
        for rr in rule_results_list:
            if rr["result"] == "FAIL":
                title = f"Compliance Failure: {rr['rule_id']}"
                message = rr["finding"]
                existing = db.query(Notification).filter(
                    Notification.user_id == bidder_user.id,
                    Notification.related_entity_id == bid.id,
                    Notification.title == title
                ).first()
                if not existing:
                    notif = Notification(user_id=bidder_user.id, title=title, message=message, notification_type="ERROR", related_entity_id=bid.id)
                    db.add(notif)
                    
        for chk in doc_checks:
            if chk["status"] == "failed":
                title = f"Verification Failed: {chk['name']}"
                message = chk["detail"]
                existing = db.query(Notification).filter(
                    Notification.user_id == bidder_user.id,
                    Notification.related_entity_id == bid.id,
                    Notification.title == title
                ).first()
                if not existing:
                    notif = Notification(user_id=bidder_user.id, title=title, message=message, notification_type="ERROR", related_entity_id=bid.id)
                    db.add(notif)
                    
    db.commit()

@router.get("", response_model=List[BidResponse])
def list_bids(
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    risk_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("bidder", "officer", "admin"))
):
    query = db.query(Bid).join(Tender, Bid.tender_id == Tender.id)
    if current_user.role == "BIDDER":
        if not current_user.vendor_id:
            return []
        query = query.filter(Bid.vendor_id == current_user.vendor_id)

    query = query.filter(Tender.estimated_value >= MIN_TENDER_VALUE_INR)

    if status_filter:
        query = query.filter(Bid.status == status_filter.upper())
    if risk_filter:
        query = query.filter(Bid.risk_level == risk_filter.upper())

    bids = query.order_by(Bid.submitted_at.desc()).all()
    results = []

    for b in bids:
        # Search filter
        if search:
            s_lower = search.lower().strip()
            if s_lower:
                v_name = (b.vendor.name if b.vendor and b.vendor.name else "").lower()
                b_id = (b.bid_id if b.bid_id else "").lower()
                v_gstin = (b.vendor.gstin if b.vendor and b.vendor.gstin else "").lower()
                v_pan = (b.vendor.pan if b.vendor and b.vendor.pan else "").lower()
                v_udyam = (b.vendor.udyam if b.vendor and b.vendor.udyam else "").lower()
                
                if (s_lower not in v_name and 
                    s_lower not in b_id and 
                    s_lower not in v_gstin and 
                    s_lower not in v_pan and 
                    s_lower not in v_udyam):
                    continue

        # Load persisted documents
        docs = []
        for d in b.documents:
            docs.append({
                "id": d.id,
                "name": d.document_type,
                "document_type": d.document_type,
                "status": d.document_status.lower(),
                "source": d.source or "Uploaded Document",
                "detail": d.detail or f"{d.filename} processed.",
                "extracted_fields": [
                    {"field_name": field.field_name, "field_value": field.field_value,
                     "confidence": field.confidence, "validation_status": field.validation_status}
                    for field in d.extracted_fields
                ],
            })

        # Load persisted audit entries
        audit_entries = []
        for a in b.audit_events:
            audit_entries.append({
                "id": a.id,
                "source": a.source,
                "label": a.action_label,
                "status": a.status,
                "timestamp": a.timestamp.strftime("%H:%M:%S")
            })

        results.append({
            "id": b.bid_id,
            "vendorName": b.vendor.name if b.vendor else "Unknown Vendor",
            "vendor_id_code": b.vendor.udyam or b.vendor.gstin or b.vendor.pan or "N/A",
            "category": b.category,
            "bidAmount": b.bid_amount,
            "submittedAt": b.submitted_at.strftime("%Y-%m-%d %I:%M %p"),
            "riskLevel": b.risk_level.lower(),
            "risk_score": b.risk_score,
            "compliance_score": b.compliance_score,
            "status": b.status.lower(),
            "aiConfidence": b.ai_confidence,
            "aiRecommendation": b.ai_recommendation or "Awaiting verification pipeline execution.",
            "aiSummary": b.ai_summary or "New bid submission registered.",
            "ai_assessment": b.ai_assessment,
            "documents": docs,
            "audit_trail": audit_entries,
            "officer": b.reviewed_by,
            "tender_title": b.tender.title if b.tender else "",
            "requirements": [
                {
                    "document_type": requirement.document_type,
                    "is_mandatory": requirement.is_mandatory,
                    "description": requirement.description,
                }
                for requirement in (b.tender.requirements if b.tender else [])
            ],
        })

    return results

@router.post("", response_model=BidResponse)
def create_bid(
    payload: BidCreate,
    current_user: User = Depends(require_role("bidder", "officer", "admin")),
    db: Session = Depends(get_db)
):
    tender = db.query(Tender).filter((Tender.id == payload.tender_id) | (Tender.tender_id == payload.tender_id)).first()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    if tender.status.upper() != "ACTIVE":
        raise HTTPException(status_code=400, detail="Tender is not active")
    if not tender_value_is_eligible(tender.estimated_value):
        raise HTTPException(status_code=400, detail=f"Tender value is below the minimum {format_inr(MIN_TENDER_VALUE_INR)} threshold")
    try:
        deadline = datetime.strptime(tender.bid_deadline, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Tender deadline is invalid")
    if deadline.date() < datetime.utcnow().date():
        raise HTTPException(status_code=400, detail="Tender deadline has passed")

    try:
        vendor_name = validate_entity_name(payload.vendor_name)
        bid_amount = parse_bid_amount(payload.bid_amount)
        pan = validate_pan(payload.pan) if payload.pan else None
        gstin = validate_gstin(payload.gstin, pan) if payload.gstin else None
        udyam = validate_udyam(payload.udyam) if payload.udyam else None
    except ValueError as exc:
        field = "bid_amount"
        message = str(exc)
        if "PAN" in message:
            field = "pan"
        elif "GSTIN" in message:
            field = "gstin"
        elif "Udyam" in message:
            field = "udyam"
        elif "entity" in message.lower():
            field = "vendor_name"
        raise HTTPException(
            status_code=422,
            detail={"field": field, "code": "INVALID_INPUT", "message": message},
        )

    if not payload.category or payload.category.strip().casefold() != tender.category.strip().casefold():
        raise HTTPException(
            status_code=422,
            detail={
                "field": "category",
                "code": "CATEGORY_NOT_ALLOWED",
                "message": "Select the category configured for the selected tender.",
            },
        )

    if current_user.role == "BIDDER":
        if not current_user.vendor_id:
            raise HTTPException(status_code=400, detail="Bidder has no associated vendor profile.")
        vendor_id = current_user.vendor_id
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise HTTPException(status_code=422, detail={"field": "vendor", "code": "VENDOR_NOT_FOUND", "message": "Bidder vendor profile was not found."})
        if vendor_name.casefold() != vendor.name.strip().casefold():
            raise HTTPException(status_code=422, detail={"field": "vendor_name", "code": "VENDOR_MISMATCH", "message": "Vendor name does not match the authenticated vendor profile."})
        for field_name, submitted, stored in (
            ("pan", pan, vendor.pan),
            ("gstin", gstin, vendor.gstin),
            ("udyam", udyam, vendor.udyam),
        ):
            if submitted and stored and submitted != stored.upper():
                raise HTTPException(
                    status_code=422,
                    detail={"field": field_name, "code": "VENDOR_MISMATCH", "message": f"{field_name.upper()} does not match the authenticated vendor profile."},
                )
    else:
        # Find or create vendor for manual entry by officer
        vendor = db.query(Vendor).filter(Vendor.name == vendor_name).first()
        if not vendor:
            vendor = Vendor(
                name=vendor_name,
                gstin=gstin,
                pan=pan,
                cin=payload.cin,
                udyam=udyam
            )
            db.add(vendor)
            db.commit()
            db.refresh(vendor)
        vendor_id = vendor.id

    bid_num = random.randint(48000, 49999)
    bid_code = f"GEM-2026-{bid_num}"

    # AUDIT ITEM 5: Starts as DRAFT with 0 scores until verification runs
    bid = Bid(
        bid_id=bid_code,
        # The request may identify a tender by its public reference. Persist
        # the database primary key so relationship joins and queue queries
        # return the newly created bid.
        tender_id=tender.id,
        vendor_id=vendor_id,
        category=tender.category,
        bid_amount=bid_amount,
        status="DRAFT",
        risk_level="MEDIUM",
        risk_score=0,
        compliance_score=0.0,
        ai_confidence=0,
        ai_recommendation="New bid created in DRAFT state. Upload documents and run verification.",
        ai_summary="Draft bid registered."
    )
    db.add(bid)
    db.commit()
    db.refresh(bid)

    AuditLogger.log_event(
        db, "BID_CREATED", "Bidder Console", f"Created new draft bid {bid_code}",
        bid_id=bid.id, user_id=current_user.id, vendor_name=vendor.name, status="pass"
    )

    notify_bid_event(db, bid, "BID_PLACED", event_id=bid.bid_id)

    return {
        "id": bid.bid_id,
        "vendorName": vendor.name,
        "vendor_id_code": vendor.udyam or vendor.gstin or "N/A",
        "category": bid.category,
        "bidAmount": bid.bid_amount,
        "submittedAt": bid.submitted_at.strftime("%Y-%m-%d %I:%M %p"),
        "riskLevel": "medium",
        "risk_score": 0,
        "compliance_score": 0.0,
        "status": "draft",
        "aiConfidence": 0,
        "aiRecommendation": bid.ai_recommendation,
        "aiSummary": bid.ai_summary,
        "documents": [],
        "audit_trail": []
    }

@router.post("/{bid_id_or_code}/documents", response_model=DocumentResponse)
def upload_document(
    bid_id_or_code: str,
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    current_user: User = Depends(require_role("bidder")),
    db: Session = Depends(get_db)
):
    bid = db.query(Bid).filter((Bid.id == bid_id_or_code) | (Bid.bid_id == bid_id_or_code)).first()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
        
    if current_user.role != "BIDDER":
        raise HTTPException(status_code=403, detail="Only bidders can upload documents")

    if bid.vendor_id != current_user.vendor_id:
        raise HTTPException(status_code=403, detail="Not authorized to upload to this bid")

    if document_type:
        allowed_types = {
            requirement.document_type.strip().upper()
            for requirement in (bid.tender.requirements if bid.tender else [])
            if requirement.document_type
        }
        normalized_document_type = document_type.strip().upper()
        if allowed_types and normalized_document_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Document type is not required for the selected tender.",
            )

    # AUDIT ITEM 13: File validation (extension and size)
    original_filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    file_bytes = file.file.read(settings.MAX_FILE_SIZE_BYTES + 1)
    ext, content_type = validate_upload(original_filename, file.content_type, file_bytes)

    file_hash = OCRService.calculate_sha256(file_bytes)

    # AUDIT ITEM 14: Prevent duplicate uploads using SHA-256
    existing_doc = db.query(Document).filter(Document.bid_id == bid.id, Document.file_hash == file_hash).first()
    if existing_doc:
        raise HTTPException(status_code=400, detail="Duplicate document upload detected (matching SHA-256 file hash)")

    safe_filename = "".join(char for char in original_filename if char.isalnum() or char in " ._-()").strip(" .")[:180]
    if not safe_filename:
        safe_filename = f"document{ext}"
    storage_key = f"bids/{bid.id}/{uuid.uuid4().hex}{ext}"
    storage = get_storage_backend()
    try:
        storage.upload_file(file_bytes, storage_key, content_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to store uploaded document") from exc

    is_gemini = settings.LLM_PROVIDER == "gemini"
    gemini_doc = None
    extraction_uncertain = False
    if is_gemini:
        gemini_doc = Document(
            bid_id=bid.id,
            document_type=(document_type or "OTHER").strip().upper(),
            filename=safe_filename,
            storage_key=storage_key,
            file_hash=file_hash,
            document_status="PROCESSING",
            verification_status="IN_PROGRESS",
            detail="Gemini document extraction is in progress.",
            source=f"Gemini ({settings.GEMINI_MODEL})",
        )
        db.add(gemini_doc)
        bid.status = "PROCESSING"
        bid.ai_assessment = None
        bid.ai_recommendation = "Gemini is extracting the uploaded document."
        bid.ai_summary = "Document extraction is in progress."
        db.commit()
        db.refresh(gemini_doc)
        try:
            extraction = _extract_with_gemini(db, gemini_doc, content_type)
            db.commit()
        except GeminiProviderError as exc:
            gemini_doc.document_status = "PROCESSING_FAILED"
            gemini_doc.verification_status = "PROCESSING_FAILED"
            gemini_doc.detail = str(exc)
            bid.status = "PROCESSING_FAILED"
            bid.ai_recommendation = "AI processing did not complete. Retry document processing; an officer must review the result."
            bid.ai_summary = f"Processing failed: {exc}"
            db.commit()
            logger.warning("Gemini document extraction failed", extra={"document_id": gemini_doc.id, "error_code": exc.code})
            return gemini_doc
        except Exception:
            gemini_doc.document_status = "PROCESSING_FAILED"
            gemini_doc.verification_status = "PROCESSING_FAILED"
            gemini_doc.detail = "Stored document could not be extracted. Retry processing."
            bid.status = "PROCESSING_FAILED"
            bid.ai_recommendation = "AI processing did not complete. Retry document processing; an officer must review the result."
            bid.ai_summary = gemini_doc.detail
            db.commit()
            logger.exception("Unexpected document extraction failure for document %s", gemini_doc.id)
            return gemini_doc
        extracted_text = None
        ocr_conf = extraction.confidence_score
        class_conf = extraction.confidence_score
        extracted_facts = [
            value for name, value in extraction.model_dump().items()
            if name not in {"document_type", "confidence_score"} and value is not None
        ]
        extraction_uncertain = extraction.confidence_score < 50 or not extracted_facts
        classified_doc_type = extraction.document_type
        extracted_fields = extracted_fields_for_document(extraction)
    else:
        # Local and CI mode keeps deterministic OCR/classification without API usage.
        extracted_text, ocr_conf = OCRService.process_file(file_bytes, safe_filename)
        classified_doc_type, class_conf = DocumentClassifier.classify(safe_filename, extracted_text)
        extracted_fields = FieldExtractor.extract_fields(
            (document_type or classified_doc_type).strip().upper(), extracted_text
        )

    doc_type = (document_type or classified_doc_type).strip().upper()
    if not doc_type:
        raise HTTPException(status_code=400, detail="Document type is required.")
    extracted_map = {field["field_name"]: field["field_value"] for field in extracted_fields}
    consistency_issues = []
    vendor = bid.vendor
    if doc_type == "PAN":
        extracted_pan = extracted_map.get("pan")
        if extracted_pan:
            try:
                validate_pan(extracted_pan)
            except ValueError:
                consistency_issues.append("MANUAL_REVIEW_REQUIRED: extracted PAN has an invalid format.")
        if extracted_pan and vendor.pan and extracted_pan.upper() != vendor.pan.upper():
            consistency_issues.append("IDENTITY_MISMATCH: extracted PAN does not match vendor PAN.")
        name_result = compare_names(extracted_map.get("entity_name"), vendor.name if vendor else None)
        if name_result == "MISMATCH":
            consistency_issues.append("IDENTITY_MISMATCH: PAN document name does not match vendor entity name.")
    elif doc_type == "GST":
        extracted_gstin = extracted_map.get("gstin")
        if extracted_gstin:
            try:
                validate_gstin(extracted_gstin, vendor.pan if vendor else None)
            except ValueError:
                consistency_issues.append("MANUAL_REVIEW_REQUIRED: extracted GSTIN failed structural validation.")
        if extracted_gstin and vendor.gstin and extracted_gstin.upper() != vendor.gstin.upper():
            consistency_issues.append("IDENTITY_MISMATCH: extracted GSTIN does not match vendor GSTIN.")
        if extracted_gstin and vendor.pan and extracted_gstin[2:12] != vendor.pan.upper():
            consistency_issues.append("IDENTITY_MISMATCH: GSTIN embedded PAN does not match vendor PAN.")
        name_result = compare_names(extracted_map.get("legal_name"), vendor.name if vendor else None)
        if name_result == "MISMATCH":
            consistency_issues.append("IDENTITY_MISMATCH: GST legal name does not match vendor entity name.")
    elif doc_type == "UDYAM":
        extracted_udyam = extracted_map.get("udyam_number")
        if extracted_udyam:
            try:
                validate_udyam(extracted_udyam)
            except ValueError:
                consistency_issues.append("MANUAL_REVIEW_REQUIRED: extracted Udyam number has an invalid format.")
        if extracted_udyam and vendor.udyam and extracted_udyam.upper() != vendor.udyam.upper():
            consistency_issues.append("IDENTITY_MISMATCH: extracted Udyam number does not match vendor Udyam number.")
        name_result = compare_names(extracted_map.get("enterprise_name"), vendor.name if vendor else None)
        if name_result == "MISMATCH":
            consistency_issues.append("IDENTITY_MISMATCH: Udyam enterprise name does not match vendor entity name.")
    elif doc_type == "EPFO":
        establishment_code = extracted_map.get("establishment_code")
        if establishment_code:
            try:
                validate_epfo(establishment_code)
            except ValueError:
                consistency_issues.append("MANUAL_REVIEW_REQUIRED: extracted EPFO identifier has an invalid format.")
        if vendor and vendor.epfo_code and establishment_code and establishment_code.upper() != vendor.epfo_code.upper():
            consistency_issues.append("IDENTITY_MISMATCH: extracted EPFO identifier does not match vendor EPFO identifier.")
    if is_gemini:
        extraction_state = "GEMINI_MULTIMODAL_EXTRACTION"
    elif ext == ".pdf":
        if extracted_text.strip():
            extraction_state = "PDF_TEXT_EXTRACTED"
        elif ocr_conf <= 50:
            extraction_state = "PDF_OCR_FAILED"
        else:
            extraction_state = "PDF_EMPTY_CONTENT"
    else:
        extraction_state = "IMAGE_TEXT_EXTRACTED" if extracted_text.strip() else "IMAGE_OCR_FAILED"

    doc = gemini_doc or Document(
        bid_id=bid.id, document_type=doc_type, filename=safe_filename,
        storage_key=storage_key, file_hash=file_hash, extracted_text=extracted_text,
        ocr_confidence=ocr_conf, source="OCR Engine",
    )
    doc.document_type = doc_type
    doc.extracted_text = extracted_text
    doc.ocr_confidence = ocr_conf
    doc.document_status = "FAILED" if consistency_issues else "WARNING" if extraction_uncertain else "UPLOADED"
    doc.verification_status = "MANUAL_REVIEW_REQUIRED" if consistency_issues or extraction_uncertain else "PENDING"
    if not is_gemini:
        doc.source = "OCR Engine"
        db.add(doc)
    doc.detail = f"{extraction_state}; classified as {doc_type} ({class_conf:.0f}% confidence)."
    if consistency_issues:
        doc.detail += f" {' '.join(consistency_issues)}"
    if extraction_uncertain:
        doc.detail += " MANUAL_REVIEW_REQUIRED: Gemini could not extract legible business facts with sufficient confidence; no missing values were inferred."
    db.commit()
    db.refresh(doc)

    # AUDIT ITEM 2: Persist every ExtractedField into DB
    if not is_gemini:
        for ef in extracted_fields:
            db.add(ExtractedField(document_id=doc.id, **ef))
        db.commit()

    notify_bid_event(db, bid, "BID_UPDATED", event_id=f"document:{doc.id}")

    AuditLogger.log_event(
        db, "DOCUMENT_UPLOADED", "Document Pipeline", f"Uploaded & classified document '{safe_filename}' as {doc_type}",
        bid_id=bid.id, user_id=current_user.id, vendor_name=bid.vendor.name if bid.vendor else "", status="pass"
    )

    return doc

@router.get("/documents", response_model=List[DocumentListResponse])
def list_bidder_documents(
    search: Optional[str] = Query(None),
    current_user: User = Depends(require_role("bidder")),
    db: Session = Depends(get_db),
):
    if current_user.role != "BIDDER":
        raise HTTPException(status_code=403, detail="Only bidders can access bidder documents")
    if not current_user.vendor_id:
        return []

    documents = (
        db.query(Document)
        .join(Bid, Document.bid_id == Bid.id)
        .join(Tender, Bid.tender_id == Tender.id)
        .filter(Bid.vendor_id == current_user.vendor_id)
        .order_by(Document.upload_timestamp.desc())
        .all()
    )
    results = []
    for document in documents:
        if search:
            term = search.strip().lower()
            searchable = " ".join([
                document.filename or "",
                document.document_type or "",
                document.bid.bid_id if document.bid else "",
                document.bid.tender.title if document.bid and document.bid.tender else "",
            ]).lower()
            if term not in searchable:
                continue

        extracted_statuses = [field.validation_status.upper() for field in document.extracted_fields]
        if not extracted_statuses:
            extracted_fields_status = "NOT_EXTRACTED"
        elif "INVALID" in extracted_statuses:
            extracted_fields_status = "INVALID"
        elif "UNCERTAIN" in extracted_statuses:
            extracted_fields_status = "UNCERTAIN"
        else:
            extracted_fields_status = "VALID"

        latest_verification = max(
            document.verifications,
            key=lambda verification: verification.timestamp or datetime.min,
            default=None,
        )
        verification_result = (
            f"{latest_verification.status}{' (verified)' if latest_verification.verified else ''}"
            if latest_verification
            else "PENDING"
        )
        try:
            file_available = bool(document.storage_key) and get_storage_backend().file_exists(document.storage_key)
        except Exception:
            file_available = False
        results.append({
            "id": document.id,
            "bid_id": document.bid_id,
            "bid_reference": document.bid.bid_id,
            "tender_id": document.bid.tender.tender_id,
            "tender_title": document.bid.tender.title,
            "filename": document.filename,
            "document_type": document.document_type,
            "upload_timestamp": document.upload_timestamp,
            "document_status": document.document_status,
            "verification_status": document.verification_status,
            "verification_result": verification_result,
            "extracted_fields_status": extracted_fields_status,
            "detail": document.detail,
            "source": document.source,
            "file_available": file_available,
            "extracted_fields": [
                {"field_name": field.field_name, "field_value": field.field_value,
                 "confidence": field.confidence, "validation_status": field.validation_status}
                for field in document.extracted_fields
            ],
        })
    return results

@router.post("/{bid_id_or_code}/verify")
def verify_bid(
    bid_id_or_code: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("bidder", "officer", "admin")),
    db: Session = Depends(get_db)
):
    bid = db.query(Bid).filter((Bid.id == bid_id_or_code) | (Bid.bid_id == bid_id_or_code)).first()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")

    if current_user.role == "BIDDER" and bid.vendor_id != current_user.vendor_id:
        raise HTTPException(status_code=403, detail="Not authorized to verify this bid")

    # Execute synchronously for SIH demo reliability
    execute_bid_verification_pipeline(bid.id, db)
    
    # Reload bid to get updated status
    db.refresh(bid)

    processing_failed = bid.status == "PROCESSING_FAILED"
    # Generate Alert for Bidder
    notif_title = f"Bid Verification: {bid.bid_id}"
    existing_notif = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.related_entity_id == bid.id,
        Notification.title == notif_title
    ).first()
    if not existing_notif:
        notif = Notification(
            user_id=current_user.id,
            title=notif_title,
            message=(bid.ai_summary if processing_failed else f"Verification completed for Bid {bid.bid_id}. Risk Level: {bid.risk_level}"),
            notification_type="ERROR" if processing_failed else "WARNING" if bid.risk_level == "HIGH" else "INFO",
            related_entity_id=bid.id
        )
        db.add(notif)
        db.commit()

    return {
        "message": "Verification processing failed; retry is available." if processing_failed else "Verification pipeline completed",
        "bid_id": bid.bid_id,
        "status": bid.status,
        "error": bid.ai_summary if processing_failed else None,
    }

@router.get("/documents/{doc_id}/view")
def view_document(
    doc_id: str,
    current_user: User = Depends(require_role("bidder", "officer", "admin")),
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if current_user.role == "BIDDER" and doc.bid.vendor_id != current_user.vendor_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this document")

    safe_filename = Path(doc.filename).name.replace('"', '').replace("'", "")
    is_pdf = safe_filename.lower().endswith(".pdf")
    storage = get_storage_backend()
    try:
        if settings.STORAGE_BACKEND == "s3":
            return RedirectResponse(storage.get_download_url(doc.storage_key), status_code=302)
        file_bytes = storage.download_bytes(doc.storage_key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="File not found in storage")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to read document file") from exc

    header = file_bytes[:1024]

    if is_pdf:
        if not header.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file: Missing %PDF- signature")
        media_type = "application/pdf"
    elif header.startswith(b"\x89PNG"):
        media_type = "image/png"
    elif header.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
    else:
        media_type = "application/octet-stream"

    headers = {
        "Content-Disposition": f'inline; filename="{safe_filename}"'
    }

    return Response(content=file_bytes, media_type=media_type, headers=headers)


@router.get("/documents/storage")
def download_document_by_storage_key(
    key: str,
    current_user: User = Depends(require_role("bidder", "officer", "admin")),
    db: Session = Depends(get_db),
):
    """Authenticated local-storage API URL returned by LocalStorageBackend."""
    doc = db.query(Document).filter(Document.storage_key == key).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if current_user.role == "BIDDER" and doc.bid.vendor_id != current_user.vendor_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this document")
    try:
        body = get_storage_backend().download_bytes(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="File not found in storage")
    media_type = "application/pdf" if doc.filename.lower().endswith(".pdf") else "application/octet-stream"
    return Response(content=body, media_type=media_type, headers={"Content-Disposition": f'inline; filename="{Path(doc.filename).name}"'})
