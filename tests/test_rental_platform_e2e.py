"""
Comprehensive Integration Tests for Milestones 2-6:
- Milestone 2: SQLAlchemy Rental DB & Spatial Comparable Engine
- Milestone 3: RMDC Normalization, Deduplication, Outlier/Stale Detection & Source Compliance
- Milestone 4: Three-Way Valuation Reconciliation (Sales vs Cost vs Income)
- Milestone 5: All /api/rental/* FastAPI Endpoints
- Milestone 6: Frontend Dashboard Integration Checks
"""
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.services.rental_comparables import RentalComparableEngine
from src.services.rental_data_collector import RentalDataCollectorService
from src.services.valuation_reconciliation import ThreeWayValuationReconciler


client = TestClient(app)


def test_rmdc_normalization_dedup_outlier_and_stale():
    collector = RentalDataCollectorService()

    # 1. Normalization (100 sqm -> 1076.4 sqft)
    norm = collector.validate_and_normalize_record({
        "latitude": 20.3040,
        "longitude": 85.8490,
        "monthly_rent_inr": 26000.0,
        "area_value": 100.0,
        "area_unit": "sqm",
        "property_type": "Apartment",
        "furnishing": "Fully Furnished",
        "data_category": "Verified_Achieved",
        "state": "Odisha",
        "city": "Bhubaneswar",
        "locality": "VSS Nagar Test",
    })
    assert norm["builtup_area_sqft"] == pytest.approx(1076.4, abs=1.0)
    assert norm["furnishing"] == "fully_furnished"
    assert norm["data_category"] == "Verified_Achieved"
    assert norm["is_stale"] is False

    # 2. Stale listing detection (> 60 days)
    stale_date = (date.today() - timedelta(days=90)).isoformat()
    stale_norm = collector.validate_and_normalize_record({
        "latitude": 20.3041,
        "longitude": 85.8491,
        "monthly_rent_inr": 25000.0,
        "area_value": 1050.0,
        "observation_date": stale_date,
    })
    assert stale_norm["is_stale"] is True

    # 3. Duplicate ingestion across sources flags duplicate without silent deletion
    unique_lat, unique_lon = 20.4123, 85.9123
    batch = [
        {
            "latitude": unique_lat,
            "longitude": unique_lon,
            "monthly_rent_inr": 24000.0,
            "area_value": 1100.0,
            "bhk": 2.0,
            "property_type": "apartment",
            "data_category": "Verified_Achieved",
            "city": "Cuttack_Test_Zone",
            "locality": "CDA Test",
        },
        {
            "latitude": unique_lat + 0.0001,  # ~11m away -> within 50m duplicate threshold
            "longitude": unique_lon + 0.0001,
            "monthly_rent_inr": 24200.0,
            "area_value": 1110.0,
            "bhk": 2.0,
            "property_type": "apartment",
            "data_category": "Advertised_Asking",
            "city": "Cuttack_Test_Zone",
            "locality": "CDA Test",
        },
    ]
    res = collector.ingest_listing_batch(batch, source_name="user_submitted_lease", location_query="CDA Test")
    assert res["records_accepted"] == 2
    assert res["duplicates_flagged"] >= 1


def test_comparable_segregation_and_insufficient_data():
    engine = RentalComparableEngine()

    # Empty ocean coordinate should cleanly return INSUFFICIENT_COMPARABLES
    empty = engine.find_comparables(latitude=10.0, longitude=65.0, radius_km=2.0, property_type="apartment")
    assert empty["total_matched"] == 0
    assert empty["data_confidence_label"] == "INSUFFICIENT_COMPARABLES"
    assert empty["segregated_statistics"]["verified_achieved_stats"]["count"] == 0

    # Bhubaneswar VSS Nagar / Patia seeded benchmarks must exist and separate categories cleanly
    bbsr = engine.find_comparables(latitude=20.3036, longitude=85.8485, radius_km=5.0, property_type="apartment")
    assert bbsr["total_matched"] >= 3
    assert bbsr["segregated_statistics"]["historical_benchmark_stats"]["count"] >= 3
    assert bbsr["segregated_statistics"]["historical_benchmark_stats"]["median_monthly_rent"] > 10000


def test_three_way_reconciliation_property_type_logic():
    reconciler = ThreeWayValuationReconciler()

    # Commercial office must give majority weight (>=50%) to Income Approach when rent evidence is supplied
    com_rec = reconciler.evaluate_income_and_reconcile(
        latitude=20.3036,
        longitude=85.8485,
        asset_type="commercial",
        structure_type="office",
        commercial_type="office",
        valuation_area_sqft=2000.0,
        currency="INR",
        sales_comparison_value=18000000.0,
        cost_approach_value=17000000.0,
        m10_prediction={},
        property_input={"monthly_rent_inr": 135000.0},
    )
    weights_com = com_rec["three_way_reconciliation"]["approaches"]
    assert weights_com["approach_c_income_capitalization"]["weight_pct"] > weights_com["approach_a_sales_comparison"]["weight_pct"]

    # Vacant land without lease must assign 0% weight to Income Approach
    land_rec = reconciler.evaluate_income_and_reconcile(
        latitude=20.3036,
        longitude=85.8485,
        asset_type="land",
        structure_type="land",
        commercial_type="",
        valuation_area_sqft=1500.0,
        currency="INR",
        sales_comparison_value=12000000.0,
        cost_approach_value=11500000.0,
        m10_prediction={},
        property_input={},
    )
    assert land_rec["three_way_reconciliation"]["approaches"]["approach_c_income_capitalization"]["weight_pct"] == 0.0
    assert land_rec["income_valuation"]["status"] == "NOT_APPLICABLE_VACANT_LAND"


def test_api_rental_endpoints_and_ui_integration():
    # 1. Gross Yield
    r1 = client.post("/api/rental/gross-yield", json={"monthly_rent": 22000, "property_value": 7500000})
    assert r1.status_code == 200
    assert r1.json()["gross_rental_yield_pct"] == pytest.approx(3.52, abs=1e-2)

    # 2. NOI
    r2 = client.post("/api/rental/noi", json={"monthly_rent": 100000, "vacancy_rate_pct": 5.0, "collection_loss_pct": 0.0, "maintenance_annual": 180000})
    assert r2.status_code == 200
    assert r2.json()["noi_annual"] == 960000.0

    # 3. Cap Rate & Direct Cap Error Handling on unrealistic Cap Rate
    r3_ok = client.post("/api/rental/cap-rate", json={"noi_annual": 960000, "cap_rate_pct": 8.0})
    assert r3_ok.status_code == 200
    assert r3_ok.json()["direct_capitalization_value"] == 12000000.0

    r3_bad = client.post("/api/rental/cap-rate", json={"noi_annual": 960000, "cap_rate_pct": 65.0})
    assert r3_bad.status_code == 422

    # 4. GRM
    r4 = client.post("/api/rental/grm", json={"monthly_rent": 25000, "property_value": 7500000})
    assert r4.status_code == 200
    assert r4.json()["derived_grm"] == 25.0

    # 5. Full Rental Valuation Estimate
    r5 = client.post("/api/rental/valuation", json={"latitude": 20.3036, "longitude": 85.8485, "property_type": "apartment", "area_sqft": 1050})
    assert r5.status_code == 200
    assert r5.json()["income_valuation"]["achievable_monthly_rent"] > 0

    # 6. Search, Location Stats, Median Rent, History, Forecast, Sensitivity, Source Health
    assert client.get("/api/rental/comparables?latitude=20.3036&longitude=85.8485&radius_km=5").status_code == 200
    assert client.get("/api/rental/location-statistics?latitude=20.3036&longitude=85.8485").status_code == 200
    assert client.get("/api/rental/median-rent?latitude=20.3036&longitude=85.8485").status_code == 200
    assert client.get("/api/rental/yield-history?city=Bhubaneswar").status_code == 200
    assert client.post("/api/rental/forecast", json={"current_monthly_rent": 25000, "property_type": "apartment"}).status_code == 200
    assert client.post("/api/rental/sensitivity", json={"base_monthly_rent": 25000, "base_cap_rate_pct": 3.8}).status_code == 200

    # 7. Compliance check on restricted portals
    sh = client.get("/api/rental/source-health").json()["sources"]
    restricted = [s for s in sh if s["source_name"] == "99acres"][0]
    assert restricted["api_available"] is False
    assert restricted["redistribution_permitted"] is False

    # 8. Main property valuation integrates Three-Way Reconciliation & Rental Yield
    r_main = client.post("/api/property/valuation", json={
        "location": {"latitude": 20.3036, "longitude": 85.8485, "country_code": "IN"},
        "property_details": {"asset_type": "residential", "structure_type": "standalone_house", "area_value": 1800, "plot_area_sqft": 1500}
    })
    assert r_main.status_code == 200
    body = r_main.json()
    assert "income_approach_and_reconciliation" in body
    assert "three_way_reconciliation" in body["income_approach_and_reconciliation"]

    # 9. Frontend Dashboard renders Income Sensitivity Lab & 3-Way Reconciliation
    from pathlib import Path
    dist_assets = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "assets"
    bundle = client.get("/").text + "".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist_assets.glob("*.js"))
    assert "sens-slider-rent" in bundle
    assert "Three-Way Reconciliation" in bundle
