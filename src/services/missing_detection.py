"""
Missing Feature Detection & Imputation Service.
Audits harvested location intelligence and user inputs across the 10 specialist clusters.
Distinguishes between Essential user-prompted features (e.g. built area) and
Imputable secondary features (e.g. proxy noise dB, median building age).
Prevents zero-imputation and safely flags unavailable specialist models.
"""
from typing import Dict, Any, List, Set
from pathlib import Path
import yaml
import numpy as np

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "schema.yaml"
if CONFIG_PATH.exists():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        SCHEMA = yaml.safe_load(f)
else:
    SCHEMA = {"clusters": {}}


class MissingFeatureDetectionService:
    """Audits incoming features against the 10 specialist models and handles imputation."""

    # Essential fields that cannot be imputed and require user input
    ESSENTIAL_FIELDS = {
        "residential": {"built_area_sqm"},
        "commercial": {"built_area_sqm"},
        "land": {"land_area_sqm"},
    }

    # Documented cohort default imputations when external providers lack data
    COHORT_DEFAULTS = {
        "building_height_est_m": 24.0,
        "building_coverage_ratio_250m": 0.40,
        "built_up_change_3y": 0.05,
        "vegetation_index_250m": 0.25,
        "impervious_surface_250m": 0.60,
        "night_light_intensity": 45.0,
        "traffic_weekday_weekend_ratio": 1.15,
        "traffic_monthly_growth": 0.04,
        "heavy_vehicle_share": 0.12,
        "pedestrian_count": 300,
        "congestion_index": 0.50,
        "noise_db_proxy": 68.0,
        "pollution_pm25": 45.0,
        "population_growth_5y": 0.05,
        "daytime_population": 20000.0,
        "household_size_mean": 3.5,
        "education_access_score": 7.5,
        "inventory_months": 14.0,
        "days_on_market_median": 60,
        "property_age_years": 8.0,
        "floor_number": 3,
        "total_floors": 15,
        "construction_quality_code": "GRADE_B",
        "condition_code": "GOOD",
        "parking_spaces": 1,
        "elevator": 1,
        "frontage_m": 12.0,
        "road_access_type": "PAVED_TWO_LANE",
        "project_status_code": "APPROVED",
        "expected_completion_years": 2.5,
        "smart_city_flag": 1,
        "gross_rental_yield": 0.038,
        "vacancy_rate_area": 0.05,
        "rent_growth_1y": 0.055,
        "repeat_sale_return": 0.075,
    }

    def audit_and_impute(
        self,
        features: Dict[str, Any],
        asset_type: str = "residential"
    ) -> Dict[str, Any]:
        """
        Scans all 10 clusters, categorizes missing fields, performs documented imputation,
        and determines which specialist models are eligible to score.
        """
        norm_asset = str(asset_type).lower().strip()
        essential_reqs = self.ESSENTIAL_FIELDS.get(norm_asset, {"built_area_sqm"})

        missing_essential = [k for k in essential_reqs if k not in features or features[k] is None or features[k] <= 0]

        cluster_audits = {}
        imputed_features = dict(features)
        total_schema_fields = 0
        total_available_fields = 0

        clusters = SCHEMA.get("clusters", {})
        for cluster_name, field_list in clusters.items():
            avail = []
            miss = []
            for f in field_list:
                total_schema_fields += 1
                if f in features and features[f] is not None and features[f] != "":
                    avail.append(f)
                    total_available_fields += 1
                else:
                    miss.append(f)
                    # Apply documented model imputation if available
                    if f in self.COHORT_DEFAULTS:
                        imputed_features[f] = self.COHORT_DEFAULTS[f]

            # Specialist sufficiency rule: must have at least 1 primary signal
            is_model_eligible = len(avail) >= 1
            cluster_audits[cluster_name] = {
                "available_features": avail,
                "missing_features": miss,
                "completeness_ratio": round(len(avail) / max(len(field_list), 1), 2),
                "model_status": "active" if is_model_eligible else "unavailable",
            }

        completeness_score = round((total_available_fields / max(total_schema_fields, 1)) * 100.0, 1)

        return {
            "is_valid_for_valuation": len(missing_essential) == 0,
            "missing_essential_user_fields": missing_essential,
            "data_completeness_pct": completeness_score,
            "cluster_audits": cluster_audits,
            "imputed_features": imputed_features,
        }
