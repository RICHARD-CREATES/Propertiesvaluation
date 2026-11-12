"""
Phase 4 Tests — Authenticated Ingestion Adapters, Private Evidence Vault,
Quarantine Scanning, PII Redaction, Retries & Dataset Overlap Prevention
"""
import base64
from datetime import date
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from src.api.app import app
from src.core.evidence_schema import (
    CanonicalTransaction,
    DatasetMembership,
    EvidenceDocumentRecord,
    ImmutableRecordError,
    IngestionRun,
    RawSourceRecord,
    run_phase4_migrations,
)
from src.core.evidence_storage import (
    EvidenceAccessDeniedError,
    PrivateEvidenceVault,
    redact_pii_dict,
)
from src.core.ground_truth_db import GroundTruthTransaction, init_ground_truth_db
from src.core.security_auth import VerificationAuthManager, get_auth_manager
from src.ingestion.adapters import (
    AdapterValidationError,
    AuthorizedBrokerFeedAdapter,
    GovtBMVReferenceAdapter,
    ORERAProjectDisclosureAdapter,
    UserDocumentEvidenceAdapter,
)
from src.ingestion.pipeline import ControlledIngestionPipeline, DatasetOverlapError
from src.services.verification_engine import (
    TransactionVerificationService,
    UnauthorizedActorError,
)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _setup_phase4_db(tmp_path):
    db_file = tmp_path / "phase4_test.db"
    eng = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    GroundTruthTransaction.__table__.create(bind=eng, checkfirst=True)
    run_phase4_migrations(eng)
    return eng


def test_server_auth_rejects_client_actor_claims_and_unauthenticated_http(tmp_path):
    eng = _setup_phase4_db(tmp_path)
    auth = VerificationAuthManager(secret_key=b"test-only-hmac-key-32bytes-len!!")
    strict_verifier = TransactionVerificationService(enforce_server_auth=True)

    with Session(eng) as db:
        # Raw client actor strings MUST fail when enforce_server_auth=True
        with pytest.raises(UnauthorizedActorError):
            strict_verifier.admit_record(
                db,
                {
                    "transaction_id": "FORGE_01",
                    "property_type": "apartment",
                    "sale_price_inr": 6000000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                },
                source_type="USER_SUBMITTED_DEED",
                source_reference="forge_attempt",
                actor_id="self_declared_officer",
                actor_role="AUTHORIZED_REGISTRY_VERIFIER",
            )

        # Forged token fails verification
        with pytest.raises(UnauthorizedActorError):
            strict_verifier.admit_record(
                db,
                {
                    "transaction_id": "FORGE_02",
                    "property_type": "apartment",
                    "sale_price_inr": 6000000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                },
                source_type="USER_SUBMITTED_DEED",
                source_reference="forge_attempt",
                auth_token="v1.eyJyb2xlIjoiQVVUSE9SSVpFRF9SRUdJU1RSWV9WRVJJRklFUiJ9.bad_sig",
            )

    # HTTP routes strictly reject unauthenticated requests (401)
    client = TestClient(app)
    assert client.get("/api/ingestion/runs").status_code == 401
    assert client.post("/api/ingestion/runs/broker-feed", json={"source_reference": "x", "payload": []}).status_code == 401
    assert client.post("/api/verification/transition", json={
        "transaction_id": "X", "target_status": "REGISTRATION_VERIFIED",
        "verification_method": "OFFICIAL_IGR_EC_VERIFICATION", "reason": "bypass"
    }).status_code == 401

    # Wrong role (INTERNAL_AUTOMATED_VALIDATOR) blocked from broker ingestion endpoint (403)
    bad_role_token = get_auth_manager().issue_token("auto_bot", "INTERNAL_AUTOMATED_VALIDATOR")
    resp_403 = client.post(
        "/api/ingestion/runs/broker-feed",
        json={"source_reference": "x", "payload": []},
        headers={"Authorization": f"Bearer {bad_role_token}"},
    )
    assert resp_403.status_code == 403


def test_user_document_vault_quarantine_hash_consent_and_pii_redaction(tmp_path):
    eng = _setup_phase4_db(tmp_path)
    vault = PrivateEvidenceVault(vault_root=tmp_path / "private_vault")
    adapter = UserDocumentEvidenceAdapter(vault=vault)
    pipeline = ControlledIngestionPipeline()

    sys_principal = VerificationAuthManager().verify_token(
        get_auth_manager().issue_token("ingest_svc", "SYSTEM_INGESTION")
    )
    rev_principal = VerificationAuthManager().verify_token(
        get_auth_manager().issue_token("rev_priya", "HUMAN_REVIEWER")
    )

    clean_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nRegistered Sale Deed Patia Rs 6500000"
    risky_pdf = b"%PDF-1.4\n1 0 obj\n<< /JavaScript (app.alert(1)) >>\n"
    spoofed_pdf = b"NOT_A_PDF_HEADER_MZ_PAYLOAD"

    with Session(eng) as db:
        res = pipeline.ingest_batch(
            db=db,
            adapter=adapter,
            source_reference="bbsr_portal_uploads",
            principal=sys_principal,
            raw_records=[
                # 1. Valid consented PDF with PII that MUST be redacted in archive & uncertain extraction
                {
                    "transaction_id": "DOC_PATIA_OK",
                    "property_id": "IN:OD:KHORDHA:PATIA:U12",
                    "consent_granted": True,
                    "consent_reference": "CONSENT-2025-11",
                    "evidence_document_type": "EXECUTED_SALE_DEED",
                    "evidence_document_reference": "SRO/KH/2025/9001",
                    "document_filename": "deed_9001.pdf",
                    "document_bytes": clean_pdf,
                    "expected_sha256": _sha256_bytes(clean_pdf),
                    "property_type": "apartment",
                    "transaction_date": "2025-10-05",
                    "sale_price_inr": 6500000.0,
                    "builtup_area_sqft": 1300.0,
                    "locality": "Patia",
                    "latitude": 20.3533,
                    "longitude": 85.8266,
                    "buyer_name": "Ramesh Kumar Mohanty",
                    "seller_name": "Odisha Builders Pvt Ltd",
                    "pan": "ABCDE1234F",
                    "extraction_confidence": 0.78,
                    "uncertain_fields": ["carpet_area_sqft"],
                },
                # 2. Missing consent -> REJECTED
                {
                    "transaction_id": "DOC_NO_CONSENT",
                    "consent_granted": False,
                    "consent_reference": "",
                    "evidence_document_type": "EXECUTED_SALE_DEED",
                    "evidence_document_reference": "SRO/9002",
                    "document_filename": "deed.pdf",
                    "document_bytes": clean_pdf,
                    "property_type": "apartment",
                    "sale_price_inr": 6000000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                },
                # 3. SHA-256 mismatch -> REJECTED
                {
                    "transaction_id": "DOC_BAD_HASH",
                    "consent_granted": True,
                    "consent_reference": "CONSENT-2025-12",
                    "evidence_document_type": "DIGITALLY_SIGNED_EC",
                    "evidence_document_reference": "IGR-EC-101",
                    "document_filename": "ec_101.pdf",
                    "document_bytes": clean_pdf,
                    "expected_sha256": "0" * 64,
                    "property_type": "apartment",
                    "sale_price_inr": 6000000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                },
                # 4. Malware/JavaScript PDF -> QUARANTINED
                {
                    "transaction_id": "DOC_MALWARE",
                    "consent_granted": True,
                    "consent_reference": "CONSENT-2025-13",
                    "evidence_document_type": "EXECUTED_SALE_DEED",
                    "evidence_document_reference": "SRO/9003",
                    "document_filename": "evil.pdf",
                    "document_bytes": risky_pdf,
                    "property_type": "apartment",
                    "sale_price_inr": 6000000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                },
                # 5. Magic header spoofing -> REJECTED
                {
                    "transaction_id": "DOC_SPOOF",
                    "consent_granted": True,
                    "consent_reference": "CONSENT-2025-14",
                    "evidence_document_type": "EXECUTED_SALE_DEED",
                    "evidence_document_reference": "SRO/9004",
                    "document_filename": "spoof.pdf",
                    "document_bytes": spoofed_pdf,
                    "property_type": "apartment",
                    "sale_price_inr": 6000000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                },
            ],
        )

        assert res["accepted"] == 1
        assert res["quarantined"] == 1
        assert res["rejected"] == 3
        assert len(list((tmp_path / "private_vault" / "quarantine_rejected").iterdir())) == 1

        # Verify valid transaction stayed strictly UNVERIFIED (never auto-promoted to REGISTRATION_VERIFIED)
        tx = db.query(CanonicalTransaction).filter_by(transaction_id="DOC_PATIA_OK").one()
        assert tx.verification_status == "UNVERIFIED"
        assert tx.requires_human_review is True
        flags = json.loads(tx.review_flags_json)
        assert any("LOW_EXTRACTION_CONFIDENCE" in f for f in flags)

        # Verify PII was redacted in stored raw_source_records & evidence_documents!
        raw_rec = db.query(RawSourceRecord).filter_by(raw_record_id=tx.raw_record_id).one()
        assert "Ramesh Kumar Mohanty" not in raw_rec.raw_payload_json
        assert "ABCDE1234F" not in raw_rec.raw_payload_json

        evd = db.query(EvidenceDocumentRecord).filter_by(transaction_id="DOC_PATIA_OK").one()
        assert "Ramesh Kumar Mohanty" not in (evd.pii_redacted_summary_json or "")

        # RBAC check on raw evidence vault read
        with pytest.raises(EvidenceAccessDeniedError):
            vault.read_document_bytes(evd.storage_uri, evd.sha256_digest, sys_principal)

        raw_bytes = vault.read_document_bytes(evd.storage_uri, evd.sha256_digest, rev_principal)
        assert raw_bytes == clean_pdf


def test_broker_bmv_orera_adapters_segregation_malformed_and_idempotency(tmp_path):
    eng = _setup_phase4_db(tmp_path)
    broker_adapter = AuthorizedBrokerFeedAdapter()
    bmv_adapter = GovtBMVReferenceAdapter()
    orera_adapter = ORERAProjectDisclosureAdapter()
    pipeline = ControlledIngestionPipeline()

    principal = VerificationAuthManager().verify_token(
        get_auth_manager().issue_token("ingest_svc", "SYSTEM_INGESTION")
    )

    # Malformed CSV & malformed JSON rejected cleanly
    with pytest.raises(AdapterValidationError):
        broker_adapter.parse_records("{bad json", format_hint="json")
    with pytest.raises(AdapterValidationError):
        broker_adapter.parse_records("col1,col2\nonly_one_val\n", format_hint="csv")

    csv_feed = (
        "transaction_id,partner_id,broker_rera_id,data_use_authorization_ref,data_use_authorized,"
        "property_type,claimed_transaction_date,claimed_closing_price,area_value,area_unit,locality,latitude,longitude\n"
        "BRK_BBSR_01,PTR_OD_01,ORERA_AGT_101,MOU-2025-A,true,apartment,2025-09-12,7200000,120,sqm,Patia,20.353,85.826\n"
    )
    parsed_broker = broker_adapter.parse_records(csv_feed, format_hint="csv")
    # CSV parses "true" as string -> simulate authorized boolean normalization in batch_metadata
    batch_meta = {"data_use_authorized": True}

    with Session(eng) as db:
        # 1. Authorized broker feed -> stays UNVERIFIED/SOURCE_CONFIRMED_BROKER, never ground-truth eligible
        res_b1 = pipeline.ingest_batch(db, broker_adapter, parsed_broker, "broker_csv_01", principal=principal, batch_metadata=batch_meta)
        assert res_b1["accepted"] == 1
        brk_tx = db.query(CanonicalTransaction).filter_by(transaction_id="BRK_BBSR_01").one()
        assert round(brk_tx.builtup_area_sqft, 1) == 1291.7  # 120 sqm -> sqft normalized!
        assert brk_tx.source_category == "UNVERIFIED_BROKER_OR_LISTING"
        assert brk_tx.eligible_for_ground_truth_validation is False
        assert brk_tx.eligible_for_model_training is False

        # Re-ingesting identical broker CSV -> idempotent duplicate skipped cleanly!
        res_b2 = pipeline.ingest_batch(db, broker_adapter, parsed_broker, "broker_csv_01", principal=principal, batch_metadata=batch_meta)
        assert res_b2["accepted"] == 0
        assert res_b2["duplicates"] == 1

        # 2. BMV Circle Rate -> keeps sale_price_inr = None, source_category = GOVT_CIRCLE_RATE_REFERENCE
        bmv_res = pipeline.ingest_batch(
            db,
            bmv_adapter,
            [{
                "transaction_id": "BMV_PATIA_2025",
                "circular_or_query_ref": "IGR/KHORDHA/BMV/2025/PATIA",
                "property_type": "residential_land",
                "benchmark_value_inr": 3500000.0,
                "land_area_sqft": 2400.0,
                "mouza": "Patia",
                "latitude": 20.354,
                "longitude": 85.825,
            }],
            "manual_igrodisha_bmv",
            principal=principal,
        )
        assert bmv_res["accepted"] == 1
        bmv_tx = db.query(CanonicalTransaction).filter_by(transaction_id="BMV_PATIA_2025").one()
        assert bmv_tx.sale_price_inr is None
        assert bmv_tx.circle_rate_inr == 3500000.0
        assert bmv_tx.source_category == "GOVT_CIRCLE_RATE_REFERENCE"
        assert bmv_tx.eligible_for_ground_truth_validation is False

        # 3. ORERA project disclosure -> keeps sale_price_inr = None, source_category = ORERA_BDA_ENRICHMENT
        orera_res = pipeline.ingest_batch(
            db,
            orera_adapter,
            [{
                "orera_registration_no": "RP/19/2025/00881",
                "property_type": "apartment",
                "total_land_area_sqft": 87120.0,
                "mouza": "Patia",
                "qpr_period_end_date": "2025-09-30",
                "latitude": 20.355,
                "longitude": 85.822,
            }],
            "manual_orera_qpr",
            principal=principal,
        )
        assert orera_res["accepted"] == 1
        orera_tx = db.query(CanonicalTransaction).filter_by(transaction_id="ORERA-RP/19/2025/00881").one()
        assert orera_tx.sale_price_inr is None
        assert orera_tx.source_category == "ORERA_BDA_ENRICHMENT"
        assert orera_tx.eligible_for_ground_truth_validation is False


def test_retry_handling_and_immutable_dataset_membership_overlap_block(tmp_path):
    eng = _setup_phase4_db(tmp_path)
    verifier = TransactionVerificationService(enforce_server_auth=True)
    pipeline = ControlledIngestionPipeline(verification_service=verifier, max_retries=3, retry_backoff_sec=0.001)

    # Test SQLite busy/lock retry recovery helper
    calls = {"n": 0}

    def flaky_op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("stmt", {}, Exception("database is locked"))
        return "RECOVERED"

    assert pipeline._run_with_retry(flaky_op) == "RECOVERED"
    assert calls["n"] == 3

    # Build a fully verified transaction + second transaction sharing the SAME property_id
    reg_principal = VerificationAuthManager().verify_token(
        get_auth_manager().issue_token("reg_officer", "AUTHORIZED_REGISTRY_VERIFIER")
    )
    doc_hash1 = _sha256_bytes(b"%PDF-1.4 deed A").lower()
    doc_hash2 = _sha256_bytes(b"%PDF-1.4 deed B").lower()

    with Session(eng) as db:
        for tid, dref, dh, ddt in [
            ("EVAL_TX_1", "SRO/2025/A1", doc_hash1, "2024-01-10"),
            ("EVAL_TX_2_SAME_PROP", "SRO/2025/A2", doc_hash2, "2025-06-15"),
        ]:
            verifier.admit_record(
                db,
                {
                    "transaction_id": tid,
                    "property_id": "PROP-SHARED-BBSR-55",
                    "property_type": "apartment",
                    "transaction_date": ddt,
                    "sale_price_inr": 6200000.0,
                    "builtup_area_sqft": 1200.0,
                    "locality": "Patia",
                    "latitude": 20.353,
                    "longitude": 85.826,
                    "transaction_classification": "ARMS_LENGTH_MARKET",
                    "is_arms_length": True,
                },
                source_type="USER_SUBMITTED_DEED",
                source_reference="seed",
                principal=reg_principal,
            )
            verifier.transition_status(
                db, tid, "DOCUMENT_VERIFIED",
                verification_method="MANUAL_DEED_REVIEW", reason="ok",
                evidence_document_type="EXECUTED_SALE_DEED",
                evidence_document_reference=dref,
                evidence_document_hash=dh,
                clear_human_review=True,
                principal=reg_principal,
            )
            verifier.transition_status(
                db, tid, "REGISTRATION_VERIFIED",
                verification_method="OFFICIAL_IGR_EC_VERIFICATION", reason="ec verified",
                corroboration_reference=f"IGR-{tid}",
                registration_date=date(2025, 6, 20),
                clear_human_review=True,
                principal=reg_principal,
            )

        # Assign EVAL_TX_1 to TRAINING
        res_tr = pipeline.assign_dataset_membership(
            db, dataset_version_id="DS_2025_V1", dataset_role="TRAINING",
            transaction_ids=["EVAL_TX_1"], principal=reg_principal,
        )
        assert res_tr["assigned_count"] == 1

        # Assigning EVAL_TX_1 OR even EVAL_TX_2_SAME_PROP (shared property_id!) to INDEPENDENT_EVALUATION MUST FAIL!
        with pytest.raises(DatasetOverlapError, match="TRAINING_EVALUATION_OVERLAP_DETECTED"):
            pipeline.assign_dataset_membership(
                db, dataset_version_id="DS_2025_V1", dataset_role="INDEPENDENT_EVALUATION",
                transaction_ids=["EVAL_TX_2_SAME_PROP"], principal=reg_principal,
            )

    # Verify DatasetMembership triggers prevent UPDATE and DELETE at direct SQLite level
    with eng.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE dataset_memberships SET dataset_role = 'INDEPENDENT_EVALUATION'"))
    with eng.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM dataset_memberships"))


def test_authenticated_api_ingestion_and_existing_compatibility():
    init_ground_truth_db()
    client = TestClient(app)

    # Smoke verify existing endpoints still work
    assert client.get("/api/validation/ground-truth").status_code == 200
    assert client.get("/api/analytics/data-quality").status_code == 200

    # Authenticated BMV read/write smoke via Bearer token
    token = get_auth_manager().issue_token("api_tester", "SENIOR_AUDIT_ADMIN")
    resp = client.get("/api/ingestion/runs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "runs" in resp.json()
