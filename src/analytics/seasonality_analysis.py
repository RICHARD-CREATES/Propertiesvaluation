"""
Module 6: Seasonality & Chronological Validation Engine
=====================================================
Reuses:
- src/analytics/data_quality.py (IndianPropertyDataQualityAuditor)

Guardrails enforced strictly:
1. Minimum History Gate: Requires >= 24 distinct YYYY-MM months with >= 5 valid
   transactions per month (`min_months=24, min_deals_per_month=5` by default).
   Otherwise returns `status="INSUFFICIENT_SEASONALITY_HISTORY"` with diagnostics
   and does NOT claim seasonal premiums or discounts.
2. Property-Mix Control: Computes mix-adjusted Price-per-SqFt indices by normalizing
   every transaction against its own canonical `property_type` median PPS before
   aggregating across months or Indian seasonal quarters.
3. Chronological Split Validation: Trains seasonal multipliers strictly on earlier
   months (`train_fraction=0.75`) and evaluates on strictly later out-of-time months
   to measure generalization error + uncertainty (P25-P75 & std).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.analytics.data_quality import IndianPropertyDataQualityAuditor, _first_present


INDIAN_SEASON_MAP = {
    1: "Jan-Mar (Q1 Fiscal Close)",
    2: "Jan-Mar (Q1 Fiscal Close)",
    3: "Jan-Mar (Q1 Fiscal Close)",
    4: "Apr-Jun (Q2 Akshaya Tritiya / Summer)",
    5: "Apr-Jun (Q2 Akshaya Tritiya / Summer)",
    6: "Apr-Jun (Q2 Akshaya Tritiya / Summer)",
    7: "Jul-Sep (Q3 Monsoon)",
    8: "Jul-Sep (Q3 Monsoon)",
    9: "Jul-Sep (Q3 Monsoon)",
    10: "Oct-Dec (Q4 Festive / Navratri-Diwali)",
    11: "Oct-Dec (Q4 Festive / Navratri-Diwali)",
    12: "Oct-Dec (Q4 Festive / Navratri-Diwali)",
}


def _parse_tx_date(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("unknown", "nan", "none", "null"):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


class SeasonalityAnalyzer:
    """Strict sample-gated, mix-adjusted Indian real-estate seasonality analyzer."""

    def __init__(self, auditor: Optional[IndianPropertyDataQualityAuditor] = None) -> None:
        self.auditor = auditor or IndianPropertyDataQualityAuditor()

    def analyze(
        self,
        records: List[Dict[str, Any]],
        min_months: int = 24,
        min_deals_per_month: int = 5,
        chronological_train_fraction: float = 0.75,
    ) -> Dict[str, Any]:
        """Run seasonality diagnostics subject to history gates, mix normalization, and chronological validation."""
        dated_rows: List[Dict[str, Any]] = []
        missing_or_bad_date = 0
        excluded_invalid = 0

        for raw in records:
            dt = _parse_tx_date(_first_present(raw, "transaction_date", "date", "sale_date"))
            if dt is None:
                missing_or_bad_date += 1
                continue
            checked = self.auditor.validate_single_record(raw)
            if not checked["is_valid"] or checked["price_per_sqft_inr"] is None:
                excluded_invalid += 1
                continue

            dated_rows.append(
                {
                    "dt": dt,
                    "ym": dt.strftime("%Y-%m"),
                    "month": dt.month,
                    "season": INDIAN_SEASON_MAP[dt.month],
                    "property_type": checked["normalized_property_type"],
                    "price_per_sqft_inr": float(checked["price_per_sqft_inr"]),
                }
            )

        by_ym: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in dated_rows:
            by_ym[r["ym"]].append(r)

        qualifying_months = sorted(ym for ym, grp in by_ym.items() if len(grp) >= min_deals_per_month)
        all_months = sorted(by_ym.keys())

        if len(qualifying_months) < min_months:
            return {
                "status": "INSUFFICIENT_SEASONALITY_HISTORY",
                "reason": (
                    f"Found {len(qualifying_months)} qualifying months (>= {min_deals_per_month} deals/month), "
                    f"which is below the strict minimum gate of {min_months} months."
                ),
                "history_diagnostics": {
                    "total_input_records": len(records),
                    "valid_dated_records": len(dated_rows),
                    "excluded_invalid_records": excluded_invalid,
                    "missing_or_unparseable_dates": missing_or_bad_date,
                    "distinct_months_observed": len(all_months),
                    "qualifying_months_meeting_density": len(qualifying_months),
                    "required_min_months": min_months,
                    "required_min_deals_per_month": min_deals_per_month,
                    "earliest_month": all_months[0] if all_months else None,
                    "latest_month": all_months[-1] if all_months else None,
                },
                "monthly_seasonal_indices": [],
                "indian_season_summary": [],
                "chronological_validation": None,
            }

        # Filter to qualifying months and sort strictly chronologically
        qual_set = set(qualifying_months)
        active_rows = sorted([r for r in dated_rows if r["ym"] in qual_set], key=lambda r: r["dt"])

        # Property-mix normalization baselines (median PPS per canonical property_type)
        type_vals: Dict[str, List[float]] = defaultdict(list)
        for r in active_rows:
            type_vals[r["property_type"]].append(r["price_per_sqft_inr"])
        type_medians = {pt: float(np.median(vals)) for pt, vals in type_vals.items()}

        for r in active_rows:
            baseline = type_medians[r["property_type"]]
            r["mix_adjusted_index"] = (r["price_per_sqft_inr"] / baseline) * 100.0 if baseline > 0 else 100.0

        # Calendar month-of-year (1..12) summary
        by_cal_month: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        by_season: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in active_rows:
            by_cal_month[r["month"]].append(r)
            by_season[r["season"]].append(r)

        monthly_indices = []
        for m in sorted(by_cal_month.keys()):
            grp = by_cal_month[m]
            idx_arr = np.asarray([g["mix_adjusted_index"] for g in grp], dtype=float)
            p25, p50, p75 = np.percentile(idx_arr, [25, 50, 75])
            monthly_indices.append(
                {
                    "calendar_month": m,
                    "deal_count": len(grp),
                    "mix_adjusted_median_index": round(float(p50), 2),
                    "mix_adjusted_mean_index": round(float(np.mean(idx_arr)), 2),
                    "uncertainty_std_index": round(float(np.std(idx_arr, ddof=1)) if len(idx_arr) > 1 else 0.0, 2),
                    "uncertainty_iqr_band": [round(float(p25), 2), round(float(p75), 2)],
                    "unadjusted_median_pps_inr": round(float(np.median([g["price_per_sqft_inr"] for g in grp])), 2),
                }
            )

        season_summary = []
        for sname, grp in sorted(by_season.items()):
            idx_arr = np.asarray([g["mix_adjusted_index"] for g in grp], dtype=float)
            p25, p50, p75 = np.percentile(idx_arr, [25, 50, 75])
            season_summary.append(
                {
                    "indian_season": sname,
                    "deal_count": len(grp),
                    "mix_adjusted_median_index": round(float(p50), 2),
                    "uncertainty_std_index": round(float(np.std(idx_arr, ddof=1)) if len(idx_arr) > 1 else 0.0, 2),
                    "uncertainty_iqr_band": [round(float(p25), 2), round(float(p75), 2)],
                }
            )

        # Chronological Train / Out-of-Time Test Validation
        split_idx = max(12, min(len(qualifying_months) - 3, int(len(qualifying_months) * chronological_train_fraction)))
        train_yms = set(qualifying_months[:split_idx])
        test_yms = set(qualifying_months[split_idx:])

        train_rows = [r for r in active_rows if r["ym"] in train_yms]
        test_rows = [r for r in active_rows if r["ym"] in test_yms]

        # Recompute property-type baselines ONLY on train_rows so zero future target leakage occurs
        tr_type_vals: Dict[str, List[float]] = defaultdict(list)
        for r in train_rows:
            tr_type_vals[r["property_type"]].append(r["price_per_sqft_inr"])
        tr_type_medians = {pt: float(np.median(v)) for pt, v in tr_type_vals.items()}
        overall_tr_med = float(np.median([r["price_per_sqft_inr"] for r in train_rows]))

        tr_month_indices: Dict[int, List[float]] = defaultdict(list)
        for r in train_rows:
            base = tr_type_medians.get(r["property_type"], overall_tr_med)
            tr_month_indices[r["month"]].append((r["price_per_sqft_inr"] / base) * 100.0)
        learned_month_index = {m: float(np.median(v)) for m, v in tr_month_indices.items()}

        abs_errors: List[float] = []
        baseline_errors: List[float] = []
        for r in test_rows:
            base = tr_type_medians.get(r["property_type"], overall_tr_med)
            actual_idx = (r["price_per_sqft_inr"] / base) * 100.0
            pred_seasonal_idx = learned_month_index.get(r["month"], 100.0)
            abs_errors.append(abs(actual_idx - pred_seasonal_idx))
            baseline_errors.append(abs(actual_idx - 100.0))

        mae_seasonal = float(np.mean(abs_errors)) if abs_errors else None
        mae_flat = float(np.mean(baseline_errors)) if baseline_errors else None

        return {
            "status": "OK",
            "property_mix_controlled": True,
            "history_diagnostics": {
                "total_input_records": len(records),
                "valid_dated_records": len(active_rows),
                "excluded_invalid_records": excluded_invalid,
                "missing_or_unparseable_dates": missing_or_bad_date,
                "qualifying_months_count": len(qualifying_months),
                "earliest_month": qualifying_months[0],
                "latest_month": qualifying_months[-1],
                "property_type_baselines_pps_inr": {k: round(v, 2) for k, v in sorted(type_medians.items())},
            },
            "monthly_seasonal_indices": monthly_indices,
            "indian_season_summary": season_summary,
            "chronological_validation": {
                "train_months_count": len(train_yms),
                "test_months_count": len(test_yms),
                "train_deals": len(train_rows),
                "test_deals": len(test_rows),
                "seasonal_model_index_mae": round(mae_seasonal, 3) if mae_seasonal is not None else None,
                "flat_nonseasonal_baseline_mae": round(mae_flat, 3) if mae_flat is not None else None,
                "outperforms_flat_baseline": bool(mae_seasonal is not None and mae_flat is not None and mae_seasonal < mae_flat),
            },
        }
