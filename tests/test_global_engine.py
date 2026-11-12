"""
Comprehensive Test Suite for the Global AI Property Valuation System.
Verifies all 10 Specialist Models, Location Intelligence Service,
Missing Feature Detector, Global Valuation Engine, and FastAPI endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from src.core.units import convert_area_to_sqm, convert_sqm_to_local, format_currency
from src.services.location_intelligence import LocationIntelligenceService
from src.services.missing_detection import MissingFeatureDetectionService
from src.services.specialist_models import (
    TransactionIntelligenceAI,
    GovernmentCadastralAI,
    SatelliteBuildingIntelligenceAI,
    GeospatialConnectivityAI,
    TrafficMobilityAI,
    PopulationDemographicAI,
    RealEstateMarketAI,
    PhysicalPropertyAI,
    FutureDevelopmentAI,
    RentalInvestmentAI,
)
from src.services.valuation_engine import GlobalPropertyValuationEngine
from src.api.app import app


def test_unit_conversions():
    # 1000 sq ft -> ~92.9 sqm
    sqm = convert_area_to_sqm(1000, "sqft")
    assert 92.0 <= sqm <= 94.0

    # 1 acre -> ~4046.8 sqm
    sqm_acre = convert_area_to_sqm(1, "acre")
    assert 4040.0 <= sqm_acre <= 4050.0

    # Currency formatters
    inr_fmt = format_currency(25000000, "INR")
    assert "2.50 Cr" in inr_fmt or "Rs." in inr_fmt

    usd_fmt = format_currency(1200000, "USD")
    assert "$1.20M" in usd_fmt


def test_location_intelligence_harvesting():
    lis = LocationIntelligenceService()
    # Test valid coords (Powai / IIT Bombay)
    res = lis.harvest(19.1254, 72.9157, accuracy_m=10.0, country_code="IN")
    assert res["metadata"]["country_code"] == "IN"
    assert "intelligence" in res
    intel = res["intelligence"]

    # Verify all layers present
    for layer in ["geocoding", "cadastre", "satellite", "connectivity", "traffic", "demographics", "market", "future_development", "rental", "transactions"]:
        assert layer in intel

    # Verify provenance metadata on attributes
    sample_attr = intel["connectivity"]["distance_metro_km"]
    assert "value" in sample_attr
    assert "source" in sample_attr
    assert "observation_date" in sample_attr
    assert "confidence" in sample_attr
    assert "is_observed" in sample_attr


def test_ten_specialist_models():
    base_price_sqm = 200000.0  # INR per sqm (~Rs. 18,500/sqft)
    dummy_features = {
        "comparable_sales_count_500m_12m": 14,
        "comparable_median_price_sqm_500m_12m": 210000.0,
        "fsi_far": 2.5,
        "zoning_code": "RESIDENTIAL",
        "title_status_code": "CLEAN",
        "building_footprint_area_sqm": 300.0,
        "vegetation_index_250m": 0.32,
        "distance_metro_km": 0.8,
        "distance_nh_km": 1.5,
        "vehicles_per_minute_peak": 55.0,
        "noise_db_proxy": 69.0,
        "population_density_1km": 15000.0,
        "local_price_growth_1y": 0.08,
        "inventory_months": 11.0,
        "property_age_years": 4.0,
        "construction_quality_code": "GRADE_A",
        "announced_infrastructure_distance_km": 1.5,
        "project_status_code": "UNDER_CONSTRUCTION",
        "gross_rental_yield": 0.039,
    }

    m01 = TransactionIntelligenceAI().predict(dummy_features)
    assert m01["status"] == "active"
    assert m01["predicted_price_sqm"] > 0

    m02 = GovernmentCadastralAI().predict(dummy_features, base_price_sqm)
    assert m02["status"] == "active"

    m03 = SatelliteBuildingIntelligenceAI().predict(dummy_features, base_price_sqm)
    assert m03["status"] == "active"

    m04 = GeospatialConnectivityAI().predict(dummy_features, base_price_sqm)
    assert m04["status"] == "active"

    # Traffic merit test: high traffic yields positive demand uplift (> base_price_sqm) for BOTH residential and commercial
    m05_res = TrafficMobilityAI().predict(dummy_features, base_price_sqm, asset_type="residential")
    m05_com = TrafficMobilityAI().predict(dummy_features, base_price_sqm, asset_type="commercial")
    m05_low = TrafficMobilityAI().predict({**dummy_features, "vehicles_per_minute_peak": 15.0}, base_price_sqm, asset_type="residential")
    assert m05_res["predicted_price_sqm"] > base_price_sqm
    assert m05_res["predicted_price_sqm"] > m05_low["predicted_price_sqm"]
    assert m05_com["predicted_price_sqm"] > m05_res["predicted_price_sqm"]

    m06 = PopulationDemographicAI().predict(dummy_features, base_price_sqm)
    assert m06["status"] == "active"

    m07 = RealEstateMarketAI().predict(dummy_features, base_price_sqm)
    assert m07["status"] == "active"

    m08 = PhysicalPropertyAI().predict(dummy_features, base_price_sqm)
    assert m08["status"] == "active"

    m09 = FutureDevelopmentAI().predict(dummy_features, base_price_sqm)
    assert m09["status"] == "active"

    m10 = RentalInvestmentAI().predict(dummy_features, base_price_sqm)
    assert m10["status"] == "active"
    assert m10["gross_rental_yield_pct"] > 0


def test_missing_feature_detection():
    service = MissingFeatureDetectionService()

    # Missing essential built area for residential should fail validation
    res = service.audit_and_impute({}, asset_type="residential")
    assert res["is_valid_for_valuation"] is False
    assert "built_area_sqm" in res["missing_essential_user_fields"]

    # When area is provided, validation passes and non-essential missing are imputed
    res2 = service.audit_and_impute({"built_area_sqm": 95.0}, asset_type="residential")
    assert res2["is_valid_for_valuation"] is True
    assert res2["imputed_features"]["property_age_years"] == 8.0  # Documented default


def test_global_valuation_engine_e2e():
    engine = GlobalPropertyValuationEngine()
    lis = LocationIntelligenceService()

    intel = lis.harvest(19.1254, 72.9157, country_code="IN")
    prop_input = {
        "asset_type": "residential",
        "built_area_sqm": 100.0,
        "bedrooms": 2.0,
        "bathrooms": 2.0,
        "property_age_years": 3.0,
        "construction_quality_code": "GRADE_A",
    }

    result = engine.evaluate_property(prop_input, intel)
    assert result["status"] == "success"
    assert "fair_market_value" in result["valuation"]
    assert result["valuation"]["fair_market_value"] > 0
    assert result["valuation"]["valuation_interval"]["low"] < result["valuation"]["fair_market_value"]
    assert result["valuation"]["valuation_interval"]["high"] > result["valuation"]["fair_market_value"]

    # Check 10 models status list
    models_contrib = result["explainability"]["specialist_models_contributed"]
    assert len(models_contrib) == 10


def test_fastapi_endpoints():
    client = TestClient(app)

    # Health
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["specialist_models_registered"] == 10

    # Location endpoint
    r_loc = client.post("/api/property/location", json={"latitude": 19.1254, "longitude": 72.9157, "country_code": "IN"})
    assert r_loc.status_code == 200
    assert r_loc.json()["status"] == "valid"

    # Full valuation endpoint
    val_payload = {
        "location": {"latitude": 19.1254, "longitude": 72.9157, "country_code": "IN"},
        "property_details": {
            "asset_type": "residential",
            "area_value": 1100.0,
            "area_unit": "sqft",
            "bedrooms": 2.0,
            "bathrooms": 2.0,
            "property_age_years": 4.0,
            "floor_number": 8,
            "total_floors": 22,
        }
    }
    r_val = client.post("/api/property/valuation", json=val_payload)
    assert r_val.status_code == 200
    val_data = r_val.json()
    assert val_data["status"] == "success"
    val_id = val_data["valuation_id"]

    # Retrieve valuation by ID
    r_get = client.get(f"/api/property/valuation/{val_id}")
    assert r_get.status_code == 200

    # Explanation endpoint
    r_exp = client.get(f"/api/property/explanation/{val_id}")
    assert r_exp.status_code == 200
    assert "top_positive_factors" in r_exp.json()["explainability"]


def test_radial_proximity_distance_decay_and_corridor_merit():
    base_price_sqm = 60000.0
    m04 = GeospatialConnectivityAI()

    # Nearest core (<= 1 km) gets highest maximum uplift
    core = m04.predict({
        "distance_school_km": 0.6,
        "distance_hospital_km": 0.8,
        "distance_bus_stand_km": 0.7,
        "distance_metro_km": 0.7,
        "distance_rail_km": 0.9,
        "distance_airport_km": 1.2,
        "distance_it_hub_km": 1.0,
        "amenity_score": 8.0,
    }, base_price_sqm)

    # User scenario: school <= 5 km, bus stand <= 4 km, airport <= 5 km, IT hub ~ 15 km
    corridor_5_15 = m04.predict({
        "distance_school_km": 5.0,
        "distance_hospital_km": 4.0,
        "distance_bus_stand_km": 4.0,
        "distance_metro_km": 4.5,
        "distance_rail_km": 5.0,
        "distance_airport_km": 5.0,
        "distance_it_hub_km": 15.0,
        "amenity_score": 7.0,
    }, base_price_sqm)

    # Outer remote zone (> 26 km from all hubs)
    remote = m04.predict({
        "distance_school_km": 28.0,
        "distance_hospital_km": 28.0,
        "distance_bus_stand_km": 28.0,
        "distance_metro_km": 28.0,
        "distance_rail_km": 28.0,
        "distance_airport_km": 28.0,
        "distance_it_hub_km": 28.0,
        "amenity_score": 5.0,
    }, base_price_sqm)

    assert core["predicted_price_sqm"] > corridor_5_15["predicted_price_sqm"] > remote["predicted_price_sqm"]
    assert corridor_5_15["radial_proximity_uplift_pct"] > 5.0

    # End-to-end API valuation reflects monotonic radius ordering via overrides
    client = TestClient(app)
    r_near = client.post("/api/property/valuation", json={
        "location": {"latitude": 20.3533, "longitude": 85.8266, "country_code": "IN"},
        "property_details": {"asset_type": "residential", "structure_type": "apartment", "area_value": 1200},
        "overrides": {
            "distance_school_km": 0.7, "distance_hospital_km": 0.8,
            "distance_bus_stand_km": 0.6, "distance_rail_km": 0.9,
            "distance_airport_km": 1.5, "distance_it_hub_km": 1.2,
        },
    })
    r_mid = client.post("/api/property/valuation", json={
        "location": {"latitude": 20.3533, "longitude": 85.8266, "country_code": "IN"},
        "property_details": {"asset_type": "residential", "structure_type": "apartment", "area_value": 1200},
        "overrides": {
            "distance_school_km": 5.0, "distance_hospital_km": 4.0,
            "distance_bus_stand_km": 4.0, "distance_rail_km": 5.0,
            "distance_airport_km": 5.0, "distance_it_hub_km": 15.0,
        },
    })
    r_far = client.post("/api/property/valuation", json={
        "location": {"latitude": 20.3533, "longitude": 85.8266, "country_code": "IN"},
        "property_details": {"asset_type": "residential", "structure_type": "apartment", "area_value": 1200},
        "overrides": {
            "distance_school_km": 26.0, "distance_hospital_km": 26.0,
            "distance_bus_stand_km": 26.0, "distance_rail_km": 26.0,
            "distance_airport_km": 26.0, "distance_it_hub_km": 26.0,
        },
    })
    assert r_near.status_code == 200 and r_mid.status_code == 200 and r_far.status_code == 200
    v_near = r_near.json()["valuation"]["fair_market_value"]
    v_mid = r_mid.json()["valuation"]["fair_market_value"]
    v_far = r_far.json()["valuation"]["fair_market_value"]
    assert v_near > v_mid > v_far
