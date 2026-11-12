"""
Read-Only Analytics & Intelligence FastAPI Router (/api/analytics/*).

Strictly read-only: performs SELECT queries only (never modifies database tables
or overrides production valuation weights) and computes in-memory diagnostics across:
1. Data Quality Intelligence
2. Exploratory Property EDA
3. Micro-Market & Spatial Locality Dispersion
4. Feature Price Drivers & Zero-Leakage Permutation Importance
5. Verified Production Model TreeSHAP Explainability
6. Mix-Adjusted Seasonality & Chronological Validation
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from src.analytics.coverage_intelligence import GeographicCoverageAnalyzer
from src.analytics.data_quality import IndianPropertyDataQualityAuditor
from src.analytics.micro_market_analysis import MicroMarketAnalyzer
from src.analytics.model_explainability import ProductionModelSHAPExplainer
from src.analytics.price_driver_analysis import PriceDriverAnalyzer
from src.analytics.property_eda import PropertyEDAAnalyzer
from src.analytics.seasonality_analysis import SeasonalityAnalyzer
from src.core.ground_truth_db import GroundTruthTransaction
from src.core.rental_db import SessionLocal
from src.services.evidence_bridge import fetch_verified_canonical_analytics_records

router = APIRouter(prefix="/api/analytics", tags=["Read-Only Market & Model Analytics"])
coverage_router = APIRouter(tags=["Read-Only Geographic Coverage Intelligence"])

_auditor = IndianPropertyDataQualityAuditor()
_eda = PropertyEDAAnalyzer(auditor=_auditor)
_micro = MicroMarketAnalyzer(auditor=_auditor)
_drivers = PriceDriverAnalyzer(auditor=_auditor)
_shap_explainer = ProductionModelSHAPExplainer()
_seasonality = SeasonalityAnalyzer(auditor=_auditor)
_coverage = GeographicCoverageAnalyzer()


def _fetch_readonly_ground_truth_records(
    city: Optional[str] = None,
    locality: Optional[str] = None,
    property_type: Optional[str] = None,
    data_category: Optional[str] = None,
    include_synthetic: bool = False,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    """Read-only ORM loader unifying verified CanonicalTransaction & GroundTruthTransaction records."""
    with SessionLocal() as db:
        canonical_rows = (
            fetch_verified_canonical_analytics_records(
                db,
                city=city,
                locality=locality,
                property_type=property_type,
                include_unverified=False,
                limit=limit,
            )
            if not data_category
            else []
        )

        q = db.query(GroundTruthTransaction)
        if not include_synthetic:
            q = q.filter(GroundTruthTransaction.data_category != "Synthetic_Test_Record")
        if data_category:
            q = q.filter(GroundTruthTransaction.data_category == data_category)
        if city:
            q = q.filter(GroundTruthTransaction.city == city)
        if locality:
            q = q.filter(GroundTruthTransaction.locality == locality)
        if property_type:
            q = q.filter(GroundTruthTransaction.property_type == property_type.lower().strip())

        rows = q.order_by(GroundTruthTransaction.transaction_date.desc()).limit(limit).all()

    seen_ids = {c["transaction_id"] for c in canonical_rows}
    merged = list(canonical_rows)
    for r in rows:
        if r.transaction_id in seen_ids:
            continue
        seen_ids.add(r.transaction_id)
        merged.append(
            {
                "transaction_id": r.transaction_id,
                "property_type": r.property_type,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "locality": r.locality,
                "city": r.city,
                "state": r.state,
                "country": r.country_code,
                "sale_price": r.sale_price,
                "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
                "builtup_area_sqft": r.builtup_area_sqft,
                "carpet_area_sqft": r.carpet_area_sqft,
                "plot_area_sqft": r.plot_area_sqft,
                "bedrooms": r.bhk,
                "property_age_years": r.construction_age_years,
                "source_name": r.source_name,
                "data_category": r.data_category,
                "verification_status": r.verification_status,
            }
        )
    return merged[:limit]


@router.get("/data-quality")
def get_data_quality_audit(
    city: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    data_category: Optional[str] = Query(None),
    include_synthetic: bool = Query(False),
    limit: int = Query(2000, ge=1, le=5000),
):
    """Read-only data quality, RERA physics, semantic missingness, and IQR/MAD outlier audit."""
    records = _fetch_readonly_ground_truth_records(
        city=city,
        property_type=property_type,
        data_category=data_category,
        include_synthetic=include_synthetic,
        limit=limit,
    )
    audit = _auditor.audit_dataset(records)
    return {
        "read_only": True,
        "synthetic_records_included": include_synthetic,
        **audit,
    }


@router.get("/eda")
def get_property_eda(
    city: Optional[str] = Query(None),
    locality: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    data_category: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
):
    """Read-only exploratory quantile & age-cohort breakdown over stored non-synthetic records."""
    records = _fetch_readonly_ground_truth_records(
        city=city,
        locality=locality,
        property_type=property_type,
        data_category=data_category,
        include_synthetic=False,
        limit=limit,
    )
    return {"read_only": True, **_eda.analyze(records)}


@router.get("/micro-markets")
def get_micro_market_analysis(
    city: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    cluster_radius_km: float = Query(3.0, gt=0.1, le=50.0),
    min_reliable_samples: int = Query(5, ge=2, le=100),
    limit: int = Query(2000, ge=1, le=5000),
):
    """Read-only homogeneous locality/tier dispersion and spatial cluster summary."""
    records = _fetch_readonly_ground_truth_records(
        city=city,
        property_type=property_type,
        include_synthetic=False,
        limit=limit,
    )
    return {
        "read_only": True,
        **_micro.analyze(records, cluster_radius_km=cluster_radius_km, min_reliable_samples=min_reliable_samples),
    }


@router.get("/drivers")
def get_price_driver_analysis(
    city: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    cluster_radius_km: float = Query(3.0, gt=0.1, le=50.0),
    limit: int = Query(2000, ge=1, le=5000),
):
    """Read-only associative price correlations, SizeBand curves, and spatial-split feature importance."""
    records = _fetch_readonly_ground_truth_records(
        city=city,
        property_type=property_type,
        include_synthetic=False,
        limit=limit,
    )
    return {"read_only": True, **_drivers.analyze(records, cluster_radius_km=cluster_radius_km)}


@router.get("/explain")
def explain_production_valuation(
    property_type: str = Query("apartment"),
    latitude: float = Query(20.353),
    longitude: float = Query(85.826),
    builtup_area_sqft: Optional[float] = Query(1250.0, gt=0),
    plot_area_sqft: Optional[float] = Query(None, gt=0),
    bedrooms: Optional[float] = Query(2.0, ge=0),
    bathrooms: Optional[float] = Query(2.0, ge=0),
    property_age_years: Optional[float] = Query(4.0, ge=0),
    floor_number: Optional[int] = Query(3, ge=0),
    total_floors: Optional[int] = Query(12, ge=1),
    state: str = Query("Odisha"),
    city: str = Query("Bhubaneswar"),
    construction_grade: str = Query("GRADE_B"),
    commercial_type: str = Query("retail"),
    road_width_ft: str = Query("30ft"),
    corner_plot: str = Query("standard"),
    top_k: int = Query(5, ge=1, le=15),
):
    """Read-only verified TreeSHAP attribution against live trained production model artifacts."""
    payload = {
        "property_type": property_type,
        "latitude": latitude,
        "longitude": longitude,
        "builtup_area_sqft": builtup_area_sqft,
        "plot_area_sqft": plot_area_sqft,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "property_age_years": property_age_years,
        "floor_number": floor_number,
        "total_floors": total_floors,
        "state": state,
        "city": city,
        "construction_grade": construction_grade,
        "commercial_type": commercial_type,
        "road_width_ft": road_width_ft,
        "corner_plot": corner_plot,
    }
    return {"read_only": True, **_shap_explainer.explain_instance(payload, top_k=top_k)}


@router.get("/seasonality")
def get_seasonality_analysis(
    city: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    min_months: int = Query(24, ge=6, le=120),
    min_deals_per_month: int = Query(5, ge=1, le=100),
    limit: int = Query(5000, ge=1, le=10000),
):
    """Read-only mix-adjusted seasonality and chronological split validation with strict sample gates."""
    records = _fetch_readonly_ground_truth_records(
        city=city,
        property_type=property_type,
        include_synthetic=False,
        limit=limit,
    )
    return {
        "read_only": True,
        **_seasonality.analyze(
            records,
            min_months=min_months,
            min_deals_per_month=min_deals_per_month,
        ),
    }


@router.get("/coverage")
@coverage_router.get("/api/coverage/bhubaneswar")
def get_geographic_coverage(city: str = Query("Bhubaneswar")):
    """Read-only Bhubaneswar/city locality coverage report with strict verified sample gates."""
    with SessionLocal() as db:
        return _coverage.build_city_coverage_report(db, city=city)
