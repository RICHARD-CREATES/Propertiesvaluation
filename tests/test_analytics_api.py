"""Integration tests for Read-Only /api/analytics/* FastAPI endpoints."""
from fastapi.testclient import TestClient

from src.api.app import app
from src.core.ground_truth_db import GroundTruthTransaction
from src.core.rental_db import SessionLocal

client = TestClient(app)


def test_analytics_endpoints_are_read_only_and_preserve_database():
    with SessionLocal() as db:
        count_before = db.query(GroundTruthTransaction).count()

    # 1. Verify read-only GET endpoints all succeed cleanly
    r_dq = client.get("/api/analytics/data-quality")
    assert r_dq.status_code == 200
    assert r_dq.json()["read_only"] is True
    assert r_dq.json()["synthetic_records_included"] is False

    r_eda = client.get("/api/analytics/eda")
    assert r_eda.status_code == 200
    assert r_eda.json()["read_only"] is True

    r_mm = client.get("/api/analytics/micro-markets")
    assert r_mm.status_code == 200
    assert r_mm.json()["read_only"] is True
    assert r_mm.json()["homogeneous_grouping_enforced"] is True

    r_drv = client.get("/api/analytics/drivers")
    assert r_drv.status_code == 200
    assert r_drv.json()["read_only"] is True

    r_exp_apt = client.get("/api/analytics/explain?property_type=apartment&builtup_area_sqft=1400&latitude=20.35&longitude=85.82")
    assert r_exp_apt.status_code == 200
    exp_apt = r_exp_apt.json()
    assert exp_apt["read_only"] is True
    assert exp_apt["status"] == "OK"
    assert exp_apt["additivity_verified"] is True

    r_exp_house = client.get("/api/analytics/explain?property_type=house&builtup_area_sqft=2000&plot_area_sqft=2400&latitude=20.30&longitude=85.82")
    assert r_exp_house.status_code == 200
    exp_house = r_exp_house.json()
    assert exp_house["read_only"] is True
    assert exp_house["status"] == "OK"
    assert exp_house["additivity_verified"] is True

    r_seas = client.get("/api/analytics/seasonality")
    assert r_seas.status_code == 200
    seas = r_seas.json()
    assert seas["read_only"] is True
    assert seas["status"] in ("OK", "INSUFFICIENT_SEASONALITY_HISTORY")

    # 2. Verify mutating HTTP methods are rejected (405 Method Not Allowed)
    assert client.post("/api/analytics/data-quality", json={}).status_code == 405
    assert client.delete("/api/analytics/eda").status_code == 405

    # 3. Verify GroundTruthTransaction table row count is completely unchanged
    with SessionLocal() as db:
        count_after = db.query(GroundTruthTransaction).count()
    assert count_after == count_before
