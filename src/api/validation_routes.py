"""
FastAPI Router for Independent Valuation Accuracy & Evidence Validation (Milestone 7 - Task 6).
Mounted cleanly onto the main FastAPI application in src/api/app.py.
"""
import json
from collections import Counter
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.ground_truth_db import GroundTruthTransaction, ValidationEvaluationRun
from src.core.rental_db import SessionLocal
from src.services.validation_engine import IndependentValidationEngine

router = APIRouter(prefix="/api/validation", tags=["Independent Valuation Accuracy & Evidence Validation"])

val_engine = IndependentValidationEngine()


class GroundTruthRecordInput(BaseModel):
    transaction_id: Optional[str] = None
    property_type: str
    latitude: float
    longitude: float
    locality: str
    city: str
    state: str
    country_code: str = "IN"
    sale_price: float
    transaction_date: str
    builtup_area_sqft: Optional[float] = None
    carpet_area_sqft: Optional[float] = None
    plot_area_sqft: Optional[float] = None
    bhk: Optional[float] = None
    construction_age_years: Optional[float] = None
    source_name: str
    data_category: str = "Verified_Registered_Transaction"
    verification_status: Optional[str] = None
    evidence_url: Optional[str] = None
    document_reference: Optional[str] = None


class IngestBatchRequest(BaseModel):
    transactions: List[GroundTruthRecordInput]


class SpatialSplitRequest(BaseModel):
    cluster_radius_km: float = Field(3.0, gt=0.1, le=50.0)
    seed: int = 42


class EvaluateRequest(BaseModel):
    include_splits: Optional[List[str]] = None
    persist_run: bool = True


@router.post("/ground-truth/ingest")
def api_ingest_ground_truth(req: IngestBatchRequest):
    """Ingests ground-truth deed records with strict validation, duplicate check, and source segregation."""
    raw_list = [t.model_dump() for t in req.transactions]
    res = val_engine.ingest_transactions(raw_list)
    if res["accepted"] == 0 and res["duplicates_detected"] == 0 and res["rejected"] > 0:
        raise HTTPException(status_code=400, detail={"message": "All submitted records failed validation.", "errors": res["errors"]})
    return {"status": "success", **res}


@router.get("/ground-truth")
def api_list_ground_truth(
    data_category: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Lists stored ground-truth records with explicit provenance separation."""
    with SessionLocal() as db:
        q = db.query(GroundTruthTransaction)
        if data_category:
            q = q.filter(GroundTruthTransaction.data_category == data_category)
        if property_type:
            q = q.filter(GroundTruthTransaction.property_type == property_type.lower())
        total = q.count()
        rows = q.order_by(GroundTruthTransaction.created_at.desc()).limit(limit).all()

        all_cats = db.query(GroundTruthTransaction.data_category).all()
        source_breakdown = dict(Counter(c[0] for c in all_cats))

        items = [
            {
                "transaction_id": r.transaction_id,
                "property_type": r.property_type,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "locality": r.locality,
                "city": r.city,
                "state": r.state,
                "sale_price": r.sale_price,
                "transaction_date": r.transaction_date.isoformat(),
                "builtup_area_sqft": r.builtup_area_sqft,
                "plot_area_sqft": r.plot_area_sqft,
                "source_name": r.source_name,
                "data_category": r.data_category,
                "verification_status": r.verification_status,
                "evidence_url": r.evidence_url,
                "document_reference": r.document_reference,
                "geo_cluster_id": r.geo_cluster_id,
                "split_group": r.split_group,
                "is_duplicate": r.is_duplicate,
            }
            for r in rows
        ]
    return {"status": "success", "total_matching": total, "source_breakdown": source_breakdown, "transactions": items}


@router.post("/spatial-split")
def api_run_spatial_split(req: SpatialSplitRequest):
    """Assigns spatially clustered train/validation/test splits guaranteeing zero geographic leakage."""
    try:
        res = val_engine.run_spatial_split_on_db(cluster_radius_km=req.cluster_radius_km, seed=req.seed)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/evaluate")
def api_evaluate_ground_truth(req: EvaluateRequest):
    """Evaluates valuation approaches strictly against held-out verified independent ground-truth deeds."""
    try:
        res = val_engine.evaluate_ground_truth(include_splits=req.include_splits, persist_run=req.persist_run)
        return {"status": "success", **res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/dashboard")
def api_validation_dashboard():
    """Returns full validation dashboard telemetry, metrics, error distributions, and unvalidated components."""
    with SessionLocal() as db:
        all_rows = db.query(GroundTruthTransaction).all()
        source_breakdown = dict(Counter(r.data_category for r in all_rows))
        verified_count = sum(1 for r in all_rows if r.data_category == "Verified_Registered_Transaction" and not r.is_duplicate)
        latest = db.query(ValidationEvaluationRun).order_by(ValidationEvaluationRun.evaluated_at.desc()).first()

    if latest:
        return {
            "status": "success",
            "validation_status": latest.validation_status,
            "evaluated_at": latest.evaluated_at.isoformat() + "Z",
            "verified_sample_count": latest.verified_sample_count,
            "source_breakdown": source_breakdown,
            "overall_metrics_by_approach": json.loads(latest.overall_metrics_json),
            "metrics_by_property_type": json.loads(latest.category_metrics_json),
            "metrics_by_locality": json.loads(latest.locality_metrics_json),
            "geographic_validation_coverage": json.loads(latest.spatial_split_audit_json),
            "unvalidated_components": json.loads(latest.unvalidated_components_json),
            "historical_run_available": True,
        }

    # Live check when no evaluation snapshot persisted yet
    live = val_engine.evaluate_ground_truth(persist_run=False)
    live["status"] = "success"
    live["historical_run_available"] = False
    return live
