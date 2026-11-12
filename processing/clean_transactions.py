"""
Data Cleaning & Schema Transformation Module.
Standardizes property transaction and benchmark observation records,
normalizes dates, filters invalid rows, and prepares data for feature assembly.
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from processing.normalize_units import normalize_area_to_sqft
from processing.validate_coordinates import validate_coordinates


VALID_PROPERTY_CATEGORIES = {
    "apartment": ["apartment", "flat", "high_rise", "condo"],
    "independent_house": ["independent_house", "house", "villa", "bungalow", "builder_floor", "standalone_house"],
    "residential_land": ["residential_land", "plot", "land", "residential_plot"],
    "commercial": ["commercial", "commercial_retail", "commercial_office", "retail", "shop", "office", "warehouse"],
    "agricultural": ["agricultural", "agricultural_land", "farmland", "farm_land"],
    "industrial": ["industrial", "industrial_land", "industrial_plot", "factory"],
    "rental": ["rental", "lease", "rent"]
}


def map_property_category(category_raw: str) -> str:
    """Normalizes any property category string to one of the 7 official classes."""
    c = str(category_raw).lower().strip().replace(" ", "_")
    for standard_cat, aliases in VALID_PROPERTY_CATEGORIES.items():
        if c in aliases:
            return standard_cat
        for alias in aliases:
            if alias in c:
                return standard_cat
    return "apartment"


def clean_and_normalize_record(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Cleans an individual record, validates coordinates, normalizes area and currency.
    Returns cleaned dict or None if invalid.
    """
    # 1. Validate Coordinates
    lat = row.get("latitude")
    lon = row.get("longitude")
    country = str(row.get("country_code", "IN")).upper()
    coord_res = validate_coordinates(lat, lon, country)
    if not coord_res["is_valid"]:
        return None

    # 2. Normalize Area
    area_val = float(row.get("area_value", row.get("built_area_sqft", row.get("plot_area_sqft", 0.0))) or 0.0)
    area_unit = str(row.get("area_unit", "sqft"))
    state = row.get("state")
    area_sqft, area_sqm, normalized_unit = normalize_area_to_sqft(area_val, area_unit, state)

    if area_sqft <= 0:
        return None

    # 3. Target Price Validation
    price = float(row.get("price_inr", row.get("sale_price", row.get("monthly_rent", 0.0))) or 0.0)
    if price <= 0:
        return None

    # 4. Property Category Mapping
    category = map_property_category(row.get("property_type", row.get("asset_type", "apartment")))

    # 5. Cleaned Output Record
    cleaned = dict(row)
    cleaned["latitude"] = coord_res["sanitized_lat"]
    cleaned["longitude"] = coord_res["sanitized_lon"]
    cleaned["area_sqft"] = area_sqft
    cleaned["area_sqm"] = area_sqm
    cleaned["original_area_value"] = area_val
    cleaned["original_area_unit"] = normalized_unit
    cleaned["property_category"] = category
    cleaned["price_inr"] = price
    cleaned["price_per_sqft"] = round(price / max(area_sqft, 1.0), 2)
    cleaned["log_price"] = float(np.log1p(price))
    cleaned["log_price_per_sqft"] = float(np.log1p(price / max(area_sqft, 1.0)))
    cleaned["currency"] = str(row.get("currency", "INR")).upper()
    cleaned["country_code"] = country
    cleaned["target_type"] = str(row.get("target_type", "registered_transaction_price"))
    cleaned["source_id"] = str(row.get("source_id", "internal_registry"))
    
    # Date standardization
    tx_date = row.get("transaction_date", row.get("date", datetime.now().strftime("%Y-%m-%d")))
    try:
        cleaned["transaction_date"] = pd.to_datetime(tx_date).strftime("%Y-%m-%d")
        cleaned["transaction_year"] = pd.to_datetime(tx_date).year
    except Exception:
        cleaned["transaction_date"] = datetime.now().strftime("%Y-%m-%d")
        cleaned["transaction_year"] = datetime.now().year

    return cleaned
