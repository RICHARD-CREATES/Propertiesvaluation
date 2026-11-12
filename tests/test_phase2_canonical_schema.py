"""
Phase 2 Tests — Canonical Evidence Schema, Immutable Raw Archive & Non-Destructive Migration
"""
from datetime import date
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from src.core.evidence_schema import (
    CANONICAL_SOURCE_CATEGORIES,
    CANONICAL_VERIFICATION_STATUSES,
    EVIDENCE_DOCUMENT_TYPES,
    PHASE2_MIGRATION_ID,
    TRANSACTION_CLASSIFICATIONS,
    CanonicalTransaction,
    ImmutableRecordError,
    RawSourceRecord,
    SchemaMigrationHistory,
    VerificationAuditLog,
    archive_raw_source_record,
    compute_eligibility_flags,
    run_phase2_migrations,
)
from src.core.ground_truth_db import GroundTruthTransaction, compute_dedup_signature, init_ground_truth_db


def _create_pre_phase2_db(tmp_path):
    db_file = tmp_path / "phase2_isolated.db"
    eng = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    GroundTruthTransaction.__table__.create(bind=eng, checkfirst=True)
    return eng


def test_phase2_migration_preserves_existing_ground_truth_and_is_idempotent(tmp_path):
    eng = _create_pre_phase2_db(tmp_path)

    # Seed a Milestone 7 row BEFORE Phase 2 migration runs
    with Session(eng) as db:
        pre_row = GroundTruthTransaction(
            transaction_id="M7_PREEXISTING_001",
            dedup_signature=compute_dedup_signature("apartment", 20.353, 85.826, 6200000.0, "2025-11-01", 1250.0),
            property_type="apartment",
            latitude=20.353,
            longitude=85.826,
            locality="Patia",
            city="Bhubaneswar",
            state="Odisha",
            country_code="IN",
            sale_price=6200000.0,
            transaction_date=date(2025, 11, 1),
            builtup_area_sqft=1250.0,
            source_name="Test_IGR_Seed",
            data_category="Verified_Registered_Transaction",
            verification_status="verified_independent_deed",
            document_reference="SRO/KH/2025/101",
        )
        db.add(pre_row)
        db.commit()

    # Run migration first time
    res1 = run_phase2_migrations(eng)
    assert res1["migration_id"] == PHASE2_MIGRATION_ID
    assert res1["status"] == "APPLIED"
    assert "ground_truth_transactions" in res1["existing_tables_preserved"]
    assert set(res1["created_tables"]) == {
        "schema_migration_history",
        "raw_source_records",
        "canonical_transactions",
        "verification_audit_logs",
    }

    # Verify pre-existing Milestone 7 row survived completely intact
    with Session(eng) as db:
        persisted = db.query(GroundTruthTransaction).filter_by(transaction_id="M7_PREEXISTING_001").one()
        assert persisted.sale_price == 6200000.0
        assert persisted.document_reference == "SRO/KH/2025/101"

    # Re-run migration -> idempotent
    res2 = run_phase2_migrations(eng)
    assert res2["status"] == "ALREADY_APPLIED"
    assert res2["created_tables"] == []


def test_immutable_raw_record_idempotency_and_tamper_protection(tmp_path):
    eng = _create_pre_phase2_db(tmp_path)
    run_phase2_migrations(eng)

    sample_raw = {
        "deed_no": "SRO-BBSR-2025-441",
        "mouza": "Patia",
        "consideration_inr": 6500000,
        "builtup_sqft": 1300,
    }

    with Session(eng) as db:
        r1, created1 = archive_raw_source_record(
            db,
            source_type="USER_SUBMITTED_DEED",
            source_reference="user_upload_batch_01",
            raw_payload=sample_raw,
            external_record_key="SRO-BBSR-2025-441",
        )
        db.commit()
        raw_id = r1.raw_record_id
        sha1 = r1.payload_sha256
        assert created1 is True
        assert len(sha1) == 64

    # Idempotent duplicate raw ingestion (even with key order permuted)
    permuted = {
        "builtup_sqft": 1300,
        "consideration_inr": 6500000,
        "mouza": "Patia",
        "deed_no": "SRO-BBSR-2025-441",
    }
    with Session(eng) as db:
        r2, created2 = archive_raw_source_record(
            db,
            source_type="USER_SUBMITTED_DEED",
            source_reference="user_upload_batch_02",
            raw_payload=permuted,
        )
        assert created2 is False
        assert r2.raw_record_id == raw_id
        assert r2.payload_sha256 == sha1

    # Tamper attempt (UPDATE) must raise ImmutableRecordError
    with Session(eng) as db:
        rec = db.query(RawSourceRecord).filter_by(raw_record_id=raw_id).one()
        rec.source_reference = "tampered_source"
        with pytest.raises(ImmutableRecordError):
            db.commit()
        db.rollback()

    # Tamper attempt (DELETE) must raise ImmutableRecordError
    with Session(eng) as db:
        rec = db.query(RawSourceRecord).filter_by(raw_record_id=raw_id).one()
        db.delete(rec)
        with pytest.raises(ImmutableRecordError):
            db.commit()
        db.rollback()


def test_canonical_20_fields_missing_optionals_and_atypical_classifications(tmp_path):
    eng = _create_pre_phase2_db(tmp_path)
    run_phase2_migrations(eng)

    inspector = inspect(eng)
    cols = {c["name"] for c in inspector.get_columns("canonical_transactions")}
    required_20 = {
        "transaction_id",
        "property_id",
        "property_type",
        "transaction_date",
        "registration_date",
        "sale_price_inr",
        "land_area_sqft",
        "builtup_area_sqft",
        "carpet_area_sqft",
        "locality",
        "city",
        "district",
        "state",
        "latitude",
        "longitude",
        "source_type",
        "source_reference",
        "verification_status",
        "evidence_document_reference",
        "ingestion_timestamp",
    }
    assert required_20.issubset(cols)
    assert set(CANONICAL_VERIFICATION_STATUSES) == {
        "UNVERIFIED",
        "SOURCE_CONFIRMED",
        "DOCUMENT_VERIFIED",
        "REGISTRATION_VERIFIED",
        "REJECTED",
    }
    assert {"AGREEMENT_FOR_SALE", "EXECUTED_SALE_DEED", "DIGITALLY_SIGNED_EC"}.issubset(set(EVIDENCE_DOCUMENT_TYPES))
    assert {"ARMS_LENGTH_MARKET", "GIFT_DEED", "RELATED_PARTY_TRANSFER", "DISTRESS_OR_AUCTION_SALE", "PARTIAL_INTEREST_TRANSFER"}.issubset(
        set(TRANSACTION_CLASSIFICATIONS)
    )

    with Session(eng) as db:
        # 1. ORERA project record missing sale_price_inr & registration_date -> stays None, not invented!
        raw_orera, _ = archive_raw_source_record(
            db, "ORERA_DISCLOSURE", "https://rera.odisha.gov.in/project/RP/19/2025/001", {"project": "Patia Greens"}
        )
        orera_tx = CanonicalTransaction(
            transaction_id="ORERA_REF_001",
            property_id="ORERA:RP/19/2025/001",
            property_type="apartment",
            transaction_date=None,
            registration_date=None,
            sale_price_inr=None,
            land_area_sqft=43560.0,
            builtup_area_sqft=None,
            carpet_area_sqft=None,
            locality="Patia",
            city="Bhubaneswar",
            district="Khordha",
            state="Odisha",
            latitude=20.355,
            longitude=85.818,
            source_type="ORERA_DISCLOSURE",
            source_reference="https://rera.odisha.gov.in",
            verification_status="SOURCE_CONFIRMED",
            evidence_document_reference="RP/19/2025/001",
            raw_record_id=raw_orera.raw_record_id,
            source_category="ORERA_BDA_ENRICHMENT",
            evidence_document_type="ORERA_QPR_FILING",
            transaction_classification="NON_SALE_REFERENCE",
            is_arms_length=False,
            requires_human_review=False,
            eligible_for_ground_truth_validation=False,
            eligible_for_model_training=False,
        )
        db.add(orera_tx)

        # 2. Registered GIFT_DEED: REGISTRATION_VERIFIED, yet NEVER arm's-length market -> ineligible!
        raw_gift, _ = archive_raw_source_record(
            db, "USER_SUBMITTED_DEED", "gift_deed_01", {"deed_type": "GIFT_DEED", "consideration": 1000000}
        )
        gt_flag, train_flag = compute_eligibility_flags(
            verification_status="REGISTRATION_VERIFIED",
            source_category="REGISTRATION_VERIFIED_TX",
            transaction_classification="GIFT_DEED",
            is_arms_length=False,
            sale_price_inr=1000000.0,
            requires_human_review=False,
        )
        assert gt_flag is False
        assert train_flag is False

        gift_tx = CanonicalTransaction(
            transaction_id="DEED_GIFT_001",
            property_id="IN:OD:KHORDHA:PATIA:PL42",
            property_type="apartment",
            transaction_date=date(2025, 10, 10),
            registration_date=date(2025, 10, 12),
            sale_price_inr=1000000.0,
            builtup_area_sqft=1200.0,
            locality="Patia",
            city="Bhubaneswar",
            district="Khordha",
            state="Odisha",
            latitude=20.354,
            longitude=85.822,
            source_type="USER_SUBMITTED_DEED",
            source_reference="IGR_EC_CHK",
            verification_status="REGISTRATION_VERIFIED",
            evidence_document_reference="SRO/KH/2025/G99",
            raw_record_id=raw_gift.raw_record_id,
            source_category="REGISTRATION_VERIFIED_TX",
            evidence_document_type="EXECUTED_SALE_DEED",
            transaction_classification="GIFT_DEED",
            is_arms_length=False,
            requires_human_review=True,
            eligible_for_ground_truth_validation=gt_flag,
            eligible_for_model_training=train_flag,
        )
        db.add(gift_tx)
        db.commit()

        fetched_orera = db.query(CanonicalTransaction).filter_by(transaction_id="ORERA_REF_001").one()
        assert fetched_orera.sale_price_inr is None
        assert fetched_orera.transaction_date is None


def test_data_segregation_and_separate_validation_vs_training_gates():
    # Verify all 7 segregation categories and strict separation between DOCUMENT_VERIFIED & REGISTRATION_VERIFIED
    assert len(CANONICAL_SOURCE_CATEGORIES) == 7

    # DOCUMENT_VERIFIED Agreement for Sale -> eligible for GT validation if reviewed arm's-length,
    # NEVER automatically eligible for ML model training
    gt_doc, train_doc = compute_eligibility_flags(
        verification_status="DOCUMENT_VERIFIED",
        source_category="DOCUMENT_VERIFIED_TX",
        transaction_classification="ARMS_LENGTH_MARKET",
        is_arms_length=True,
        sale_price_inr=6200000.0,
        requires_human_review=False,
    )
    assert gt_doc is True
    assert train_doc is False

    # REGISTRATION_VERIFIED + ARMS_LENGTH_MARKET + reviewed -> eligible for both
    gt_reg, train_reg = compute_eligibility_flags(
        verification_status="REGISTRATION_VERIFIED",
        source_category="REGISTRATION_VERIFIED_TX",
        transaction_classification="ARMS_LENGTH_MARKET",
        is_arms_length=True,
        sale_price_inr=6200000.0,
        requires_human_review=False,
    )
    assert gt_reg is True
    assert train_reg is True

    # Non-market / unverified / circle-rate / broker categories always blocked from both
    for blocked_cat in (
        "SOURCE_CONFIRMED_BROKER",
        "UNVERIFIED_BROKER_OR_LISTING",
        "GOVT_CIRCLE_RATE_REFERENCE",
        "ORERA_BDA_ENRICHMENT",
        "SYNTHETIC_TEST",
    ):
        g, t = compute_eligibility_flags(
            verification_status="REGISTRATION_VERIFIED",
            source_category=blocked_cat,
            transaction_classification="ARMS_LENGTH_MARKET",
            is_arms_length=True,
            sale_price_inr=6200000.0,
            requires_human_review=False,
        )
        assert (g, t) == (False, False)


def test_atomic_transaction_rollback_prevents_orphan_records(tmp_path):
    eng = _create_pre_phase2_db(tmp_path)
    run_phase2_migrations(eng)

    with Session(eng) as db:
        try:
            raw_row, _ = archive_raw_source_record(
                db, "USER_SUBMITTED_DEED", "rollback_test", {"test": "rollback_payload"}
            )
            # Trigger constraint failure (missing required non-null property_type)
            bad_tx = CanonicalTransaction(
                transaction_id="BAD_ROLLBACK_TX",
                property_type=None,  # NOT NULL violation
                source_type="USER_SUBMITTED_DEED",
                source_reference="rollback_test",
                raw_record_id=raw_row.raw_record_id,
                source_category="DOCUMENT_VERIFIED_TX",
            )
            db.add(bad_tx)
            db.commit()
        except Exception:
            db.rollback()

    with Session(eng) as db:
        assert db.query(RawSourceRecord).count() == 0
        assert db.query(CanonicalTransaction).count() == 0


def test_live_init_ground_truth_db_applies_phase2_safely():
    init_ground_truth_db()
    from src.core.rental_db import engine

    tables = set(inspect(engine).get_table_names())
    assert {
        "ground_truth_transactions",
        "validation_evaluation_runs",
        "raw_source_records",
        "canonical_transactions",
        "verification_audit_logs",
        "schema_migration_history",
    }.issubset(tables)
