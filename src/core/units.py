"""
Unit and Currency Standardization Core.
Converts area units (sq ft, sq m, acres, hectares) to standard square meters (sqm)
and provides safe currency display across global jurisdictions.
"""
from typing import Union, Tuple

SQFT_TO_SQM = 0.092903
ACRE_TO_SQM = 4046.856422
HECTARE_TO_SQM = 10000.0


def convert_area_to_sqm(value: float, unit: str) -> float:
    """Converts input area to standard metric square meters (sqm)."""
    if value is None or value <= 0:
        return 0.0
    u = str(unit).lower().strip()
    if u in ["sqft", "sq ft", "square_feet", "sq_ft", "feet"]:
        return round(value * SQFT_TO_SQM, 2)
    elif u in ["acre", "acres"]:
        return round(value * ACRE_TO_SQM, 2)
    elif u in ["hectare", "hectares", "ha"]:
        return round(value * HECTARE_TO_SQM, 2)
    elif u in ["sqm", "sq m", "square_meters", "sq_m", "meter", "m2"]:
        return round(float(value), 2)
    else:
        # Default assume sqm if unknown
        return round(float(value), 2)


def convert_sqm_to_local(sqm: float, target_unit: str = "sqft") -> float:
    """Converts standard sqm to user-requested display unit."""
    if sqm is None or sqm <= 0:
        return 0.0
    u = str(target_unit).lower().strip()
    if u in ["sqft", "sq ft", "square_feet"]:
        return round(sqm / SQFT_TO_SQM, 2)
    elif u in ["acre", "acres"]:
        return round(sqm / ACRE_TO_SQM, 4)
    elif u in ["hectare", "hectares", "ha"]:
        return round(sqm / HECTARE_TO_SQM, 4)
    return round(float(sqm), 2)


def format_currency(amount: float, currency_code: str = "INR") -> str:
    """Formats amount according to local currency conventions without charmap errors."""
    code = str(currency_code).upper().strip()
    if code == "INR":
        if abs(amount) >= 1e7:
            return f"Rs. {amount / 1e7:.2f} Cr"
        elif abs(amount) >= 1e5:
            return f"Rs. {amount / 1e5:.2f} L"
        else:
            return f"Rs. {amount:,.0f}"
    elif code == "USD":
        if abs(amount) >= 1e6:
            return f"${amount / 1e6:.2f}M"
        return f"${amount:,.0f}"
    elif code == "GBP":
        if abs(amount) >= 1e6:
            return f"GBP {amount / 1e6:.2f}M"
        return f"GBP {amount:,.0f}"
    elif code == "EUR":
        if abs(amount) >= 1e6:
            return f"EUR {amount / 1e6:.2f}M"
        return f"EUR {amount:,.0f}"
    else:
        return f"{code} {amount:,.0f}"
