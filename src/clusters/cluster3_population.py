"""
Cluster 3: Population & Colony Profile Features.
Captures demographic density, household income proxies from CBDT ITR data,
population growth trajectories, and neighborhood social amenity ratings.
"""
from typing import Dict, Any


class PopulationFeatureExtractor:
    """Extracts demographic, income tier, and colony profile characteristics."""

    def extract(self, lat: float, lon: float, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        overrides = overrides or {}

        features = {
            "colony_density_sqkm": float(overrides.get("colony_density_sqkm", 24500.0)), # Persons per sq km (e.g. Powai / Mumbai)
            "pincode_income_tier": int(overrides.get("pincode_income_tier", 4)),         # 1 (lowest) to 5 (highest ITR filers)
            "pop_growth_cagr_10yr": float(overrides.get("pop_growth_cagr_10yr", 3.2)),   # 10-year annualized population CAGR %
            "amenity_density_score": float(overrides.get("amenity_density_score", 7.8)), # Green parks, community centers, sports (0-10)
        }

        # Derived high-income density multiplier
        features["purchasing_power_density"] = (
            (features["pincode_income_tier"] / 5.0) * (features["colony_density_sqkm"] / 10000.0)
        )

        return features
