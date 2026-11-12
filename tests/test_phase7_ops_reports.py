"""Phase 7 & 8 Tests — Ops Hardening, Rate Limiting, SQLite Backups, Auth & Reports."""
import hashlib
import json
import logging
import os
import sqlite3

from fastapi.testclient import TestClient

from src.api.app import app
from src.core.ops_utils import (
    RedactingJsonFormatter,
    SlidingWindowRateLimiter,
    backup_sqlite_database,
)


def test_pii_redacting_json_logger_and_rate_limiter():
    fmt = RedactingJsonFormatter()
    rec = logging.LogRecord(
        "test", logging.INFO, __file__, 1,
        "Contact buyer@example.com PAN ABCDE1234F phone 9876543210 Aadhaar 1234 5678 9012",
        (), None,
    )
    out = json.loads(fmt.format(rec))
    assert "buyer@example.com" not in out["message"]
    assert "ABCDE1234F" not in out["message"]
    assert "9876543210" not in out["message"]
    assert "1234 5678 9012" not in out["message"]

    limiter = SlidingWindowRateLimiter(max_requests_per_minute=2)
    assert limiter.allow_request("1.2.3.4", now_ts=100.0) == (True, 0)
    assert limiter.allow_request("1.2.3.4", now_ts=110.0) == (True, 0)
    allowed, retry = limiter.allow_request("1.2.3.4", now_ts=120.0)
    assert allowed is False
    assert retry >= 1


def test_sqlite_online_backup_snapshot_and_checksum(tmp_path):
    src_db = tmp_path / "source.db"
    conn = sqlite3.connect(str(src_db))
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO demo VALUES (1, 'patia_deed')")
    conn.commit()
    conn.close()

    res = backup_sqlite_database(src_db, tmp_path / "backups")
    assert res["method"] == "sqlite3_online_backup_api"
    assert res["size_bytes"] > 0
    b_path = res["backup_file"]
    with open(b_path, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == res["sha256"]

    b_conn = sqlite3.connect(b_path)
    assert b_conn.execute("SELECT note FROM demo WHERE id = 1").fetchone()[0] == "patia_deed"
    b_conn.close()


def test_health_downloadable_report_and_staff_auth():
    client = TestClient(app)

    # 1. Health endpoint
    h = client.get("/api/health")
    assert h.status_code == 200
    hb = h.json()
    assert hb["status"] == "healthy"
    assert hb["specialist_models_registered"] == 10
    assert "apartment" in hb["production_models_loaded"]

    # 2. Valuation + HTML/JSON report download
    val_resp = client.post("/api/property/valuation", json={
        "location": {"latitude": 20.3533, "longitude": 85.8266, "country_code": "IN"},
        "property_details": {
            "asset_type": "residential",
            "structure_type": "apartment",
            "area_value": 1250,
            "monthly_rent_inr": 24000,
        },
    })
    assert val_resp.status_code == 200
    val_id = val_resp.json()["valuation_id"]

    r_html = client.get(f"/api/property/valuation/{val_id}/report?format=html")
    assert r_html.status_code == 200
    assert "Model Estimate vs Verified Market Transactions" in r_html.text
    assert val_id in r_html.text

    r_json = client.get(f"/api/property/valuation/{val_id}/report?format=json")
    assert r_json.status_code == 200
    assert r_json.json()["valuation_id"] == val_id
    assert "Model Valuation Estimate" in r_json.json()["disclaimer"]

    # 3. Password login & admin review queue RBAC
    assert client.get("/api/admin/review-queue").status_code == 401
    bad_login = client.post("/api/auth/login", json={"username": "reviewer_bbsr", "password": "wrong"})
    assert bad_login.status_code == 401

    rev_pass = os.environ.get("DEMO_REVIEWER_PASS", "ReviewBbsr#2026")
    good_login = client.post("/api/auth/login", json={"username": "reviewer_bbsr", "password": rev_pass})
    assert good_login.status_code == 200
    token = good_login.json()["access_token"]
    assert good_login.json()["actor_role"] == "HUMAN_REVIEWER"

    q_resp = client.get("/api/admin/review-queue", headers={"Authorization": f"Bearer {token}"})
    assert q_resp.status_code == 200
    assert q_resp.json()["viewer_role"] == "HUMAN_REVIEWER"

    # HUMAN_REVIEWER blocked from sync-ground-truth (403)
    assert client.post("/api/admin/sync-ground-truth", headers={"Authorization": f"Bearer {token}"}).status_code == 403
