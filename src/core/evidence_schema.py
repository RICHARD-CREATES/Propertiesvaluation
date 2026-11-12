"""
Canonical Evidence Schema, Immutable Raw-Source Storage & Non-Destructive Migrations
====================================================================================
Milestone 8 — Phase 2

Design Principles:
1. Backward Compatibility: Preserves existing `ground_truth_transactions` and
   `validation_evaluation_runs` tables untouched; bridges optionally via FK.
2. Immutable Raw Archive: Stores verbatim original source payloads + deterministic
   SHA-256 digests in `raw_source_records` with ORM update/delete protection.
3. Exact Provenance & Classification: Distinguishes Agreement for Sale, executed Sale
   Deed, digitally signed EC, broker attestations, circle rates, and RERA filings.
   Never assumes a registered deed is automatically arm's-length market value.
4. Separate Eligibility Gates: Keeps `eligible_for_ground_truth_validation` and
   `eligible_for_model_training` strictly distinct from raw verification status.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Session

from src.core.rental_db import Base, _gen_uuid, engine


class ImmutableRecordError(RuntimeError):
    """Raised if any code attempts to mutate or delete an immutable audit or raw-source row."""


# Phase 3 Status Taxonomy (anchored in Phase 2 Schema)
CANONICAL_VERIFICATION_STATUSES = (
    "UNVERIFIED",
    "SOURCE_CONFIRMED",
    "DOCUMENT_VERIFIED",
    "REGISTRATION_VERIFIED",
    "REJECTED",
)

# Evidence Document Distinction (Agreement != Executed Sale Deed != Digitally Signed EC)
EVIDENCE_DOCUMENT_TYPES = (
    "EXECUTED_SALE_DEED",
    "AGREEMENT_FOR_SALE",
    "DIGITALLY_SIGNED_EC",
    "CERTIFIED_COPY_IGR",
    "INDEX_II_EXTRACT",
    "ALLOTMENT_OR_POSSESSION_LETTER",
    "BROKER_ATTESTATION",
    "GOVT_BENCHMARK_CIRCULAR",
    "ORERA_QPR_FILING",
    "BDA_PERMIT_RECORD",
    "LISTING_SNAPSHOT",
    "NONE",
)

# Transaction Economic Classification (Registration != Arm's-Length Market Transaction)
TRANSACTION_CLASSIFICATIONS = (
    "ARMS_LENGTH_MARKET",
    "ATYPICAL_UNCLASSIFIED",
    "GIFT_DEED",
    "RELATED_PARTY_TRANSFER",
    "DISTRESS_OR_AUCTION_SALE",
    "PARTIAL_INTEREST_TRANSFER",
    "PARTITION_OR_FAMILY_SETTLEMENT",
    "DEVELOPER_BULK_ALLOTMENT",
    "NON_SALE_REFERENCE",
)

# Strict Data Segregation Categories (Never mixed silently)
CANONICAL_SOURCE_CATEGORIES = (
    "REGISTRATION_VERIFIED_TX",
    "DOCUMENT_VERIFIED_TX",
    "SOURCE_CONFIRMED_BROKER",
    "UNVERIFIED_BROKER_OR_LISTING",
    "GOVT_CIRCLE_RATE_REFERENCE",
    "ORERA_BDA_ENRICHMENT",
    "SYNTHETIC_TEST",
)

CANONICAL_SOURCE_TYPES = (
    "USER_SUBMITTED_DEED",
    "OFFICIAL_REGISTRY_EC",
    "ORERA_DISCLOSURE",
    "BDA_PLANNING",
    "BHULEKH_ROR",
    "GOVT_CIRCLE_RATE",
    "AUTHORIZED_BROKER_FEED",
    "LICENSED_DATASET",
    "ADVERTISED_LISTING",
    "SYNTHETIC_TEST",
)

PHASE2_MIGRATION_ID = "0001_phase2_canonical_evidence_schema"
PHASE3_MIGRATION_ID = "0002_phase3_verification_hardening_and_triggers"
PHASE4_MIGRATION_ID = "0003_phase4_ingestion_vault_and_memberships"

DATASET_ROLES = ("TRAINING", "VALIDATION", "HOLD_OUT_TEST", "INDEPENDENT_EVALUATION")

COMPLETED_SALE_DOCUMENT_TYPES = {
    "EXECUTED_SALE_DEED",
    "CERTIFIED_COPY_IGR",
    "DIGITALLY_SIGNED_EC",
    "INDEX_II_EXTRACT",
}

REGISTRATION_CORROBORATING_DOCUMENT_TYPES = {
    "EXECUTED_SALE_DEED",
    "CERTIFIED_COPY_IGR",
    "DIGITALLY_SIGNED_EC",
    "INDEX_II_EXTRACT",
}


def compute_canonical_payload_sha256(payload: Any) -> str:
    """Computes a deterministic SHA-256 hex digest over raw source payloads for idempotency."""
    canonical_str = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


class SchemaMigrationHistory(Base):
    __tablename__ = "schema_migration_history"

    migration_id = Column(String(96), primary_key=True)
    description = Column(Text, nullable=False)
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RawSourceRecord(Base):
    """Append-only archive of exact untouched source payloads with SHA-256 checksum."""
    __tablename__ = "raw_source_records"

    raw_record_id = Column(String(36), primary_key=True, default=_gen_uuid)
    source_type = Column(String(48), nullable=False, index=True)
    source_reference = Column(String(256), nullable=False)
    external_record_key = Column(String(128), nullable=True, index=True)
    payload_sha256 = Column(String(64), unique=True, nullable=False, index=True)
    raw_payload_json = Column(Text, nullable=False)
    ingestion_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_raw_source_type_ext", "source_type", "external_record_key"),
    )


class CanonicalTransaction(Base):
    """
    Phase 2 Canonical Evidence Record containing all 20 required normalized fields,
    evidence taxonomy, arm's-length classification, strict segregation category,
    and decoupled validation vs training eligibility flags.
    """
    __tablename__ = "canonical_transactions"

    # Primary key + all 20 required canonical fields
    id = Column(String(36), primary_key=True, default=_gen_uuid)
    transaction_id = Column(String(128), unique=True, nullable=False, index=True)
    property_id = Column(String(128), nullable=True, index=True)
    property_type = Column(String(40), nullable=False, index=True)
    transaction_date = Column(Date, nullable=True, index=True)
    registration_date = Column(Date, nullable=True, index=True)
    sale_price_inr = Column(Float, nullable=True)
    land_area_sqft = Column(Float, nullable=True)
    builtup_area_sqft = Column(Float, nullable=True)
    carpet_area_sqft = Column(Float, nullable=True)
    locality = Column(String(128), nullable=True, index=True)
    city = Column(String(64), nullable=False, default="Bhubaneswar", index=True)
    district = Column(String(64), nullable=True, index=True)
    state = Column(String(64), nullable=False, default="Odisha", index=True)
    latitude = Column(Float, nullable=True, index=True)
    longitude = Column(Float, nullable=True, index=True)
    source_type = Column(String(48), nullable=False, index=True)
    source_reference = Column(String(256), nullable=False)
    verification_status = Column(String(32), nullable=False, default="UNVERIFIED", index=True)
    evidence_document_reference = Column(String(256), nullable=True)
    ingestion_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Immutable provenance linkage & evidence classification
    raw_record_id = Column(
        String(36),
        ForeignKey("raw_source_records.raw_record_id"),
        nullable=False,
        index=True,
    )
    source_category = Column(String(48), nullable=False, index=True)
    evidence_document_type = Column(String(48), nullable=False, default="NONE")
    transaction_classification = Column(String(48), nullable=False, default="ATYPICAL_UNCLASSIFIED")
    is_arms_length = Column(Boolean, nullable=True)

    # Human review, deduplication candidates & explicit eligibility separation
    requires_human_review = Column(Boolean, nullable=False, default=True, index=True)
    eligible_for_ground_truth_validation = Column(Boolean, nullable=False, default=False, index=True)
    eligible_for_model_training = Column(Boolean, nullable=False, default=False, index=True)
    review_flags_json = Column(Text, nullable=True)
    dedup_signature = Column(String(64), nullable=True, index=True)
    probable_duplicate_of_tx_id = Column(String(128), nullable=True, index=True)

    # Phase 3 verification hardening, sanity references, and exclusion traceability
    circle_rate_inr = Column(Float, nullable=True)
    evidence_document_hash = Column(String(64), nullable=True, index=True)
    source_document_hash = Column(String(64), nullable=True, index=True)
    verification_method = Column(String(64), nullable=True)
    reviewer_identity = Column(String(96), nullable=True)
    used_in_model_training = Column(Boolean, nullable=False, default=False, index=True)
    validation_exclusion_reasons_json = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Non-breaking optional bridge to Milestone 7 ground_truth_transactions row
    ground_truth_tx_id = Column(
        String(36),
        ForeignKey("ground_truth_transactions.id"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index("idx_canon_loc_type_status", "city", "locality", "property_type", "verification_status"),
        Index("idx_canon_segregation", "source_category", "eligible_for_ground_truth_validation", "eligible_for_model_training"),
    )


class VerificationAuditLog(Base):
    """Append-only verification status transition ledger recording evidence & rule outcomes."""
    __tablename__ = "verification_audit_logs"

    audit_id = Column(String(36), primary_key=True, default=_gen_uuid)
    transaction_id = Column(
        String(128),
        ForeignKey("canonical_transactions.transaction_id"),
        nullable=False,
        index=True,
    )
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    evidence_document_type = Column(String(48), nullable=True)
    evidence_document_reference = Column(String(256), nullable=True)
    evidence_document_hash = Column(String(64), nullable=True)
    verification_method = Column(String(64), nullable=True)
    actor = Column(String(64), nullable=False, default="system_ingestion")
    actor_role = Column(String(48), nullable=False, default="SYSTEM_INGESTION")
    reason = Column(Text, nullable=False)
    rejection_or_escalation_reason = Column(Text, nullable=True)
    checks_snapshot_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


# Strict Immutability Enforcement on RawSourceRecord and VerificationAuditLog
@event.listens_for(RawSourceRecord, "before_update")
def _prevent_raw_update(mapper, connection, target):
    raise ImmutableRecordError(
        f"RawSourceRecord '{target.raw_record_id}' is immutable and cannot be modified after archival."
    )


@event.listens_for(RawSourceRecord, "before_delete")
def _prevent_raw_delete(mapper, connection, target):
    raise ImmutableRecordError(
        f"RawSourceRecord '{target.raw_record_id}' is immutable and cannot be deleted."
    )


@event.listens_for(VerificationAuditLog, "before_update")
def _prevent_audit_update(mapper, connection, target):
    raise ImmutableRecordError(
        f"VerificationAuditLog '{target.audit_id}' is immutable and cannot be modified."
    )


@event.listens_for(VerificationAuditLog, "before_delete")
def _prevent_audit_delete(mapper, connection, target):
    raise ImmutableRecordError(
        f"VerificationAuditLog '{target.audit_id}' is immutable and cannot be deleted."
    )


class EvidenceDocumentRecord(Base):
    """Metadata ledger pointing to quarantined/scanned raw evidence stored privately outside web roots."""
    __tablename__ = "evidence_documents"

    evidence_id = Column(String(48), primary_key=True)
    transaction_id = Column(
        String(128),
        ForeignKey("canonical_transactions.transaction_id"),
        nullable=False,
        index=True,
    )
    evidence_document_type = Column(String(48), nullable=False)
    storage_uri = Column(String(256), nullable=False)
    sha256_digest = Column(String(64), nullable=False, index=True)
    mime_type = Column(String(64), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    scan_status = Column(String(64), nullable=False)
    consent_granted = Column(Boolean, nullable=False, default=False)
    consent_reference = Column(String(128), nullable=True)
    pii_redacted_summary_json = Column(Text, nullable=True)
    uploaded_by_actor = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DatasetMembership(Base):
    """Immutable dataset split ledger preventing training vs independent-evaluation overlap."""
    __tablename__ = "dataset_memberships"

    membership_id = Column(String(36), primary_key=True, default=_gen_uuid)
    dataset_version_id = Column(String(64), nullable=False, index=True)
    dataset_role = Column(String(32), nullable=False, index=True)  # TRAINING, VALIDATION, HOLD_OUT_TEST, INDEPENDENT_EVALUATION
    transaction_id = Column(
        String(128),
        ForeignKey("canonical_transactions.transaction_id"),
        nullable=False,
        index=True,
    )
    property_id = Column(String(128), nullable=True, index=True)
    record_sha256 = Column(String(64), nullable=False)
    assigned_by = Column(String(64), nullable=False)
    assigned_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_membership_ver_tx", "dataset_version_id", "transaction_id", unique=True),
    )


class IngestionRun(Base):
    """Audit and observability record for controlled batch/single ingestion executions."""
    __tablename__ = "ingestion_runs"

    run_id = Column(String(36), primary_key=True, default=_gen_uuid)
    adapter_name = Column(String(64), nullable=False, index=True)
    source_type = Column(String(48), nullable=False, index=True)
    source_reference = Column(String(256), nullable=False)
    actor_id = Column(String(64), nullable=False)
    actor_role = Column(String(48), nullable=False)
    status = Column(String(32), nullable=False, default="RUNNING", index=True)
    submitted_count = Column(Integer, nullable=False, default=0)
    accepted_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    quarantined_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    error_summary_json = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


@event.listens_for(DatasetMembership, "before_update")
def _prevent_membership_update(mapper, connection, target):
    raise ImmutableRecordError(
        f"DatasetMembership '{target.membership_id}' is immutable to prevent silent train/eval contamination."
    )


@event.listens_for(DatasetMembership, "before_delete")
def _prevent_membership_delete(mapper, connection, target):
    raise ImmutableRecordError(
        f"DatasetMembership '{target.membership_id}' is immutable and cannot be deleted."
    )


def evaluate_detailed_eligibility(
    verification_status: str,
    source_category: str,
    transaction_classification: str,
    is_arms_length: Optional[bool],
    sale_price_inr: Optional[float],
    requires_human_review: bool,
    evidence_document_type: str = "EXECUTED_SALE_DEED",
    applicable_area_sqft: Optional[float] = 1000.0,
    has_unresolved_duplicates: bool = False,
    used_in_model_training: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates decoupled Ground-Truth Validation vs Model-Training eligibility with explicit exclusion reasons.
    No transaction is made eligible merely by status alone; all structural, evidentiary, review,
    arm's-length, and non-overlap conditions must hold simultaneously.
    """
    exclusion_reasons: List[str] = []

    disallowed_categories = {
        "SYNTHETIC_TEST": "Synthetic provenance blocked from production validation and training.",
        "UNVERIFIED_BROKER_OR_LISTING": "Unverified broker or advertised listing record is excluded.",
        "GOVT_CIRCLE_RATE_REFERENCE": "Government circle rate / BMV is a benchmark floor, not a market sale.",
        "ORERA_BDA_ENRICHMENT": "ORERA/BDA planning disclosure has no verified sale consideration.",
        "SOURCE_CONFIRMED_BROKER": "Broker report lacks executed/registered sale documentary evidence.",
    }
    non_market_classes = {
        "GIFT_DEED",
        "RELATED_PARTY_TRANSFER",
        "DISTRESS_OR_AUCTION_SALE",
        "PARTIAL_INTEREST_TRANSFER",
        "PARTITION_OR_FAMILY_SETTLEMENT",
        "NON_SALE_REFERENCE",
    }

    if verification_status == "REJECTED":
        exclusion_reasons.append("Transaction verification_status is REJECTED.")
    elif verification_status not in ("DOCUMENT_VERIFIED", "REGISTRATION_VERIFIED"):
        exclusion_reasons.append(
            f"Verification status '{verification_status}' has not reached DOCUMENT_VERIFIED or REGISTRATION_VERIFIED."
        )

    if source_category in disallowed_categories:
        exclusion_reasons.append(disallowed_categories[source_category])

    if evidence_document_type == "AGREEMENT_FOR_SALE":
        exclusion_reasons.append(
            "AGREEMENT_FOR_SALE does not establish a completed property sale transaction."
        )
    elif evidence_document_type not in COMPLETED_SALE_DOCUMENT_TYPES:
        exclusion_reasons.append(
            f"Evidence type '{evidence_document_type}' is not a completed deed/registration extract."
        )

    if transaction_classification in non_market_classes:
        exclusion_reasons.append(
            f"Non-arm's-length or non-market transaction classification '{transaction_classification}'."
        )
    elif transaction_classification != "ARMS_LENGTH_MARKET" or is_arms_length is not True:
        exclusion_reasons.append("Arm's-length market transfer has not been confirmed by evidence.")

    if sale_price_inr is None or sale_price_inr <= 0.0:
        exclusion_reasons.append("Valid positive sale_price_inr is missing.")
    if applicable_area_sqft is None or applicable_area_sqft <= 0.0:
        exclusion_reasons.append("Applicable positive area measurement (built-up, carpet, or land) is missing.")

    if requires_human_review:
        exclusion_reasons.append("Transaction has unresolved human-review flags.")
    if has_unresolved_duplicates:
        exclusion_reasons.append("Transaction has unresolved duplicate review flags.")
    if used_in_model_training:
        exclusion_reasons.append("Record was used in model training and cannot enter independent evaluation.")

    gt_eligible = len(exclusion_reasons) == 0

    train_exclusions = list(exclusion_reasons)
    if verification_status != "REGISTRATION_VERIFIED" or source_category != "REGISTRATION_VERIFIED_TX":
        train_exclusions.append(
            "Model training strictly requires REGISTRATION_VERIFIED provenance (DOCUMENT_VERIFIED excluded)."
        )

    train_eligible = len(train_exclusions) == 0
    return {
        "eligible_for_ground_truth_validation": gt_eligible,
        "eligible_for_model_training": train_eligible,
        "exclusion_reasons": exclusion_reasons if not gt_eligible else (train_exclusions if not train_eligible else []),
    }


def compute_eligibility_flags(
    verification_status: str,
    source_category: str,
    transaction_classification: str,
    is_arms_length: Optional[bool],
    sale_price_inr: Optional[float],
    requires_human_review: bool,
    evidence_document_type: str = "EXECUTED_SALE_DEED",
    applicable_area_sqft: Optional[float] = 1000.0,
    has_unresolved_duplicates: bool = False,
    used_in_model_training: bool = False,
) -> Tuple[bool, bool]:
    """Backward-compatible wrapper returning (eligible_for_ground_truth_validation, eligible_for_model_training)."""
    res = evaluate_detailed_eligibility(
        verification_status=verification_status,
        source_category=source_category,
        transaction_classification=transaction_classification,
        is_arms_length=is_arms_length,
        sale_price_inr=sale_price_inr,
        requires_human_review=requires_human_review,
        evidence_document_type=evidence_document_type,
        applicable_area_sqft=applicable_area_sqft,
        has_unresolved_duplicates=has_unresolved_duplicates,
        used_in_model_training=used_in_model_training,
    )
    return res["eligible_for_ground_truth_validation"], res["eligible_for_model_training"]


def archive_raw_source_record(
    db: Session,
    source_type: str,
    source_reference: str,
    raw_payload: Dict[str, Any],
    external_record_key: Optional[str] = None,
) -> Tuple[RawSourceRecord, bool]:
    """
    Idempotently archives an immutable raw payload by deterministic SHA-256 hash.
    Returns (record, created_new). Never overwrites existing raw records.
    """
    if source_type not in CANONICAL_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type '{source_type}'. Expected one of {CANONICAL_SOURCE_TYPES}.")

    digest = compute_canonical_payload_sha256(raw_payload)
    existing = db.query(RawSourceRecord).filter(RawSourceRecord.payload_sha256 == digest).first()
    if existing is not None:
        return existing, False

    canonical_json = json.dumps(raw_payload, sort_keys=True, ensure_ascii=False, default=str)
    rec = RawSourceRecord(
        source_type=source_type,
        source_reference=source_reference,
        external_record_key=external_record_key,
        payload_sha256=digest,
        raw_payload_json=canonical_json,
    )
    db.add(rec)
    db.flush()
    return rec, True


def run_phase2_migrations(bind_engine: Any = None) -> Dict[str, Any]:
    """
    Additive, idempotent migration for Milestone 8 Phase 2 tables.
    Never drops, recreates, or overwrites existing Milestone 7 or rental tables.
    """
    target_engine = bind_engine or engine
    inspector = inspect(target_engine)
    existing_before = set(inspector.get_table_names())

    # Ensure Milestone 7 parent table exists if running against a fresh isolated test DB,
    # without altering it if it already exists.
    from src.core.ground_truth_db import GroundTruthTransaction  # noqa: F401

    ordered_tables = [
        GroundTruthTransaction.__table__,
        SchemaMigrationHistory.__table__,
        RawSourceRecord.__table__,
        CanonicalTransaction.__table__,
        VerificationAuditLog.__table__,
    ]

    created_tables = []
    for tbl in ordered_tables:
        if tbl.name not in existing_before:
            tbl.create(bind=target_engine, checkfirst=True)
            created_tables.append(tbl.name)

    with Session(target_engine) as db:
        already_applied = (
            db.query(SchemaMigrationHistory)
            .filter(SchemaMigrationHistory.migration_id == PHASE2_MIGRATION_ID)
            .first()
        )
        migration_recorded = False
        if already_applied is None:
            db.add(
                SchemaMigrationHistory(
                    migration_id=PHASE2_MIGRATION_ID,
                    description=(
                        "Add immutable raw_source_records, canonical_transactions (20 required fields + "
                        "classification/segregation), verification_audit_logs, and schema_migration_history."
                    ),
                )
            )
            db.commit()
            migration_recorded = True

    return {
        "migration_id": PHASE2_MIGRATION_ID,
        "status": "APPLIED" if migration_recorded else "ALREADY_APPLIED",
        "created_tables": created_tables,
        "existing_tables_preserved": sorted(existing_before),
    }


def run_phase3_migrations(bind_engine: Any = None) -> Dict[str, Any]:
    """
    Additive, idempotent migration for Milestone 8 Phase 3 verification hardening:
    1. Ensures Phase 2 tables exist without altering Milestone 7 tables.
    2. Safely adds Phase 3 columns via ALTER TABLE ADD COLUMN if upgrading an existing Phase 2 DB.
    3. Installs database-level SQLite triggers blocking UPDATE and DELETE on
       `raw_source_records` and `verification_audit_logs`.
    """
    target_engine = bind_engine or engine
    run_phase2_migrations(target_engine)

    inspector = inspect(target_engine)
    added_columns: List[str] = []

    additive_columns = {
        "canonical_transactions": [
            ("circle_rate_inr", "FLOAT"),
            ("evidence_document_hash", "VARCHAR(64)"),
            ("source_document_hash", "VARCHAR(64)"),
            ("verification_method", "VARCHAR(64)"),
            ("reviewer_identity", "VARCHAR(96)"),
            ("used_in_model_training", "BOOLEAN NOT NULL DEFAULT 0"),
            ("validation_exclusion_reasons_json", "TEXT"),
            ("rejection_reason", "TEXT"),
        ],
        "verification_audit_logs": [
            ("evidence_document_hash", "VARCHAR(64)"),
            ("verification_method", "VARCHAR(64)"),
            ("actor_role", "VARCHAR(48) NOT NULL DEFAULT 'SYSTEM_INGESTION'"),
            ("rejection_or_escalation_reason", "TEXT"),
        ],
    }

    with target_engine.begin() as conn:
        for table_name, col_defs in additive_columns.items():
            existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
            for col_name, sql_type in col_defs:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}"))
                    added_columns.append(f"{table_name}.{col_name}")

        triggers_installed: List[str] = []
        if target_engine.dialect.name == "sqlite":
            trigger_ddl = [
                (
                    "trg_raw_source_records_no_update",
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_raw_source_records_no_update
                    BEFORE UPDATE ON raw_source_records
                    FOR EACH ROW
                    BEGIN
                        SELECT RAISE(ABORT, 'raw_source_records is immutable: UPDATE prohibited');
                    END;
                    """,
                ),
                (
                    "trg_raw_source_records_no_delete",
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_raw_source_records_no_delete
                    BEFORE DELETE ON raw_source_records
                    FOR EACH ROW
                    BEGIN
                        SELECT RAISE(ABORT, 'raw_source_records is immutable: DELETE prohibited');
                    END;
                    """,
                ),
                (
                    "trg_verification_audit_logs_no_update",
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_verification_audit_logs_no_update
                    BEFORE UPDATE ON verification_audit_logs
                    FOR EACH ROW
                    BEGIN
                        SELECT RAISE(ABORT, 'verification_audit_logs is immutable: UPDATE prohibited');
                    END;
                    """,
                ),
                (
                    "trg_verification_audit_logs_no_delete",
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_verification_audit_logs_no_delete
                    BEFORE DELETE ON verification_audit_logs
                    FOR EACH ROW
                    BEGIN
                        SELECT RAISE(ABORT, 'verification_audit_logs is immutable: DELETE prohibited');
                    END;
                    """,
                ),
            ]
            for trg_name, ddl in trigger_ddl:
                conn.execute(text(ddl))
                triggers_installed.append(trg_name)

            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_canon_src_doc_hash ON canonical_transactions (source_document_hash)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_canon_evid_doc_hash ON canonical_transactions (evidence_document_hash)"))

    with Session(target_engine) as db:
        already_applied = (
            db.query(SchemaMigrationHistory)
            .filter(SchemaMigrationHistory.migration_id == PHASE3_MIGRATION_ID)
            .first()
        )
        migration_recorded = False
        if already_applied is None:
            db.add(
                SchemaMigrationHistory(
                    migration_id=PHASE3_MIGRATION_ID,
                    description=(
                        "Add Phase 3 verification/exclusion traceability columns and SQLite "
                        "BEFORE UPDATE/DELETE triggers on raw_source_records and verification_audit_logs."
                    ),
                )
            )
            db.commit()
            migration_recorded = True

    return {
        "migration_id": PHASE3_MIGRATION_ID,
        "status": "APPLIED" if migration_recorded else "ALREADY_APPLIED",
        "added_columns": added_columns,
        "triggers_installed": triggers_installed,
    }


def run_phase4_migrations(bind_engine: Any = None) -> Dict[str, Any]:
    """
    Additive, idempotent migration for Milestone 8 Phase 4:
    1. Ensures Phase 2 & Phase 3 schemas and triggers are active.
    2. Creates `evidence_documents`, `dataset_memberships`, and `ingestion_runs`.
    3. Installs SQLite BEFORE UPDATE/DELETE immutability triggers on `dataset_memberships`.
    """
    target_engine = bind_engine or engine
    run_phase3_migrations(target_engine)

    inspector = inspect(target_engine)
    existing_before = set(inspector.get_table_names())
    phase4_tables = [
        EvidenceDocumentRecord.__table__,
        DatasetMembership.__table__,
        IngestionRun.__table__,
    ]
    created_tables: List[str] = []
    for tbl in phase4_tables:
        if tbl.name not in existing_before:
            tbl.create(bind=target_engine, checkfirst=True)
            created_tables.append(tbl.name)

    triggers_installed: List[str] = []
    if target_engine.dialect.name == "sqlite":
        with target_engine.begin() as conn:
            for trg_name, action in (
                ("trg_dataset_memberships_no_update", "BEFORE UPDATE"),
                ("trg_dataset_memberships_no_delete", "BEFORE DELETE"),
            ):
                conn.execute(
                    text(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {trg_name}
                        {action} ON dataset_memberships
                        FOR EACH ROW
                        BEGIN
                            SELECT RAISE(ABORT, 'dataset_memberships is immutable: {action} prohibited');
                        END;
                        """
                    )
                )
                triggers_installed.append(trg_name)

    with Session(target_engine) as db:
        already_applied = (
            db.query(SchemaMigrationHistory)
            .filter(SchemaMigrationHistory.migration_id == PHASE4_MIGRATION_ID)
            .first()
        )
        migration_recorded = False
        if already_applied is None:
            db.add(
                SchemaMigrationHistory(
                    migration_id=PHASE4_MIGRATION_ID,
                    description=(
                        "Add evidence_documents private vault ledger, immutable dataset_memberships "
                        "split audit table (+ SQLite triggers), and ingestion_runs tracking table."
                    ),
                )
            )
            db.commit()
            migration_recorded = True

    return {
        "migration_id": PHASE4_MIGRATION_ID,
        "status": "APPLIED" if migration_recorded else "ALREADY_APPLIED",
        "created_tables": created_tables,
        "triggers_installed": triggers_installed,
    }
