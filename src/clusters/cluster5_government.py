"""
Cluster 5: Government Project Signals.
Captures public infrastructure investment, statutory RERA registration density,
Smart Cities Mission inclusion, and government housing scheme proximity.
"""
from typing import Dict, Any


class GovernmentSignalFeatureExtractor:
    """Extracts public policy, infra capex, and regulatory compliance density."""

    def extract(self, lat: float, lon: float, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        overrides = overrides or {}

        features = {
            "is_smart_city_mission": int(overrides.get("is_smart_city_mission", 1)),      # 1 if in Smart Cities Mission list
            "rera_projects_within_2km": int(overrides.get("rera_projects_within_2km", 18)), # Total RERA registered projects
            "rera_delayed_project_pct": float(overrides.get("rera_delayed_project_pct", 12.5)), # % projects with delayed revisions
            "pmay_affordable_zone_flag": int(overrides.get("pmay_affordable_zone_flag", 0)),   # 1 if in notified PMAY zone
            "public_infra_capex_cr": float(overrides.get("public_infra_capex_cr", 1450.0)),     # State capex on bridges/flyovers in Cr
        }

        # Regulatory reliability index (higher RERA density with lower delays = prime institutional development)
        clean_rera_ratio = 1.0 - (features["rera_delayed_project_pct"] / 100.0)
        features["institutional_dev_score"] = features["rera_projects_within_2km"] * clean_rera_ratio

        return features
