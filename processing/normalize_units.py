"""
State-Specific Indian Land & Built-Up Area Normalization Engine.
Translates regional Indian measurement units into standard Square Feet (sqft)
and Square Meters (sqm) while strictly preserving original values and state contexts.
"""
from typing import Tuple, Dict, Any, Optional

# Standard conversion constants to Square Feet (sqft)
UNIVERSAL_UNITS_TO_SQFT: Dict[str, float] = {
    "sqft": 1.0,
    "sq_ft": 1.0,
    "square_feet": 1.0,
    "sqm": 10.7639104,
    "sq_m": 10.7639104,
    "square_meters": 10.7639104,
    "acre": 43560.0,
    "acres": 43560.0,
    "hectare": 107639.104,
    "hectares": 107639.104,
    "sqyard": 9.0,
    "sq_yard": 9.0,
    "sq_yards": 9.0,
    "gaj": 9.0,
    "decimal": 435.6,
    "cent": 435.6,
    "ground": 2400.0,       # Standard Chennai / TN (1 ground = 2400 sq ft)
    "marla": 272.25,        # Punjab / Haryana
    "kanal": 5445.0,        # Punjab / Haryana (1 kanal = 20 marla)
}

# State-Specific Regional Unit Conversions to Square Feet
STATE_SPECIFIC_UNITS_TO_SQFT: Dict[str, Dict[str, float]] = {
    "ODISHA": {
        "guntha": 2400.0,       # In Odisha revenue standard, 1 Guntha = 2,400 sq ft (4 decimals)
        "bigha": 14400.0,       # 1 Bigha = 6 Guntha = 14,400 sq ft (some regions = 25 Guntha)
        "decimal": 435.6,
        "acre": 43560.0,
        "katha": 2880.0,
    },
    "MAHARASHTRA": {
        "guntha": 1089.0,       # 33 ft x 33 ft = 1,089 sq ft (1/40th acre)
        "bigha": 21780.0,       # Standard MH Bigha = 20 Gunthas
        "acre": 43560.0,
    },
    "GUJARAT": {
        "guntha": 1089.0,
        "bigha": 17424.0,       # Standard Gujarat Vigha = 16 Gunthas (~1,619 sqm)
        "acre": 43560.0,
    },
    "KARNATAKA": {
        "guntha": 1089.0,
        "cent": 435.6,
        "acre": 43560.0,
    },
    "UTTAR PRADESH": {
        "bigha": 27225.0,       # Standard Pucca Bigha = 3,025 sq yards = 27,225 sq ft
        "katha": 1361.25,       # 1/20th of a Bigha = 1,361.25 sq ft (also Biswa)
        "biswa": 1361.25,
        "biswansi": 68.0625,
        "gaj": 9.0,
    },
    "BIHAR": {
        "bigha": 27225.0,
        "katha": 1361.25,
        "dhur": 68.0625,
        "decimal": 435.6,
    },
    "WEST BENGAL": {
        "bigha": 14400.0,       # Standard Bengal Bigha = 14,400 sq ft = 1,337.8 sqm
        "katha": 720.0,         # 1/20th Bigha = 720 sq ft
        "chhatak": 45.0,
        "decimal": 435.6,
    },
    "TAMIL NADU": {
        "ground": 2400.0,
        "cent": 435.6,
        "acre": 43560.0,
        "guntha": 1089.0,
    },
    "KERALA": {
        "cent": 435.6,
        "acre": 43560.0,
    },
    "PUNJAB": {
        "gaj": 9.0,
        "marla": 272.25,
        "kanal": 5445.0,
        "bigha": 9075.0,
        "killa": 43560.0,       # 1 Killa = 8 Kanals = 1 Acre
    },
    "HARYANA": {
        "gaj": 9.0,
        "marla": 272.25,
        "kanal": 5445.0,
        "bigha": 9075.0,
        "killa": 43560.0,
    },
    "DELHI": {
        "gaj": 9.0,
        "sqyard": 9.0,
        "bigha": 9075.0,
        "biswa": 453.75,
    }
}


def normalize_area_to_sqft(
    value: float,
    unit: str,
    state: Optional[str] = None
) -> Tuple[float, float, str]:
    """
    Normalizes an area measurement into Square Feet and Square Meters.
    
    Args:
        value: Original numerical area value
        unit: Unit string (e.g. 'guntha', 'decimal', 'sqft', 'acre', 'gaj', 'bigha')
        state: State name or jurisdiction for regional unit disambiguation (e.g. 'Odisha', 'Maharashtra')
        
    Returns:
        (area_sqft, area_sqm, normalized_unit_name)
    """
    if value is None or value <= 0:
        return 0.0, 0.0, "sqft"

    clean_unit = str(unit).lower().strip().replace(" ", "_").replace("-", "_")
    clean_state = str(state).upper().strip() if state else None

    factor = None

    # 1. Check state-specific dictionary first
    if clean_state and clean_state in STATE_SPECIFIC_UNITS_TO_SQFT:
        factor = STATE_SPECIFIC_UNITS_TO_SQFT[clean_state].get(clean_unit)

    # 2. Check universal dictionary
    if factor is None:
        factor = UNIVERSAL_UNITS_TO_SQFT.get(clean_unit)

    # 3. Default fallback for standard regional units if state not provided
    if factor is None:
        if clean_unit == "guntha":
            factor = 1089.0  # National standard (33x33 ft)
        elif clean_unit == "bigha":
            factor = 14400.0 # Common standard
        elif clean_unit in ["katha", "biswa"]:
            factor = 1361.25
        else:
            factor = 1.0     # Default assumes square feet

    area_sqft = round(float(value) * factor, 2)
    area_sqm = round(area_sqft * 0.09290304, 2)

    return area_sqft, area_sqm, clean_unit
