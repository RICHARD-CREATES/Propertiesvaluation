"""Focused tests for Module 6: SeasonalityAnalyzer."""
from src.analytics.seasonality_analysis import SeasonalityAnalyzer


def test_insufficient_seasonality_history_gate():
    # Only 12 months -> fails >= 24 months minimum gate
    records = [
        {
            "property_type": "apartment",
            "builtup_area_sqft": 1000,
            "sale_price": 5500000,
            "latitude": 20.30,
            "longitude": 85.82,
            "transaction_date": f"2025-{m:02d}-10",
        }
        for m in range(1, 13)
        for _ in range(6)
    ]

    res = SeasonalityAnalyzer().analyze(records, min_months=24, min_deals_per_month=5)
    assert res["status"] == "INSUFFICIENT_SEASONALITY_HISTORY"
    assert res["monthly_seasonal_indices"] == []
    assert res["chronological_validation"] is None
    assert res["history_diagnostics"]["qualifying_months_meeting_density"] == 12


def test_seasonality_property_mix_control_and_chronological_validation():
    # Build 26 months (2024-01 .. 2026-02) with 6 deals/month
    # True festive Q4 (Oct-Dec) uplift: +10% across BOTH apartment & commercial
    # Deliberate property-mix confound in Aug (Q3): 5 commercial deals (15,000/sqft) vs 1 apartment (5,000/sqft)
    # Without mix control Aug unadjusted PPS=15,000 looks falsely inflated; WITH mix control, Oct-Dec wins!
    records = []
    start_year, start_month = 2024, 1
    for step in range(26):
        yr = start_year + (start_month - 1 + step) // 12
        mo = ((start_month - 1 + step) % 12) + 1
        seasonal_mult = 1.10 if mo in (10, 11, 12) else (0.94 if mo in (7, 8, 9) else 1.00)

        for k in range(6):
            if mo == 8 and k < 5:
                ptype = "commercial"
                base_pps = 15000.0
            elif mo in (10, 11, 12):
                ptype = "apartment"
                base_pps = 5500.0
            else:
                ptype = "commercial" if k == 0 else "apartment"
                base_pps = 15000.0 if ptype == "commercial" else 5500.0

            area = 1000.0
            records.append(
                {
                    "property_type": ptype,
                    "builtup_area_sqft": area,
                    "sale_price": area * base_pps * seasonal_mult,
                    "latitude": 20.30,
                    "longitude": 85.82,
                    "transaction_date": f"{yr:04d}-{mo:02d}-{10 + k:02d}",
                }
            )

    res = SeasonalityAnalyzer().analyze(records, min_months=24, min_deals_per_month=5)
    assert res["status"] == "OK"
    assert res["property_mix_controlled"] is True
    assert res["history_diagnostics"]["qualifying_months_count"] == 26

    # Check Q4 festive beat Q3 monsoon on mix-adjusted index despite Aug commercial mix skew!
    by_season = {s["indian_season"]: s for s in res["indian_season_summary"]}
    q4_idx = by_season["Oct-Dec (Q4 Festive / Navratri-Diwali)"]["mix_adjusted_median_index"]
    q3_idx = by_season["Jul-Sep (Q3 Monsoon)"]["mix_adjusted_median_index"]
    assert q4_idx > q3_idx

    # Verify chronological validation ran and beat flat baseline
    val = res["chronological_validation"]
    assert val["train_months_count"] >= 12
    assert val["test_months_count"] >= 3
    assert val["outperforms_flat_baseline"] is True
