"""Phase 5 Tests — Bhubaneswar Locality Coverage Intelligence & Sample Sufficiency."""
from datetime import date
import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.analytics.coverage_intelligence import GeographicCoverageAnalyzer
from src.api.app import app
from src.core.evidence_schema import run_phase4_migrations
from src.core.ground_truth_db import GroundTruthTransaction
from src.core.security_auth import VerificationAuthManager, get_auth_manager
from src.services.verification_engine import TransactionVerificationService


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _setup_db(tmp_path):
    db_file = tmp_path / "phase5_coverage.db"
    eng = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    GroundTruthTransaction.__table__.create(bind=eng, checkfirst=True)
    run_phase4_migrations(eng)
    return eng


def test_coverage_sample_gates_and_strict_segregation(tmp_path):
    eng = _setup_db(tmp_path)
    verifier = TransactionVerificationService(enforce_server_auth=True)
    reg_principal = VerificationAuthManager().verify_token(
        get_auth_manager().issue_token("reg_officer", "AUTHORIZED_REGISTRY_VERIFIER")
    )
    analyzer = GeographicCoverageAnalyzer()

    with Session(eng) as db:
        # 1. Insert 3 unverified broker records + 2 circle rate refs in Khandagiri
        for idx in range(3):
            verifier.admit_record(
                db,
                {
                    "transaction_id": f"BRK_KHAND_{idx}",
                    "property_type": "apartment",
                    "transaction_date": "2025-09-01",
                    "sale_price_inr": 5000000.0 + idx * 100000,
                    "builtup_area_sqft": 1100.0,
                    "locality": "Khandagiri",
                    "latitude": 20.257,
                    "longitude": 85.779,
                },
                source_type="AUTHORIZED_BROKER_FEED",
                source_reference="broker_feed",
                principal=reg_principal,
            )

        # 2. Insert 6 clean REGISTRATION_VERIFIED sales in Patia (between 5 and 15 -> PRELIMINARY_DESCRIPTIVE_ONLY!)
        for idx in range(6):
            tid = f"PATIA_VER_{idx}"
            dh = _sha256(f"deed-patia-{idx}")
            verifier.admit_record(
                db,
                {
                    "transaction_id": tid,
                    "property_id": f"PROP:PATIA:{idx}",
                    "property_type": "apartment",
                    "transaction_date": f"2025-0{min(9, idx + 1)}-15",
                    "sale_price_inr": 6000000.0 + idx * 250000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                    "latitude": 20.353 + idx * 0.0005,
                    "longitude": 85.826 + idx * 0.0005,
                    "transaction_classification": "ARMS_LENGTH_MARKET",
                    "is_arms_length": True,
                },
                source_type="USER_SUBMITTED_DEED",
                source_reference="upload",
                principal=reg_principal,
            )
            verifier.transition_status(
                db, tid, "DOCUMENT_VERIFIED",
                verification_method="MANUAL_DEED_REVIEW", reason="ok",
                evidence_document_type="EXECUTED_SALE_DEED",
                evidence_document_reference=f"SRO/KH/2025/P{idx}",
                evidence_document_hash=dh,
                clear_human_review=True,
                principal=reg_principal,
            )
            verifier.transition_status(
                db, tid, "REGISTRATION_VERIFIED",
                verification_method="OFFICIAL_IGR_EC_VERIFICATION", reason="ec checked",
                corroboration_reference=f"IGR-EC-{idx}",
                registration_date=date(2025, 10, 1),
                clear_human_review=True,
                principal=reg_principal,
            )

        # 3. Insert 3 verified deeds in Saheed Nagar (< 5 threshold -> INSUFFICIENT_VERIFIED_SAMPLE, medians suppressed!)
        for idx in range(3):
            tid = f"SAHEED_VER_{idx}"
            dh = _sha256(f"deed-saheed-{idx}")
            verifier.admit_record(
                db,
                {
                    "transaction_id": tid,
                    "property_id": f"PROP:SAHEED:{idx}",
                    "property_type": "apartment",
                    "transaction_date": "2025-08-01",
                    "sale_price_inr": 9000000.0 + idx * 200000.0,
                    "builtup_area_sqft": 1350.0,
                    "locality": "Saheed Nagar",
                    "latitude": 20.2896 + idx * 0.0005,
                    "longitude": 85.8445 + idx * 0.0005,
                    "transaction_classification": "ARMS_LENGTH_MARKET",
                    "is_arms_length": True,
                },
                source_type="USER_SUBMITTED_DEED",
                source_reference="upload",
                principal=reg_principal,
            )
            verifier.transition_status(
                db, tid, "DOCUMENT_VERIFIED",
                verification_method="MANUAL_DEED_REVIEW", reason="ok",
                evidence_document_type="EXECUTED_SALE_DEED",
                evidence_document_reference=f"SRO/KH/2025/S{idx}",
                evidence_document_hash=dh,
                clear_human_review=True,
                principal=reg_principal,
            )
            verifier.transition_status(
                db, tid, "REGISTRATION_VERIFIED",
                verification_method="OFFICIAL_IGR_EC_VERIFICATION", reason="ec checked",
                corroboration_reference=f"IGR-ECS-{idx}",
                registration_date=date(2025, 9, 1),
                clear_human_review=True,
                principal=reg_principal,
            )

        report = analyzer.build_city_coverage_report(db, city="Bhubaneswar")
        by_loc = {l["locality"]: l for l in report["localities"]}

        assert report["verified_completed_sales_count"] == 9
        assert report["unverified_or_broker_count"] == 3

        # Khandagiri has ONLY broker records -> 0 verified, medians MUST be suppressed!
        khand = by_loc["Khandagiri"]
        assert khand["verified_transaction_count"] == 0
        assert khand["unverified_or_broker_count"] == 3
        assert khand["sufficiency_status"] == "INSUFFICIENT_VERIFIED_SAMPLE"
        assert khand["median_verified_price_inr"] is None

        # Saheed Nagar has 3 verified (<5) -> medians suppressed!
        saheed = by_loc["Saheed Nagar"]
        assert saheed["verified_transaction_count"] == 3
        assert saheed["sufficiency_status"] == "INSUFFICIENT_VERIFIED_SAMPLE"
        assert saheed["median_verified_price_inr"] is None

        # Patia has 6 verified (5..14) -> PRELIMINARY_DESCRIPTIVE_ONLY with median & caveat!
        patia = by_loc["Patia"]
        assert patia["verified_transaction_count"] == 6
        assert patia["sufficiency_status"] == "PRELIMINARY_DESCRIPTIVE_ONLY"
        assert patia["median_verified_price_inr"] is not None
        assert patia["verified_ppsf_distribution"]["median"] > 0
        assert any("Preliminary descriptive sample" in lim for lim in patia["limitations"])


def test_coverage_readonly_api_endpoints():
    client = TestClient(app)
    r1 = client.get("/api/coverage/bhubaneswar")
    r2 = client.get("/api/analytics/coverage")
    assert r1.status_code == 200
    assert r2.status_code == 200
    body = r1.json()
    assert body["read_only"] is True
    assert body["city"] == "Bhubaneswar"
    assert len(body["localities"]) >= 14  # All pre-seeded Bhubaneswar corridors visible
