"""
Geospatial Coordinate Validation & Administrative Boundary Checker.
Validates GPS coordinates and verifies geographical boundaries for India.
"""
from typing import Tuple, Dict, Any, Optional

# Official geographic bounding box for the Republic of India (including island territories)
INDIA_GEO_BOUNDS = {
    "min_lat": 6.75,     # Indira Point, Great Nicobar
    "max_lat": 37.10,    # Northern Jammu & Kashmir / Ladakh
    "min_lon": 68.10,    # Guhar Moti, Gujarat (Westernmost)
    "max_lon": 97.45,    # Kibithu, Arunachal Pradesh (Easternmost)
}

GLOBAL_BOUNDS = {
    "min_lat": -90.0,
    "max_lat": 90.0,
    "min_lon": -180.0,
    "max_lon": 180.0
}


def validate_coordinates(
    lat: float,
    lon: float,
    country_code: str = "IN"
) -> Dict[str, Any]:
    """
    Validates latitude and longitude values.
    
    Returns:
        dict containing 'is_valid', 'is_in_country', 'sanitized_lat', 'sanitized_lon', 'message'
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        return {
            "is_valid": False,
            "is_in_country": False,
            "sanitized_lat": None,
            "sanitized_lon": None,
            "message": "Coordinates must be valid numerical values."
        }

    # Check global validity
    if not (GLOBAL_BOUNDS["min_lat"] <= lat <= GLOBAL_BOUNDS["max_lat"] and
            GLOBAL_BOUNDS["min_lon"] <= lon <= GLOBAL_BOUNDS["max_lon"]):
        return {
            "is_valid": False,
            "is_in_country": False,
            "sanitized_lat": None,
            "sanitized_lon": None,
            "message": f"Coordinates ({lat}, {lon}) out of global range."
        }

    # If country is India, check territory bounding box
    is_in_india = (
        INDIA_GEO_BOUNDS["min_lat"] <= lat <= INDIA_GEO_BOUNDS["max_lat"] and
        INDIA_GEO_BOUNDS["min_lon"] <= lon <= INDIA_GEO_BOUNDS["max_lon"]
    )

    if country_code.upper() == "IN" and not is_in_india:
        return {
            "is_valid": True,
            "is_in_country": False,
            "sanitized_lat": round(lat, 6),
            "sanitized_lon": round(lon, 6),
            "message": f"Coordinates ({lat}, {lon}) lie outside territorial India bounding box."
        }

    return {
        "is_valid": True,
        "is_in_country": is_in_india if country_code.upper() == "IN" else True,
        "sanitized_lat": round(lat, 6),
        "sanitized_lon": round(lon, 6),
        "message": "Coordinates valid."
    }
