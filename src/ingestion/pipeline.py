"""
Controlled, Atomic Ingestion Pipeline with Retry & Dataset Membership Guardrails
================================================================================
Milestone 8 — Phase 4 Step 6
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.core.evidence_schema import (
    DATASET_ROLES,
    CanonicalTransaction,
    DatasetMembership,
    EvidenceDocumentRecord,
    IngestionRun,
    RawSourceRecord,
    compute_canonical_payload_sha256,
)
from src.core.evidence_storage import (
    DocumentIntegrityError,
    DocumentQuarantinedError,
    DocumentValidationError,
    redact_pii_text,
)
from src.core.security_auth import AuthenticationError, VerifiedPrincipal, get_auth_manager
from src.ingestion.adapters import AdapterValidationError, BaseSourceAdapter, NormalizedIngestionItem
from src.services.verification_engine import (
    TransactionVerificationService,
    UnauthorizedActorError,
    VerificationTransitionError,
)


class DatasetOverlapError(ValueError):
    """Raised when a transaction or property_id would overlap across training and evaluation datasets."""


class ControlledIngestionPipeline:
    """
    Executes source adapters inside authenticated, idempotent, savepoint-isolated,
    retry-resilient database runs without ever discarding raw records or mutating history.
    """

    def __init__(
        self,
        verification_service: Optional[TransactionVerificationService] = None,
        max_retries: int = 3,
        retry_backoff_sec: float = 0.05,
    ) -> None:
        self.verifier = verification_service or TransactionVerificationService(enforce_server_auth=True)
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec

    @staticmethod
    def _resolve_principal(
        principal: Optional[VerifiedPrincipal] = None,
        auth_token: Optional[str] = None,
    ) -> VerifiedPrincipal:
        if principal is not None:
            if not getattr(principal, "verified_by_server", False):
                raise UnauthorizedActorError("Principal must carry server verification.")
            return principal
        if auth_token:
            try:
                return get_auth_manager().verify_token(auth_token)
            except AuthenticationError as exc:
                raise UnauthorizedActorError(str(exc)) from exc
        raise UnauthorizedActorError("Authenticated VerifiedPrincipal or Bearer token required for ingestion.")

    def _run_with_retry(self, fn: Callable[[], Any]) -> Any:
        attempt = 0
        while True:
            try:
                return fn()
            except OperationalError as exc:
                attempt += 1
                msg = str(exc).lower()
                if attempt >= self.max_retries or ("locked" not in msg and "busy" not in msg):
                    raise
                time.sleep(self.retry_backoff_sec * attempt)

    def ingest_batch(
        self,
        db: Session,
        adapter: BaseSourceAdapter,
        raw_records: List[Dict[str, Any]],
        source_reference: str,
        principal: Optional[VerifiedPrincipal] = None,
        auth_token: Optional[str] = None,
        batch_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Normalizes, deduplicates, validates, and persists an ingestion batch cleanly.
        Tracks run metrics and sanitized errors inside `ingestion_runs`.
        """
        resolved_principal = self._resolve_principal(principal, auth_token)
        if resolved_principal.actor_role not in {
            "SYSTEM_INGESTION",
            "HUMAN_REVIEWER",
            "AUTHORIZED_REGISTRY_VERIFIER",
            "SENIOR_AUDIT_ADMIN",
        }:
            raise UnauthorizedActorError(
                f"Role '{resolved_principal.actor_role}' is not authorized to run ingestion pipelines."
            )

        run_row = IngestionRun(
            adapter_name=adapter.adapter_name,
            source_type=adapter.source_type,
            source_reference=source_reference,
            actor_id=resolved_principal.actor_id,
            actor_role=resolved_principal.actor_role,
            status="RUNNING",
            submitted_count=len(raw_records),
        )
        db.add(run_row)
        db.commit()
        db.refresh(run_row)

        accepted = 0
        duplicates = 0
        quarantined = 0
        rejected = 0
        sanitized_errors: List[Dict[str, Any]] = []
        ingested_tx_ids: List[str] = []

        for idx, raw_rec in enumerate(raw_records):
            try:
                item: NormalizedIngestionItem = adapter.normalize_record(
                    raw_rec, principal=resolved_principal, batch_metadata=batch_metadata
                )

                # Deterministic payload SHA-256 idempotency BEFORE savepoint insert
                combined_payload = {**item.raw_payload_sanitized, **item.canonical_payload}
                payload_sha = compute_canonical_payload_sha256(combined_payload)
                existing_raw = db.query(RawSourceRecord).filter_by(payload_sha256=payload_sha).first()
                req_tx_id = item.canonical_payload.get("transaction_id")
                existing_tx = (
                    db.query(CanonicalTransaction).filter_by(transaction_id=req_tx_id).first()
                    if req_tx_id
                    else None
                )
                if existing_raw is not None or existing_tx is not None:
                    duplicates += 1
                    continue

                def _persist_single() -> CanonicalTransaction:
                    with db.begin_nested():
                        # 1. Admit record strictly as UNVERIFIED (or REJECTED if hard invariant fails)
                        tx_obj = self.verifier.admit_record(
                            db=db,
                            raw_payload=combined_payload,
                            source_type=item.source_type,
                            source_reference=item.source_reference,
                            currency=item.currency,
                            principal=resolved_principal,
                            auto_commit=False,
                        )

                        # 2. If uncertainty/review notes raised by adapter (e.g. extraction confidence < 0.90), append safely
                        if item.review_notes:
                            existing_flags = json.loads(tx_obj.review_flags_json or "[]")
                            for note in item.review_notes:
                                if note not in existing_flags:
                                    existing_flags.append(note)
                            tx_obj.review_flags_json = json.dumps(existing_flags)
                            tx_obj.requires_human_review = True
                            db.flush()

                        # 3. Record private evidence vault metadata if attached (strictly separate from document bytes)
                        if item.document_metadata:
                            evd = EvidenceDocumentRecord(
                                evidence_id=item.document_metadata["evidence_id"],
                                transaction_id=tx_obj.transaction_id,
                                evidence_document_type=item.document_metadata["evidence_document_type"],
                                storage_uri=item.document_metadata["storage_uri"],
                                sha256_digest=item.document_metadata["sha256_digest"],
                                mime_type=item.document_metadata["mime_type"],
                                file_size_bytes=item.document_metadata["file_size_bytes"],
                                scan_status=item.document_metadata["scan_status"],
                                consent_granted=item.consent_granted,
                                consent_reference=item.consent_reference,
                                pii_redacted_summary_json=item.document_metadata.get("pii_redacted_summary_json"),
                                uploaded_by_actor=resolved_principal.actor_id,
                            )
                            db.add(evd)
                            db.flush()

                        # 4. Never allow adapters to promote above SOURCE_CONFIRMED (and only if principal role is permitted)!
                        if (
                            item.post_admit_target_status == "SOURCE_CONFIRMED"
                            and tx_obj.verification_status == "UNVERIFIED"
                            and resolved_principal.actor_role in {
                                "INTERNAL_AUTOMATED_VALIDATOR",
                                "HUMAN_REVIEWER",
                                "AUTHORIZED_REGISTRY_VERIFIER",
                                "SENIOR_AUDIT_ADMIN",
                            }
                        ):
                            self.verifier.transition_status(
                                db=db,
                                transaction_id=tx_obj.transaction_id,
                                target_status="SOURCE_CONFIRMED",
                                principal=resolved_principal,
                                verification_method="ADAPTER_SOURCE_METADATA_CONFIRMATION",
                                reason=f"Metadata confirmed via {adapter.adapter_name}.",
                                auto_commit=False,
                            )
                        elif item.post_admit_target_status in ("DOCUMENT_VERIFIED", "REGISTRATION_VERIFIED"):
                            raise VerificationTransitionError(
                                "Ingestion adapters cannot auto-promote to DOCUMENT_VERIFIED or REGISTRATION_VERIFIED."
                            )

                        return tx_obj

                saved_tx = self._run_with_retry(_persist_single)
                if saved_tx.verification_status == "REJECTED":
                    rejected += 1
                else:
                    accepted += 1
                    ingested_tx_ids.append(saved_tx.transaction_id)

            except DocumentQuarantinedError as exc:
                quarantined += 1
                sanitized_errors.append({"row_index": idx, "category": "QUARANTINED", "error": redact_pii_text(str(exc))})
            except (DocumentIntegrityError, DocumentValidationError, AdapterValidationError, VerificationTransitionError) as exc:
                rejected += 1
                sanitized_errors.append({"row_index": idx, "category": "REJECTED", "error": redact_pii_text(str(exc))})
            except Exception as exc:
                rejected += 1
                sanitized_errors.append({"row_index": idx, "category": "ERROR", "error": redact_pii_text(str(exc))})

        final_status = "COMPLETED"
        if quarantined > 0 or rejected > 0:
            final_status = "COMPLETED_WITH_QUARANTINE" if (accepted + duplicates) > 0 else "FAILED_OR_ALL_REJECTED"

        run_row.accepted_count = accepted
        run_row.duplicate_count = duplicates
        run_row.quarantined_count = quarantined
        run_row.rejected_count = rejected
        run_row.status = final_status
        run_row.error_summary_json = json.dumps(sanitized_errors[:50])
        run_row.finished_at = datetime.utcnow()
        db.commit()

        return {
            "run_id": run_row.run_id,
            "adapter_name": adapter.adapter_name,
            "source_type": adapter.source_type,
            "status": final_status,
            "submitted": len(raw_records),
            "accepted": accepted,
            "duplicates": duplicates,
            "quarantined": quarantined,
            "rejected": rejected,
            "ingested_transaction_ids": ingested_tx_ids,
            "errors": sanitized_errors,
        }

    def assign_dataset_membership(
        self,
        db: Session,
        dataset_version_id: str,
        dataset_role: str,
        transaction_ids: List[str],
        principal: Optional[VerifiedPrincipal] = None,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records immutable split memberships preventing training vs independent evaluation overlap
        on both `transaction_id` and non-null `property_id`.
        """
        resolved_principal = self._resolve_principal(principal, auth_token)
        if dataset_role not in DATASET_ROLES:
            raise ValueError(f"Unsupported dataset_role '{dataset_role}'. Expected one of {DATASET_ROLES}.")

        conflicting_roles = (
            ("TRAINING", "VALIDATION")
            if dataset_role in ("HOLD_OUT_TEST", "INDEPENDENT_EVALUATION")
            else ("HOLD_OUT_TEST", "INDEPENDENT_EVALUATION")
        )

        added = 0
        with db.begin_nested():
            for tid in transaction_ids:
                tx = db.query(CanonicalTransaction).filter_by(transaction_id=tid).first()
                if tx is None:
                    raise ValueError(f"CanonicalTransaction '{tid}' not found.")
                # Check BOTH transaction_id and property_id against conflicting dataset splits first
                overlap_q = db.query(DatasetMembership).filter(DatasetMembership.dataset_role.in_(conflicting_roles))
                overlap_match = overlap_q.filter(
                    (DatasetMembership.transaction_id == tx.transaction_id)
                    | ((DatasetMembership.property_id == tx.property_id) & (DatasetMembership.property_id.isnot(None)))
                ).first()
                if overlap_match is not None:
                    raise DatasetOverlapError(
                        f"TRAINING_EVALUATION_OVERLAP_DETECTED: '{tid}' / property '{tx.property_id}' "
                        f"already assigned to '{overlap_match.dataset_role}' ({overlap_match.dataset_version_id})."
                    )

                if dataset_role in ("HOLD_OUT_TEST", "INDEPENDENT_EVALUATION") and not tx.eligible_for_ground_truth_validation:
                    raise DatasetOverlapError(
                        f"Transaction '{tid}' is ineligible for independent evaluation/hold-out."
                    )
                if dataset_role == "TRAINING" and not tx.eligible_for_model_training:
                    raise DatasetOverlapError(
                        f"Transaction '{tid}' is ineligible for model training (requires REGISTRATION_VERIFIED + arm's-length)."
                    )

                rec_hash = compute_canonical_payload_sha256(
                    {
                        "transaction_id": tx.transaction_id,
                        "property_id": tx.property_id,
                        "dataset_version_id": dataset_version_id,
                        "dataset_role": dataset_role,
                    }
                )
                membership = DatasetMembership(
                    dataset_version_id=dataset_version_id,
                    dataset_role=dataset_role,
                    transaction_id=tx.transaction_id,
                    property_id=tx.property_id,
                    record_sha256=rec_hash,
                    assigned_by=resolved_principal.actor_id,
                )
                db.add(membership)
                if dataset_role in ("TRAINING", "VALIDATION"):
                    tx.used_in_model_training = True
                    tx.eligible_for_ground_truth_validation = False
                added += 1

        db.commit()
        return {
            "dataset_version_id": dataset_version_id,
            "dataset_role": dataset_role,
            "assigned_count": added,
        }
