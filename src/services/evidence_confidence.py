"""
Evidence-Quality Confidence Scoring & Statistically Calibrated Prediction Uncertainty (Milestone 7 - Tasks 4 & 5).

Never fabricates hardcoded confidence scores or arbitrary percentage intervals.
Computes decomposed evidence-quality metrics from measurable comparable signals and
empirical holdout residual quantiles. Returns INSUFFICIENT_EVIDENCE when verified data is insufficient.
"""
import math
from typing import Any, Dict, List, Optional
import numpy as np


SOURCE_RELIABILITY_WEIGHTS = {
    "Verified_Registered_Transaction": 1.00,
    "Verified_Achieved": 0.90,
    "User_Verified": 0.85,
    "User_Submitted": 0.72,
    "Broker_Reported": 0.55,
    "Historical_Hub_Benchmark": 0.45,
    "Historical_Benchmark": 0.45,
    "Historical_Regional_Benchmark": 0.45,
    "Advertised_Asking": 0.30,
    "Advertised_Asking_Price": 0.30,
    "Estimated_From_Yield": 0.25,
    "Estimated_Category_Baseline": 0.20,
    "Synthetic_Test_Record": 0.00,
}

# Additive weighting across the 6 transparent evidence quality dimensions (sum = 1.00)
EVIDENCE_WEIGHTS = {
    "comparable_count_score": 0.22,
    "geographic_distance_score": 0.18,
    "property_similarity_score": 0.18,
    "transaction_recency_score": 0.12,
    "source_reliability_score": 0.18,
    "data_completeness_score": 0.12,
}


class EvidenceConfidenceService:
    """Computes decomposed evidence quality scores and calibrated prediction intervals."""

    def compute_evidence_score(
        self,
        comparables_count: int,
        median_distance_km: Optional[float],
        search_radius_km: float,
        avg_similarity_0_100: Optional[float],
        median_age_days: Optional[float],
        source_categories: List[str],
        observed_critical_fields: int,
        total_critical_fields: int,
    ) -> Dict[str, Any]:
        """
        Computes the 6 measurable sub-scores, composite evidence score (0.0-1.0),
        confidence tier, and explicit plain-English reasons for any confidence deficit.
        """
        reasons: List[str] = []

        # 1. Comparable count saturation (0 comps -> 0.0; >= 8 verified/matched comps -> 1.0)
        count_score = min(1.0, max(0, comparables_count) / 8.0)
        if comparables_count == 0:
            reasons.append("No matching local comparable transactions found within search radius.")
        elif comparables_count < 3:
            reasons.append(f"Low comparable sample size (n={comparables_count} < 3 recommended minimum).")

        # 2. Geographic distance decay
        if comparables_count > 0 and median_distance_km is not None:
            dist_score = max(0.0, min(1.0, 1.0 - (median_distance_km / max(search_radius_km, 0.5)) * 0.75))
            if median_distance_km > 3.0:
                reasons.append(f"Median comparable distance is {median_distance_km:.1f} km (wide spatial radius).")
        else:
            dist_score = 0.0

        # 3. Property similarity (0-100 scale)
        if comparables_count > 0 and avg_similarity_0_100 is not None:
            sim_score = max(0.0, min(1.0, float(avg_similarity_0_100) / 100.0))
            if sim_score < 0.65:
                reasons.append(f"Low physical similarity to available comparables (avg {avg_similarity_0_100:.0f}/100).")
        else:
            sim_score = 0.0

        # 4. Transaction recency exponential decay (half-life ~250 days)
        if comparables_count > 0 and median_age_days is not None:
            age_d = max(0.0, float(median_age_days))
            recency_score = math.exp(-age_d / 365.0)
            if age_d > 365.0:
                reasons.append(f"Available evidence is aged (median {int(age_d)} days old).")
        else:
            recency_score = 0.0

        # 5. Source reliability score
        if source_categories:
            rel_vals = [SOURCE_RELIABILITY_WEIGHTS.get(cat, 0.25) for cat in source_categories]
            source_score = float(np.mean(rel_vals))
            if source_score < 0.60:
                reasons.append("Evidence relies on benchmarks, estimates, or unverified listings rather than registered deeds.")
        else:
            source_score = 0.20
            reasons.append("Using category baseline without verified transaction provenance.")

        # 6. Data completeness across Priority 1 & 2 attributes
        comp_ratio = max(0.0, min(1.0, observed_critical_fields / max(1, total_critical_fields)))
        if comp_ratio < 0.80:
            reasons.append(
                f"Property input completeness is {round(comp_ratio * 100)}% ({observed_critical_fields}/{total_critical_fields} critical fields)."
            )

        components = {
            "comparable_count_score": round(count_score, 3),
            "geographic_distance_score": round(dist_score, 3),
            "property_similarity_score": round(sim_score, 3),
            "transaction_recency_score": round(recency_score, 3),
            "source_reliability_score": round(source_score, 3),
            "data_completeness_score": round(comp_ratio, 3),
        }

        composite = round(sum(EVIDENCE_WEIGHTS[k] * v for k, v in components.items()), 3)

        if comparables_count == 0 or composite < 0.35:
            tier = "INSUFFICIENT_EVIDENCE"
        elif composite >= 0.78 and comparables_count >= 3 and source_score >= 0.75:
            tier = "HIGH"
        elif composite >= 0.55:
            tier = "MODERATE"
        else:
            tier = "LOW"

        return {
            "composite_confidence_score": composite,
            "confidence_tier": tier,
            "score_components": components,
            "component_weights": EVIDENCE_WEIGHTS,
            "reasons_for_low_confidence": reasons,
        }

    def compute_calibrated_interval(
        self,
        point_estimate: float,
        holdout_abs_pct_errors: List[float],
        confidence_level: float = 0.90,
        min_calibration_samples: int = 10,
    ) -> Dict[str, Any]:
        """
        Produces statistically calibrated conformal prediction intervals ONLY when enough
        independent ground-truth holdout residuals exist (`n >= min_calibration_samples`).
        Returns INSUFFICIENT_EVIDENCE instead of fabricating arbitrary error percentages.
        """
        n = len(holdout_abs_pct_errors)
        limitations: List[str] = []

        if n < min_calibration_samples:
            limitations.append(
                f"Only {n} independent verified holdout transactions available for calibration "
                f"(minimum {min_calibration_samples} required for a {int(confidence_level * 100)}% empirical quantile)."
            )
            return {
                "point_estimate": round(float(point_estimate), 0),
                "lower_estimate": None,
                "upper_estimate": None,
                "confidence_level": None,
                "status": "INSUFFICIENT_EVIDENCE",
                "calibration_sample_count": n,
                "empirical_quantile_margin_pct": None,
                "evidence_limitations": limitations,
            }

        errs = np.sort(np.abs(np.array(holdout_abs_pct_errors, dtype=float)))
        # Finite-sample conformal quantile level: ceil((n + 1) * conf) / n
        q_level = min(1.0, math.ceil((n + 1) * confidence_level) / n)
        margin_pct = float(np.quantile(errs, q_level))

        lower = round(float(point_estimate) * max(0.05, 1.0 - margin_pct), 0)
        upper = round(float(point_estimate) * (1.0 + margin_pct), 0)

        return {
            "point_estimate": round(float(point_estimate), 0),
            "lower_estimate": lower,
            "upper_estimate": upper,
            "confidence_level": confidence_level,
            "status": "CALIBRATED_ON_INDEPENDENT_HOLDOUT",
            "calibration_sample_count": n,
            "empirical_quantile_margin_pct": round(margin_pct * 100.0, 2),
            "evidence_limitations": limitations,
        }
