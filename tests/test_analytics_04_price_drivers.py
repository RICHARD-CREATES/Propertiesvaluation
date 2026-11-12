"""Focused tests for Module 4: PriceDriverAnalyzer."""
from src.analytics.price_driver_analysis import PriceDriverAnalyzer


def test_price_drivers_correlations_size_bands_and_spatial_permutation_importance():
    # 5 distinct spatial clusters (>10 km apart) so train/val spatial split succeeds cleanly
    clusters = [
        (20.296, 85.824, "Bhubaneswar"),
        (20.462, 85.882, "Cuttack"),
        (19.813, 85.831, "Puri"),
        (22.260, 84.853, "Rourkela"),
        (21.466, 83.981, "Sambalpur"),
    ]
    records = []
    for idx, (lat, lon, city) in enumerate(clusters):
        for offset, area in enumerate([750, 1050, 1550, 2200]):
            # Monotonic positive area effect + mild age depreciation
            age = 1 + offset * 4
            remodel = 1 if offset == 3 else age
            pps = 6800 - offset * 350  # mild diminishing price/sqft with larger SizeBand
            price = area * pps
            records.append(
                {
                    "transaction_id": f"TX_{idx}_{offset}",
                    "property_type": "apartment",
                    "city": city,
                    "locality": f"{city}_Core",
                    "builtup_area_sqft": area,
                    "bedrooms": 2 if area < 1300 else 3,
                    "bathrooms": 2,
                    "property_age_years": age,
                    "remodel_age_years": remodel,
                    "sale_price": price,
                    "latitude": lat + offset * 0.001,
                    "longitude": lon + offset * 0.001,
                }
            )

    analyzer = PriceDriverAnalyzer()
    res = analyzer.analyze(records, cluster_radius_km=3.0, seed=42)

    assert res["valid_analyzed_records"] == 20
    assert "not causal" in res["causal_disclaimer"].lower()
    assert res["correlations"]["area_sqft"]["vs_total_price_inr"]["pearson_r"] > 0.9

    apt_bands = res["size_band_curves_by_property_type"]["apartment"]
    band_names = [b["size_band"] for b in apt_bands]
    assert "small_lt_800" in band_names
    assert "large_1800_3000" in band_names
    # Diminishing pps verified across bands
    assert apt_bands[0]["median_pps_inr"] > apt_bands[-1]["median_pps_inr"]

    assert "older_building_recently_remodeled_0_5y" in res["age_vs_remodel_pps_inr"]

    perm = res["spatial_permutation_importance"]
    assert perm["status"] == "OK_ZERO_SPATIAL_LEAKAGE"
    assert perm["leakage_audit"]["leakage_detected"] is False
    assert perm["importances"][0]["feature"] == "area_sqft"


def test_single_spatial_cluster_refuses_leaky_permutation_importance():
    # All 10 properties within 200 meters of each other -> single spatial cluster
    records = [
        {
            "property_type": "apartment",
            "builtup_area_sqft": 1000 + i * 100,
            "sale_price": (1000 + i * 100) * 5500,
            "latitude": 20.300 + i * 0.0001,
            "longitude": 85.820 + i * 0.0001,
        }
        for i in range(10)
    ]
    res = PriceDriverAnalyzer().analyze(records, cluster_radius_km=3.0)
    assert res["spatial_permutation_importance"]["status"] != "OK_ZERO_SPATIAL_LEAKAGE"
    assert res["spatial_permutation_importance"]["importances"] == []
