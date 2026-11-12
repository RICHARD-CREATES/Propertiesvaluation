"""
FastAPI Router for Rental Yield, NOI, Cap Rate, GRM, Comparables, Forecasting & RMDC.
Mounted cleanly onto the main FastAPI application in src/api/app.py.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.rental_db import RentalListing, RentalPriceHistory, SessionLocal
from src.core.rental_finance import (
    analyze_rental_cash_flow,
    calculate_cap_rate,
    calculate_direct_capitalization_value,
    calculate_grm,
    calculate_gross_rental_yield,
    calculate_net_operating_income,
    calculate_net_rental_yield,
    calculate_value_from_grm,
    calculate_value_from_gross_yield,
    run_rental_sensitivity_analysis,
)
from src.services.location_intelligence import LocationIntelligenceService
from src.services.rental_comparables import RentalComparableEngine, _normalize_property_category
from src.services.rental_data_collector import RentalDataCollectorService
from src.services.valuation_reconciliation import ThreeWayValuationReconciler

router = APIRouter(prefix="/api/rental", tags=["Rental Yield & Income Valuation Engine"])

comp_engine = RentalComparableEngine()
collector_service = RentalDataCollectorService()
reconciler = ThreeWayValuationReconciler()
location_service = LocationIntelligenceService()


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
class GrossYieldRequest(BaseModel):
    monthly_rent: float = Field(..., ge=0)
    property_value: Optional[float] = Field(None, gt=0)
    target_gross_yield_pct: Optional[float] = Field(None, gt=0, le=50.0)


class NetYieldRequest(BaseModel):
    noi_annual: float
    property_value: float = Field(..., gt=0)


class NOIRequest(BaseModel):
    monthly_rent: float = Field(..., ge=0)
    vacancy_rate_pct: float = Field(5.0, ge=0.0, le=100.0)
    collection_loss_pct: float = Field(1.0, ge=0.0, le=100.0)
    property_tax_annual: float = Field(0.0, ge=0.0)
    maintenance_annual: float = Field(0.0, ge=0.0)
    insurance_annual: float = Field(0.0, ge=0.0)
    utilities_annual: float = Field(0.0, ge=0.0)
    management_fee_pct: float = Field(0.0, ge=0.0, le=50.0)
    other_operating_expenses_annual: float = Field(0.0, ge=0.0)
    other_income_annual: float = Field(0.0, ge=0.0)


class CapRateRequest(BaseModel):
    noi_annual: float
    property_value: Optional[float] = Field(None, gt=0)
    cap_rate_pct: Optional[float] = Field(None, ge=1.0, le=25.0)


class GRMRequest(BaseModel):
    monthly_rent: float = Field(..., gt=0)
    property_value: Optional[float] = Field(None, ge=0)
    comparable_grm: Optional[float] = Field(None, gt=0, le=100.0)


class RentalValuationRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    property_type: str = "apartment"
    area_sqft: float = Field(1050.0, gt=0)
    monthly_rent: Optional[float] = Field(None, ge=0)
    property_value: Optional[float] = Field(None, gt=0)
    vacancy_rate_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    collection_loss_pct: float = Field(1.0, ge=0.0, le=100.0)
    property_tax_annual: float = Field(0.0, ge=0.0)
    maintenance_annual: float = Field(0.0, ge=0.0)
    insurance_annual: float = Field(0.0, ge=0.0)
    utilities_annual: float = Field(0.0, ge=0.0)
    management_fee_pct: float = Field(0.0, ge=0.0, le=50.0)
    other_operating_expenses_annual: float = Field(0.0, ge=0.0)
    cap_rate_pct: Optional[float] = Field(None, ge=1.0, le=25.0)
    comparable_grm: Optional[float] = Field(None, gt=0, le=100.0)


class ComparablesQueryRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_km: float = Field(5.0, gt=0.0, le=50.0)
    property_type: Optional[str] = "apartment"
    bhk: Optional[float] = None
    furnishing: Optional[str] = None
    area_sqft: Optional[float] = None
    limit: int = Field(25, ge=1, le=100)


class ForecastRequest(BaseModel):
    current_monthly_rent: float = Field(..., ge=0)
    property_type: str = "apartment"
    historical_growth_pct: float = Field(6.2, ge=-5.0, le=20.0)
    inflation_pct: float = Field(4.8, ge=0.0, le=15.0)
    vacancy_rate_pct: float = Field(5.0, ge=0.0, le=100.0)


class SensitivityRequest(BaseModel):
    base_monthly_rent: float = Field(..., gt=0)
    base_cap_rate_pct: float = Field(8.0, ge=1.0, le=25.0)
    vacancy_rate_pct: float = Field(5.0, ge=0.0, le=100.0)
    collection_loss_pct: float = Field(1.0, ge=0.0, le=100.0)
    annual_fixed_opex: float = Field(0.0, ge=0.0)
    management_fee_pct: float = Field(0.0, ge=0.0, le=50.0)


class RefreshRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    location_label: str = "Selected Location"
    radius_km: float = Field(5.0, gt=0.0, le=25.0)


class VerifyRentalRecordRequest(BaseModel):
    source_name: str = "user_submitted_lease"
    data_category: str = "Verified_Achieved"
    property_type: str = "apartment"
    bhk: Optional[float] = 2.0
    bathrooms: Optional[float] = 2.0
    area_value: float = Field(..., gt=50.0)
    area_unit: str = "sqft"
    monthly_rent_inr: float = Field(..., gt=0.0)
    security_deposit_inr: Optional[float] = None
    maintenance_monthly_inr: float = 0.0
    lease_duration_months: Optional[int] = 11
    furnishing: str = "semi_furnished"
    parking_slots: int = 1
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    state: str = "Odisha"
    city: str = "Bhubaneswar"
    locality: str = "Central"
    observation_date: Optional[str] = None


# ==============================================================================
# Financial Endpoints (Models A - F)
# ==============================================================================
@router.post("/gross-yield")
def api_gross_yield(req: GrossYieldRequest):
    try:
        annual_rent = round(req.monthly_rent * 12.0, 2)
        res: Dict[str, Any] = {"monthly_rent": req.monthly_rent, "annual_gross_rent": annual_rent}
        if req.property_value is not None:
            res["gross_rental_yield_pct"] = calculate_gross_rental_yield(req.monthly_rent, req.property_value)
        if req.target_gross_yield_pct is not None:
            res["implied_property_value"] = calculate_value_from_gross_yield(
                req.monthly_rent, req.target_gross_yield_pct
            )
        if req.property_value is None and req.target_gross_yield_pct is None:
            raise HTTPException(status_code=400, detail="Provide either 'property_value' or 'target_gross_yield_pct'.")
        return {"status": "success", **res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/net-yield")
def api_net_yield(req: NetYieldRequest):
    try:
        net_y = calculate_net_rental_yield(req.noi_annual, req.property_value)
        return {
            "status": "success",
            "noi_annual": req.noi_annual,
            "property_value": req.property_value,
            "net_rental_yield_pct": net_y,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/noi")
def api_noi(req: NOIRequest):
    try:
        noi_res = calculate_net_operating_income(
            monthly_rent=req.monthly_rent,
            vacancy_rate_pct=req.vacancy_rate_pct,
            collection_loss_pct=req.collection_loss_pct,
            property_tax_annual=req.property_tax_annual,
            maintenance_annual=req.maintenance_annual,
            insurance_annual=req.insurance_annual,
            utilities_annual=req.utilities_annual,
            management_fee_pct=req.management_fee_pct,
            other_operating_expenses_annual=req.other_operating_expenses_annual,
            other_income_annual=req.other_income_annual,
        )
        return {"status": "success", **noi_res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/cap-rate")
def api_cap_rate(req: CapRateRequest):
    try:
        out: Dict[str, Any] = {"noi_annual": req.noi_annual}
        if req.property_value is not None:
            out["derived_cap_rate_pct"] = calculate_cap_rate(req.noi_annual, req.property_value)
        if req.cap_rate_pct is not None:
            out["direct_capitalization_value"] = calculate_direct_capitalization_value(
                req.noi_annual, req.cap_rate_pct
            )
        if req.property_value is None and req.cap_rate_pct is None:
            raise HTTPException(status_code=400, detail="Provide either 'property_value' or 'cap_rate_pct'.")
        return {"status": "success", **out}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/grm")
def api_grm(req: GRMRequest):
    try:
        out: Dict[str, Any] = {"monthly_rent": req.monthly_rent, "annual_gross_rent": round(req.monthly_rent * 12.0, 2)}
        if req.property_value is not None:
            out["derived_grm"] = calculate_grm(req.property_value, req.monthly_rent)
        if req.comparable_grm is not None:
            out["grm_implied_property_value"] = calculate_value_from_grm(req.monthly_rent, req.comparable_grm)
        if req.property_value is None and req.comparable_grm is None:
            raise HTTPException(status_code=400, detail="Provide either 'property_value' or 'comparable_grm'.")
        return {"status": "success", **out}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/estimate")
@router.post("/valuation")
def api_rental_valuation(req: RentalValuationRequest):
    """Full Income-Based Valuation + Rental Estimation + 3-Way Reconciliation summary."""
    try:
        intel = location_service.harvest(req.latitude, req.longitude)
        base_price_sqm = float(
            intel["intelligence"]["transactions"]["comparable_median_price_sqm_500m_12m"]["value"]
        )
        area_sqm = req.area_sqft * 0.092903
        sales_est = req.property_value or round(base_price_sqm * area_sqm, 0)

        prop_input: Dict[str, Any] = {
            "collection_loss_pct": req.collection_loss_pct,
            "property_tax_annual": req.property_tax_annual,
            "maintenance_annual": req.maintenance_annual,
            "insurance_annual": req.insurance_annual,
            "management_fee_pct": req.management_fee_pct,
            "operating_expenses_annual": req.other_operating_expenses_annual,
        }
        if req.monthly_rent is not None:
            prop_input["monthly_rent_inr"] = req.monthly_rent
        if req.vacancy_rate_pct is not None:
            prop_input["vacancy_rate_pct"] = req.vacancy_rate_pct
        if req.cap_rate_pct is not None:
            prop_input["cap_rate_pct"] = req.cap_rate_pct
        if req.comparable_grm is not None:
            prop_input["comparable_grm"] = req.comparable_grm

        cat_norm = _normalize_property_category(req.property_type)
        asset_type = "commercial" if cat_norm in ("office", "retail", "warehouse", "industrial") else "residential"

        result = reconciler.evaluate_income_and_reconcile(
            latitude=req.latitude,
            longitude=req.longitude,
            asset_type=asset_type,
            structure_type=cat_norm,
            commercial_type=cat_norm,
            valuation_area_sqft=req.area_sqft,
            currency=intel["metadata"]["currency"],
            sales_comparison_value=sales_est,
            cost_approach_value=sales_est,
            m10_prediction={},
            property_input=prop_input,
        )
        return {"status": "success", "location": intel["metadata"], **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/forecast")
def api_rental_forecast(req: ForecastRequest):
    res = comp_engine.forecast_rental_income(
        current_monthly_rent=req.current_monthly_rent,
        property_type=req.property_type,
        historical_growth_pct=req.historical_growth_pct,
        inflation_pct=req.inflation_pct,
        vacancy_rate_pct=req.vacancy_rate_pct,
    )
    return {"status": "success", **res}


@router.post("/sensitivity")
def api_rental_sensitivity(req: SensitivityRequest):
    try:
        res = run_rental_sensitivity_analysis(
            base_monthly_rent=req.base_monthly_rent,
            base_cap_rate_pct=req.base_cap_rate_pct,
            vacancy_rate_pct=req.vacancy_rate_pct,
            collection_loss_pct=req.collection_loss_pct,
            annual_fixed_opex=req.annual_fixed_opex,
            management_fee_pct=req.management_fee_pct,
        )
        return {"status": "success", **res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ==============================================================================
# Spatial Comparables, Statistics & RMDC Endpoints
# ==============================================================================
@router.post("/comparables")
def api_comparables_post(req: ComparablesQueryRequest):
    res = comp_engine.find_comparables(
        latitude=req.latitude,
        longitude=req.longitude,
        radius_km=req.radius_km,
        property_type=req.property_type,
        bhk=req.bhk,
        furnishing=req.furnishing,
        area_sqft=req.area_sqft,
        limit=req.limit,
    )
    return {"status": "success", **res}


@router.get("/comparables")
@router.get("/search")
def api_comparables_get(
    latitude: float = Query(20.3036, ge=-90.0, le=90.0),
    longitude: float = Query(85.8485, ge=-180.0, le=180.0),
    radius_km: float = Query(5.0, gt=0.0, le=50.0),
    property_type: Optional[str] = Query("apartment"),
    bhk: Optional[float] = Query(None),
    furnishing: Optional[str] = Query(None),
    area_sqft: Optional[float] = Query(None),
    min_rent: Optional[float] = Query(None),
    max_rent: Optional[float] = Query(None),
    limit: int = Query(25, ge=1, le=100),
):
    res = comp_engine.find_comparables(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        property_type=property_type,
        bhk=bhk,
        furnishing=furnishing,
        area_sqft=area_sqft,
        min_rent=min_rent,
        max_rent=max_rent,
        limit=limit,
    )
    return {"status": "success", **res}


@router.get("/location-statistics")
@router.get("/locality-statistics")
def api_location_statistics(
    latitude: float = Query(20.3036, ge=-90.0, le=90.0),
    longitude: float = Query(85.8485, ge=-180.0, le=180.0),
    radius_km: float = Query(5.0, gt=0.0, le=50.0),
    property_type: str = Query("apartment"),
):
    comps = comp_engine.find_comparables(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        property_type=property_type,
    )
    yield_info = comp_engine.derive_market_yield_and_cap_rate(
        latitude=latitude,
        longitude=longitude,
        property_type=property_type,
        radius_km=max(radius_km, 10.0),
    )
    return {
        "status": "success",
        "location_query": {"latitude": latitude, "longitude": longitude, "radius_km": radius_km},
        "data_confidence_score": comps["data_confidence_score"],
        "data_confidence_label": comps["data_confidence_label"],
        "segregated_statistics": comps["segregated_statistics"],
        "yield_and_cap_rate_intelligence": yield_info,
    }


@router.get("/median-rent")
@router.get("/rent-per-sqft")
def api_median_rent_summary(
    latitude: float = Query(20.3036, ge=-90.0, le=90.0),
    longitude: float = Query(85.8485, ge=-180.0, le=180.0),
    radius_km: float = Query(5.0, gt=0.0, le=50.0),
    property_type: str = Query("apartment"),
):
    comps = comp_engine.find_comparables(
        latitude=latitude, longitude=longitude, radius_km=radius_km, property_type=property_type
    )
    seg = comps["segregated_statistics"]
    return {
        "status": "success",
        "property_type": _normalize_property_category(property_type),
        "radius_km": radius_km,
        "verified_median_rent": seg["verified_achieved_stats"]["median_monthly_rent"],
        "verified_median_rent_per_sqft": seg["verified_achieved_stats"]["median_rent_per_sqft"],
        "advertised_median_rent": seg["advertised_asking_stats"]["median_monthly_rent"],
        "advertised_median_rent_per_sqft": seg["advertised_asking_stats"]["median_rent_per_sqft"],
        "historical_benchmark_median_rent": seg["historical_benchmark_stats"]["median_monthly_rent"],
        "historical_benchmark_rent_per_sqft": seg["historical_benchmark_stats"]["median_rent_per_sqft"],
        "confidence": comps["data_confidence_label"],
    }


@router.get("/history")
@router.get("/yield-history")
def api_rental_history(city: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    with SessionLocal() as db:
        q = db.query(RentalPriceHistory)
        if city:
            q = q.filter(RentalPriceHistory.city.ilike(f"%{city}%"))
        rows = q.order_by(RentalPriceHistory.snapshot_date.desc()).limit(limit).all()

        if not rows:
            # Return seeded historical benchmarks with explicit observation_date
            lq = db.query(RentalListing)
            if city:
                lq = lq.filter(RentalListing.city.ilike(f"%{city}%"))
            b_rows = lq.order_by(RentalListing.observation_date.desc()).limit(limit).all()
            history = [
                {
                    "city": r.city,
                    "locality": r.locality,
                    "property_type": r.property_type,
                    "data_category": r.data_category,
                    "monthly_rent_inr": r.monthly_rent_inr,
                    "rent_per_sqft_inr": round(r.monthly_rent_inr / max(r.builtup_area_sqft or r.carpet_area_sqft, 1.0), 2),
                    "gross_yield_pct": r.implied_gross_yield_pct,
                    "snapshot_date": r.observation_date.isoformat() if r.observation_date else None,
                }
                for r in b_rows
            ]
        else:
            history = [
                {
                    "city": r.city,
                    "locality": r.locality,
                    "property_type": r.property_type,
                    "data_category": r.data_category,
                    "monthly_rent_inr": r.monthly_rent_inr,
                    "rent_per_sqft_inr": r.rent_per_sqft_inr,
                    "gross_yield_pct": r.gross_yield_pct,
                    "snapshot_date": r.snapshot_date.isoformat() if r.snapshot_date else None,
                }
                for r in rows
            ]

    return {"status": "success", "count": len(history), "history": history}


@router.post("/verify")
def api_verify_rental_record(req: VerifyRentalRecordRequest):
    """Ingests a verified lease agreement or broker comparable through RMDC cleaning, dedup, and outlier audit."""
    res = collector_service.ingest_listing_batch(
        raw_records=[req.model_dump()],
        source_name=req.source_name,
        location_query=f"{req.locality}, {req.city}",
    )
    if res["records_accepted"] == 0:
        raise HTTPException(status_code=400, detail=f"Record rejected: {res['errors']}")
    return {"status": "success", **res}


@router.post("/refresh")
def api_refresh_sources(req: RefreshRequest):
    res = collector_service.trigger_manual_refresh(
        latitude=req.latitude,
        longitude=req.longitude,
        location_label=req.location_label,
        radius_km=req.radius_km,
    )
    return {"status": "success", **res}


@router.get("/collection-status")
def api_collection_status(limit: int = Query(20, ge=1, le=100)):
    return {"status": "success", "jobs": collector_service.get_collection_jobs(limit=limit)}


@router.get("/source-health")
def api_source_health():
    return {"status": "success", "sources": collector_service.get_source_health()}
