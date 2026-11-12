"""
Phase 3 Tests — Verification State Machine, SQLite Hardening Triggers,
Duplicate Review Signals, Eligibility Gates & Audit Integrity
"""
from datetime import date
import hashlib
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.app import app
from src.core.evidence_schema import (
    CanonicalTransaction,
    ImmutableRecordError,
    RawSourceRecord,
    VerificationAuditLog,
    run_phase3_migrations,
)
from src.core.ground_truth_db import GroundTruthTransaction, init_ground_truth_db
from src.services.verification_engine import (
    PPSFSanityConfig,
    TransactionVerificationService,
    UnauthorizedActorError,
    VerificationTransitionError,
    run_transaction_validation_checks,
)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _setup_phase3_db(tmp_path):
    db_file = tmp_path / "phase3_test.db"
    eng = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    GroundTruthTransaction.__table__.create(bind=eng, checkfirst=True)
    run_phase3_migrations(eng)
    return eng


def _valid_patia_payload(**overrides):
    base = {
        "transaction_id": "BBSR_PATIA_001",
        "property_id": "IN:OD:KHORDHA:PATIA:U101",
        "property_type": "apartment",
        "transaction_date": "2025-10-15",
        "sale_price_inr": 6500000.0,
        "builtup_area_sqft": 1300.0,
        "carpet_area_sqft": 1040.0,
        "locality": "Patia",
        "city": "Bhubaneswar",
        "district": "Khordha",
        "state": "Odisha",
        "latitude": 20.3535,
        "longitude": 85.8260,
        "evidence_document_reference": "SRO/BBSR/2025/1001",
        "evidence_document_type": "EXECUTED_SALE_DEED",
        "evidence_document_hash": _sha256("doc-patia-001"),
        "transaction_classification": "ARMS_LENGTH_MARKET",
        "is_arms_length": True,
    }
    base.update(overrides)
    return base


def test_valid_lifecycle_and_invalid_skip_transitions(tmp_path):
    eng = _setup_phase3_db(tmp_path)
    svc = TransactionVerificationService()
    doc_hash = _sha256("deed-bytes-001")

    with Session(eng) as db:
        # Cannot directly admit as REGISTRATION_VERIFIED
        with pytest.raises(VerificationTransitionError):
            svc.admit_record(
                db,
                _valid_patia_payload(requested_status="REGISTRATION_VERIFIED"),
                source_type="USER_SUBMITTED_DEED",
                source_reference="portal_upload",
            )

        tx = svc.admit_record(
            db,
            _valid_patia_payload(),
            source_type="USER_SUBMITTED_DEED",
            source_reference="portal_upload",
        )
        assert tx.verification_status == "UNVERIFIED"
        assert tx.eligible_for_ground_truth_validation is False
        assert tx.eligible_for_model_training is False

        # Illegal direct skip UNVERIFIED -> REGISTRATION_VERIFIED
        with pytest.raises(VerificationTransitionError):
            svc.transition_status(
                db,
                tx.transaction_id,
                "REGISTRATION_VERIFIED",
                actor_id="verifier_01",
                actor_role="AUTHORIZED_REGISTRY_VERIFIER",
                verification_method="OFFICIAL_IGR_EC_VERIFICATION",
                reason="Attempting invalid skip",
                corroboration_reference="IGR-EC-99",
                registration_date=date(2025, 10, 20),
            )

        # Valid progression: UNVERIFIED -> SOURCE_CONFIRMED -> DOCUMENT_VERIFIED -> REGISTRATION_VERIFIED
        r1 = svc.transition_status(
            db,
            tx.transaction_id,
            "SOURCE_CONFIRMED",
            actor_id="auto_val",
            actor_role="INTERNAL_AUTOMATED_VALIDATOR",
            verification_method="AUTOMATED_SANITY_CHECK",
            reason="Metadata corroborated with Patia bounds.",
        )
        assert r1["verification_status"] == "SOURCE_CONFIRMED"
        assert r1["eligible_for_ground_truth_validation"] is False

        r2 = svc.transition_status(
            db,
            tx.transaction_id,
            "DOCUMENT_VERIFIED",
            actor_id="rev_ananya",
            actor_role="HUMAN_REVIEWER",
            verification_method="MANUAL_DEED_REVIEW",
            reason="Executed sale deed verified cleanly.",
            evidence_document_type="EXECUTED_SALE_DEED",
            evidence_document_reference="SRO/BBSR/2025/1001",
            evidence_document_hash=doc_hash,
            clear_human_review=True,
        )
        assert r2["verification_status"] == "DOCUMENT_VERIFIED"
        assert r2["eligible_for_ground_truth_validation"] is True
        assert r2["eligible_for_model_training"] is False  # strictly NOT training-eligible yet!

        r3 = svc.transition_status(
            db,
            tx.transaction_id,
            "REGISTRATION_VERIFIED",
            actor_id="reg_officer_1",
            actor_role="AUTHORIZED_REGISTRY_VERIFIER",
            verification_method="OFFICIAL_IGR_EC_VERIFICATION",
            reason="Corroborated against digitally signed IGR Odisha EC.",
            evidence_document_hash=doc_hash,
            registration_date=date(2025, 10, 18),
            corroboration_reference="IGR-OD-EC-2025-8821",
            clear_human_review=True,
        )
        assert r3["verification_status"] == "REGISTRATION_VERIFIED"
        assert r3["eligible_for_ground_truth_validation"] is True
        assert r3["eligible_for_model_training"] is True

        logs = (
            db.query(VerificationAuditLog)
            .filter_by(transaction_id=tx.transaction_id)
            .order_by(VerificationAuditLog.created_at.asc())
            .all()
        )
        assert [l.to_status for l in logs] == [
            "UNVERIFIED",
            "SOURCE_CONFIRMED",
            "DOCUMENT_VERIFIED",
            "REGISTRATION_VERIFIED",
        ]


def test_unauthorized_actor_and_forged_or_ocr_only_evidence_blocked(tmp_path):
    eng = _setup_phase3_db(tmp_path)
    svc = TransactionVerificationService()

    with Session(eng) as db:
        tx = svc.admit_record(
            db,
            _valid_patia_payload(transaction_id="AUTH_TEST_01"),
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
        )

        # Public/unauthorized actor blocked
        with pytest.raises(UnauthorizedActorError):
            svc.transition_status(
                db, tx.transaction_id, "SOURCE_CONFIRMED",
                actor_id="anon", actor_role="PUBLIC_SUBMITTER",
                verification_method="MANUAL", reason="self approve",
            )

        # Automated validator cannot approve DOCUMENT_VERIFIED
        with pytest.raises(UnauthorizedActorError):
            svc.transition_status(
                db, tx.transaction_id, "DOCUMENT_VERIFIED",
                actor_id="bot", actor_role="INTERNAL_AUTOMATED_VALIDATOR",
                verification_method="OCR_RESULT_ONLY", reason="ocr",
            )

        # Move to DOCUMENT_VERIFIED properly
        svc.transition_status(
            db, tx.transaction_id, "DOCUMENT_VERIFIED",
            actor_id="rev_1", actor_role="HUMAN_REVIEWER",
            verification_method="MANUAL_DEED_REVIEW", reason="deed checked",
            evidence_document_type="EXECUTED_SALE_DEED",
            evidence_document_reference="SRO/2025/88",
            evidence_document_hash=_sha256("valid-hash"),
        )

        # HUMAN_REVIEWER cannot unilaterally grant REGISTRATION_VERIFIED
        with pytest.raises(UnauthorizedActorError):
            svc.transition_status(
                db, tx.transaction_id, "REGISTRATION_VERIFIED",
                actor_id="rev_1", actor_role="HUMAN_REVIEWER",
                verification_method="OFFICIAL_IGR_EC_VERIFICATION",
                reason="trying self registry verify",
                corroboration_reference="IGR-123",
                registration_date=date(2025, 10, 18),
            )

        # Authorized verifier using OCR_RESULT_ONLY or plausible regex or bad hash MUST fail; retain_on_incomplete keeps DOCUMENT_VERIFIED
        held = svc.transition_status(
            db, tx.transaction_id, "REGISTRATION_VERIFIED",
            actor_id="reg_1", actor_role="AUTHORIZED_REGISTRY_VERIFIER",
            verification_method="OCR_RESULT_ONLY",
            reason="Only OCR ran",
            evidence_document_hash="not-a-valid-sha256",
            corroboration_reference="",
            retain_on_incomplete=True,
        )
        assert held["outcome"] == "RETAINED_AT_CURRENT_STATUS"
        assert held["verification_status"] == "DOCUMENT_VERIFIED"
        assert len(held["gaps"]) >= 3


def test_agreement_for_sale_and_atypical_exclusions(tmp_path):
    eng = _setup_phase3_db(tmp_path)
    svc = TransactionVerificationService()

    with Session(eng) as db:
        tx_afs = svc.admit_record(
            db,
            _valid_patia_payload(
                transaction_id="AFS_001",
                evidence_document_type="AGREEMENT_FOR_SALE",
                evidence_document_reference="AFS/2025/77",
            ),
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
        )
        res_doc = svc.transition_status(
            db, tx_afs.transaction_id, "DOCUMENT_VERIFIED",
            actor_id="rev_1", actor_role="HUMAN_REVIEWER",
            verification_method="MANUAL_REVIEW",
            reason="Agreement for sale verified as preliminary contract only.",
            evidence_document_type="AGREEMENT_FOR_SALE",
            evidence_document_reference="AFS/2025/77",
            evidence_document_hash=_sha256("afs-doc"),
        )
        assert res_doc["verification_status"] == "DOCUMENT_VERIFIED"
        # An Agreement for Sale MUST NOT enter completed sale validation or training
        assert res_doc["eligible_for_ground_truth_validation"] is False
        assert res_doc["eligible_for_model_training"] is False
        assert "AGREEMENT_FOR_SALE_INCOMPLETE_TRANSACTION" in res_doc["review_flags"]

        # Blocked from REGISTRATION_VERIFIED
        with pytest.raises(VerificationTransitionError):
            svc.transition_status(
                db, tx_afs.transaction_id, "REGISTRATION_VERIFIED",
                actor_id="reg_1", actor_role="AUTHORIZED_REGISTRY_VERIFIER",
                verification_method="OFFICIAL_IGR_EC_VERIFICATION",
                reason="Attempting on agreement",
                corroboration_reference="IGR-AFS",
                registration_date=date(2025, 10, 20),
            )

        # Training overlap blocks validation eligibility even for clean REGISTRATION_VERIFIED
        tx_clean = svc.admit_record(
            db,
            _valid_patia_payload(transaction_id="OVERLAP_01", property_id="IN:OD:P99", evidence_document_reference="SRO/99"),
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
        )
        tx_clean.used_in_model_training = True
        db.commit()
        svc.transition_status(
            db, tx_clean.transaction_id, "DOCUMENT_VERIFIED",
            actor_id="rev_1", actor_role="HUMAN_REVIEWER",
            verification_method="MANUAL_DEED_REVIEW", reason="ok",
            evidence_document_type="EXECUTED_SALE_DEED",
            evidence_document_reference="SRO/99",
            evidence_document_hash=_sha256("sro-99"),
            clear_human_review=True,
        )
        r_ov = svc.transition_status(
            db, tx_clean.transaction_id, "REGISTRATION_VERIFIED",
            actor_id="reg_1", actor_role="AUTHORIZED_REGISTRY_VERIFIER",
            verification_method="OFFICIAL_IGR_EC_VERIFICATION", reason="igr verified",
            corroboration_reference="IGR-99",
            registration_date=date(2025, 10, 20),
            clear_human_review=True,
        )
        assert r_ov["verification_status"] == "REGISTRATION_VERIFIED"
        assert r_ov["eligible_for_ground_truth_validation"] is False
        assert any("training" in x.lower() for x in r_ov["exclusion_reasons"])


def test_direct_sqlite_triggers_and_orm_block_mutations(tmp_path):
    eng = _setup_phase3_db(tmp_path)
    svc = TransactionVerificationService()

    with Session(eng) as db:
        tx = svc.admit_record(
            db,
            _valid_patia_payload(transaction_id="IMMUT_01"),
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
        )
        raw_id = tx.raw_record_id
        log_row = db.query(VerificationAuditLog).filter_by(transaction_id=tx.transaction_id).first()
        audit_id = log_row.audit_id

    # 1. ORM-level block
    with Session(eng) as db:
        raw_obj = db.query(RawSourceRecord).filter_by(raw_record_id=raw_id).one()
        raw_obj.source_reference = "mutated"
        with pytest.raises(ImmutableRecordError):
            db.commit()
        db.rollback()

        audit_obj = db.query(VerificationAuditLog).filter_by(audit_id=audit_id).one()
        audit_obj.reason = "tampered_reason"
        with pytest.raises(ImmutableRecordError):
            db.commit()
        db.rollback()

    # 2. Direct SQLite trigger block (bypassing ORM completely!)
    with eng.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE raw_source_records SET source_reference = 'hack' WHERE raw_record_id = :rid"), {"rid": raw_id})
    with eng.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM raw_source_records WHERE raw_record_id = :rid"), {"rid": raw_id})
    with eng.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE verification_audit_logs SET to_status = 'REGISTRATION_VERIFIED' WHERE audit_id = :aid"), {"aid": audit_id})
    with eng.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM verification_audit_logs WHERE audit_id = :aid"), {"aid": audit_id})


def test_duplicate_review_flags_and_circle_rate_anomaly_are_non_destructive(tmp_path):
    eng = _setup_phase3_db(tmp_path)
    svc = TransactionVerificationService(ppsf_config=PPSFSanityConfig())

    with Session(eng) as db:
        # Original record (with below-circle-rate consideration -> flagged ONLY, NOT rejected!)
        t1 = svc.admit_record(
            db,
            _valid_patia_payload(
                transaction_id="DUP_BASE",
                property_id="PROP-P10",
                sale_price_inr=5000000.0,
                circle_rate_inr=5500000.0,
                evidence_document_reference="SRO/KH/2025/55",
                evidence_document_hash=_sha256("shared-deed-bytes"),
            ),
            source_type="USER_SUBMITTED_DEED",
            source_reference="batch1",
        )
        assert t1.verification_status == "UNVERIFIED"  # NOT rejected despite below circle rate!
        assert "BELOW_CIRCLE_RATE_REVIEW" in json.loads(t1.review_flags_json)

        # Second record sharing property_id within 15 days + same doc ref + same doc hash + same coords/price/area
        t2 = svc.admit_record(
            db,
            _valid_patia_payload(
                transaction_id="DUP_SECOND",
                property_id="PROP-P10",
                transaction_date="2025-10-25",
                sale_price_inr=5020000.0,
                latitude=20.3536,
                longitude=85.8261,
                evidence_document_reference="SRO/KH/2025/55",
                evidence_document_hash=_sha256("shared-deed-bytes"),
            ),
            source_type="USER_SUBMITTED_DEED",
            source_reference="batch2",
        )
        flags_t2 = set(json.loads(t2.review_flags_json))
        assert {
            "DUPLICATE_REGISTRATION_IDENTIFIER_REVIEW",
            "REPEATED_SOURCE_DOCUMENT_HASH_REVIEW",
            "SAME_PROPERTY_CLOSE_DATES_REVIEW",
            "NEAR_IDENTICAL_PRICE_LOCATION_AREA_REVIEW",
        }.issubset(flags_t2)
        assert t2.probable_duplicate_of_tx_id == "DUP_BASE"
        # Neither transaction deleted or auto-merged
        assert db.query(CanonicalTransaction).count() == 2


def test_transition_rollback_on_audit_failure_preserves_atomicity(tmp_path):
    eng = _setup_phase3_db(tmp_path)
    svc = TransactionVerificationService()

    with Session(eng) as db:
        tx = svc.admit_record(
            db,
            _valid_patia_payload(transaction_id="RB_TX_01"),
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
        )
        initial_log_count = db.query(VerificationAuditLog).filter_by(transaction_id=tx.transaction_id).count()

        with patch.object(svc, "_append_audit_log", side_effect=RuntimeError("Simulated audit write crash")):
            with pytest.raises(RuntimeError):
                svc.transition_status(
                    db, tx.transaction_id, "SOURCE_CONFIRMED",
                    actor_id="val_1", actor_role="INTERNAL_AUTOMATED_VALIDATOR",
                    verification_method="META_CHK", reason="should rollback cleanly",
                )

    with Session(eng) as db:
        reloaded = db.query(CanonicalTransaction).filter_by(transaction_id="RB_TX_01").one()
        assert reloaded.verification_status == "UNVERIFIED"
        assert db.query(VerificationAuditLog).filter_by(transaction_id="RB_TX_01").count() == initial_log_count


def test_authoritative_polygon_and_existing_api_compatibility(tmp_path):
    init_ground_truth_db()
    eng = _setup_phase3_db(tmp_path)
    svc = TransactionVerificationService()

    with Session(eng) as db:
        tx = svc.admit_record(
            db,
            _valid_patia_payload(transaction_id="POLY_01", locality="Patia", latitude=20.2100, longitude=85.7500),
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
        )
        poly_map = {
            "patia": [
                (20.33, 85.80),
                (20.38, 85.80),
                (20.38, 85.85),
                (20.33, 85.85),
            ]
        }
        chk = run_transaction_validation_checks(tx, db, authoritative_polygons=poly_map)
        assert chk["geo_check_mode"] == "AUTHORITATIVE_POLYGON"
        assert "OUTSIDE_AUTHORITATIVE_LOCALITY_POLYGON_REVIEW" in chk["review_flags"]

    client = TestClient(app)
    assert client.get("/api/validation/ground-truth").status_code == 200
    assert client.get("/api/analytics/data-quality").status_code == 200
