"""
Ground-Truth Transaction Validation Database Schema (Milestone 7 - Task 1).

Provides strict provenance-segregated storage for independent real estate transaction validation:
- Verified_Registered_Transaction: Eligible for accuracy validation (requires evidence_url or document_reference)
- Broker_Report: Informational market signal (excluded from independent ground truth)
- Advertised_Asking_Price: Listing ask only (never substituted as executed sale price)
- Historical_Benchmark: Regional hub index (never treated as independent test data)
- Synthetic_Test_Record: Explicitly segregated and blocked from production ground truth
"""
import hashlib
import math
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from src.core.rental_db import Base, SessionLocal, engine


VALID_DATA_CATEGORIES = {
    "Verified_Registered_Transaction",
    "Broker_Report",
    "Advertised_Asking_Price",
    "Historical_Benchmark",
    "Synthetic_Test_Record",
}

VALID_PROPERTY_TYPES = {
    "apartment",
    "standalone_house",
    "commercial",
    "residential_land",
    "agricultural",
    "industrial",
}


def _gen_uuid() -> str:
    return str(uuid.uuid4())


def compute_dedup_signature(
    property_type: str,
    latitude: float,
    longitude: float,
    sale_price: float,
    transaction_date_str: str,
    builtup_area_sqft: Optional[float],
) -> str:
    """Deterministic fingerprint to detect duplicate transaction deeds."""
    area_key = round(float(builtup_area_sqft or 0.0), 0)
    raw = f"{property_type}|{round(latitude, 5)}|{round(longitude, 5)}|{round(sale_price, 0)}|{transaction_date_str}|{area_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class GroundTruthTransaction(Base):
    __tablename__ = "ground_truth_transactions"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    transaction_id = Column(String(128), unique=True, nullable=False, index=True)
    dedup_signature = Column(String(64), nullable=False, index=True)

    property_type = Column(String(40), nullable=False, index=True)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    locality = Column(String(128), nullable=False, index=True)
    city = Column(String(64), nullable=False, index=True)
    state = Column(String(64), nullable=False, index=True)
    country_code = Column(String(8), nullable=False, default="IN")

    sale_price = Column(Float, nullable=False)
    transaction_date = Column(Date, nullable=False, index=True)
    builtup_area_sqft = Column(Float, nullable=True)
    carpet_area_sqft = Column(Float, nullable=True)
    plot_area_sqft = Column(Float, nullable=True)
    bhk = Column(Float, nullable=True)
    construction_age_years = Column(Float, nullable=True)

    source_name = Column(String(64), nullable=False, index=True)
    data_category = Column(String(40), nullable=False, index=True)
    verification_status = Column(String(40), nullable=False, default="unverified", index=True)
    evidence_url = Column(Text, nullable=True)
    document_reference = Column(String(256), nullable=True)

    geo_cluster_id = Column(String(64), nullable=True, index=True)
    split_group = Column(String(16), nullable=False, default="unassigned", index=True)  # 'unassigned', 'train', 'validation', 'test'
    is_duplicate = Column(Boolean, default=False, index=True)
    duplicate_of_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_gt_geo", "latitude", "longitude"),
        Index("idx_gt_cat_type_split", "data_category", "property_type", "split_group"),
    )


class ValidationEvaluationRun(Base):
    __tablename__ = "validation_evaluation_runs"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    evaluated_at = Column(DateTime, default=datetime.utcnow, index=True)
    dataset_scope = Column(String(64), nullable=False)
    validation_status = Column(String(48), nullable=False)  # 'VALIDATED', 'PARTIALLY_VALIDATED', 'INSUFFICIENT_VERIFIED_GROUND_TRUTH'
    verified_sample_count = Column(Integer, default=0)
    overall_metrics_json = Column(Text, nullable=False)
    category_metrics_json = Column(Text, nullable=False)
    locality_metrics_json = Column(Text, nullable=False)
    spatial_split_audit_json = Column(Text, nullable=False)
    source_breakdown_json = Column(Text, nullable=False)
    unvalidated_components_json = Column(Text, nullable=False)


def init_ground_truth_db() -> None:
    """Creates ground truth validation tables and applies non-destructive Phase 2/3/4 evidence migrations."""
    Base.metadata.create_all(bind=engine)
    from src.core.evidence_schema import run_phase4_migrations

    run_phase4_migrations(engine)


def validate_transaction_payload(raw: dict) -> dict:
    """
    Strictly validates incoming transaction records, enforces geographic bounds,
    prevents synthetic/asking prices from passing as Verified_Registered_Transaction,
    and requires evidence_url or document_reference for verified deeds.
    """
    tx_id = str(raw.get("transaction_id") or f"TX-{uuid.uuid4().hex[:10].upper()}").strip()
    prop_type = str(raw.get("property_type") or "").lower().strip()
    if prop_type not in VALID_PROPERTY_TYPES:
        raise ValueError(f"Unsupported property_type '{prop_type}'. Expected one of {sorted(VALID_PROPERTY_TYPES)}.")

    try:
        lat = float(raw["latitude"])
        lon = float(raw["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Valid numeric 'latitude' and 'longitude' are required.") from exc

    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Invalid GPS coordinates: ({lat}, {lon}).")

    try:
        sale_price = float(raw["sale_price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid 'sale_price'.") from exc
    if not math.isfinite(sale_price) or sale_price <= 0.0:
        raise ValueError(f"Sale price must be strictly positive (got {sale_price}).")

    builtup = raw.get("builtup_area_sqft")
    carpet = raw.get("carpet_area_sqft")
    plot = raw.get("plot_area_sqft")
    if builtup is not None:
        builtup = float(builtup)
        if not math.isfinite(builtup) or builtup <= 0.0:
            raise ValueError(f"builtup_area_sqft must be positive (got {builtup}).")
    if carpet is not None:
        carpet = float(carpet)
        if not math.isfinite(carpet) or carpet <= 0.0:
            raise ValueError(f"carpet_area_sqft must be positive (got {carpet}).")
    if plot is not None:
        plot = float(plot)
        if not math.isfinite(plot) or plot <= 0.0:
            raise ValueError(f"plot_area_sqft must be positive (got {plot}).")

    if prop_type != "residential_land" and builtup is None and carpet is None and plot is None:
        raise ValueError("At least one area measurement (builtup_area_sqft, carpet_area_sqft, or plot_area_sqft) is required.")
    if prop_type == "residential_land" and plot is None and builtup is None:
        raise ValueError("Vacant land transactions require 'plot_area_sqft'.")

    tx_date_raw = raw.get("transaction_date")
    if isinstance(tx_date_raw, date):
        tx_date = tx_date_raw
    elif tx_date_raw:
        try:
            tx_date = datetime.strptime(str(tx_date_raw)[:10], "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid transaction_date '{tx_date_raw}'. Expected YYYY-MM-DD.") from exc
    else:
        raise ValueError("Missing required 'transaction_date' (YYYY-MM-DD).")

    locality = str(raw.get("locality") or "").strip()
    city = str(raw.get("city") or "").strip()
    state = str(raw.get("state") or "").strip()
    if not locality or not city or not state:
        raise ValueError("'locality', 'city', and 'state' are required fields.")

    source_name = str(raw.get("source_name") or "").strip()
    if not source_name:
        raise ValueError("'source_name' is required for provenance tracking.")

    data_category = str(raw.get("data_category") or "Verified_Registered_Transaction").strip()
    if data_category not in VALID_DATA_CATEGORIES:
        raise ValueError(f"Invalid data_category '{data_category}'. Must be one of {sorted(VALID_DATA_CATEGORIES)}.")

    evidence_url = str(raw.get("evidence_url") or "").strip() or None
    doc_ref = str(raw.get("document_reference") or "").strip() or None
    verif_status = str(raw.get("verification_status") or "").strip().lower()

    # Enforce strict ground-truth provenance rules
    if data_category == "Synthetic_Test_Record" or "synthetic" in source_name.lower() or "synthetic" in verif_status:
        data_category = "Synthetic_Test_Record"
        verif_status = "rejected_synthetic"
    elif data_category == "Advertised_Asking_Price":
        verif_status = "asking_only"
    elif data_category == "Verified_Registered_Transaction":
        if not evidence_url and not doc_ref:
            raise ValueError(
                "Verified_Registered_Transaction requires an 'evidence_url' or 'document_reference' (e.g. SRO Deed Number)."
            )
        verif_status = "verified_independent_deed"
    else:
        verif_status = verif_status or "non_ground_truth"

    sig = compute_dedup_signature(prop_type, lat, lon, sale_price, tx_date.isoformat(), builtup or plot or carpet)

    return {
        "transaction_id": tx_id,
        "dedup_signature": sig,
        "property_type": prop_type,
        "latitude": lat,
        "longitude": lon,
        "locality": locality,
        "city": city,
        "state": state,
        "country_code": str(raw.get("country_code") or "IN").upper().strip(),
        "sale_price": round(sale_price, 2),
        "transaction_date": tx_date,
        "builtup_area_sqft": builtup,
        "carpet_area_sqft": carpet,
        "plot_area_sqft": plot,
        "bhk": float(raw["bhk"]) if raw.get("bhk") is not None else None,
        "construction_age_years": float(raw["construction_age_years"]) if raw.get("construction_age_years") is not None else None,
        "source_name": source_name,
        "data_category": data_category,
        "verification_status": verif_status,
        "evidence_url": evidence_url,
        "document_reference": doc_ref,
    }
