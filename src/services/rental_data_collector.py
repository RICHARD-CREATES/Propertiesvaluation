"""
Rental Market Data Collector (RMDC) Microservice Engine.

Implements compliant data ingestion, normalization, duplicate detection,
outlier/staleness flagging, job auditing, and source health tracking.
Never bypasses portal bot protections or treats advertised listings as verified leases.
"""
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from src.core.rental_db import (
    LocalityRentalStatistic,
    RentalCollectionJob,
    RentalDataSource,
    RentalListing,
    RentalPriceHistory,
    SessionLocal,
    init_rental_db,
)
from src.services.location_intelligence import haversine_km
from src.services.rental_comparables import _normalize_property_category


def normalize_area_sqft(area_value: float, area_unit: str = "sqft") -> float:
    """Converts sqft, sqm, or sqyards into standardized square feet."""
    val = float(area_value or 0.0)
    unit = str(area_unit or "sqft").lower().strip()
    if unit in ("sqm", "sq m", "m2", "square_meters"):
        return round(val * 10.7639, 1)
    if unit in ("sqyard", "sqyards", "sq_yard", "gaj"):
        return round(val * 9.0, 1)
    return round(val, 1)


def normalize_furnishing(furnishing_raw: Optional[str]) -> str:
    f = str(furnishing_raw or "semi_furnished").lower().strip()
    if "fully" in f or f == "furnished":
        return "fully_furnished"
    if "unfurn" in f or "bare" in f:
        return "unfurnished"
    return "semi_furnished"


def normalize_data_category(category_raw: Optional[str]) -> str:
    c = str(category_raw or "User_Submitted").strip()
    valid = {
        "Verified_Achieved",
        "Advertised_Asking",
        "Broker_Reported",
        "User_Submitted",
        "Historical_Benchmark",
    }
    if c in valid:
        return c
    lower = c.lower()
    if "verified" in lower or "executed" in lower or "deed" in lower:
        return "Verified_Achieved"
    if "asking" in lower or "advertised" in lower or "listing" in lower:
        return "Advertised_Asking"
    if "broker" in lower:
        return "Broker_Reported"
    if "benchmark" in lower or "historical" in lower:
        return "Historical_Benchmark"
    return "User_Submitted"


class BaseRentalSourceAdapter:
    """Base interface for rental data adapters with explicit licensing & access checks."""
    source_name: str = "base"
    api_available: bool = False
    compliance_note: str = "Uninitialized"

    def fetch_listings(self, latitude: float, longitude: float, radius_km: float) -> Dict[str, Any]:
        raise NotImplementedError


class PortalRestrictedAdapter(BaseRentalSourceAdapter):
    """Explicit compliance placeholder for protected portals without open API authorization."""

    def __init__(self, portal_name: str):
        self.source_name = portal_name
        self.api_available = False
        self.compliance_note = (
            f"{portal_name} enforces bot protection and restricts redistribution without "
            "a licensed partner API agreement. Automated scraping disabled by compliance policy."
        )

    def fetch_listings(self, latitude: float, longitude: float, radius_km: float) -> Dict[str, Any]:
        return {
            "status": "RESTRICTED",
            "source_name": self.source_name,
            "records": [],
            "message": self.compliance_note,
        }


class AuthorizedPartnerFeedAdapter(BaseRentalSourceAdapter):
    """Adapter for authorized local benchmarks, user leases, and verified partner feeds."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.api_available = True
        self.compliance_note = f"Authorized ingestion adapter for {source_name}"

    def fetch_listings(self, latitude: float, longitude: float, radius_km: float) -> Dict[str, Any]:
        return {
            "status": "READY",
            "source_name": self.source_name,
            "records": [],
            "message": f"Adapter {self.source_name} listening for verified feed / submissions.",
        }


class RentalDataCollectorService:
    """
    Orchestrates compliant rental data ingestion, cleaning, duplicate detection,
    outlier/staleness validation, job tracking, and locality statistic snapshots.
    """

    STALE_DAYS_THRESHOLD = 60

    def __init__(self):
        init_rental_db(seed_historical_benchmarks=True)
        self.adapters: Dict[str, BaseRentalSourceAdapter] = {
            "pan_india_rental_yield_index": AuthorizedPartnerFeedAdapter("pan_india_rental_yield_index"),
            "verified_broker_submission": AuthorizedPartnerFeedAdapter("verified_broker_submission"),
            "user_submitted_lease": AuthorizedPartnerFeedAdapter("user_submitted_lease"),
            "igr_odisha_lease_registry": PortalRestrictedAdapter("igr_odisha_lease_registry"),
            "rera_odisha_disclosures": PortalRestrictedAdapter("rera_odisha_disclosures"),
            "99acres": PortalRestrictedAdapter("99acres"),
            "magicbricks": PortalRestrictedAdapter("magicbricks"),
            "housing_com": PortalRestrictedAdapter("housing_com"),
            "nobroker": PortalRestrictedAdapter("nobroker"),
        }

    def validate_and_normalize_record(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Validates mandatory attributes and normalizes units/categories before DB storage."""
        lat = float(raw["latitude"])
        lon = float(raw["longitude"])
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Invalid GPS coordinates: ({lat}, {lon})")

        rent = float(raw["monthly_rent_inr"])
        if rent <= 0.0:
            raise ValueError(f"Monthly rent must be > 0, got {rent}")

        raw_area = float(raw.get("builtup_area_sqft") or raw.get("carpet_area_sqft") or raw.get("area_value") or 0.0)
        area_unit = raw.get("area_unit", "sqft")
        norm_area = normalize_area_sqft(raw_area, area_unit)
        if norm_area <= 50.0:
            raise ValueError(f"Invalid or missing property area ({norm_area} sq ft)")

        carpet_area = (
            normalize_area_sqft(raw["carpet_area_sqft"], area_unit)
            if raw.get("carpet_area_sqft")
            else round(norm_area * 0.80, 1)
        )
        builtup_area = (
            normalize_area_sqft(raw["builtup_area_sqft"], area_unit)
            if raw.get("builtup_area_sqft")
            else norm_area
        )

        obs_date_raw = raw.get("observation_date")
        if isinstance(obs_date_raw, date):
            obs_date = obs_date_raw
        elif obs_date_raw:
            obs_date = datetime.strptime(str(obs_date_raw)[:10], "%Y-%m-%d").date()
        else:
            obs_date = date.today()

        is_stale = (date.today() - obs_date).days > self.STALE_DAYS_THRESHOLD
        data_cat = normalize_data_category(raw.get("data_category"))
        verif_status = raw.get("verification_status") or (
            "verified_executed_lease" if data_cat == "Verified_Achieved" else "pending_verification"
        )

        return {
            "source_name": str(raw.get("source_name", "user_submitted_lease")).strip(),
            "external_listing_id": raw.get("external_listing_id"),
            "data_category": data_cat,
            "verification_status": verif_status,
            "property_type": _normalize_property_category(raw.get("property_type")),
            "bhk": float(raw["bhk"]) if raw.get("bhk") is not None else None,
            "bathrooms": float(raw["bathrooms"]) if raw.get("bathrooms") is not None else None,
            "carpet_area_sqft": carpet_area,
            "builtup_area_sqft": builtup_area,
            "floor_number": int(raw["floor_number"]) if raw.get("floor_number") is not None else None,
            "total_floors": int(raw["total_floors"]) if raw.get("total_floors") is not None else None,
            "building_age_years": float(raw["building_age_years"]) if raw.get("building_age_years") is not None else None,
            "monthly_rent_inr": round(rent, 2),
            "security_deposit_inr": float(raw["security_deposit_inr"]) if raw.get("security_deposit_inr") is not None else None,
            "maintenance_monthly_inr": float(raw.get("maintenance_monthly_inr", 0.0) or 0.0),
            "lease_duration_months": int(raw["lease_duration_months"]) if raw.get("lease_duration_months") is not None else None,
            "implied_gross_yield_pct": float(raw["implied_gross_yield_pct"]) if raw.get("implied_gross_yield_pct") is not None else None,
            "furnishing": normalize_furnishing(raw.get("furnishing")),
            "parking_slots": int(raw.get("parking_slots", 0) or 0),
            "latitude": lat,
            "longitude": lon,
            "country_code": str(raw.get("country_code", "IN")).upper(),
            "state": str(raw.get("state", "Odisha")).strip(),
            "city": str(raw.get("city", "Bhubaneswar")).strip(),
            "locality": str(raw.get("locality", "Central")).strip(),
            "pin_code": str(raw.get("pin_code", "")).strip() or None,
            "observation_date": obs_date,
            "last_verified_date": obs_date if data_cat == "Verified_Achieved" else None,
            "is_stale": is_stale,
            "confidence_score": 0.92 if data_cat == "Verified_Achieved" else (0.78 if data_cat == "Broker_Reported" else 0.65),
        }

    def detect_duplicate(self, norm: Dict[str, Any], db: Session) -> Optional[str]:
        """
        Deterministic + fuzzy duplicate detection:
        Matches active listings within 50m GPS radius, same property category,
        area within +/-5%, and rent within +/-5%. Returns canonical_group_id if duplicate.
        """
        deg_pad = 0.002  # ~220m bounding check
        candidates = db.query(RentalListing).filter(
            RentalListing.is_active.is_(True),
            RentalListing.property_type == norm["property_type"],
            RentalListing.latitude.between(norm["latitude"] - deg_pad, norm["latitude"] + deg_pad),
            RentalListing.longitude.between(norm["longitude"] - deg_pad, norm["longitude"] + deg_pad),
        ).all()

        norm_area = norm["builtup_area_sqft"] or norm["carpet_area_sqft"]
        for cand in candidates:
            dist_km = haversine_km(norm["latitude"], norm["longitude"], cand.latitude, cand.longitude)
            if dist_km > 0.05:  # > 50m away
                continue
            cand_area = cand.builtup_area_sqft or cand.carpet_area_sqft or 1.0
            area_diff = abs(cand_area - norm_area) / max(cand_area, 1.0)
            rent_diff = abs(cand.monthly_rent_inr - norm["monthly_rent_inr"]) / max(cand.monthly_rent_inr, 1.0)

            bhk_match = (norm["bhk"] is None or cand.bhk is None or abs(norm["bhk"] - cand.bhk) < 0.5)
            if area_diff <= 0.05 and rent_diff <= 0.05 and bhk_match:
                if not cand.canonical_group_id:
                    cand.canonical_group_id = cand.id
                    db.flush()
                return cand.canonical_group_id
        return None

    def detect_outlier(self, norm: Dict[str, Any], db: Session) -> bool:
        """
        Robust IQR outlier detection against homogeneous records in same city + category.
        Flags outliers cleanly without silently deleting them.
        """
        peers = db.query(RentalListing).filter(
            RentalListing.is_active.is_(True),
            RentalListing.is_outlier.is_(False),
            RentalListing.city == norm["city"],
            RentalListing.property_type == norm["property_type"],
        ).all()

        if len(peers) < 4:
            # Sanity fallback bounds for INR/sqft/mo (less than Rs. 2/sqft or > Rs. 800/sqft)
            rps = norm["monthly_rent_inr"] / max(norm["builtup_area_sqft"], 1.0)
            return rps < 2.0 or rps > 800.0

        peer_rps = np.array(
            [p.monthly_rent_inr / max(p.builtup_area_sqft or p.carpet_area_sqft, 1.0) for p in peers],
            dtype=float,
        )
        q1 = float(np.percentile(peer_rps, 25))
        q3 = float(np.percentile(peer_rps, 75))
        iqr = max(q3 - q1, float(np.median(peer_rps)) * 0.25)
        low_bound = max(2.0, q1 - 2.0 * iqr)
        high_bound = q3 + 2.5 * iqr

        target_rps = norm["monthly_rent_inr"] / max(norm["builtup_area_sqft"], 1.0)
        return target_rps < low_bound or target_rps > high_bound

    def ingest_listing_batch(
        self,
        raw_records: List[Dict[str, Any]],
        source_name: str,
        location_query: str = "Manual/Partner Batch",
        radius_km: float = 5.0,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Executes full RMDC normalization, deduplication, outlier audit, and DB insertion with job log."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            job = RentalCollectionJob(
                source_name=source_name,
                location_query=location_query,
                radius_km=radius_km,
                started_at=datetime.utcnow(),
                records_collected=len(raw_records),
                status="RUNNING",
            )
            db.add(job)
            db.flush()

            accepted = 0
            rejected = 0
            duplicates_flagged = 0
            outliers_flagged = 0
            errors: List[str] = []

            for idx, raw in enumerate(raw_records):
                try:
                    raw_with_src = {**raw, "source_name": raw.get("source_name") or source_name}
                    norm = self.validate_and_normalize_record(raw_with_src)
                    dup_group = self.detect_duplicate(norm, db)
                    is_outlier = self.detect_outlier(norm, db)

                    listing_id = str(uuid.uuid4())
                    listing = RentalListing(
                        id=listing_id,
                        canonical_group_id=dup_group or listing_id,
                        is_duplicate=dup_group is not None,
                        is_outlier=is_outlier,
                        **norm,
                    )
                    db.add(listing)
                    db.flush()

                    # Append historical rent tracking snapshot
                    rps = round(norm["monthly_rent_inr"] / max(norm["builtup_area_sqft"], 1.0), 2)
                    db.add(
                        RentalPriceHistory(
                            listing_id=listing.id,
                            city=norm["city"],
                            locality=norm["locality"],
                            property_type=norm["property_type"],
                            data_category=norm["data_category"],
                            monthly_rent_inr=norm["monthly_rent_inr"],
                            rent_per_sqft_inr=rps,
                            gross_yield_pct=norm["implied_gross_yield_pct"],
                            snapshot_date=norm["observation_date"],
                        )
                    )

                    accepted += 1
                    if dup_group is not None:
                        duplicates_flagged += 1
                    if is_outlier:
                        outliers_flagged += 1
                except Exception as exc:
                    rejected += 1
                    errors.append(f"Row {idx}: {exc}")

            job.records_accepted = accepted
            job.records_rejected = rejected
            job.completed_at = datetime.utcnow()
            job.error_log = "; ".join(errors[:10]) if errors else None
            job.status = "SUCCESS" if rejected == 0 else ("PARTIAL_SUCCESS" if accepted > 0 else "FAILED")

            src_row = db.query(RentalDataSource).filter_by(source_name=source_name).first()
            if src_row and accepted > 0:
                src_row.last_successful_collection = datetime.utcnow()

            db.commit()

            return {
                "job_id": job.id,
                "status": job.status,
                "records_collected": len(raw_records),
                "records_accepted": accepted,
                "records_rejected": rejected,
                "duplicates_flagged": duplicates_flagged,
                "outliers_flagged": outliers_flagged,
                "errors": errors,
            }
        finally:
            if close_db:
                db.close()

    def trigger_manual_refresh(
        self,
        latitude: float,
        longitude: float,
        location_label: str = "User Selected Location",
        radius_km: float = 5.0,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Triggers a compliant manual collection check across registered adapters.
        Respects portal terms (no bot-bypass scraping), logs job runs, and returns adapter statuses.
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            adapter_reports = []
            for name, adapter in self.adapters.items():
                res = adapter.fetch_listings(latitude, longitude, radius_km)
                job = RentalCollectionJob(
                    source_name=name,
                    location_query=location_label,
                    radius_km=radius_km,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    records_collected=len(res.get("records", [])),
                    records_accepted=0,
                    records_rejected=0,
                    error_log=None if res["status"] == "READY" else res["message"],
                    status=res["status"],
                )
                db.add(job)
                adapter_reports.append({
                    "source_name": name,
                    "api_available": adapter.api_available,
                    "status": res["status"],
                    "message": res["message"],
                })

            db.commit()
            return {
                "refresh_timestamp": datetime.utcnow().isoformat() + "Z",
                "location": {"latitude": latitude, "longitude": longitude, "label": location_label, "radius_km": radius_km},
                "adapter_reports": adapter_reports,
            }
        finally:
            if close_db:
                db.close()

    def get_source_health(self, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            rows = db.query(RentalDataSource).order_by(RentalDataSource.source_name).all()
            return [
                {
                    "source_name": r.source_name,
                    "source_type": r.source_type,
                    "api_available": r.api_available,
                    "licensing_status": r.licensing_status,
                    "redistribution_permitted": r.redistribution_permitted,
                    "is_enabled": r.is_enabled,
                    "last_successful_collection": r.last_successful_collection.isoformat() if r.last_successful_collection else None,
                    "notes": r.notes,
                }
                for r in rows
            ]
        finally:
            if close_db:
                db.close()

    def get_collection_jobs(self, limit: int = 20, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            jobs = db.query(RentalCollectionJob).order_by(RentalCollectionJob.started_at.desc()).limit(limit).all()
            return [
                {
                    "job_id": j.id,
                    "source_name": j.source_name,
                    "location_query": j.location_query,
                    "radius_km": j.radius_km,
                    "status": j.status,
                    "records_collected": j.records_collected,
                    "records_accepted": j.records_accepted,
                    "records_rejected": j.records_rejected,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                    "error_log": j.error_log,
                }
                for j in jobs
            ]
        finally:
            if close_db:
                db.close()
