"""
Module 3: Micro-Market & Spatial Locality Analytics Engine
=========================================================
Reuses:
- src/analytics/data_quality.py (IndianPropertyDataQualityAuditor)
- src/services/spatial_split.py (assign_spatial_clusters)
- src/services/location_intelligence.py (haversine_km)

Key Statistical Guardrails:
1. Never blends heterogeneous property types (apartments, houses, villas, land, commercial)
   within the same locality summary.
2. Strictly separates Standard Error of the Mean (SEM = std / sqrt(n), which ONLY measures
   sample-mean precision) from individual property valuation dispersion (empirical P10-P90,
   P25-P75 IQR, sample StdDev, and CV%). SEM is NEVER labeled or used as an individual
   prediction interval.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.analytics.data_quality import IndianPropertyDataQualityAuditor, _first_present
from src.services.location_intelligence import haversine_km
from src.services.spatial_split import assign_spatial_clusters


def _compute_cohort_metrics(
    pps_values: List[float],
    min_reliable_samples: int = 5,
) -> Dict[str, Any]:
    """Compute homogeneous cohort stats separating mean precision (SEM) from individual dispersion."""
    arr = np.asarray(pps_values, dtype=float)
    n = int(arr.size)
    if n == 0:
        return {"count": 0, "reliability_status": "EMPTY"}

    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    sem_val = float(std_val / np.sqrt(n)) if n > 1 else None
    p10, p25, p50, p75, p90 = np.percentile(arr, [10, 25, 50, 75, 90])
    iqr = float(p75 - p25)
    cv_pct = round((std_val / mean_val) * 100.0, 2) if (n > 1 and mean_val > 1e-9) else 0.0

    # Within-tier spread classification
    if n < min_reliable_samples:
        reliability = "LOW_SAMPLE_SIZE"
    elif cv_pct <= 15.0:
        reliability = "TIGHT_HOMOGENEOUS"
    elif cv_pct <= 30.0:
        reliability = "MODERATE_DISPERSION"
    else:
        reliability = "HIGH_DISPERSION_CHECK_SUBTIERS"

    return {
        "count": n,
        "reliability_status": reliability,
        "central_tendency_pps_inr": {
            "median": round(float(p50), 2),
            "mean": round(mean_val, 2),
            "mean_standard_error_sem": round(sem_val, 2) if sem_val is not None else None,
            "sem_interpretation_note": (
                "SEM measures precision of the cohort average ONLY; never use as an individual property prediction interval."
            ),
        },
        "individual_property_dispersion_pps_inr": {
            "sample_std": round(std_val, 2),
            "cv_pct": cv_pct,
            "p10": round(float(p10), 2),
            "p25": round(float(p25), 2),
            "p75": round(float(p75), 2),
            "p90": round(float(p90), 2),
            "iqr": round(iqr, 2),
            "p90_p10_band": [round(float(p10), 2), round(float(p90), 2)],
        },
    }


class MicroMarketAnalyzer:
    """Homogeneous locality, tier, and spatial cluster analytics engine."""

    def __init__(self, auditor: Optional[IndianPropertyDataQualityAuditor] = None) -> None:
        self.auditor = auditor or IndianPropertyDataQualityAuditor()

    def analyze(
        self,
        records: List[Dict[str, Any]],
        cluster_radius_km: float = 3.0,
        min_reliable_samples: int = 5,
    ) -> Dict[str, Any]:
        """Compute locality x property-type stats, tier dispersion, and GPS spatial cluster summaries."""
        normalized_rows: List[Dict[str, Any]] = []
        excluded_invalid = 0

        for raw in records:
            checked = self.auditor.validate_single_record(raw)
            if not checked["is_valid"] or checked["price_per_sqft_inr"] is None:
                excluded_invalid += 1
                continue

            city = str(_first_present(raw, "city") or "UNKNOWN_CITY").strip()
            locality = str(_first_present(raw, "locality", "micro_market", "neighborhood") or "UNKNOWN_LOCALITY").strip()
            tier = str(_first_present(raw, "micro_market_tier", "tier") or "UNCLASSIFIED_TIER").strip()
            lat = _first_present(raw, "latitude")
            lon = _first_present(raw, "longitude")

            row_copy = {
                "city": city,
                "locality": locality,
                "tier": tier,
                "property_type": checked["normalized_property_type"],
                "price_inr": float(checked["normalized_price_inr"]),
                "area_sqft": float(checked["normalized_area_sqft"]),
                "price_per_sqft_inr": float(checked["price_per_sqft_inr"]),
                "latitude": float(lat) if lat is not None else None,
                "longitude": float(lon) if lon is not None else None,
            }
            normalized_rows.append(row_copy)

        # 1. Homogeneous (city, locality, property_type) cohorts
        cohort_groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        tier_groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

        for r in normalized_rows:
            cohort_groups[(r["city"], r["locality"], r["property_type"])].append(r)
            tier_groups[(r["tier"], r["property_type"])].append(r)

        locality_cohorts = []
        for (city, locality, ptype), grp in sorted(cohort_groups.items()):
            stats = _compute_cohort_metrics([g["price_per_sqft_inr"] for g in grp], min_reliable_samples)
            coords = [(g["latitude"], g["longitude"]) for g in grp if g["latitude"] is not None and g["longitude"] is not None]
            centroid = (
                {
                    "latitude": round(float(np.mean([c[0] for c in coords])), 6),
                    "longitude": round(float(np.mean([c[1] for c in coords])), 6),
                }
                if coords
                else None
            )
            locality_cohorts.append(
                {
                    "city": city,
                    "locality": locality,
                    "property_type": ptype,
                    "centroid": centroid,
                    **stats,
                }
            )

        tier_dispersion = [
            {
                "micro_market_tier": tier,
                "property_type": ptype,
                **_compute_cohort_metrics([g["price_per_sqft_inr"] for g in grp], min_reliable_samples),
            }
            for (tier, ptype), grp in sorted(tier_groups.items())
        ]

        # 2. Connected GPS spatial clusters (reusing assign_spatial_clusters & haversine_km)
        gps_rows = [r for r in normalized_rows if r["latitude"] is not None and r["longitude"] is not None]
        spatial_clusters_summary: List[Dict[str, Any]] = []
        if gps_rows:
            clustered = assign_spatial_clusters(gps_rows, cluster_radius_km=cluster_radius_km)
            by_cluster_and_type: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
            for c_row in clustered:
                by_cluster_and_type[(c_row["geo_cluster_id"], c_row["property_type"])].append(c_row)

            for (cid, ptype), grp in sorted(by_cluster_and_type.items()):
                lats = [g["latitude"] for g in grp]
                lons = [g["longitude"] for g in grp]
                c_lat = float(np.mean(lats))
                c_lon = float(np.mean(lons))
                max_spread_km = max(haversine_km(c_lat, c_lon, la, lo) for la, lo in zip(lats, lons))
                spatial_clusters_summary.append(
                    {
                        "geo_cluster_id": cid,
                        "property_type": ptype,
                        "centroid": {"latitude": round(c_lat, 6), "longitude": round(c_lon, 6)},
                        "max_radius_from_centroid_km": round(max_spread_km, 3),
                        **_compute_cohort_metrics([g["price_per_sqft_inr"] for g in grp], min_reliable_samples),
                    }
                )

        return {
            "total_records": len(records),
            "valid_analyzed_records": len(normalized_rows),
            "excluded_invalid_records": excluded_invalid,
            "homogeneous_grouping_enforced": True,
            "uncertainty_policy": (
                "SEM reports uncertainty of sample mean only. Individual property dispersion uses empirical quantiles (P10-P90, IQR)."
            ),
            "locality_cohorts": locality_cohorts,
            "tier_dispersion": tier_dispersion,
            "spatial_clusters": spatial_clusters_summary,
        }
