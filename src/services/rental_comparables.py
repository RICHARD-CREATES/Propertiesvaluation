"""
Comparable Rental Property Engine & Yield Intelligence Service.

Implements:
- Geospatial radius search (500m, 1km, 2km, 5km, 10km) using Haversine distance.
- Multi-factor similarity ranking (distance, property category, BHK, carpet area, furnishing, freshness).
- Strict separation between Verified Achieved Rents, Advertised Asking Rents, and Historical Benchmarks.
- Locality & property-type-specific rental yield intelligence (min, median, max, IQR, confidence).
- Rental income forecasting (1y, 3y, 5y across Conservative, Base, Optimistic scenarios, nominal vs real).
"""
from datetime import date
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from src.core.rental_db import RentalListing, SessionLocal, init_rental_db
from src.services.location_intelligence import haversine_km


# Evidence-based baseline cap-rate and gross-yield envelopes by Indian property category
# Used only when local comparable transaction density is below threshold (<3 comps), always disclosed.
CATEGORY_MARKET_BASELINES = {
    "apartment": {"gross_yield_pct": 3.8, "cap_rate_pct": 3.1, "vacancy_pct": 5.0, "opex_ratio_pct": 14.0, "grm": 26.3},
    "standalone_house": {"gross_yield_pct": 2.4, "cap_rate_pct": 1.9, "vacancy_pct": 4.0, "opex_ratio_pct": 15.0, "grm": 41.7},
    "villa": {"gross_yield_pct": 2.5, "cap_rate_pct": 2.0, "vacancy_pct": 5.0, "opex_ratio_pct": 16.0, "grm": 40.0},
    "builder_floor": {"gross_yield_pct": 3.3, "cap_rate_pct": 2.7, "vacancy_pct": 5.0, "opex_ratio_pct": 14.0, "grm": 30.3},
    "office": {"gross_yield_pct": 8.5, "cap_rate_pct": 7.6, "vacancy_pct": 7.0, "opex_ratio_pct": 12.0, "grm": 11.8},
    "retail": {"gross_yield_pct": 9.2, "cap_rate_pct": 8.2, "vacancy_pct": 6.0, "opex_ratio_pct": 11.0, "grm": 10.9},
    "warehouse": {"gross_yield_pct": 8.0, "cap_rate_pct": 7.1, "vacancy_pct": 8.0, "opex_ratio_pct": 10.0, "grm": 12.5},
    "industrial": {"gross_yield_pct": 8.2, "cap_rate_pct": 7.2, "vacancy_pct": 8.0, "opex_ratio_pct": 11.0, "grm": 12.2},
    "mixed_use": {"gross_yield_pct": 6.2, "cap_rate_pct": 5.4, "vacancy_pct": 6.0, "opex_ratio_pct": 13.0, "grm": 16.1},
}


def _normalize_property_category(prop_type: Optional[str]) -> str:
    pt = str(prop_type or "apartment").lower().strip()
    if pt in ("standalone_house", "independent_house", "house", "bungalow"):
        return "standalone_house"
    if "villa" in pt:
        return "villa"
    if "builder" in pt:
        return "builder_floor"
    if "office" in pt or pt == "commercial":
        return "office"
    if "retail" in pt or "shop" in pt or "showroom" in pt:
        return "retail"
    if "industrial" in pt or "factory" in pt:
        return "industrial"
    if "warehouse" in pt or "logistics" in pt:
        return "warehouse"
    if "mixed" in pt:
        return "mixed_use"
    return "apartment"


def _compute_stats_slice(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculates robust median/IQR/min/max statistics for a homogeneous slice of rental listings."""
    if not records:
        return {
            "count": 0,
            "status": "INSUFFICIENT_DATA",
            "min_monthly_rent": None,
            "p25_monthly_rent": None,
            "median_monthly_rent": None,
            "mean_monthly_rent": None,
            "p75_monthly_rent": None,
            "max_monthly_rent": None,
            "median_rent_per_sqft": None,
            "median_gross_yield_pct": None,
            "date_range": None,
        }

    rents = np.array([r["monthly_rent_inr"] for r in records], dtype=float)
    rent_sqfts = np.array(
        [r["rent_per_sqft_inr"] for r in records if r["rent_per_sqft_inr"] and r["rent_per_sqft_inr"] > 0],
        dtype=float,
    )
    yields = np.array(
        [r["implied_gross_yield_pct"] for r in records if r.get("implied_gross_yield_pct")],
        dtype=float,
    )
    dates = sorted([r["observation_date"] for r in records if r.get("observation_date")])

    return {
        "count": len(records),
        "status": "SUFFICIENT" if len(records) >= 3 else "LOW_SAMPLE_SIZE",
        "min_monthly_rent": round(float(np.min(rents)), 0),
        "p25_monthly_rent": round(float(np.percentile(rents, 25)), 0),
        "median_monthly_rent": round(float(np.median(rents)), 0),
        "mean_monthly_rent": round(float(np.mean(rents)), 0),
        "p75_monthly_rent": round(float(np.percentile(rents, 75)), 0),
        "max_monthly_rent": round(float(np.max(rents)), 0),
        "median_rent_per_sqft": round(float(np.median(rent_sqfts)), 2) if len(rent_sqfts) > 0 else None,
        "median_gross_yield_pct": round(float(np.median(yields)), 2) if len(yields) > 0 else None,
        "date_range": {"earliest": dates[0], "latest": dates[-1]} if dates else None,
    }


class RentalComparableEngine:
    """Spatial Comparable Rental Matching, Yield Intelligence & Forecasting Engine."""

    def __init__(self):
        init_rental_db(seed_historical_benchmarks=True)

    def _compute_similarity_score(
        self,
        listing: RentalListing,
        distance_km: float,
        radius_km: float,
        target_category: str,
        target_bhk: Optional[float],
        target_area_sqft: Optional[float],
        target_furnishing: Optional[str],
    ) -> float:
        """Scores comparable relevance from 0 to 100 based on proximity, property traits, and verification."""
        score = 0.0

        # 1. Proximity (up to 35 pts)
        dist_ratio = max(0.0, 1.0 - (distance_km / max(radius_km, 0.5)))
        score += 35.0 * dist_ratio

        # 2. Area similarity (up to 25 pts)
        listing_area = listing.builtup_area_sqft or listing.carpet_area_sqft or 1000.0
        if target_area_sqft and target_area_sqft > 0:
            area_diff_ratio = abs(listing_area - target_area_sqft) / max(target_area_sqft, 1.0)
            score += max(0.0, 25.0 * (1.0 - min(1.0, area_diff_ratio)))
        else:
            score += 15.0

        # 3. BHK similarity (up to 15 pts)
        if target_bhk and listing.bhk:
            bhk_diff = abs(float(listing.bhk) - float(target_bhk))
            score += max(0.0, 15.0 - bhk_diff * 7.5)
        else:
            score += 10.0

        # 4. Furnishing match (up to 10 pts)
        if target_furnishing and listing.furnishing:
            score += 10.0 if target_furnishing.lower() == listing.furnishing.lower() else 4.0
        else:
            score += 6.0

        # 5. Verification & Provenance Quality (up to 15 pts)
        cat_bonus = {
            "Verified_Achieved": 15.0,
            "User_Submitted": 13.0,
            "Broker_Reported": 11.0,
            "Historical_Benchmark": 9.0,
            "Advertised_Asking": 6.0,
        }.get(listing.data_category, 5.0)
        score += cat_bonus

        return round(min(100.0, score), 1)

    def find_comparables(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
        property_type: Optional[str] = "apartment",
        bhk: Optional[float] = None,
        furnishing: Optional[str] = None,
        area_sqft: Optional[float] = None,
        min_rent: Optional[float] = None,
        max_rent: Optional[float] = None,
        limit: int = 25,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Searches rental comparables within specified radius (0.5km, 1km, 2km, 5km, 10km)
        and computes separate summary statistics for Verified Achieved vs Advertised Asking vs Historical Benchmarks.
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            target_cat = _normalize_property_category(property_type)
            # Bounding box pre-filter (~1 deg lat = 111 km)
            deg_pad = max(0.05, radius_km / 100.0)

            query = db.query(RentalListing).filter(
                RentalListing.is_active.is_(True),
                RentalListing.is_outlier.is_(False),
                RentalListing.is_duplicate.is_(False),
                RentalListing.latitude.between(latitude - deg_pad, latitude + deg_pad),
                RentalListing.longitude.between(longitude - deg_pad, longitude + deg_pad),
            )

            # Strict category isolation: do not mix commercial & residential categories
            if property_type:
                query = query.filter(RentalListing.property_type == target_cat)

            candidates = query.all()

            matched = []
            for item in candidates:
                dist = haversine_km(latitude, longitude, item.latitude, item.longitude)
                if dist > radius_km:
                    continue
                if min_rent is not None and item.monthly_rent_inr < min_rent:
                    continue
                if max_rent is not None and item.monthly_rent_inr > max_rent:
                    continue

                area_basis = item.builtup_area_sqft or item.carpet_area_sqft or 1.0
                rent_per_sqft = round(item.monthly_rent_inr / max(area_basis, 1.0), 2)
                sim_score = self._compute_similarity_score(
                    listing=item,
                    distance_km=dist,
                    radius_km=radius_km,
                    target_category=target_cat,
                    target_bhk=bhk,
                    target_area_sqft=area_sqft,
                    target_furnishing=furnishing,
                )

                matched.append({
                    "id": item.id,
                    "source_name": item.source_name,
                    "data_category": item.data_category,
                    "verification_status": item.verification_status,
                    "property_type": item.property_type,
                    "bhk": item.bhk,
                    "carpet_area_sqft": item.carpet_area_sqft,
                    "builtup_area_sqft": item.builtup_area_sqft,
                    "monthly_rent_inr": item.monthly_rent_inr,
                    "rent_per_sqft_inr": rent_per_sqft,
                    "implied_gross_yield_pct": item.implied_gross_yield_pct,
                    "furnishing": item.furnishing,
                    "parking_slots": item.parking_slots,
                    "city": item.city,
                    "locality": item.locality,
                    "latitude": item.latitude,
                    "longitude": item.longitude,
                    "distance_km": dist,
                    "observation_date": item.observation_date.isoformat() if item.observation_date else None,
                    "similarity_score": sim_score,
                    "is_stale": item.is_stale,
                })

            matched.sort(key=lambda x: (-x["similarity_score"], x["distance_km"]))

            # Strict provenance segregation
            verified_records = [
                r for r in matched if r["data_category"] in ("Verified_Achieved", "User_Submitted", "Broker_Reported")
            ]
            advertised_records = [r for r in matched if r["data_category"] == "Advertised_Asking"]
            benchmark_records = [r for r in matched if r["data_category"] == "Historical_Benchmark"]

            # Confidence calculation based on comparable density, verification level, and distance
            total_count = len(matched)
            if total_count == 0:
                confidence = 0.25
                confidence_label = "INSUFFICIENT_COMPARABLES"
            else:
                avg_dist = float(np.mean([r["distance_km"] for r in matched[:10]]))
                verified_share = (len(verified_records) + 0.6 * len(benchmark_records)) / total_count
                sample_factor = min(1.0, total_count / 8.0)
                dist_factor = max(0.3, 1.0 - (avg_dist / max(radius_km, 1.0)) * 0.5)
                confidence = round(0.35 + 0.30 * sample_factor + 0.20 * dist_factor + 0.15 * verified_share, 2)
                confidence_label = "HIGH" if confidence >= 0.78 else ("MODERATE" if confidence >= 0.58 else "LOW")

            return {
                "search_params": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius_km": radius_km,
                    "property_type": target_cat,
                },
                "total_matched": total_count,
                "data_confidence_score": confidence,
                "data_confidence_label": confidence_label,
                "segregated_statistics": {
                    "verified_achieved_stats": _compute_stats_slice(verified_records),
                    "advertised_asking_stats": _compute_stats_slice(advertised_records),
                    "historical_benchmark_stats": _compute_stats_slice(benchmark_records),
                },
                "comparables": matched[:limit],
            }
        finally:
            if close_db:
                db.close()

    def derive_market_yield_and_cap_rate(
        self,
        latitude: float,
        longitude: float,
        property_type: str = "apartment",
        radius_km: float = 10.0,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Derives market rental yield, capitalization rate, and GRM from local comparable evidence.
        Falls back cleanly with full disclosure to calibrated regional category baselines when
        fewer than 2 verified comparables exist within radius.
        """
        target_cat = _normalize_property_category(property_type)
        comp_res = self.find_comparables(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            property_type=target_cat,
            db=db,
        )

        verified = comp_res["segregated_statistics"]["verified_achieved_stats"]
        benchmarks = comp_res["segregated_statistics"]["historical_benchmark_stats"]
        baseline = CATEGORY_MARKET_BASELINES.get(target_cat, CATEGORY_MARKET_BASELINES["apartment"])

        if verified["count"] >= 2 and verified["median_gross_yield_pct"]:
            gross_yield = verified["median_gross_yield_pct"]
            vacancy = baseline["vacancy_pct"]
            opex_ratio = baseline["opex_ratio_pct"]
            cap_rate = round(gross_yield * (1.0 - vacancy / 100.0) * (1.0 - opex_ratio / 100.0), 2)
            source_desc = f"Verified Local Lease Comps (n={verified['count']} within {radius_km}km)"
            evidence_tier = "Verified_Local_Evidence"
            conf = comp_res["data_confidence_score"]
        elif benchmarks["count"] >= 1 and benchmarks["median_gross_yield_pct"] and target_cat == "apartment":
            gross_yield = benchmarks["median_gross_yield_pct"]
            vacancy = baseline["vacancy_pct"]
            opex_ratio = baseline["opex_ratio_pct"]
            cap_rate = round(gross_yield * (1.0 - vacancy / 100.0) * (1.0 - opex_ratio / 100.0), 2)
            source_desc = f"Regional Verified Rental Yield Index (n={benchmarks['count']} within {radius_km}km)"
            evidence_tier = "Historical_Regional_Benchmark"
            conf = max(0.55, comp_res["data_confidence_score"])
        else:
            gross_yield = baseline["gross_yield_pct"]
            cap_rate = baseline["cap_rate_pct"]
            vacancy = baseline["vacancy_pct"]
            opex_ratio = baseline["opex_ratio_pct"]
            source_desc = f"Category-Specific Indian Market Baseline ({target_cat.replace('_', ' ').title()})"
            evidence_tier = "Estimated_Category_Baseline"
            conf = 0.48

        grm = round(100.0 / max(gross_yield, 0.5), 2)

        return {
            "property_type": target_cat,
            "derived_gross_yield_pct": gross_yield,
            "derived_cap_rate_pct": cap_rate,
            "derived_grm": grm,
            "assumed_vacancy_rate_pct": vacancy,
            "assumed_opex_ratio_pct": opex_ratio,
            "justification_source": source_desc,
            "evidence_tier": evidence_tier,
            "confidence_score": conf,
            "comparable_search_summary": {
                "verified_count": verified["count"],
                "advertised_count": comp_res["segregated_statistics"]["advertised_asking_stats"]["count"],
                "benchmark_count": benchmarks["count"],
            },
        }

    def forecast_rental_income(
        self,
        current_monthly_rent: float,
        property_type: str = "apartment",
        historical_growth_pct: float = 6.2,
        inflation_pct: float = 4.8,
        vacancy_rate_pct: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Forecasts 1-year, 3-year, and 5-year monthly & annual rental income across
        Conservative, Base, and Optimistic scenarios, keeping Nominal growth separate from Real growth.
        Applies realistic mean-reversion dampening so growth does not compound unrealistically.
        """
        target_cat = _normalize_property_category(property_type)
        base_rent = max(0.0, float(current_monthly_rent))

        # Mean-reversion clamp around sustainable rental growth
        vacancy_drag = max(0.0, (vacancy_rate_pct - 5.0) * 0.15)
        cat_premium = 0.6 if target_cat in ("office", "retail") else 0.0

        nominal_base_rate = max(2.0, min(11.0, historical_growth_pct + cat_premium - vacancy_drag))
        nominal_conservative_rate = max(1.0, nominal_base_rate - 2.0)
        nominal_optimistic_rate = min(13.0, nominal_base_rate + 2.2)

        scenarios = {}
        for name, annual_rate_pct in [
            ("conservative", nominal_conservative_rate),
            ("base", nominal_base_rate),
            ("optimistic", nominal_optimistic_rate),
        ]:
            horizons = {}
            for yr in (1, 3, 5):
                # Dampening factor over longer horizons avoids perpetual high compounding assumptions
                dampened_rate = (annual_rate_pct / 100.0) * (0.97 if yr == 1 else (0.93 if yr == 3 else 0.88))
                nominal_monthly = round(base_rent * ((1.0 + dampened_rate) ** yr), 0)
                real_monthly = round(nominal_monthly / ((1.0 + inflation_pct / 100.0) ** yr), 0)
                horizons[f"year_{yr}"] = {
                    "nominal_monthly_rent": nominal_monthly,
                    "nominal_annual_rent": round(nominal_monthly * 12.0, 0),
                    "real_monthly_rent_today_inr": real_monthly,
                    "effective_annual_growth_pct": round(dampened_rate * 100.0, 2),
                }
            scenarios[name] = {
                "initial_annual_growth_pct": round(annual_rate_pct, 2),
                "horizons": horizons,
            }

        return {
            "current_monthly_rent": round(base_rent, 0),
            "assumed_inflation_pct": inflation_pct,
            "property_type": target_cat,
            "scenarios": scenarios,
            "methodology_note": "Mean-reverting nominal rent projections with explicit inflation-adjusted real rent separation.",
        }
