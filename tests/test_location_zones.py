"""Tests for backend-driven Green (medical) & Yellow (transit/edu/work) priority zones."""

from fastapi.testclient import TestClient

from src.api.app import app
from src.services.location_zones import LocationZoneEngine


client = TestClient(app)


def _sample_valuation_payload(latitude: float, longitude: float) -> dict:
    return {
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": 25.0,
            "country_code": "IN",
        },
        "property_details": {
            "asset_type": "residential",
            "structure_type": "standalone_house",
            "plot_area_sqft": 2400.0,
            "construction_grade": "standard",
            "area_value": 2000.0,
            "area_unit": "sqft",
            "bedrooms": 3,
            "bathrooms": 3,
            "property_age_years": 2.0,
            "floor_number": 0,
            "total_floors": 2,
            "locality_tier": "suburban",
            "furnishing": "semi_furnished",
            "parking_slots": "1_covered",
            "approval_status": "approved_freehold",
            "maintenance_state": "well_maintained",
        },
    }


def test_zone_engine_patia_kims_both_green_and_yellow():
    result = LocationZoneEngine.evaluate_zones_for_point(20.3533, 85.8266)

    assert result["in_green_zone"] is True
    assert result["in_yellow_zone"] is True
    assert result["in_any_zone"] is True
    assert result["zone_classification"] == "GREEN_AND_YELLOW_PRIORITY_ZONES"
    assert result["green_zone_land_uplift_pct"] > 0
    assert result["yellow_zone_land_uplift_pct"] > 0
    assert result["total_zone_land_uplift_pct"] == (
        result["green_zone_land_uplift_pct"] + result["yellow_zone_land_uplift_pct"]
    )
    assert result["land_rate_multiplier"] > 1.0
    assert len(result["green_zones"]) > 0
    assert len(result["yellow_zones"]) > 0
    assert all(z["hex_color"] == "#22c55e" for z in result["green_zones"])
    assert all(z["hex_color"] == "#eab308" for z in result["yellow_zones"])


def test_zone_engine_green_only_yellow_only_and_outside_overrides():
    far_all = {
        "distance_hospital_km": 18.0,
        "distance_rail_km": 18.0,
        "distance_metro_km": 18.0,
        "distance_bus_stand_km": 18.0,
        "distance_school_km": 18.0,
        "distance_it_hub_km": 18.0,
    }
    outside = LocationZoneEngine.evaluate_zones_for_point(20.15, 85.98, distance_hints=far_all)
    assert outside["in_any_zone"] is False
    assert outside["in_green_zone"] is False
    assert outside["in_yellow_zone"] is False
    assert outside["zone_classification"] == "OUTSIDE_PRIORITY_ZONES"
    assert outside["green_zone_land_uplift_pct"] == 0.0
    assert outside["yellow_zone_land_uplift_pct"] == 0.0
    assert outside["total_zone_land_uplift_pct"] == 0.0
    assert outside["land_rate_multiplier"] == 1.0

    green_only = LocationZoneEngine.evaluate_zones_for_point(
        20.15,
        85.98,
        distance_hints={**far_all, "distance_hospital_km": 1.0},
    )
    assert green_only["in_green_zone"] is True
    assert green_only["in_yellow_zone"] is False
    assert green_only["in_any_zone"] is True
    assert green_only["green_zone_land_uplift_pct"] > 0
    assert green_only["yellow_zone_land_uplift_pct"] == 0.0

    yellow_only = LocationZoneEngine.evaluate_zones_for_point(
        20.15,
        85.98,
        distance_hints={
            **far_all,
            "distance_rail_km": 1.2,
            "distance_metro_km": 1.4,
            "distance_bus_stand_km": 1.0,
            "distance_school_km": 1.1,
            "distance_it_hub_km": 2.5,
        },
    )
    assert yellow_only["in_green_zone"] is False
    assert yellow_only["in_yellow_zone"] is True
    assert yellow_only["in_any_zone"] is True
    assert yellow_only["green_zone_land_uplift_pct"] == 0.0
    assert yellow_only["yellow_zone_land_uplift_pct"] > 0


def test_zones_and_location_api_return_green_only_and_hide_yellow_from_user():
    resp_zones = client.get(
        "/api/property/zones",
        params={"latitude": 20.3533, "longitude": 85.8266, "country_code": "IN"},
    )
    assert resp_zones.status_code == 200
    data_zones = resp_zones.json()
    assert data_zones["base_land_rate_sqft"] > 0
    za = data_zones["zone_analysis"]
    assert za["in_any_zone"] is True
    assert za["in_green_zone"] is True
    assert all(z["hex_color"] == "#22c55e" for z in za["green_zones"])
    # Yellow zone calculation remains strictly backend-only and is NEVER exposed publicly
    for hidden_key in ("yellow_zones", "in_yellow_zone", "yellow_zone_land_uplift_pct", "active_yellow_hubs_count", "nearest_yellow_hub"):
        assert hidden_key not in za
    assert "yellow" not in resp_zones.text.lower()
    # Yet total backend uplift reflects BOTH medical + backend transit/edu/work analysis
    assert za["total_zone_land_uplift_pct"] > za["green_zone_land_uplift_pct"]

    resp_loc = client.post(
        "/api/property/location",
        json={"latitude": 20.3533, "longitude": 85.8266, "country_code": "IN"},
    )
    assert resp_loc.status_code == 200
    loc_data = resp_loc.json()
    assert "zone_analysis" in loc_data
    assert loc_data["zone_analysis"]["in_green_zone"] is True
    assert "yellow" not in resp_loc.text.lower()


def test_backend_valuation_uplifts_land_cost_inside_zones_vs_outside():
    in_zone_resp = client.post(
        "/api/property/valuation",
        json=_sample_valuation_payload(20.3533, 85.8266),
    )
    out_zone_resp = client.post(
        "/api/property/valuation",
        json=_sample_valuation_payload(20.15, 85.98),
    )
    assert in_zone_resp.status_code == 200
    assert out_zone_resp.status_code == 200

    in_data = in_zone_resp.json()
    out_data = out_zone_resp.json()

    assert in_data["zone_analysis"]["in_any_zone"] is True
    assert in_data["zone_analysis"]["total_zone_land_uplift_pct"] > 0
    assert "yellow" not in in_zone_resp.text.lower()

    assert out_data["zone_analysis"]["in_any_zone"] is False
    assert out_data["zone_analysis"]["zone_classification"] == "OUTSIDE_PRIORITY_ZONES"
    assert out_data["zone_analysis"]["total_zone_land_uplift_pct"] == 0.0

    in_brk = in_data["land_and_house_breakdown"]
    out_brk = out_data["land_and_house_breakdown"]
    assert in_brk["zone_land_uplift_pct"] > 0
    assert out_brk["zone_land_uplift_pct"] == 0.0
    assert in_brk["right_now_land_rate_sqft"] > out_brk["right_now_land_rate_sqft"]
    assert in_brk["stage1_land_price"] > out_brk["stage1_land_price"]


def test_frontend_dashboard_wires_backend_zone_overlays():
    from pathlib import Path
    resp = client.get("/")
    assert resp.status_code == 200
    dist_assets = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "assets"
    app_js = [p for p in dist_assets.glob("*.js") if "-vendor-" not in p.name]
    app_bundle = resp.text + "".join(p.read_text(encoding="utf-8", errors="ignore") for p in app_js)
    for marker in (
        "map-zone-status-bar",
        "/api/property/zones",
        "/api/platform/config",
        "/api/property/valuation",
    ):
        assert marker in app_bundle
    assert "yellow" not in app_bundle.lower()


def test_pan_india_and_global_zone_coverage():
    for lat, lon, expected_hospital_sub in [
        (19.1254, 72.9157, "Hiranandani"),
        (12.9698, 77.7499, "Manipal"),
        (51.5074, -0.1278, "St Thomas"),
    ]:
        res = client.get("/api/property/zones", params={"latitude": lat, "longitude": lon})
        assert res.status_code == 200
        za = res.json()["zone_analysis"]
        assert za["zone_discovery_mode"] == "catalog_geo_anchors"
        assert za["in_any_zone"] is True
        assert za["total_zone_land_uplift_pct"] > 0
        assert any(expected_hospital_sub in g["name"] for g in za["green_zones"])

    remote = client.get("/api/property/zones", params={"latitude": 20.80, "longitude": 84.30})
    assert remote.status_code == 200
    r_za = remote.json()["zone_analysis"]
    assert r_za["in_any_zone"] is False
    assert r_za["zone_classification"] == "OUTSIDE_PRIORITY_ZONES"
    assert r_za["total_zone_land_uplift_pct"] == 0.0


def test_backend_platform_config_hydrates_all_lists_and_removes_static_html_lists():
    cfg_resp = client.get("/api/platform/config")
    assert cfg_resp.status_code == 200
    cfg = cfg_resp.json()
    assert len(cfg["location_presets"]) >= 20
    assert len(cfg["countries"]) >= 4
    assert "structure_type" in cfg["selectors"]
    assert "flood_risk" in cfg["selectors"]
    assert "odisha" not in [r["id"] for r in cfg["region_filters"]]
    assert all(
        "bhubaneswar" not in p["label"].lower() and "odisha" not in p["label"].lower() and p["region"] != "odisha"
        for p in cfg["location_presets"]
    )
    assert "bhubaneswar" not in cfg["default_location"]["label"].lower()

    html = client.get("/").text
    assert "<option " not in html
    assert 'onclick="setCoords(' not in html
