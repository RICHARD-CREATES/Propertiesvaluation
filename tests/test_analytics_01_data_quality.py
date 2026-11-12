"""Focused Unit Tests for Module 1: src/analytics/data_quality.py."""
import pandas as pd
import pytest

from src.analytics.data_quality import (
    IndianPropertyDataQualityAuditor,
    classify_field_presence,
    normalize_area_to_sqft,
)


def test_indian_unit_conversions_and_presence_semantics():
    assert normalize_area_to_sqft(100.0, "sqm") == pytest.approx(1076.39, abs=0.5)
    assert normalize_area_to_sqft(200.0, "gaj") == 1800.0
    assert normalize_area_to_sqft(5.0, "decimal") == pytest.approx(2178.0, abs=0.1)

    # Absent amenity vs missing/unknown
    assert classify_field_presence(0, is_amenity=True) == "ABSENT_AMENITY"
    assert classify_field_presence("None", is_amenity=True) == "ABSENT_AMENITY"
    assert classify_field_presence(None, is_amenity=True) == "MISSING_UNKNOWN"
    assert classify_field_presence("", is_amenity=True) == "MISSING_UNKNOWN"


def test_rera_impossible_measurements_and_location_consistency():
    auditor = IndianPropertyDataQualityAuditor()

    # Valid Bhubaneswar apartment
    ok = auditor.validate_single_record({
        "property_type": "apartment",
        "latitude": 20.3036, "longitude": 85.8485, "country_code": "IN",
        "sale_price": 7500000, "builtup_area_sqft": 1200, "carpet_area_sqft": 950,
        "uds_sqft": 340, "construction_age_years": 10, "remodel_age_years": 2,
        "parking_slots": 0,
    })
    assert ok["is_valid"] is True
    assert ok["semantic_field_status"]["parking"] == "ABSENT_AMENITY"

    # Impossible: Carpet area exceeds Built-up area & Remodel age exceeds Construction age & Outside India bounds
    bad = auditor.validate_single_record({
        "property_type": "apartment",
        "latitude": 51.5074, "longitude": -0.1278, "country_code": "IN",
        "sale_price": -100, "builtup_area_sqft": 1000, "carpet_area_sqft": 1250,
        "construction_age_years": 5, "remodel_age_years": 12,
    })
    assert bad["is_valid"] is False
    joined = " | ".join(bad["issues"])
    assert "carpet_area_sqft" in joined
    assert "remodel_age_years" in joined
    assert "outside India bounding box" in joined
    assert "non-positive price" in joined


def test_iqr_mad_outliers_and_dataset_audit():
    auditor = IndianPropertyDataQualityAuditor()

    # Price/sqft array with an extreme anomaly (45000 when median ~6000)
    vals = [5800.0, 6000.0, 6100.0, 6200.0, 5950.0, 6300.0, 6050.0, 45000.0]
    out = auditor.detect_outliers_iqr_and_mad(vals)
    assert out["status"] == "COMPUTED"
    assert out["iqr_flags"][-1] is True
    assert out["mad_flags"][-1] is True
    assert out["flagged_count"] == 1
    assert len(out["combined_outlier_flags"]) == 8  # Non-destructive: nothing deleted

    df = pd.DataFrame([
        {"property_type": "apartment", "latitude": 20.3036, "longitude": 85.8485, "sale_price": 7200000, "builtup_area_sqft": 1200, "transaction_date": "2025-05-01"},
        {"property_type": "apartment", "latitude": 20.3036, "longitude": 85.8485, "sale_price": 7200000, "builtup_area_sqft": 1200, "transaction_date": "2025-05-01"},  # Duplicate
        {"property_type": "apartment", "latitude": 20.3100, "longitude": 85.8500, "sale_price": 6500000, "builtup_area_sqft": 1100, "transaction_date": "2025-05-10"},
        {"property_type": "apartment", "latitude": 20.3200, "longitude": 85.8550, "sale_price": 6800000, "builtup_area_sqft": 1150, "transaction_date": "2025-05-15"},
        {"property_type": "apartment", "latitude": 20.3300, "longitude": 85.8600, "sale_price": 50000000, "builtup_area_sqft": 1000, "transaction_date": "2025-05-20"},  # Extreme luxury/outlier
    ])
    summary = auditor.audit_dataset(df)
    assert summary["total_rows"] == 5
    assert summary["valid_rows"] == 5
    assert summary["duplicate_rows_detected"] == 1
    assert summary["price_per_sqft_outlier_audit"]["flagged_count"] == 1
