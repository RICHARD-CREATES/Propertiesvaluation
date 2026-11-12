"""
Module 2: Property Exploratory Data Analysis (EDA) Engine
=========================================================
Computes univariate distributions, quantile summaries, skewness/IQR spread,
property-type distributions, and construction/renovation age cohort analytics
reusing Module 1's IndianPropertyDataQualityAuditor without modifying stored data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np

from src.analytics.data_quality import (
    IndianPropertyDataQualityAuditor,
    _first_present,
)


def _compute_distribution_summary(values: List[float]) -> Dict[str, Any]:
    """Compute robust univariate summary statistics for positive numeric values."""
    clean = [float(v) for v in values if v is not None and np.isfinite(v)]
    n = len(clean)
    if n == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "max": None,
            "iqr": None,
            "skewness": None,
        }

    arr = np.asarray(clean, dtype=float)
    q10, q25, q50, q75, q90 = np.percentile(arr, [10, 25, 50, 75, 90])
    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr, ddof=1)) if n > 1 else 0.0

    skew_val: Optional[float] = None
    if n >= 3 and std_val > 1e-12:
        centered = arr - mean_val
        m3 = float(np.mean(centered ** 3))
        m2 = float(np.mean(centered ** 2))
        if m2 > 1e-12:
            skew_val = round(m3 / (m2 ** 1.5), 4)
    elif n >= 3:
        skew_val = 0.0

    return {
        "count": n,
        "mean": round(mean_val, 2),
        "std": round(std_val, 2),
        "min": round(float(np.min(arr)), 2),
        "p10": round(float(q10), 2),
        "p25": round(float(q25), 2),
        "median": round(float(q50), 2),
        "p75": round(float(q75), 2),
        "p90": round(float(q90), 2),
        "max": round(float(np.max(arr)), 2),
        "iqr": round(float(q75 - q25), 2),
        "skewness": skew_val,
    }


def _age_cohort(age_years: Optional[float]) -> str:
    if age_years is None:
        return "unknown"
    if age_years <= 3.0:
        return "new_0_3y"
    if age_years <= 10.0:
        return "mid_4_10y"
    if age_years <= 20.0:
        return "mature_11_20y"
    return "old_20y_plus"


def _renovation_cohort(age_years: Optional[float], remodel_age: Optional[float]) -> str:
    if remodel_age is None:
        return "unknown"
    if remodel_age <= 5.0 and (age_years is None or age_years > remodel_age):
        return "recently_renovated_0_5y"
    if remodel_age <= 5.0:
        return "new_or_remodeled_0_5y"
    return "unrenovated_or_aging"


class PropertyEDAAnalyzer:
    """Read-only exploratory analytics over Indian property transaction cohorts."""

    def __init__(self, auditor: Optional[IndianPropertyDataQualityAuditor] = None) -> None:
        self.auditor = auditor or IndianPropertyDataQualityAuditor()

    def analyze(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run normalized univariate, categorical, and age-cohort EDA on records."""
        quality_audit = self.auditor.audit_dataset(records)

        valid_items: List[Dict[str, Any]] = []
        invalid_count = 0

        for idx, raw in enumerate(records):
            checked = self.auditor.validate_single_record(raw)
            if not checked["is_valid"]:
                invalid_count += 1
                continue

            price_inr = checked["normalized_price_inr"]
            area_sqft = checked["normalized_area_sqft"]
            pps = checked["price_per_sqft_inr"]
            if price_inr is None or area_sqft is None or pps is None:
                invalid_count += 1
                continue

            age_raw = _first_present(raw, "property_age_years", "age_years")
            remodel_raw = _first_present(raw, "remodel_age_years", "renovation_age_years")
            age_val = float(age_raw) if age_raw is not None else None
            remodel_val = float(remodel_raw) if remodel_raw is not None else None

            valid_items.append(
                {
                    "index": idx,
                    "property_type": checked["normalized_property_type"],
                    "price_inr": float(price_inr),
                    "area_sqft": float(area_sqft),
                    "price_per_sqft_inr": float(pps),
                    "age_cohort": _age_cohort(age_val),
                    "renovation_cohort": _renovation_cohort(age_val, remodel_val),
                }
            )

        all_prices = [x["price_inr"] for x in valid_items]
        all_areas = [x["area_sqft"] for x in valid_items]
        all_pps = [x["price_per_sqft_inr"] for x in valid_items]

        by_type: Dict[str, List[Dict[str, Any]]] = {}
        by_age: Dict[str, List[Dict[str, Any]]] = {}
        by_renovation: Dict[str, List[Dict[str, Any]]] = {}

        for item in valid_items:
            by_type.setdefault(item["property_type"], []).append(item)
            by_age.setdefault(item["age_cohort"], []).append(item)
            by_renovation.setdefault(item["renovation_cohort"], []).append(item)

        type_breakdown = {
            ptype: {
                "count": len(grp),
                "share_pct": round((len(grp) / len(valid_items)) * 100.0, 2) if valid_items else 0.0,
                "price_inr": _compute_distribution_summary([g["price_inr"] for g in grp]),
                "price_per_sqft_inr": _compute_distribution_summary([g["price_per_sqft_inr"] for g in grp]),
                "area_sqft": _compute_distribution_summary([g["area_sqft"] for g in grp]),
            }
            for ptype, grp in sorted(by_type.items())
        }

        age_breakdown = {
            cohort: {
                "count": len(grp),
                "price_per_sqft_inr": _compute_distribution_summary([g["price_per_sqft_inr"] for g in grp]),
            }
            for cohort, grp in sorted(by_age.items())
        }

        renovation_breakdown = {
            cohort: {
                "count": len(grp),
                "price_per_sqft_inr": _compute_distribution_summary([g["price_per_sqft_inr"] for g in grp]),
            }
            for cohort, grp in sorted(by_renovation.items())
        }

        return {
            "total_records": len(records),
            "valid_analyzed_records": len(valid_items),
            "excluded_invalid_records": invalid_count,
            "outliers_retained_in_eda": True,
            "quality_summary": {
                "duplicate_count": quality_audit["duplicate_rows_detected"],
                "outlier_count_iqr_or_mad": quality_audit["price_per_sqft_outlier_audit"].get("flagged_count", 0),
                "semantic_presence_counts": quality_audit["semantic_presence_counts"],
            },
            "overall_distributions": {
                "price_inr": _compute_distribution_summary(all_prices),
                "area_sqft": _compute_distribution_summary(all_areas),
                "price_per_sqft_inr": _compute_distribution_summary(all_pps),
            },
            "by_property_type": type_breakdown,
            "by_age_cohort": age_breakdown,
            "by_renovation_cohort": renovation_breakdown,
        }
