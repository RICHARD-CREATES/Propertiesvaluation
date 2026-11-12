"""
FastAPI Server for Global AI Property Valuation & Location Intelligence.
Exposes standard endpoints for Location Selection, Automated Intelligence Harvesting,
Details Validation, 10-Specialist Valuation, and Explainability.
"""
import os
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import uuid

from src.services.location_intelligence import LocationIntelligenceService
from src.services.missing_detection import MissingFeatureDetectionService
from src.services.valuation_engine import GlobalPropertyValuationEngine
from src.services.production_models import ProductionModelService
from src.api.rental_routes import router as rental_router
from src.api.validation_routes import router as validation_router
from src.api.analytics_routes import coverage_router, router as analytics_router
from src.api.ingestion_routes import router as ingestion_router
from src.api.auth_routes import router as auth_router
from src.core.ops_utils import SlidingWindowRateLimiter, configure_structured_logging
from src.core.units import convert_area_to_sqm
from src.services.evidence_bridge import OutOfDistributionDetector
from src.services.report_generator import build_json_report_payload, render_printable_html_report

_logger = configure_structured_logging()
_rate_limiter = SlidingWindowRateLimiter(
    max_requests_per_minute=int(os.environ.get("RATE_LIMIT_RPM", "180"))
)

app = FastAPI(
    title="Global AI Property Valuation Platform",
    description="Location-First Multi-Specialist AI Valuation System with 10 Domain Models & Rental Income Capitalization",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_and_audit_middleware(request: Request, call_next):
    if os.environ.get("RATE_LIMIT_ENABLED", "1") == "1" and request.url.path != "/api/health":
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = _rate_limiter.allow_request(client_ip)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded; please retry shortly."},
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


app.include_router(rental_router)
app.include_router(validation_router)
app.include_router(analytics_router)
app.include_router(coverage_router)
app.include_router(ingestion_router)
app.include_router(auth_router)

# Services
location_service = LocationIntelligenceService()
missing_service = MissingFeatureDetectionService()
valuation_engine = GlobalPropertyValuationEngine()
production_models = ProductionModelService()

# In-memory store for session valuation artifacts
VALUATION_STORE: Dict[str, Any] = {}

STATIC_DIR = Path(__file__).resolve().parent / "static"
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="frontend-assets")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "images"
if IMAGES_DIR.exists():
    app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    dist_index = FRONTEND_DIST_DIR / "index.html"
    if dist_index.exists():
        return HTMLResponse(
            content=dist_index.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(
            content=index_path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    return HTMLResponse("<h1>Global AI Property Valuation API is running.</h1>")


# Schemas
class LocationRequest(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float] = 15.0
    country_code: Optional[str] = "IN"


class ValidateDetailsRequest(BaseModel):
    asset_type: str = "residential"
    structure_type: Optional[str] = "apartment"  # "apartment", "standalone_house", "builder_floor"
    area_value: float
    area_unit: str = "sqft"
    plot_area_sqft: Optional[float] = 0.0
    bedrooms: Optional[float] = 2.0
    bathrooms: Optional[float] = 2.0
    property_age_years: Optional[float] = 5.0
    construction_grade: Optional[str] = "GRADE_B"
    floor_number: Optional[int] = 5
    total_floors: Optional[int] = 20
    commercial_type: Optional[str] = "retail"
    land_use: Optional[str] = "residential_zoned"
    locality_tier: Optional[str] = "prime"  # "prime", "developing", "standard", "outskirts"
    road_width_ft: Optional[str] = "30ft"  # "40ft_plus", "30ft", "20ft", "15ft_narrow"
    corner_plot: Optional[str] = "standard"  # "corner_park", "standard"
    furnishing: Optional[str] = "semi_furnished"  # "fully_furnished", "semi_furnished", "unfurnished"
    parking_slots: Optional[str] = "1_covered"  # "2_covered", "1_covered", "open"
    approval_status: Optional[str] = "approved_freehold"  # "approved_freehold", "regular"
    maintenance_state: Optional[str] = "well_maintained"  # "recently_renovated", "well_maintained", "average"
    original_cost_of_house: Optional[float] = 0.0  # Optional known cost of house when created / purchased
    flood_risk: Optional[str] = "none_low"  # "none_low", "moderate_waterlogging", "high_flood_zone"
    drainage_infra: Optional[str] = "underground_storm"  # "underground_storm", "open_drain", "poor_waterlogging"
    groundwater_availability: Optional[str] = "abundant"  # "abundant", "moderate", "deep_boring_scarce"
    litigation_risk: Optional[str] = "clear_verified"  # "clear_verified", "disputed_encumbered"
    # Optional Rental & Income Valuation Inputs
    monthly_rent_inr: Optional[float] = 0.0
    vacancy_rate_pct: Optional[float] = None
    operating_expenses_annual: Optional[float] = 0.0
    cap_rate_pct: Optional[float] = None


class ValuationExecutionRequest(BaseModel):
    location: LocationRequest
    property_details: ValidateDetailsRequest
    overrides: Optional[Dict[str, Any]] = None


# Endpoints
@app.get("/api/health")
def health_check():
    from sqlalchemy import inspect as sa_inspect
    from src.core.rental_db import engine as db_engine

    try:
        tables = sorted(sa_inspect(db_engine).get_table_names())
        db_ok = True
    except Exception:
        tables = []
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "Global AI Property Valuation Engine",
        "specialist_models_registered": 10,
        "production_models_loaded": sorted(production_models.models.keys()),
        "database_connected": db_ok,
        "database_tables_count": len(tables),
        "private_evidence_vault_ready": (Path(__file__).resolve().parent.parent.parent / "data" / "private_evidence_vault").exists(),
    }


INDIAN_CITY_ALIASES = {
    "bhubanaswar": "bhubaneswar",
    "bhubneshwar": "bhubaneswar",
    "banglore": "bengaluru",
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "madras": "chennai",
    "poona": "pune",
    "gurgaon": "gurugram",
    "hydrabad": "hyderabad",
    "luckhnow": "lucknow",
    "ahmdabad": "ahmedabad",
    "ahmedbad": "ahmedabad",
    "cochin": "kochi",
    "trivandrum": "thiruvananthapuram",
    "baroda": "vadodara",
    "banaras": "varanasi",
    "benares": "varanasi",
}

KNOWN_INDIAN_METROS = {
    "mumbai", "pune", "delhi", "bhubaneswar", "bengaluru", "bangalore",
    "hyderabad", "chennai", "kolkata", "lucknow", "ahmedabad", "jaipur",
    "kochi", "patna", "indore", "bhopal", "nagpur", "surat", "chandigarh",
    "noida", "gurugram", "gurgaon", "vadodara", "varanasi", "cuttack",
    "puri", "rourkela", "sambalpur", "thane", "ghaziabad", "ludhiana"
}

@app.get("/api/property/search")
def search_address(query: Optional[str] = None, q: Optional[str] = None):
    """Searches address anywhere in India or globally with typo correction, progressive query expansion, and Nominatim."""
    import urllib.request
    import urllib.parse
    import json
    
    raw_query = query or q or ""
    cleaned_query = raw_query.strip()
    if not cleaned_query:
        return {"query": "", "results": []}
    words = cleaned_query.lower().split()
    corrected_words = [INDIAN_CITY_ALIASES.get(w, w) for w in words]
    normalized_query = " ".join(corrected_words)
    
    # Generate progressive query variants for resilient resolution
    # e.g. "vss nagar bhubanaswar" -> ["vss nagar bhubaneswar", "vss nagar, bhubaneswar", "vss, bhubaneswar", "bhubaneswar"]
    cities_in_query = [w for w in corrected_words if w in KNOWN_INDIAN_METROS or w in INDIAN_CITY_ALIASES.values()]
    localities_in_query = [w for w in corrected_words if w not in cities_in_query]
    
    search_variants = [normalized_query]
    if cities_in_query and localities_in_query:
        city_part = " ".join(cities_in_query)
        loc_part = " ".join(localities_in_query)
        search_variants.append(f"{loc_part}, {city_part}")
        
        # Strip generic area words (nagar, vihar, colony, sector, road)
        clean_loc = " ".join([w for w in localities_in_query if w not in {"nagar", "vihar", "colony", "enclave", "sector", "phase", "road", "rd", "street", "st"}])
        if clean_loc:
            search_variants.append(f"{clean_loc}, {city_part}")
        search_variants.append(city_part)
        
    results = []
    seen_coords = set()

    # 1. Query Nominatim across progressive variants until quality matches are obtained
    for variant in search_variants:
        if len(results) >= 4:
            break
        try:
            n_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(variant)}&format=json&addressdetails=1&countrycodes=in&limit=6"
            req = urllib.request.Request(n_url, headers={"User-Agent": "GlobalAIPropertyValuation/2.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    lat = float(item.get("lat"))
                    lon = float(item.get("lon"))
                    coord_key = (round(lat, 3), round(lon, 3))
                    if coord_key not in seen_coords:
                        seen_coords.add(coord_key)
                        results.append({
                            "display_name": item.get("display_name"),
                            "lat": lat,
                            "lon": lon,
                            "type": item.get("type", "location"),
                            "source": "nominatim"
                        })
        except Exception:
            pass

    # 2. Try Photon if fewer than 2 results
    if len(results) < 2:
        try:
            p_url = f"https://photon.komoot.io/api/?q={urllib.parse.quote(normalized_query)}&limit=6"
            req = urllib.request.Request(p_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for feat in data.get("features", []):
                    p = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if len(coords) == 2:
                        lon, lat = float(coords[0]), float(coords[1])
                        coord_key = (round(lat, 3), round(lon, 3))
                        if coord_key not in seen_coords:
                            seen_coords.add(coord_key)
                            parts = [p.get("name"), p.get("street"), p.get("district"), p.get("city"), p.get("state"), p.get("country")]
                            disp = ", ".join([x for x in parts if x])
                            results.append({
                                "display_name": disp or p.get("name", normalized_query),
                                "lat": lat,
                                "lon": lon,
                                "type": p.get("type", "locality"),
                                "source": "photon"
                            })
        except Exception:
            pass

    # 3. Fallback: Search against our Pan-India 50+ Hub Database if still empty
    if not results:
        for hub in location_service.HUBS:
            lat, lon, city, state, country, currency, base_price_sqm, land_rate_sqft, tier = hub
            if any(w in city.lower() for w in corrected_words) or any(w in state.lower() for w in corrected_words):
                results.append({
                    "display_name": f"{city}, {state}, India",
                    "lat": lat,
                    "lon": lon,
                    "type": "regional_hub",
                    "source": "pan_india_index"
                })

    # 4. Score and Rank Results by non-generic word overlap
    generic_stopwords = {"nagar", "road", "rd", "street", "st", "colony", "chowk", "lane", "sector", "phase", "post", "office"}
    q_tokens = [w for w in corrected_words if len(w) > 1]
    
    def score_result(r):
        name = r.get("display_name", "").lower()
        first_segment = name.split(",")[0].lower()
        pts = 0
        for w in q_tokens:
            if w in generic_stopwords:
                if w in name:
                    pts += 1
            else:
                if w in first_segment:
                    pts += 15
                elif w in name:
                    pts += 8
        return pts

    results.sort(key=score_result, reverse=True)

    return {
        "status": "success",
        "query": query,
        "normalized_query": normalized_query,
        "results": results
    }


@app.post("/api/property/location")
def validate_location(req: LocationRequest):
    """Step 1: Validates coordinates, reverse geocoding, and backend zone enrichment."""
    if not location_service.validate_coordinates(req.latitude, req.longitude):
        raise HTTPException(status_code=400, detail="Invalid GPS coordinates")
    
    harvested = location_service.harvest(
        latitude=req.latitude,
        longitude=req.longitude,
        accuracy_m=req.accuracy,
        country_code=req.country_code,
    )
    from src.services.location_zones import LocationZoneEngine

    return {
        "status": "valid",
        "metadata": harvested["metadata"],
        "geocoding": harvested["intelligence"]["geocoding"],
        "zone_analysis": LocationZoneEngine.to_public_payload(harvested.get("zone_analysis") or {}),
    }


@app.get("/api/platform/config")
def get_platform_config():
    """Returns backend-managed UI location presets, countries, option lists, and map configs."""
    from src.services.platform_catalog import PlatformCatalogService

    return PlatformCatalogService.get_frontend_bootstrap_catalog()


@app.get("/api/property/zones")
def get_property_zones(
    latitude: float = Query(...),
    longitude: float = Query(...),
    country_code: str = Query("IN"),
):
    """Public Green (Medical) zone overlay lookup; internal corridor analysis stays backend-only."""
    if not location_service.validate_coordinates(latitude, longitude):
        raise HTTPException(status_code=400, detail="Invalid GPS coordinates")
    harvested = location_service.harvest(latitude=latitude, longitude=longitude, country_code=country_code)
    meta = harvested["metadata"]
    from src.services.location_zones import LocationZoneEngine

    return {
        "latitude": latitude,
        "longitude": longitude,
        "city": meta.get("city"),
        "locality": meta.get("locality"),
        "state": meta.get("state"),
        "currency": meta.get("currency"),
        "density_tier": meta.get("density_tier"),
        "base_land_rate_sqft": meta.get("land_rate_sqft"),
        "circle_rate_sqft": meta.get("circle_rate_sqft"),
        "zone_analysis": LocationZoneEngine.to_public_payload(harvested.get("zone_analysis") or {}),
    }


@app.post("/api/property/intelligence")
def harvest_intelligence(req: LocationRequest):
    """Step 1-to-2: Harvests complete multi-layer intelligence for the location."""
    harvested = location_service.harvest(
        latitude=req.latitude,
        longitude=req.longitude,
        accuracy_m=req.accuracy,
        country_code=req.country_code,
    )
    return harvested


@app.post("/api/property/validate-details")
def validate_details(req: ValidateDetailsRequest):
    """Step 2: Normalizes property details and validates completeness."""
    sqm_area = convert_area_to_sqm(req.area_value, req.area_unit)
    norm_props = {
        "asset_type": req.asset_type,
        "built_area_sqm": sqm_area if req.asset_type != "land" else None,
        "land_area_sqm": sqm_area if req.asset_type == "land" else None,
        "bedrooms": req.bedrooms,
        "bathrooms": req.bathrooms,
        "property_age_years": req.property_age_years,
        "floor_number": req.floor_number,
        "total_floors": req.total_floors,
    }
    audit = missing_service.audit_and_impute(norm_props, asset_type=req.asset_type)
    return {
        "normalized_area_sqm": sqm_area,
        "audit": audit,
    }


@app.post("/api/property/valuation")
def execute_valuation(req: ValuationExecutionRequest):
    """Step 3: Runs full 10-specialist ensemble valuation."""
    # 1. Harvest location intelligence
    intel = location_service.harvest(
        latitude=req.location.latitude,
        longitude=req.location.longitude,
        accuracy_m=req.location.accuracy,
        country_code=req.location.country_code,
        overrides=req.overrides,
    )

    # 2. Normalize property input
    sqm_area = convert_area_to_sqm(req.property_details.area_value, req.property_details.area_unit)
    prop_dict = {
        "asset_type": req.property_details.asset_type,
        "structure_type": req.property_details.structure_type or "apartment",
        "plot_area_sqft": req.property_details.plot_area_sqft or 0.0,
        "construction_grade": req.property_details.construction_grade or "GRADE_B",
        "built_area_sqm": sqm_area if req.property_details.asset_type != "land" else None,
        "land_area_sqm": sqm_area if req.property_details.asset_type == "land" else None,
        "bedrooms": req.property_details.bedrooms,
        "bathrooms": req.property_details.bathrooms,
        "property_age_years": req.property_details.property_age_years,
        "floor_number": req.property_details.floor_number,
        "total_floors": req.property_details.total_floors,
        "commercial_type": req.property_details.commercial_type,
        "locality_tier": req.property_details.locality_tier or "prime",
        "road_width_ft": req.property_details.road_width_ft or "30ft",
        "corner_plot": req.property_details.corner_plot or "standard",
        "furnishing": req.property_details.furnishing or "semi_furnished",
        "parking_slots": req.property_details.parking_slots or "1_covered",
        "approval_status": req.property_details.approval_status or "approved_freehold",
        "maintenance_state": req.property_details.maintenance_state or "well_maintained",
        "original_cost_of_house": req.property_details.original_cost_of_house or 0.0,
        "flood_risk": req.property_details.flood_risk or "none_low",
        "drainage_infra": req.property_details.drainage_infra or "underground_storm",
        "groundwater_availability": req.property_details.groundwater_availability or "abundant",
        "litigation_risk": req.property_details.litigation_risk or "clear_verified",
        "monthly_rent_inr": req.property_details.monthly_rent_inr or 0.0,
        "operating_expenses_annual": req.property_details.operating_expenses_annual or 0.0,
    }
    if req.property_details.vacancy_rate_pct is not None:
        prop_dict["vacancy_rate_pct"] = req.property_details.vacancy_rate_pct
    if req.property_details.cap_rate_pct is not None:
        prop_dict["cap_rate_pct"] = req.property_details.cap_rate_pct

    # 3. Execute Engine
    result = valuation_engine.evaluate_property(prop_dict, intel)
    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result)

    area_sqft_val = round(sqm_area / 0.092903, 2) if sqm_area > 0 else 0.0
    ood_info = OutOfDistributionDetector.assess(
        property_type=req.property_details.structure_type or req.property_details.asset_type,
        latitude=req.location.latitude,
        longitude=req.location.longitude,
        area_sqft=area_sqft_val,
        asset_type=req.property_details.asset_type,
    )
    result.setdefault("evidence_and_uncertainty", {})["ood_assessment"] = ood_info

    val_id = f"VAL-{uuid.uuid4().hex[:8].upper()}"
    result["valuation_id"] = val_id
    VALUATION_STORE[val_id] = result

    return result


@app.get("/api/property/valuation/{val_id}")
def get_valuation(val_id: str):
    if val_id not in VALUATION_STORE:
        raise HTTPException(status_code=404, detail="Valuation report not found")
    return VALUATION_STORE[val_id]


@app.get("/api/property/valuation/{val_id}/report")
def download_valuation_report(val_id: str, format: str = Query("html", pattern="^(html|json)$")):
    """Downloads a standalone HTML (print-to-PDF) or JSON valuation evidence dossier."""
    if val_id not in VALUATION_STORE:
        raise HTTPException(status_code=404, detail="Valuation report not found")
    record = VALUATION_STORE[val_id]
    if format == "json":
        payload = build_json_report_payload(val_id, record)
        return JSONResponse(
            content=payload,
            headers={"Content-Disposition": f'attachment; filename="valuation_report_{val_id}.json"'},
        )
    html_doc = render_printable_html_report(val_id, record)
    return HTMLResponse(
        content=html_doc,
        headers={"Content-Disposition": f'inline; filename="valuation_report_{val_id}.html"'},
    )


@app.get("/api/property/explanation/{val_id}")
def get_explanation(val_id: str):
    if val_id not in VALUATION_STORE:
        raise HTTPException(status_code=404, detail="Valuation report not found")
    record = VALUATION_STORE[val_id]
    return {
        "valuation_id": val_id,
        "explainability": record.get("explainability", {}),
        "valuation_summary": record.get("valuation", {}),
    }


@app.get("/api/property/comparables/{val_id}")
def get_comparables(val_id: str):
    if val_id not in VALUATION_STORE:
        raise HTTPException(status_code=404, detail="Valuation report not found")
    record = VALUATION_STORE[val_id]
    intel = record.get("location_summary", {})
    return {
        "valuation_id": val_id,
        "location": intel,
        "benchmark_price_sqm": record.get("valuation", {}).get("price_per_sqm"),
        "comparable_sales_notes": "Extracted from authorized SRO / Land Registry deeds within 500m-1km radius",
    }


@app.get("/api/property/data-quality/{val_id}")
def get_data_quality(val_id: str):
    if val_id not in VALUATION_STORE:
        raise HTTPException(status_code=404, detail="Valuation report not found")
    record = VALUATION_STORE[val_id]
    return {
        "valuation_id": val_id,
        "sources_status": record.get("sources_status", {}),
        "data_completeness_pct": record.get("explainability", {}).get("data_completeness_pct"),
    }


# ---------------------------------------------------------------------------
# PHASE 10: PRODUCTION VALUATION ESTIMATE API (7 PROPERTY CATEGORIES)
# ---------------------------------------------------------------------------
class V1ValuationEstimateRequest(BaseModel):
    latitude: float
    longitude: float
    property_type: str = "apartment"
    builtup_area_sqft: Optional[float] = None
    carpet_area_sqft: Optional[float] = None
    plot_area_sqft: Optional[float] = None
    bedrooms: Optional[float] = 2.0
    bathrooms: Optional[float] = 2.0
    property_age: Optional[float] = 4.0
    parking: Optional[bool] = True
    floor_number: Optional[int] = 3
    total_floors: Optional[int] = 12
    state: Optional[str] = "Odisha"
    city: Optional[str] = "Bhubaneswar"
    commercial_type: Optional[str] = "retail"
    road_width_ft: Optional[str] = "30ft"
    corner_plot: Optional[str] = "standard"
    construction_grade: Optional[str] = "GRADE_B"


@app.post("/api/v1/valuation/estimate")
def estimate_v1_valuation(req: V1ValuationEstimateRequest):
    """
    Production Endpoint: Executes champion trained models (CatBoost/XGBoost)
    across the 7 property valuation categories.
    """
    return production_models.estimate(
        property_type=req.property_type,
        latitude=req.latitude,
        longitude=req.longitude,
        builtup_area_sqft=req.builtup_area_sqft,
        carpet_area_sqft=req.carpet_area_sqft,
        plot_area_sqft=req.plot_area_sqft,
        bedrooms=req.bedrooms,
        bathrooms=req.bathrooms,
        property_age=req.property_age,
        floor_number=req.floor_number,
        total_floors=req.total_floors,
        state=req.state,
        city=req.city,
        commercial_type=req.commercial_type,
        road_width_ft=req.road_width_ft,
        corner_plot=req.corner_plot,
        construction_grade=req.construction_grade
    )
