"""
Comprehensive Tests for Milestone 7: Independent Valuation Accuracy & Evidence Validation.
Covers geographic leakage, duplicate transactions, missing values, invalid coordinates,
data source segregation, metric calculations, insufficient sample sizes, empirical conformal
prediction interval calibration, and REST API / UI contracts.
"""
import math
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.core.ground_truth_db import GroundTruthTransaction, validate_transaction_payload
from src.core.rental_db import SessionLocal
from src.services.evidence_confidence import EvidenceConfidenceService
from src.services.spatial_split import SpatialLeakageError, create_spatial_splits, verify_no_geographic_leakage
from src.services.validation_engine import IndependentValidationEngine, compute_regression_metrics


client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_test_m7_records():
    """Ensures temporary Milestone 7 test transactions are cleaned up from DB after each test."""
    yield
    with SessionLocal() as db:
        db.query(GroundTruthTransaction).filter(
            GroundTruthTransaction.transaction_id.like("TEST_M7_%")
        ).delete(synchronize_session=False)
        db.commit()


def test_geographic_leakage_prevention():
    # Two clusters ~12 km apart in Bhubaneswar + 1 cluster in Cuttack (~22 km away)
    records = [
        {"transaction_id": "T1", "latitude": 20.3036, "longitude": 85.8485, "locality": "VSS Nagar", "city": "Bhubaneswar", "state": "Odisha", "property_type": "apartment", "transaction_date": "2025-05-01"},
        {"transaction_id": "T2", "latitude": 20.3040, "longitude": 85.8490, "locality": "VSS Nagar", "city": "Bhubaneswar", "state": "Odisha", "property_type": "apartment", "transaction_date": "2025-05-10"},
        {"transaction_id": "T3", "latitude": 20.3550, "longitude": 85.8180, "locality": "Patia", "city": "Bhubaneswar", "state": "Odisha", "property_type": "apartment", "transaction_date": "2025-06-01"},
        {"transaction_id": "T4", "latitude": 20.4625, "longitude": 85.8828, "locality": "CDA", "city": "Cuttack", "state": "Odisha", "property_type": "apartment", "transaction_date": "2025-06-15"},
    ]
    split = create_spatial_splits(records, cluster_radius_km=3.0, seed=42)
    assert split["status"] == "SUCCESS"
    assert split["leakage_audit"]["leakage_detected"] is False
    # T1 and T2 are ~60m apart, so they must stay in the SAME split group
    all_groups = {}
    for g in ("train", "validation", "test"):
        for r in split[g]:
            all_groups[r["transaction_id"]] = g
    assert all_groups["T1"] == all_groups["T2"]

    # Inject intentional proximity leakage between train and test -> must raise SpatialLeakageError
    leaked_train = [{"transaction_id": "LT1", "latitude": 20.3036, "longitude": 85.8485, "locality": "VSS Nagar", "geo_cluster_id": "C1"}]
    leaked_test = [{"transaction_id": "LT2", "latitude": 20.3045, "longitude": 85.8495, "locality": "VSS Nagar", "geo_cluster_id": "C2"}]
    with pytest.raises(SpatialLeakageError, match="Geographic boundary leakage"):
        verify_no_geographic_leakage(leaked_train, [], leaked_test, min_separation_km=2.0)


def test_ground_truth_validation_errors_and_segregation():
    # Invalid coordinates
    with pytest.raises(ValueError, match="Invalid GPS"):
        validate_transaction_payload({
            "property_type": "apartment", "latitude": 95.0, "longitude": 85.8,
            "sale_price": 7500000, "builtup_area_sqft": 1200, "transaction_date": "2025-06-01",
            "locality": "Patia", "city": "Bhubaneswar", "state": "Odisha", "source_name": "SRO", "evidence_url": "https://igrodisha.gov.in/deed/1"
        })

    # Missing evidence_url / document_reference for Verified_Registered_Transaction
    with pytest.raises(ValueError, match="evidence_url"):
        validate_transaction_payload({
            "property_type": "apartment", "latitude": 20.30, "longitude": 85.84,
            "sale_price": 7500000, "builtup_area_sqft": 1200, "transaction_date": "2025-06-01",
            "locality": "Patia", "city": "Bhubaneswar", "state": "Odisha", "source_name": "SRO",
            "data_category": "Verified_Registered_Transaction"
        })

    # Missing area
    with pytest.raises(ValueError, match="area measurement"):
        validate_transaction_payload({
            "property_type": "apartment", "latitude": 20.30, "longitude": 85.84,
            "sale_price": 7500000, "transaction_date": "2025-06-01",
            "locality": "Patia", "city": "Bhubaneswar", "state": "Odisha", "source_name": "SRO", "document_reference": "DEED-1"
        })

    # Synthetic record must be tagged rejected_synthetic
    syn = validate_transaction_payload({
        "property_type": "apartment", "latitude": 20.30, "longitude": 85.84,
        "sale_price": 7500000, "builtup_area_sqft": 1200, "transaction_date": "2025-06-01",
        "locality": "Patia", "city": "Bhubaneswar", "state": "Odisha",
        "source_name": "synthetic_generator", "data_category": "Synthetic_Test_Record"
    })
    assert syn["verification_status"] == "rejected_synthetic"


def test_duplicate_transaction_detection_and_source_segregation():
    engine = IndependentValidationEngine()
    records = [
        {
            "transaction_id": "TEST_M7_DUP_1",
            "property_type": "apartment", "latitude": 20.3036, "longitude": 85.8485,
            "locality": "VSS Nagar", "city": "Bhubaneswar", "state": "Odisha",
            "sale_price": 7500000, "builtup_area_sqft": 1200, "transaction_date": "2025-08-01",
            "source_name": "igr_odisha", "data_category": "Verified_Registered_Transaction",
            "document_reference": "SRO-BBSR-2025-1001"
        },
        {
            "transaction_id": "TEST_M7_DUP_2",  # Same deed fingerprint -> duplicate!
            "property_type": "apartment", "latitude": 20.3036, "longitude": 85.8485,
            "locality": "VSS Nagar", "city": "Bhubaneswar", "state": "Odisha",
            "sale_price": 7500000, "builtup_area_sqft": 1200, "transaction_date": "2025-08-01",
            "source_name": "igr_odisha_mirror", "data_category": "Verified_Registered_Transaction",
            "document_reference": "SRO-BBSR-2025-1001"
        },
        {
            "transaction_id": "TEST_M7_ASKING_1",
            "property_type": "apartment", "latitude": 20.3100, "longitude": 85.8500,
            "locality": "Saheed Nagar", "city": "Bhubaneswar", "state": "Odisha",
            "sale_price": 9000000, "builtup_area_sqft": 1200, "transaction_date": "2025-08-02",
            "source_name": "portal_asking", "data_category": "Advertised_Asking_Price"
        },
    ]
    res = engine.ingest_transactions(records)
    assert res["accepted"] == 3
    assert res["duplicates_detected"] == 1
    assert res["segregated_non_ground_truth"] == 1

    # Trying to evaluate 'train' split explicitly must raise ValueError
    with pytest.raises(ValueError, match="RULE VIOLATION"):
        engine.evaluate_ground_truth(include_splits=["train"], persist_run=False)


def test_regression_metrics_and_small_zero_handling():
    # Normal calculation with 5 samples
    y_true = [10000000.0, 12000000.0, 8000000.0, 15000000.0, 20000000.0]
    y_pred = [10500000.0, 11400000.0, 8400000.0, 14250000.0, 21000000.0]
    m = compute_regression_metrics(y_true, y_pred)
    assert m["validation_status"] == "VALIDATED"
    assert m["medape_pct"] == 5.0
    assert m["mape_pct"] == 5.0
    assert m["r2_score"] > 0.95

    # Zero actual values safely excluded from MAPE without ZeroDivisionError
    m_zero = compute_regression_metrics([0.0, 10000000.0], [500000.0, 10500000.0])
    assert m_zero["zero_or_small_actuals_excluded_from_mape"] == 1
    assert m_zero["mape_pct"] == 5.0
    assert m_zero["r2_score"] is None  # < 3 samples
    assert m_zero["validation_status"] == "UNVALIDATED_INSUFFICIENT_GROUND_TRUTH"


def test_evidence_confidence_and_interval_calibration():
    svc = EvidenceConfidenceService()

    # 1. Zero comparables -> INSUFFICIENT_EVIDENCE confidence + explicit reasons
    low = svc.compute_evidence_score(
        comparables_count=0, median_distance_km=None, search_radius_km=5.0,
        avg_similarity_0_100=None, median_age_days=None,
        source_categories=["Historical_Hub_Benchmark"], observed_critical_fields=5, total_critical_fields=10
    )
    assert low["confidence_tier"] == "INSUFFICIENT_EVIDENCE"
    assert len(low["reasons_for_low_confidence"]) >= 2

    # 2. Insufficient calibration residuals -> returns INSUFFICIENT_EVIDENCE (never fake range)
    uncal = svc.compute_calibrated_interval(point_estimate=10000000.0, holdout_abs_pct_errors=[0.05, 0.08], min_calibration_samples=10)
    assert uncal["status"] == "INSUFFICIENT_EVIDENCE"
    assert uncal["lower_estimate"] is None
    assert uncal["upper_estimate"] is None

    # 3. Sufficient holdout residuals (n=12) -> finite-sample conformal interval
    residuals = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.14, 0.18]
    cal = svc.compute_calibrated_interval(point_estimate=10000000.0, holdout_abs_pct_errors=residuals, min_calibration_samples=10)
    assert cal["status"] == "CALIBRATED_ON_INDEPENDENT_HOLDOUT"
    assert cal["lower_estimate"] < 10000000.0 < cal["upper_estimate"]


def test_validation_api_endpoints_and_ui_integration():
    # Dashboard reachable & honest when no verified independent ground truth exists
    r_dash = client.get("/api/validation/dashboard")
    assert r_dash.status_code == 200
    d = r_dash.json()
    assert "validation_status" in d
    assert "unvalidated_components" in d

    # Invalid ingest returns 400
    r_bad = client.post("/api/validation/ground-truth/ingest", json={"transactions": [{
        "property_type": "apartment", "latitude": 120.0, "longitude": 85.8,
        "sale_price": 5000000, "builtup_area_sqft": 1000, "transaction_date": "2025-07-01",
        "locality": "Patia", "city": "Bhubaneswar", "state": "Odisha", "source_name": "SRO", "document_reference": "X"
    }]})
    assert r_bad.status_code == 400

    # Main valuation returns transparent Milestone 7 evidence_and_uncertainty block
    r_val = client.post("/api/property/valuation", json={
        "location": {"latitude": 20.3036, "longitude": 85.8485, "country_code": "IN"},
        "property_details": {"asset_type": "residential", "structure_type": "apartment", "area_value": 1050}
    })
    assert r_val.status_code == 200
    eu = r_val.json()["evidence_and_uncertainty"]
    assert "evidence_quality" in eu
    assert "calibrated_prediction_interval" in eu
    assert eu["calibrated_prediction_interval"]["status"] in ("INSUFFICIENT_EVIDENCE", "CALIBRATED_ON_INDEPENDENT_HOLDOUT")

    # Dashboard bundle contains Milestone 7 components
    from pathlib import Path
    dist_assets = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "assets"
    bundle = client.get("/").text + "".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist_assets.glob("*.js"))
    assert "ev-conf-tier-badge" in bundle
    assert "/api/validation/dashboard" in bundle
