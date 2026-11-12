"""
Cluster 7: Property Physical Attributes & Title Features.
Captures unit layout, carpet area, floor height ratio, developer quality grade,
and legal title encumbrance status.
"""
from typing import Dict, Any


class PhysicalAttributeFeatureExtractor:
    """Extracts property structural, dimensional, quality, and legal attributes."""

    def extract(self, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        overrides = overrides or {}

        carpet_area = float(overrides.get("carpet_area_sqft", 950.0))
        bhk = float(overrides.get("bhk_count", 2.0))
        floor = int(overrides.get("floor_number", 12))
        total_floors = int(overrides.get("total_floors", 24))
        age_years = float(overrides.get("property_age_years", 4.5))
        grade = str(overrides.get("construction_grade", "Grade_A")) # Grade_A, Grade_B, Grade_C
        title_clear = int(overrides.get("clear_title_flag", 1))      # 1 = clean title, 0 = encumbered
        orientation = str(overrides.get("orientation", "East"))      # North, East, South, West

        # Relative floor height premium (higher floor in Indian high-rises commands premium for air/light/view)
        floor_relative_ratio = floor / max(total_floors, 1)

        features = {
            "carpet_area_sqft": carpet_area,
            "bhk_count": bhk,
            "floor_number": floor,
            "total_floors": total_floors,
            "floor_relative_ratio": round(floor_relative_ratio, 3),
            "property_age_years": age_years,
            "construction_grade": grade,
            "clear_title_flag": title_clear,
            "property_orientation": orientation,
            "sqft_per_bhk": round(carpet_area / max(bhk, 1.0), 1),
        }

        return features
