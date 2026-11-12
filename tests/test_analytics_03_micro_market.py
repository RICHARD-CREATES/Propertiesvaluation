"""Focused tests for Module 3: MicroMarketAnalyzer."""
from src.analytics.micro_market_analysis import MicroMarketAnalyzer


def test_micro_market_homogeneous_cohorts_and_sem_vs_prediction_dispersion():
    records = [
        # 5 Apartments in Patia, Bhubaneswar
        {"city": "Bhubaneswar", "locality": "Patia", "micro_market_tier": "Tier-1", "property_type": "apartment", "builtup_area_sqft": 1000, "sale_price": 5200000, "latitude": 20.353, "longitude": 85.826},
        {"city": "Bhubaneswar", "locality": "Patia", "micro_market_tier": "Tier-1", "property_type": "apartment", "builtup_area_sqft": 1100, "sale_price": 5940000, "latitude": 20.354, "longitude": 85.827},
        {"city": "Bhubaneswar", "locality": "Patia", "micro_market_tier": "Tier-1", "property_type": "apartment", "builtup_area_sqft": 1200, "sale_price": 6960000, "latitude": 20.355, "longitude": 85.828},
        {"city": "Bhubaneswar", "locality": "Patia", "micro_market_tier": "Tier-1", "property_type": "apartment", "builtup_area_sqft": 1300, "sale_price": 7800000, "latitude": 20.352, "longitude": 85.825},
        {"city": "Bhubaneswar", "locality": "Patia", "micro_market_tier": "Tier-1", "property_type": "apartment", "builtup_area_sqft": 1400, "sale_price": 8680000, "latitude": 20.356, "longitude": 85.829},
        # Land in Patia (must remain separate cohort!)
        {"city": "Bhubaneswar", "locality": "Patia", "micro_market_tier": "Tier-1", "property_type": "land", "plot_area_sqft": 2400, "sale_price": 7200000, "latitude": 20.353, "longitude": 85.826},
        # Distant location: Cuttack CDA
        {"city": "Cuttack", "locality": "CDA", "micro_market_tier": "Tier-2", "property_type": "apartment", "builtup_area_sqft": 1000, "sale_price": 4200000, "latitude": 20.462, "longitude": 85.835},
    ]

    analyzer = MicroMarketAnalyzer()
    res = analyzer.analyze(records, cluster_radius_km=3.0, min_reliable_samples=5)

    assert res["homogeneous_grouping_enforced"] is True
    assert res["valid_analyzed_records"] == 7

    # Patia Apartment vs Patia Land vs Cuttack Apartment = 3 distinct cohorts
    assert len(res["locality_cohorts"]) == 3

    patia_apts = [c for c in res["locality_cohorts"] if c["locality"] == "Patia" and c["property_type"] == "apartment"][0]
    patia_land = [c for c in res["locality_cohorts"] if c["locality"] == "Patia" and c["property_type"] == "residential_land"][0]

    assert patia_apts["count"] == 5
    assert patia_apts["reliability_status"] != "LOW_SAMPLE_SIZE"
    assert patia_land["count"] == 1
    assert patia_land["reliability_status"] == "LOW_SAMPLE_SIZE"

    # SEM strictly smaller than individual sample std; policy note explicitly attached
    sem = patia_apts["central_tendency_pps_inr"]["mean_standard_error_sem"]
    std = patia_apts["individual_property_dispersion_pps_inr"]["sample_std"]
    assert sem < std
    assert "never use as an individual property prediction interval" in patia_apts["central_tendency_pps_inr"]["sem_interpretation_note"].lower()

    # Spatial clusters separate Patia (~20.35) and Cuttack (~20.46, >12km apart)
    cluster_ids = {s["geo_cluster_id"] for s in res["spatial_clusters"]}
    assert len(cluster_ids) == 2
