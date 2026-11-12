"""
CPWD & State PWD Construction Cost Estimation Engine.
Calculates:
1. Historical construction cost ("Cost of the house created/built") based on year of construction.
2. Replacement construction cost today (what it would cost to build brand new today).
3. Structural depreciation curves based on building age.
4. Separate land value vs structure value for Standalone Houses / Bungalows.
"""
from typing import Dict, Any, Tuple
import numpy as np


class ConstructionCostEngine:
    """
    Computes engineering construction costs based on CPWD (Central Public Works Department)
    and State PWD plinth area rates across India.
    """

    # Base 2026 construction rate in INR per sqft by construction quality grade
    BASE_RATES_2026_SQFT = {
        "GRADE_A": 2650.0,  # RCC framed, premium vitrified tiles, teakwood doors, concealed wiring/plumbing
        "GRADE_B": 1950.0,  # Standard RCC framed, ceramic tiles, standard fittings
        "GRADE_C": 1350.0,  # Load bearing or basic RCC, cement/mosaic floor, standard brickwork
    }

    # Historical CPWD Construction Cost Inflation Index (normalized to 2026 = 1.0)
    # Reflects steel, cement, sand, brick, and labor inflation in India over the past 30 years
    HISTORICAL_INDEX = {
        0: 1.00,    # 2026 (New)
        1: 0.94,    # 2025
        2: 0.88,    # 2024
        3: 0.82,    # 2023
        5: 0.72,    # 2021
        7: 0.63,    # 2019
        10: 0.52,   # 2016
        15: 0.38,   # 2011
        20: 0.28,   # 2006
        25: 0.20,   # 2001
        30: 0.14,   # 1996
    }

    def get_historical_factor(self, age_years: float) -> float:
        age = max(0.0, float(age_years))
        if age in self.HISTORICAL_INDEX:
            return self.HISTORICAL_INDEX[age]
        # Interpolate
        keys = sorted(self.HISTORICAL_INDEX.keys())
        for i in range(len(keys) - 1):
            if keys[i] <= age <= keys[i + 1]:
                t = (age - keys[i]) / (keys[i + 1] - keys[i])
                return self.HISTORICAL_INDEX[keys[i]] * (1.0 - t) + self.HISTORICAL_INDEX[keys[i + 1]] * t
        return 0.10

    def compute_cost_breakdown(
        self,
        built_area_sqft: float,
        structure_type: str = "apartment",  # "standalone_house", "apartment", "builder_floor"
        property_age_years: float = 5.0,
        construction_grade: str = "GRADE_B",
        plot_area_sqft: float = 0.0,
        current_land_rate_sqft: float = 5000.0,
    ) -> Dict[str, Any]:
        """
        Computes:
        - Cost to create/build originally (historical construction cost)
        - Cost to recreate today (replacement cost)
        - Structure depreciated value
        - Land component vs Building component
        """
        grade = str(construction_grade).upper()
        if grade not in self.BASE_RATES_2026_SQFT:
            grade = "GRADE_B"

        rate_today_sqft = self.BASE_RATES_2026_SQFT[grade]
        hist_factor = self.get_historical_factor(property_age_years)
        rate_historical_sqft = round(rate_today_sqft * hist_factor, 1)

        # 1. Structure Construction Cost
        historical_construction_cost = round(built_area_sqft * rate_historical_sqft, 0)
        replacement_cost_today = round(built_area_sqft * rate_today_sqft, 0)

        # 2. Structural Depreciation (life of RCC building ~ 60 years)
        # Using standard straight-line with 10% salvage value
        depreciation_pct = min(0.65, (property_age_years / 60.0) * 0.90)
        depreciated_structure_value_today = round(replacement_cost_today * (1.0 - depreciation_pct), 0)

        # 3. Land Component (Crucial for Standalone Houses & Plots)
        is_standalone = structure_type in ["standalone_house", "independent_house", "villa", "bungalow"]
        
        if is_standalone:
            # Standalone house has exclusive land ownership!
            effective_plot_sqft = plot_area_sqft if plot_area_sqft > 0 else (built_area_sqft * 1.25)
            # Historical land cost basis (approximated based on historical land growth)
            hist_land_rate_sqft = current_land_rate_sqft * (hist_factor ** 1.3)
            historical_land_cost = round(effective_plot_sqft * hist_land_rate_sqft, 0)
            current_land_market_value = round(effective_plot_sqft * current_land_rate_sqft, 0)
        else:
            # Apartment in a high-rise has undivided share of land (UDS ~ 25-35% of built area)
            effective_plot_sqft = built_area_sqft * 0.28
            historical_land_cost = round(effective_plot_sqft * (current_land_rate_sqft * hist_factor), 0)
            current_land_market_value = round(effective_plot_sqft * current_land_rate_sqft, 0)

        # Total Original Cost to Create = Historical Structure Construction + Historical Land Basis
        total_original_creation_cost = historical_construction_cost + historical_land_cost

        return {
            "structure_type": structure_type,
            "built_area_sqft": built_area_sqft,
            "plot_area_sqft": effective_plot_sqft if is_standalone else None,
            "construction_grade": grade,
            "property_age_years": property_age_years,
            "rate_historical_per_sqft": rate_historical_sqft,
            "rate_today_per_sqft": rate_today_sqft,
            "historical_structure_cost": historical_construction_cost,
            "historical_land_cost": historical_land_cost,
            "total_creation_cost_original": total_original_creation_cost,
            "replacement_cost_new_today": replacement_cost_today,
            "depreciated_structure_value_today": depreciated_structure_value_today,
            "current_land_market_value": current_land_market_value,
            "depreciation_pct": round(depreciation_pct * 100.0, 1),
        }
