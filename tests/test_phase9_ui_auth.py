"""Phase 9 Tests — Unified Dashboard UI Workspaces, Report Controls & Admin Auth Flow."""
from fastapi.testclient import TestClient

from src.api.app import app


def test_unified_dashboard_renders_all_workspaces_and_preserves_existing_hooks():
    from pathlib import Path

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    dist_assets = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "assets"
    bundle = resp.text + "".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist_assets.glob("*.js"))

    # Preserve Milestone 6/7 UI contracts inside compiled SPA
    for legacy_hook in (
        "ev-conf-tier-badge",
        "/api/validation/dashboard",
        "sens-slider-rent",
        "Three-Way Reconciliation",
    ):
        assert legacy_hook in bundle

    # Verify Milestone 8/9 & 3D Architectural workspaces & controls
    for new_hook in (
        "workspace-valuation",
        "workspace-coverage",
        "workspace-analytics",
        "workspace-admin",
        "btn-download-html-report",
        "btn-download-json-report",
        "ev-ood-badge",
        "/api/coverage/bhubaneswar",
        "/api/analytics/eda",
        "/api/auth/login",
    ):
        assert new_hook in bundle
