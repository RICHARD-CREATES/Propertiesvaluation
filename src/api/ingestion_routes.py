"""
Authenticated Controlled Ingestion & Verification Router
========================================================
Milestone 8 — Phase 4

All endpoints require cryptographically verified server-side Bearer tokens via `require_roles`.
Client-provided `actor_id` / `actor_role` claims in request payloads are strictly ignored/rejected.
"""
from __future__ import annotations

import base64
from datetime import date
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.evidence_schema import EvidenceDocumentRecord, IngestionRun
from src.core.evidence_storage import (
    DocumentIntegrityError,
    EvidenceAccessDeniedError,
    PrivateEvidenceVault,
)
from src.core.rental_db import SessionLocal
from src.core.security_auth import VerifiedPrincipal, require_roles
from src.ingestion.adapters import (
    AdapterValidationError,
    AuthorizedBrokerFeedAdapter,
    GovtBMVReferenceAdapter,
    ORERAProjectDisclosureAdapter,
    UserDocumentEvidenceAdapter,
)
from src.ingestion.pipeline import ControlledIngestionPipeline
from src.services.verification_engine import (
    TransactionVerificationService,
    UnauthorizedActorError,
    VerificationTransitionError,
)

router = APIRouter(tags=["Authenticated Ground-Truth Ingestion & Verification"])

_vault = PrivateEvidenceVault()
_user_doc_adapter = UserDocumentEvidenceAdapter(vault=_vault)
_broker_adapter = AuthorizedBrokerFeedAdapter()
_bmv_adapter = GovtBMVReferenceAdapter()
_orera_adapter = ORERAProjectDisclosureAdapter()
_verifier = TransactionVerificationService(enforce_server_auth=True)
_pipeline = ControlledIngestionPipeline(verification_service=_verifier)

INGESTION_ROLES = ("SYSTEM_INGESTION", "HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN")
EVIDENCE_VIEW_ROLES = ("HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN")
VERIFICATION_ROLES = (
    "INTERNAL_AUTOMATED_VALIDATOR",
    "HUMAN_REVIEWER",
    "AUTHORIZED_REGISTRY_VERIFIER",
    "SENIOR_AUDIT_ADMIN",
)


class BrokerFeedRequest(BaseModel):
    source_reference: str
    format_hint: str = Field("json", pattern="^(json|csv)$")
    payload: Any  # JSON list/dict or CSV string
    partner_id: Optional[str] = None
    data_use_authorization_ref: Optional[str] = None
    data_use_authorized: Optional[bool] = None


class UserDocumentSubmissionRequest(BaseModel):
    source_reference: str = "consented_user_upload"
    consent_granted: bool
    consent_reference: str
    evidence_document_type: str
    evidence_document_reference: str
    document_filename: str
    document_base64: str
    expected_sha256: Optional[str] = None
    property_type: str
    transaction_date: Optional[str] = None
    registration_date: Optional[str] = None
    sale_price_inr: float
    builtup_area_sqft: Optional[float] = None
    carpet_area_sqft: Optional[float] = None
    land_area_sqft: Optional[float] = None
    locality: str
    city: str = "Bhubaneswar"
    district: str = "Khordha"
    state: str = "Odisha"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    property_id: Optional[str] = None
    transaction_id: Optional[str] = None
    transaction_classification: str = "ATYPICAL_UNCLASSIFIED"
    is_arms_length: Optional[bool] = None
    extraction_confidence: Optional[float] = None
    uncertain_fields: Optional[List[str]] = None
    from_official_ec_download: bool = False


class GenericFeedRequest(BaseModel):
    source_reference: str
    format_hint: str = Field("json", pattern="^(json|csv)$")
    payload: Any


class VerificationTransitionRequest(BaseModel):
    transaction_id: str
    target_status: str
    verification_method: str
    reason: str
    evidence_document_type: Optional[str] = None
    evidence_document_reference: Optional[str] = None
    evidence_document_hash: Optional[str] = None
    registration_date: Optional[str] = None
    corroboration_reference: Optional[str] = None
    transaction_classification: Optional[str] = None
    is_arms_length: Optional[bool] = None
    clear_human_review: bool = False
    retain_on_incomplete: bool = False


@router.post("/api/ingestion/runs/broker-feed")
def ingest_broker_feed(
    req: BrokerFeedRequest,
    principal: VerifiedPrincipal = Depends(require_roles(*INGESTION_ROLES)),
):
    try:
        rows = _broker_adapter.parse_records(req.payload, format_hint=req.format_hint)
    except AdapterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = {
        "partner_id": req.partner_id,
        "data_use_authorization_ref": req.data_use_authorization_ref,
        "data_use_authorized": req.data_use_authorized,
    }
    with SessionLocal() as db:
        return _pipeline.ingest_batch(
            db=db,
            adapter=_broker_adapter,
            raw_records=rows,
            source_reference=req.source_reference,
            principal=principal,
            batch_metadata=meta,
        )


@router.post("/api/ingestion/runs/user-document")
def ingest_user_document(
    req: UserDocumentSubmissionRequest,
    principal: VerifiedPrincipal = Depends(require_roles(*INGESTION_ROLES)),
):
    try:
        doc_bytes = base64.b64decode(req.document_base64.encode("ascii"), validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 encoding for document_base64.") from exc

    record = req.model_dump(exclude={"document_base64"})
    record["document_bytes"] = doc_bytes

    with SessionLocal() as db:
        return _pipeline.ingest_batch(
            db=db,
            adapter=_user_doc_adapter,
            raw_records=[record],
            source_reference=req.source_reference,
            principal=principal,
        )


@router.post("/api/ingestion/runs/govt-bmv")
def ingest_govt_bmv(
    req: GenericFeedRequest,
    principal: VerifiedPrincipal = Depends(require_roles(*INGESTION_ROLES)),
):
    try:
        rows = _bmv_adapter.parse_records(req.payload, format_hint=req.format_hint)
    except AdapterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with SessionLocal() as db:
        return _pipeline.ingest_batch(
            db=db,
            adapter=_bmv_adapter,
            raw_records=rows,
            source_reference=req.source_reference,
            principal=principal,
        )


@router.post("/api/ingestion/runs/orera-disclosure")
def ingest_orera_disclosure(
    req: GenericFeedRequest,
    principal: VerifiedPrincipal = Depends(require_roles(*INGESTION_ROLES)),
):
    try:
        rows = _orera_adapter.parse_records(req.payload, format_hint=req.format_hint)
    except AdapterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with SessionLocal() as db:
        return _pipeline.ingest_batch(
            db=db,
            adapter=_orera_adapter,
            raw_records=rows,
            source_reference=req.source_reference,
            principal=principal,
        )


@router.get("/api/ingestion/runs")
def list_ingestion_runs(
    limit: int = 50,
    principal: VerifiedPrincipal = Depends(require_roles(*INGESTION_ROLES)),
):
    with SessionLocal() as db:
        rows = db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "runs": [
                {
                    "run_id": r.run_id,
                    "adapter_name": r.adapter_name,
                    "source_type": r.source_type,
                    "status": r.status,
                    "submitted_count": r.submitted_count,
                    "accepted_count": r.accepted_count,
                    "duplicate_count": r.duplicate_count,
                    "quarantined_count": r.quarantined_count,
                    "rejected_count": r.rejected_count,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                }
                for r in rows
            ],
        }


@router.get("/api/ingestion/evidence/{evidence_id}")
def get_evidence_metadata(
    evidence_id: str,
    principal: VerifiedPrincipal = Depends(require_roles(*EVIDENCE_VIEW_ROLES)),
):
    with SessionLocal() as db:
        doc = db.query(EvidenceDocumentRecord).filter_by(evidence_id=evidence_id).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Evidence record not found.")

        try:
            _vault.read_document_bytes(doc.storage_uri, doc.sha256_digest, principal)
        except EvidenceAccessDeniedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (DocumentIntegrityError, FileNotFoundError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {
            "evidence_id": doc.evidence_id,
            "transaction_id": doc.transaction_id,
            "evidence_document_type": doc.evidence_document_type,
            "sha256_digest": doc.sha256_digest,
            "mime_type": doc.mime_type,
            "file_size_bytes": doc.file_size_bytes,
            "scan_status": doc.scan_status,
            "integrity_verified": True,
            "pii_redacted_summary": json.loads(doc.pii_redacted_summary_json or "{}"),
        }


@router.post("/api/verification/transition")
def api_transition_status(
    req: VerificationTransitionRequest,
    principal: VerifiedPrincipal = Depends(require_roles(*VERIFICATION_ROLES)),
):
    reg_dt: Optional[date] = None
    if req.registration_date:
        try:
            reg_dt = date.fromisoformat(req.registration_date[:10])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid registration_date; expected YYYY-MM-DD.") from exc

    with SessionLocal() as db:
        try:
            return _verifier.transition_status(
                db=db,
                transaction_id=req.transaction_id,
                target_status=req.target_status,
                verification_method=req.verification_method,
                reason=req.reason,
                evidence_document_type=req.evidence_document_type,
                evidence_document_reference=req.evidence_document_reference,
                evidence_document_hash=req.evidence_document_hash,
                registration_date=reg_dt,
                corroboration_reference=req.corroboration_reference,
                transaction_classification=req.transaction_classification,
                is_arms_length=req.is_arms_length,
                clear_human_review=req.clear_human_review,
                retain_on_incomplete=req.retain_on_incomplete,
                principal=principal,  # Strictly derived from verified token; client actor claims ignored
            )
        except UnauthorizedActorError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except VerificationTransitionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
