"""Phase 6 Tests — Canonical <-> Ground Truth Sync, Analytics Segregation & OOD Detection."""
from datetime import date
import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.analytics.micro_market_analysis import MicroMarketAnalyzer
from src.analytics.property_eda import PropertyEDAAnalyzer
from src.api.app import app
from src.core.evidence_schema import DatasetMembership, run_phase4_migrations
from src.core.ground_truth_db import GroundTruthTransaction
from src.core.security_auth import VerificationAuthManager, get_auth_manager
from src.services.evidence_bridge import (
    OutOfDistributionDetector,
    fetch_verified_canonical_analytics_records,
    sync_verified_canonical_to_ground_truth,
)
from src.services.verification_engine import TransactionVerificationService


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_sync_bridge_and_analytics_segregation(tmp_path):
    db_file = tmp_path / "phase6_bridge.db"
    eng = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    GroundTruthTransaction.__table__.create(bind=eng, checkfirst=True)
    run_phase4_migrations(eng)

    verifier = TransactionVerificationService(enforce_server_auth=True)
    reg_principal = VerificationAuthManager().verify_token(
        get_auth_manager().issue_token("reg_officer", "AUTHORIZED_REGISTRY_VERIFIER")
    )

    with Session(eng) as db:
        # 1. Clean REGISTRATION_VERIFIED deed -> MUST sync
        verifier.admit_record(
            db,
            {
                "transaction_id": "SYNC_OK_01",
                "property_id": "PROP:SYNC:01",
                "property_type": "apartment",
                "transaction_date": "2025-10-01",
                "sale_price_inr": 6500000.0,
                "builtup_area_sqft": 1300.0,
                "locality": "Patia",
                "latitude": 20.3533,
                "longitude": 85.8266,
                "transaction_classification": "ARMS_LENGTH_MARKET",
                "is_arms_length": True,
            },
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
            principal=reg_principal,
        )
        verifier.transition_status(
            db, "SYNC_OK_01", "DOCUMENT_VERIFIED",
            verification_method="MANUAL_DEED_REVIEW", reason="ok",
            evidence_document_type="EXECUTED_SALE_DEED",
            evidence_document_reference="SRO/SYNC/01",
            evidence_document_hash=_sha256("sync-01"),
            clear_human_review=True,
            principal=reg_principal,
        )
        verifier.transition_status(
            db, "SYNC_OK_01", "REGISTRATION_VERIFIED",
            verification_method="OFFICIAL_IGR_EC_VERIFICATION", reason="ec checked",
            corroboration_reference="IGR-SYNC-01",
            registration_date=date(2025, 10, 5),
            clear_human_review=True,
            principal=reg_principal,
        )

        # 2. Training-enrolled verified deed -> MUST NOT sync to GroundTruthTransaction!
        verifier.admit_record(
            db,
            {
                "transaction_id": "SYNC_TRAIN_ONLY",
                "property_id": "PROP:SYNC:02",
                "property_type": "apartment",
                "transaction_date": "2025-10-02",
                "sale_price_inr": 6800000.0,
                "builtup_area_sqft": 1350.0,
                "locality": "Patia",
                "latitude": 20.3540,
                "longitude": 85.8270,
                "transaction_classification": "ARMS_LENGTH_MARKET",
                "is_arms_length": True,
            },
            source_type="USER_SUBMITTED_DEED",
            source_reference="upload",
            principal=reg_principal,
        )
        verifier.transition_status(
            db, "SYNC_TRAIN_ONLY", "DOCUMENT_VERIFIED",
            verification_method="MANUAL_DEED_REVIEW", reason="ok",
            evidence_document_type="EXECUTED_SALE_DEED",
            evidence_document_reference="SRO/SYNC/02",
            evidence_document_hash=_sha256("sync-02"),
            clear_human_review=True,
            principal=reg_principal,
        )
        verifier.transition_status(
            db, "SYNC_TRAIN_ONLY", "REGISTRATION_VERIFIED",
            verification_method="OFFICIAL_IGR_EC_VERIFICATION", reason="ec checked",
            corroboration_reference="IGR-SYNC-02",
            registration_date=date(2025, 10, 6),
            clear_human_review=True,
            principal=reg_principal,
        )
        db.add(
            DatasetMembership(
                dataset_version_id="DS_TEST",
                dataset_role="TRAINING",
                transaction_id="SYNC_TRAIN_ONLY",
                property_id="PROP:SYNC:02",
                record_sha256=_sha256("sync-train"),
                assigned_by="test",
            )
        )
        db.commit()

        # 3. Broker claim & circle-rate ref -> MUST NOT sync and MUST NOT enter analytics query
        verifier.admit_record(
            db,
            {
                "transaction_id": "SYNC_BROKER_NOPE",
                "property_type": "apartment",
                "transaction_date": "2025-10-03",
                "sale_price_inr": 9000000.0,
                "builtup_area_sqft": 1200.0,
                "locality": "Patia",
                "latitude": 20.353,
                "longitude": 85.826,
            },
            source_type="AUTHORIZED_BROKER_FEED",
            source_reference="broker",
            principal=reg_principal,
        )

        sync_res = sync_verified_canonical_to_ground_truth(db)
        assert sync_res["synced_to_ground_truth"] == 1
        assert sync_res["skipped_training_overlap"] == 1
        assert db.query(GroundTruthTransaction).count() == 1
        assert db.query(GroundTruthTransaction).first().transaction_id == "SYNC_OK_01"

        analytics_rows = fetch_verified_canonical_analytics_records(db)
        assert [r["transaction_id"] for r in analytics_rows] == ["SYNC_OK_01"]
        eda = PropertyEDAAnalyzer().analyze(analytics_rows)
        assert eda["valid_analyzed_records"] == 1
        micro = MicroMarketAnalyzer().analyze(analytics_rows)
        assert micro["valid_analyzed_records"] == 1


def test_ood_detector_unit_and_valuation_endpoint():
    in_dist = OutOfDistributionDetector.assess("apartment", 20.3533, 85.8266, 1300.0, "residential")
    assert in_dist["is_ood"] is False
    assert in_dist["ood_severity"] == "IN_DISTRIBUTION"

    far_ood = OutOfDistributionDetector.assess("agricultural", 19.0760, 72.8777, 1500.0, "agricultural")
    assert far_ood["is_ood"] is True
    assert far_ood["ood_severity"] == "HIGH_OOD_FALLBACK_ACTIVE"

    client = TestClient(app)
    resp = client.post("/api/property/valuation", json={
        "location": {"latitude": 20.3533, "longitude": 85.8266, "country_code": "IN"},
        "property_details": {"asset_type": "residential", "structure_type": "apartment", "area_value": 1250},
    })
    assert resp.status_code == 200
    ood_api = resp.json()["evidence_and_uncertainty"]["ood_assessment"]
    assert ood_api["is_ood"] is False
    assert ood_api["ood_severity"] == "IN_DISTRIBUTION"
