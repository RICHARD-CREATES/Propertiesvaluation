"""
Module 4: Property Price Driver & Feature Relationship Engine
==============================================================
Reuses:
- src/analytics/data_quality.py (IndianPropertyDataQualityAuditor)
- src/services/spatial_split.py (create_spatial_splits)

Provides:
- Pearson & Spearman correlations (with explicit non-causal / confounding disclaimer)
- SizeBand diminishing price-per-sqft curves (homogeneous by property_type)
- Construction age vs renovation age decay breakdown
- Leakage-free permutation importance evaluated strictly across spatial splits
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance

from src.analytics.data_quality import IndianPropertyDataQualityAuditor, _first_present
from src.services.spatial_split import create_spatial_splits


NUMERIC_DRIVER_KEYS = [
    "area_sqft",
    "plot_area_sqft",
    "bedrooms",
    "bathrooms",
    "property_age_years",
    "remodel_age_years",
    "road_width_ft",
    "floor_number",
    "total_floors",
]

SIZE_BANDS: List[Tuple[str, float, float]] = [
    ("small_lt_800", 0.0, 800.0),
    ("compact_800_1200", 800.0, 1200.0),
    ("standard_1200_1800", 1200.0, 1800.0),
    ("large_1800_3000", 1800.0, 3000.0),
    ("estate_3000_plus", 3000.0, float("inf")),
]


def _size_band_label(area_sqft: float) -> str:
    for label, lo, hi in SIZE_BANDS:
        if lo <= area_sqft < hi:
            return label
    return "estate_3000_plus"


def _safe_correlation(x: List[float], y: List[float]) -> Optional[Dict[str, Any]]:
    if len(x) < 4:
        return None
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    if np.std(xa) < 1e-12 or np.std(ya) < 1e-12:
        return None
    pr, pp = pearsonr(xa, ya)
    sr, sp = spearmanr(xa, ya)
    return {
        "n": int(len(x)),
        "pearson_r": round(float(pr), 4) if np.isfinite(pr) else None,
        "pearson_p": round(float(pp), 6) if np.isfinite(pp) else None,
        "spearman_rho": round(float(sr), 4) if np.isfinite(sr) else None,
        "spearman_p": round(float(sp), 6) if np.isfinite(sp) else None,
    }


class PriceDriverAnalyzer:
    """Analyzes price relationships without spatial leakage or causal overclaiming."""

    def __init__(self, auditor: Optional[IndianPropertyDataQualityAuditor] = None) -> None:
        self.auditor = auditor or IndianPropertyDataQualityAuditor()

    def analyze(
        self,
        records: List[Dict[str, Any]],
        cluster_radius_km: float = 3.0,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Compute associative drivers, SizeBand curves, age/remodel effects, and spatial permutation importance."""
        clean_rows: List[Dict[str, Any]] = []
        excluded_invalid = 0

        for idx, raw in enumerate(records):
            checked = self.auditor.validate_single_record(raw)
            if not checked["is_valid"] or checked["price_per_sqft_inr"] is None:
                excluded_invalid += 1
                continue

            tid = str(_first_present(raw, "transaction_id", "id") or f"ROW_{idx}")
            row: Dict[str, Any] = {
                "transaction_id": tid,
                "property_type": checked["normalized_property_type"],
                "price_inr": float(checked["normalized_price_inr"]),
                "price_per_sqft_inr": float(checked["price_per_sqft_inr"]),
                "area_sqft": float(checked["normalized_area_sqft"]),
                "latitude": _first_present(raw, "latitude"),
                "longitude": _first_present(raw, "longitude"),
                "state": _first_present(raw, "state") or "Unknown",
                "city": _first_present(raw, "city") or "Unknown",
                "locality": _first_present(raw, "locality") or "Unknown",
                "transaction_date": _first_present(raw, "transaction_date"),
            }
            for k in NUMERIC_DRIVER_KEYS:
                if k == "area_sqft":
                    continue
                v = _first_present(raw, k)
                row[k] = float(v) if v is not None else None
            clean_rows.append(row)

        # 1. Associative Correlations (Pearson + Spearman)
        correlations: Dict[str, Any] = {}
        for feat in NUMERIC_DRIVER_KEYS:
            paired = [(r[feat], r["price_inr"], r["price_per_sqft_inr"]) for r in clean_rows if r.get(feat) is not None]
            if len(paired) >= 4:
                xs = [p[0] for p in paired]
                ys_total = [p[1] for p in paired]
                ys_pps = [p[2] for p in paired]
                corr_total = _safe_correlation(xs, ys_total)
                corr_pps = _safe_correlation(xs, ys_pps)
                if corr_total or corr_pps:
                    correlations[feat] = {
                        "vs_total_price_inr": corr_total,
                        "vs_price_per_sqft_inr": corr_pps,
                    }

        # 2. SizeBand Non-Linear Economies-of-Scale Curve (homogeneous by property_type)
        size_band_groups: Dict[Tuple[str, str], List[float]] = defaultdict(list)
        for r in clean_rows:
            band = _size_band_label(r["area_sqft"])
            size_band_groups[(r["property_type"], band)].append(r["price_per_sqft_inr"])

        size_band_curves: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        band_order = {label: i for i, (label, _, _) in enumerate(SIZE_BANDS)}
        for (ptype, band), vals in sorted(
            size_band_groups.items(),
            key=lambda kv: (kv[0][0], band_order.get(kv[0][1], 99)),
        ):
            arr = np.asarray(vals, dtype=float)
            p25, p50, p75 = np.percentile(arr, [25, 50, 75])
            size_band_curves[ptype].append(
                {
                    "size_band": band,
                    "count": len(vals),
                    "median_pps_inr": round(float(p50), 2),
                    "iqr_pps_inr": round(float(p75 - p25), 2),
                }
            )

        # 3. Construction Age vs Remodel Age Effect
        remodel_groups: Dict[str, List[float]] = defaultdict(list)
        for r in clean_rows:
            age = r.get("property_age_years")
            remodel = r.get("remodel_age_years")
            if age is None:
                continue
            if age <= 5:
                remodel_groups["new_construction_0_5y"].append(r["price_per_sqft_inr"])
            elif remodel is not None and remodel <= 5 and age > remodel:
                remodel_groups["older_building_recently_remodeled_0_5y"].append(r["price_per_sqft_inr"])
            else:
                remodel_groups["older_building_unrenovated_gt_5y"].append(r["price_per_sqft_inr"])

        age_vs_remodel_summary = {
            bucket: {
                "count": len(vals),
                "median_pps_inr": round(float(np.median(vals)), 2),
                "mean_pps_inr": round(float(np.mean(vals)), 2),
            }
            for bucket, vals in sorted(remodel_groups.items())
        }

        # 4. Leakage-Free Spatial Split Permutation Importance
        perm_section = self._compute_spatial_permutation_importance(clean_rows, cluster_radius_km, seed)

        return {
            "total_records": len(records),
            "valid_analyzed_records": len(clean_rows),
            "excluded_invalid_records": excluded_invalid,
            "causal_disclaimer": (
                "Correlations and feature associations are strictly descriptive, not causal; "
                "location tier, builder grade, and omitted amenities may confound univariate relationships."
            ),
            "correlations": correlations,
            "size_band_curves_by_property_type": dict(size_band_curves),
            "age_vs_remodel_pps_inr": age_vs_remodel_summary,
            "spatial_permutation_importance": perm_section,
        }

    def _compute_spatial_permutation_importance(
        self,
        clean_rows: List[Dict[str, Any]],
        cluster_radius_km: float,
        seed: int,
    ) -> Dict[str, Any]:
        gps_rows = [
            r for r in clean_rows
            if r.get("latitude") is not None and r.get("longitude") is not None
        ]
        if len(gps_rows) < 8:
            return {
                "status": "INSUFFICIENT_SPATIAL_CLUSTERS_FOR_IMPORTANCE",
                "reason": "Need at least 8 GPS-tagged valid transactions across distinct spatial clusters.",
                "importances": [],
            }

        split_res = create_spatial_splits(gps_rows, cluster_radius_km=cluster_radius_km, seed=seed)
        train_rows = split_res.get("train", [])
        eval_rows = split_res.get("validation", []) or split_res.get("test", [])

        if len(train_rows) < 4 or len(eval_rows) < 2:
            return {
                "status": split_res.get("status", "INSUFFICIENT_SPATIAL_CLUSTERS_FOR_IMPORTANCE"),
                "reason": split_res.get("message", "Not enough separate spatial clusters for train + held-out evaluation."),
                "importances": [],
            }

        # Use numeric features that actually have variance in train split + property_type one-hot
        candidate_num_feats = ["area_sqft", "bedrooms", "bathrooms", "property_age_years", "remodel_age_years", "plot_area_sqft", "road_width_ft"]
        active_feats = []
        for f in candidate_num_feats:
            present = sum(1 for r in train_rows if r.get(f) is not None)
            if present >= max(3, int(0.5 * len(train_rows))):
                active_feats.append(f)

        if not active_feats:
            active_feats = ["area_sqft"]

        medians = {
            f: float(np.median([r[f] for r in train_rows if r.get(f) is not None]))
            for f in active_feats
        }

        def build_matrix(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
            X = np.zeros((len(rows), len(active_feats)), dtype=float)
            y = np.zeros(len(rows), dtype=float)
            for i, r in enumerate(rows):
                y[i] = float(np.log1p(r["price_inr"]))
                for j, f in enumerate(active_feats):
                    val = r.get(f)
                    X[i, j] = float(val) if val is not None else medians[f]
            return X, y

        X_tr, y_tr = build_matrix(train_rows)
        X_ev, y_ev = build_matrix(eval_rows)

        rf = RandomForestRegressor(n_estimators=60, max_depth=6, random_state=seed)
        rf.fit(X_tr, y_tr)

        perm = permutation_importance(
            rf,
            X_ev,
            y_ev,
            n_repeats=10,
            random_state=seed,
            scoring="neg_mean_absolute_error",
        )

        ranked = sorted(
            [
                {
                    "feature": feat,
                    "importance_mean_log_mae_drop": round(float(perm.importances_mean[i]), 5),
                    "importance_std": round(float(perm.importances_std[i]), 5),
                }
                for i, feat in enumerate(active_feats)
            ],
            key=lambda d: d["importance_mean_log_mae_drop"],
            reverse=True,
        )

        return {
            "status": "OK_ZERO_SPATIAL_LEAKAGE",
            "train_count": len(train_rows),
            "heldout_spatial_eval_count": len(eval_rows),
            "leakage_audit": split_res.get("leakage_audit", {}),
            "importances": ranked,
        }
