"""
Phase 6 Integration Bridge — Canonical Evidence <-> Ground Truth Validation,
Read-Only Analytics & Out-of-Distribution (OOD) Detection
===========================================================================
Strictly maintains data segregation between verified arm's-length market deeds and
broker claims, listings, circle rates, ORERA disclosures, and synthetic records.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.core.evidence_schema import CanonicalTransaction, DatasetMembership
from src.core.ground_truth_db import GroundTruthTransaction, compute_dedup_signature
from src.services.location_intelligence import LocationIntelligenceService, haversine_km


CANONICAL_TO_M7_TYPE = {
    "apartment": "apartment",
    "builder_floor": "apartment",
    "standalone_house": "standalone_house",
    "villa": "standalone_house",
    "commercial": "commercial",
    "residential_land": "residential_land",
    "agricultural": "agricultural",
    "industrial": "industrial",
}


class OutOfDistributionDetector:
    """Detects out-of-distribution inputs relative to Bhubaneswar/Odisha training regimes."""

    BBSR_CENTER = (20.2961, 85.8245)

    @staticmethod
    def assess(
        property_type: str,
        latitude: float,
        longitude: float,
        area_sqft: float,
        asset_type: str = "residential",
    ) -> Dict[str, Any]:
        loc = LocationIntelligenceService()
        flags: List[str] = []

        clean_type = str(property_type or "").lower().strip()
        if clean_type in ("agricultural", "agricultural_land", "industrial", "industrial_land") or asset_type in ("agricultural", "industrial"):
            flags.append("DATA_NOT_READY_ASSET_CLASS")

        if not loc.is_in_india_bounds(latitude, longitude):
            flags.append("OUTSIDE_INDIA_TRAINING_DOMAIN")
        else:
            dist_bbsr = haversine_km(latitude, longitude, *OutOfDistributionDetector.BBSR_CENTER)
            if dist_bbsr > 60.0:
                flags.append(f"OUTSIDE_BHUBANESWAR_PRIMARY_CORRIDOR ({dist_bbsr:.1f} km from core)")

        if asset_type == "land" or clean_type == "residential_land":
            if area_sqft < 200.0 or area_sqft > 435600.0:
                flags.append(f"EXTREME_LAND_AREA ({area_sqft:.0f} sqft)")
        else:
            if area_sqft < 150.0 or area_sqft > 40000.0:
                flags.append(f"EXTREME_BUILTUP_AREA ({area_sqft:.0f} sqft)")

        if not flags:
            severity = "IN_DISTRIBUTION"
            fallback = "Standard production model + spatial comparable & income reconciliation applied."
        elif "DATA_NOT_READY_ASSET_CLASS" in flags or "OUTSIDE_INDIA_TRAINING_DOMAIN" in flags:
            severity = "HIGH_OOD_FALLBACK_ACTIVE"
            fallback = (
                "Insufficient local trained ML support for this jurisdiction/asset class; "
                "rely strictly on verified Cost/Income inputs and independent physical appraisal."
            )
        else:
            severity = "MODERATE_EXTRAPOLATION"
            fallback = (
                "Input lies outside core Bhubaneswar calibration density; widen uncertainty awareness "
                "and verify local circle-rate & sub-registrar comparables before relying on estimates."
            )

        return {
            "is_ood": len(flags) > 0,
            "ood_severity": severity,
            "ood_flags": flags,
            "recommended_fallback": fallback,
        }


def sync_verified_canonical_to_ground_truth(db: Session) -> Dict[str, int]:
    """
    Promotes eligible REGISTRATION_VERIFIED, ARMS_LENGTH_MARKET, non-training-overlapping
    CanonicalTransactions into Milestone 7 `ground_truth_transactions` without overwriting
    existing ground-truth rows or polluting validation with broker/circle-rate/agreement rows.
    """
    # Check active TRAINING/VALIDATION dataset memberships so zero training rows leak into GT
    trained_ids = {
        r[0]
        for r in db.query(DatasetMembership.transaction_id)
        .filter(DatasetMembership.dataset_role.in_(("TRAINING", "VALIDATION")))
        .all()
    }

    candidates = (
        db.query(CanonicalTransaction)
        .filter(
            CanonicalTransaction.eligible_for_ground_truth_validation.is_(True),
            CanonicalTransaction.verification_status == "REGISTRATION_VERIFIED",
            CanonicalTransaction.source_category == "REGISTRATION_VERIFIED_TX",
            CanonicalTransaction.used_in_model_training.is_(False),
            CanonicalTransaction.ground_truth_tx_id.is_(None),
        )
        .all()
    )

    synced = 0
    skipped_overlap = 0
    skipped_existing = 0

    for tx in candidates:
        if tx.transaction_id in trained_ids:
            tx.used_in_model_training = True
            tx.eligible_for_ground_truth_validation = False
            skipped_overlap += 1
            continue

        if tx.latitude is None or tx.longitude is None or tx.sale_price_inr is None or tx.transaction_date is None:
            continue

        m7_type = CANONICAL_TO_M7_TYPE.get(tx.property_type)
        if not m7_type:
            continue

        existing_gt = db.query(GroundTruthTransaction).filter_by(transaction_id=tx.transaction_id).first()
        if existing_gt:
            tx.ground_truth_tx_id = existing_gt.id
            skipped_existing += 1
            continue

        app_area = tx.builtup_area_sqft or tx.land_area_sqft or tx.carpet_area_sqft
        dedup_sig = tx.dedup_signature or compute_dedup_signature(
            m7_type, tx.latitude, tx.longitude, tx.sale_price_inr, tx.transaction_date.isoformat(), app_area
        )

        gt_row = GroundTruthTransaction(
            transaction_id=tx.transaction_id,
            dedup_signature=dedup_sig,
            property_type=m7_type,
            latitude=tx.latitude,
            longitude=tx.longitude,
            locality=tx.locality or "Unspecified",
            city=tx.city,
            state=tx.state,
            country_code="IN",
            sale_price=tx.sale_price_inr,
            transaction_date=tx.transaction_date,
            builtup_area_sqft=tx.builtup_area_sqft,
            carpet_area_sqft=tx.carpet_area_sqft,
            plot_area_sqft=tx.land_area_sqft,
            source_name=tx.source_type,
            data_category="Verified_Registered_Transaction",
            verification_status="verified_independent_deed",
            document_reference=tx.evidence_document_reference,
            is_duplicate=False,
        )
        db.add(gt_row)
        db.flush()
        tx.ground_truth_tx_id = gt_row.id
        synced += 1

    db.commit()
    return {
        "synced_to_ground_truth": synced,
        "skipped_training_overlap": skipped_overlap,
        "linked_existing": skipped_existing,
    }


def fetch_verified_canonical_analytics_records(
    db: Session,
    city: Optional[str] = None,
    locality: Optional[str] = None,
    property_type: Optional[str] = None,
    include_unverified: bool = False,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    """
    Queries CanonicalTransaction strictly segregated for analytics modules.
    By default returns ONLY `eligible_for_ground_truth_validation == True` completed market sales.
    """
    q = db.query(CanonicalTransaction).filter(CanonicalTransaction.source_category != "SYNTHETIC_TEST")
    if not include_unverified:
        q = q.filter(CanonicalTransaction.eligible_for_ground_truth_validation.is_(True))
    if city:
        q = q.filter(CanonicalTransaction.city == city)
    if locality:
        q = q.filter(CanonicalTransaction.locality == locality)
    if property_type:
        q = q.filter(CanonicalTransaction.property_type == property_type.lower().strip())

    rows = q.order_by(CanonicalTransaction.transaction_date.desc()).limit(limit).all()
    return [
        {
            "transaction_id": r.transaction_id,
            "property_type": r.property_type,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "locality": r.locality,
            "city": r.city,
            "state": r.state,
            "country": "IN",
            "sale_price": r.sale_price_inr,
            "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
            "builtup_area_sqft": r.builtup_area_sqft,
            "carpet_area_sqft": r.carpet_area_sqft,
            "plot_area_sqft": r.land_area_sqft,
            "source_name": r.source_type,
            "data_category": r.source_category,
            "verification_status": r.verification_status,
        }
        for r in rows
    ]
