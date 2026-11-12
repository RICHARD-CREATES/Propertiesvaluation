"""Focused tests for Module 2: PropertyEDAAnalyzer."""
from src.analytics.property_eda import PropertyEDAAnalyzer


def test_property_eda_quantiles_cohorts_and_outlier_retention():
    records = [
        # Valid apartments across ages and units
        {"property_type": "apartment", "builtup_area_sqft": 1000, "sale_price": 5000000, "property_age_years": 2, "remodel_age_years": 2, "latitude": 20.30, "longitude": 85.82},
        {"property_type": "flat", "area_sqft": 1200, "price_inr": 6600000, "property_age_years": 8, "remodel_age_years": 8, "latitude": 20.31, "longitude": 85.83},
        {"property_type": "apartment", "area_value": 100, "area_unit": "sqm", "sale_price": 64.5834, "currency": "LAKH", "property_age_years": 15, "remodel_age_years": 2, "latitude": 20.32, "longitude": 85.84},
        {"property_type": "house", "builtup_area_sqft": 2000, "sale_price": 12000000, "property_age_years": 25, "latitude": 20.29, "longitude": 85.81},
        # High-price luxury outlier (must be retained in EDA distributions, flagged in quality_summary)
        {"property_type": "apartment", "builtup_area_sqft": 1500, "sale_price": 45000000, "property_age_years": 1, "latitude": 20.30, "longitude": 85.82},
        # Physically invalid record (carpet > builtup -> excluded from valid EDA)
        {"property_type": "apartment", "builtup_area_sqft": 1000, "carpet_area_sqft": 1400, "sale_price": 5000000, "latitude": 20.30, "longitude": 85.82},
    ]

    analyzer = PropertyEDAAnalyzer()
    result = analyzer.analyze(records)

    assert result["total_records"] == 6
    assert result["valid_analyzed_records"] == 5
    assert result["excluded_invalid_records"] == 1
    assert result["outliers_retained_in_eda"] is True
    assert result["quality_summary"]["outlier_count_iqr_or_mad"] >= 1

    overall_pps = result["overall_distributions"]["price_per_sqft_inr"]
    assert overall_pps["count"] == 5
    assert overall_pps["max"] == 30000.0
    assert overall_pps["skewness"] > 0.5  # positive skew from luxury unit

    assert "apartment" in result["by_property_type"]
    assert "standalone_house" in result["by_property_type"]
    assert result["by_property_type"]["apartment"]["count"] == 4
    assert "recently_renovated_0_5y" in result["by_renovation_cohort"]
    assert "new_0_3y" in result["by_age_cohort"]
    assert "old_20y_plus" in result["by_age_cohort"]


def test_property_eda_empty_and_all_invalid():
    analyzer = PropertyEDAAnalyzer()
    empty_res = analyzer.analyze([])
    assert empty_res["valid_analyzed_records"] == 0
    assert empty_res["overall_distributions"]["price_inr"]["count"] == 0
    assert empty_res["overall_distributions"]["price_inr"]["median"] is None
