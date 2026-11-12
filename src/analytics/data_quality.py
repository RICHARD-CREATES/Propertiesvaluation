"""
Module 1: Indian Real Estate Data Quality Intelligence (src/analytics/data_quality.py).

Reuses:
- src/core/units.py (area conversions & currency standardization)
- src/services/missing_detection.py (essential vs secondary missing audit)
- src/core/ground_truth_db.py (dedup fingerprinting)

Provides:
- Unit normalization to standard INR & square feet (sqft, sqm, sqyard/gaj, acre, hectare)
- Indian RERA / physical consistency validation (Carpet <= Built-Up, UDS bounds, Construction Age >= Remodel Age >= 0)
- Semantic separation of MISSING_UNKNOWN vs ABSENT_AMENITY (never corrupts absent amenities with mode fill)
- Non-destructive IQR and Modified-Z (MAD) outlier flagging (retains legitimate luxury/distress records)
- Location & India GPS boundary consistency checks + non-destructive duplicate detection
"""
import math
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from src.core.ground_truth_db import compute_dedup_signature
from src.core.units import ACRE_TO_SQM, HECTARE_TO_SQM, SQFT_TO_SQM, convert_area_to_sqm, convert_sqm_to_local
from src.services.location_intelligence import LocationIntelligenceService
from src.services.missing_detection import MissingFeatureDetectionService


AMENITY_ABSENCE_MARKERS = {"none", "absent", "no", "na", "n/a", "0", "false", "no_parking", "open"}
MISSING_UNKNOWN_MARKERS = {"", "nan", "null", "unknown", "?", "missing", "unreported"}

CANONICAL_PROPERTY_TYPES = {
    "flat": "apartment",
    "condo": "apartment",
    "apartment": "apartment",
    "high_rise": "apartment",
    "house": "standalone_house",
    "standalone_house": "standalone_house",
    "independent_house": "standalone_house",
    "villa": "villa",
    "bungalow": "villa",
    "builder_floor": "builder_floor",
    "office": "commercial",
    "retail": "commercial",
    "commercial": "commercial",
    "warehouse": "commercial",
    "land": "residential_land",
    "plot": "residential_land",
    "residential_land": "residential_land",
    "agricultural": "agricultural",
    "industrial": "industrial",
    "rental": "rental",
}


def normalize_area_to_sqft(value: Any, unit: str = "sqft") -> Optional[float]:
    """Converts sqft, sqm, sqyard/gaj, acre, hectare, or decimal to square feet reusing units.py."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    val = float(value)
    if val <= 0.0:
        return val  # Preserve <= 0 so impossible-measurement validator flags it explicitly

    u = str(unit or "sqft").lower().strip()
    if u in ("sqft", "sq ft", "sq_ft", "square_feet", "feet"):
        return round(val, 2)
    if u in ("sqyard", "sqyards", "sq_yard", "gaj"):
        return round(val * 9.0, 2)
    if u in ("decimal", "dec"):
        # Standard Indian land unit: 1 decimal = 435.6 sq ft (1/100 acre)
        return round(val * 435.6, 2)
    sqm = convert_area_to_sqm(val, u)
    return round(convert_sqm_to_local(sqm, "sqft"), 2)


def classify_field_presence(val: Any, is_amenity: bool = False) -> str:
    """
    Distinguishes MISSING_UNKNOWN from ABSENT_AMENITY vs PRESENT.
    Prevents semantic corruption where 'No Parking' or 'None' gets imputed with a mode.
    """
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "MISSING_UNKNOWN"
    s = str(val).strip().lower()
    if s in MISSING_UNKNOWN_MARKERS:
        return "MISSING_UNKNOWN"
    if is_amenity and (s in AMENITY_ABSENCE_MARKERS or val == 0 or val is False):
        return "ABSENT_AMENITY"
    return "PRESENT"


def normalize_currency_to_inr(amount: Any, currency: str = "INR") -> Optional[float]:
    """Validates currency is INR (including standard INR Lakh/Crore multipliers) without fabricating FX rates."""
    if amount is None or (isinstance(amount, float) and not math.isfinite(amount)):
        return None
    val = float(amount)
    c = str(currency or "INR").upper().strip()
    if c == "INR":
        return round(val, 2)
    if c in ("INR_LAKH", "LAKH", "LAKHS", "L"):
        return round(val * 100_000.0, 2)
    if c in ("INR_CRORE", "CRORE", "CRORES", "CR"):
        return round(val * 10_000_000.0, 2)
    raise ValueError(f"Unsupported non-INR currency '{c}' for Indian analytics standardization without live FX rate.")


def _first_present(raw: Dict[str, Any], *keys: str) -> Any:
    """Returns the first key present with a non-None, finite value (safely preserves numeric 0)."""
    for k in keys:
        if k in raw:
            v = raw[k]
            if v is None:
                continue
            if isinstance(v, float) and not math.isfinite(v):
                continue
            return v
    return None


class IndianPropertyDataQualityAuditor:
    """Audits DataFrames or record lists for schema, physical RERA logic, missing semantics, duplicates, and outliers."""

    def __init__(self):
        self.missing_service = MissingFeatureDetectionService()
        self.loc_service = LocationIntelligenceService()

    def validate_single_record(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Validates a single property record against Indian physical, legal, and spatial constraints."""
        issues: List[str] = []
        warnings: List[str] = []

        prop_raw = str(raw.get("property_type") or "").lower().strip()
        prop_type = CANONICAL_PROPERTY_TYPES.get(prop_raw)
        if not prop_type:
            issues.append(f"Invalid or unsupported property_type '{raw.get('property_type')}'.")

        area_unit = str(_first_present(raw, "area_unit") or "sqft")
        raw_builtup = _first_present(raw, "builtup_area_sqft", "area_sqft", "area_value")
        builtup = normalize_area_to_sqft(raw_builtup, area_unit)
        carpet = normalize_area_to_sqft(_first_present(raw, "carpet_area_sqft"), area_unit)
        plot = normalize_area_to_sqft(_first_present(raw, "plot_area_sqft"), area_unit)
        uds = normalize_area_to_sqft(_first_present(raw, "uds_sqft"), area_unit)

        # Price normalization
        price_val = _first_present(raw, "sale_price", "price_inr")
        currency_val = str(_first_present(raw, "currency") or "INR")
        price_inr = normalize_currency_to_inr(price_val, currency_val)

        if price_inr is None:
            issues.append("Missing price_inr / sale_price.")
        elif price_inr <= 0.0:
            issues.append(f"Impossible non-positive price ({price_inr} INR).")

        # Area checks
        if prop_type == "residential_land":
            effective_area = plot if plot is not None else builtup
            if effective_area is None or effective_area <= 0.0:
                issues.append("Vacant residential land requires positive plot_area_sqft.")
        else:
            effective_area = builtup if builtup is not None else carpet
            if effective_area is None or effective_area <= 0.0:
                issues.append("Built property requires positive builtup_area_sqft or carpet_area_sqft.")

        # RERA Rule: Carpet area cannot exceed Built-up area
        if carpet is not None:
            if carpet <= 0.0:
                issues.append(f"Impossible non-positive carpet_area_sqft ({carpet}).")
            elif builtup is not None and builtup > 0.0 and carpet > builtup * 1.02:
                issues.append(f"Impossible physical ratio: carpet_area_sqft ({carpet}) exceeds builtup_area_sqft ({builtup}).")

        # UDS (Undivided Share of Land) checks for apartments
        if uds is not None:
            if uds <= 0.0:
                issues.append(f"Impossible non-positive uds_sqft ({uds}).")
            elif prop_type == "apartment" and builtup is not None and builtup > 0 and uds > builtup * 1.5:
                warnings.append(f"Unusually high apartment UDS ({uds} sqft vs built-up {builtup} sqft).")

        # Construction age vs Renovation age checks
        age = raw.get("construction_age_years") if raw.get("construction_age_years") is not None else raw.get("property_age_years")
        remodel_age = raw.get("remodel_age_years")
        if age is not None:
            age_f = float(age)
            if age_f < 0.0 or age_f > 150.0:
                issues.append(f"Impossible construction_age_years ({age_f}). Expected [0, 150].")
            if remodel_age is not None:
                rem_f = float(remodel_age)
                if rem_f < 0.0:
                    issues.append(f"Impossible negative remodel_age_years ({rem_f}).")
                elif rem_f > age_f:
                    issues.append(f"Inconsistent ages: remodel_age_years ({rem_f}) exceeds construction_age_years ({age_f}).")

        # Location & India bounds consistency
        lat = raw.get("latitude")
        lon = raw.get("longitude")
        country = str(raw.get("country_code", "IN")).upper().strip()
        if lat is None or lon is None:
            issues.append("Missing GPS latitude/longitude.")
        else:
            lat_f, lon_f = float(lat), float(lon)
            if not self.loc_service.validate_coordinates(lat_f, lon_f):
                issues.append(f"Invalid global GPS coordinates ({lat_f}, {lon_f}).")
            elif country == "IN" and not self.loc_service.is_in_india_bounds(lat_f, lon_f):
                issues.append(f"Location inconsistency: country='IN' but GPS ({lat_f}, {lon_f}) lies outside India bounding box.")

        # Semantic presence audit (Amenities vs Missing)
        amenity_status = {
            "parking": classify_field_presence(_first_present(raw, "parking_slots", "parking"), is_amenity=True),
            "elevator": classify_field_presence(_first_present(raw, "elevator"), is_amenity=True),
            "furnishing": classify_field_presence(_first_present(raw, "furnishing"), is_amenity=False),
            "carpet_area": classify_field_presence(_first_present(raw, "carpet_area_sqft"), is_amenity=False),
        }

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "normalized_property_type": prop_type,
            "normalized_area_sqft": effective_area,
            "normalized_price_inr": price_inr,
            "price_per_sqft_inr": round(price_inr / effective_area, 2) if (price_inr and effective_area and effective_area > 0) else None,
            "semantic_field_status": amenity_status,
        }

    def detect_outliers_iqr_and_mad(
        self,
        values: List[float],
        mad_threshold: float = 3.5,
        iqr_multiplier: float = 1.5,
    ) -> Dict[str, Any]:
        """
        Detects outliers non-destructively using BOTH IQR and Modified Z-Score (MAD).
        Never deletes extreme points automatically; returns boolean flags and thresholds.
        """
        arr = np.asarray(values, dtype=float)
        n = len(arr)
        if n < 4:
            return {
                "sample_count": n,
                "status": "INSUFFICIENT_SAMPLES_FOR_OUTLIER_DETECTION",
                "iqr_flags": [False] * n,
                "mad_flags": [False] * n,
                "combined_outlier_flags": [False] * n,
                "bounds": None,
            }

        q1 = float(np.percentile(arr, 25))
        med = float(np.median(arr))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1

        iqr_low = q1 - iqr_multiplier * iqr
        iqr_high = q3 + iqr_multiplier * iqr
        iqr_flags = [(float(x) < iqr_low or float(x) > iqr_high) for x in arr]

        abs_dev = np.abs(arr - med)
        mad = float(np.median(abs_dev))
        if mad > 1e-9:
            # 0.6745 scales MAD to match normal distribution standard deviation
            mod_z = 0.6745 * (arr - med) / mad
            mad_flags = [abs(float(z)) > mad_threshold for z in mod_z]
        else:
            mad_flags = [False] * n

        combined = [a or b for a, b in zip(iqr_flags, mad_flags)]

        return {
            "sample_count": n,
            "status": "COMPUTED",
            "median": round(med, 2),
            "q1": round(q1, 2),
            "q3": round(q3, 2),
            "iqr": round(iqr, 2),
            "mad": round(mad, 2),
            "iqr_bounds": [round(iqr_low, 2), round(iqr_high, 2)],
            "mad_threshold": mad_threshold,
            "iqr_flags": iqr_flags,
            "mad_flags": mad_flags,
            "combined_outlier_flags": combined,
            "flagged_count": sum(combined),
            "handling_policy": "Flagged for human/domain review; legitimate luxury/distress records are never deleted.",
        }

    def audit_dataset(self, df: Any) -> Dict[str, Any]:
        """Performs full staging audit on a DataFrame or list of dicts: schema, impossible values, duplicates, missing semantics, outliers."""
        records = df.to_dict(orient="records") if isinstance(df, pd.DataFrame) else list(df)
        valid_count = 0
        invalid_records = []
        signatures: Dict[str, int] = {}
        duplicate_indices: List[int] = []
        valid_pps_indices: List[int] = []
        valid_pps_values: List[float] = []
        absent_vs_missing_summary = {"MISSING_UNKNOWN": 0, "ABSENT_AMENITY": 0, "PRESENT": 0}

        for idx, rec in enumerate(records):
            res = self.validate_single_record(rec)
            for status_val in res["semantic_field_status"].values():
                absent_vs_missing_summary[status_val] = absent_vs_missing_summary.get(status_val, 0) + 1

            if res["is_valid"]:
                valid_count += 1
                if res["price_per_sqft_inr"] is not None:
                    valid_pps_indices.append(idx)
                    valid_pps_values.append(res["price_per_sqft_inr"])
                sig = compute_dedup_signature(
                    res["normalized_property_type"],
                    float(rec["latitude"]),
                    float(rec["longitude"]),
                    float(res["normalized_price_inr"]),
                    str(rec.get("transaction_date", "unknown"))[:10],
                    res["normalized_area_sqft"],
                )
                if sig in signatures:
                    duplicate_indices.append(idx)
                else:
                    signatures[sig] = idx
            else:
                invalid_records.append({"row_index": idx, "issues": res["issues"]})

        outlier_audit = self.detect_outliers_iqr_and_mad(valid_pps_values)

        return {
            "total_rows": len(records),
            "valid_rows": valid_count,
            "invalid_rows_count": len(invalid_records),
            "invalid_row_details": invalid_records[:25],
            "duplicate_rows_detected": len(duplicate_indices),
            "duplicate_row_indices": duplicate_indices[:25],
            "semantic_presence_counts": absent_vs_missing_summary,
            "price_per_sqft_outlier_audit": {
                "status": outlier_audit["status"],
                "flagged_count": outlier_audit.get("flagged_count", 0),
                "iqr_bounds": outlier_audit.get("iqr_bounds"),
                "mad": outlier_audit.get("mad"),
                "handling_policy": outlier_audit.get("handling_policy"),
            },
        }
