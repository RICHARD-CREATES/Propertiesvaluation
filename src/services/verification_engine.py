"""
Milestone 8 — Phase 3: Verification State Machine, Validation Rules & Audit Ledger
=================================================================================
Enforces evidence-backed state transitions, actor authorization, configurable market/PPSF
anomaly review flags, 4-signal non-destructive duplicate detection, decoupled ground-truth vs
training eligibility, and atomic audit logging alongside Phase 2 immutable raw archives.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from src.core.evidence_schema import (
    CANONICAL_SOURCE_CATEGORIES,
    CANONICAL_VERIFICATION_STATUSES,
    COMPLETED_SALE_DOCUMENT_TYPES,
    EVIDENCE_DOCUMENT_TYPES,
    TRANSACTION_CLASSIFICATIONS,
    CanonicalTransaction,
    DatasetMembership,
    VerificationAuditLog,
    archive_raw_source_record,
    compute_canonical_payload_sha256,
    evaluate_detailed_eligibility,
)
from src.core.ground_truth_db import compute_dedup_signature
from src.core.security_auth import AuthenticationError, VerifiedPrincipal, get_auth_manager
from src.services.location_intelligence import LocationIntelligenceService, haversine_km


class VerificationTransitionError(ValueError):
    """Raised when a verification state transition violates evidence or state-machine rules."""


class UnauthorizedActorError(PermissionError):
    """Raised when an unauthorized actor role attempts a protected state transition."""


AUTHORIZED_ACTOR_ROLES = {
    "SYSTEM_INGESTION",
    "INTERNAL_AUTOMATED_VALIDATOR",
    "HUMAN_REVIEWER",
    "AUTHORIZED_REGISTRY_VERIFIER",
    "SENIOR_AUDIT_ADMIN",
}

TRUSTED_REGISTRATION_METHODS = {
    "OFFICIAL_IGR_EC_VERIFICATION",
    "SRO_CERTIFIED_COPY_MATCH",
    "AUTHORIZED_REGISTRY_API",
}

UNTRUSTED_SHORTCUT_METHODS = {
    "OCR_RESULT_ONLY",
    "PLAUSIBLE_REGEX_ONLY",
    "FILE_UPLOAD_ONLY",
    "BROKER_CLAIM_ONLY",
}

# Explicit State Transition Matrix: (from_status, to_status) -> transition policy
EXPLICIT_TRANSITION_MATRIX: Dict[Tuple[Optional[str], str], Dict[str, Any]] = {
    (None, "UNVERIFIED"): {
        "allowed_roles": {"SYSTEM_INGESTION", "HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Initial record admission strictly enters UNVERIFIED.",
    },
    (None, "REJECTED"): {
        "allowed_roles": {"SYSTEM_INGESTION", "INTERNAL_AUTOMATED_VALIDATOR", "HUMAN_REVIEWER", "SENIOR_AUDIT_ADMIN"},
        "description": "Initial admission rejected due to hard invariant failure (e.g. non-INR, impossible physics/dates).",
    },
    ("UNVERIFIED", "SOURCE_CONFIRMED"): {
        "allowed_roles": {"INTERNAL_AUTOMATED_VALIDATOR", "HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Metadata/source cross-checked against RERA/BDA/BMV or authorized partner attestation.",
    },
    ("UNVERIFIED", "DOCUMENT_VERIFIED"): {
        "allowed_roles": {"HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Documentary sale proof (deed/certified copy/EC extract/agreement) reviewed by human/verifier.",
    },
    ("SOURCE_CONFIRMED", "DOCUMENT_VERIFIED"): {
        "allowed_roles": {"HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Source-confirmed record upgraded upon valid documentary review.",
    },
    ("DOCUMENT_VERIFIED", "REGISTRATION_VERIFIED"): {
        "allowed_roles": {"AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Completed deed independently corroborated via IGR EC / SRO certified copy / authorized registry.",
    },
    ("UNVERIFIED", "REJECTED"): {
        "allowed_roles": {"INTERNAL_AUTOMATED_VALIDATOR", "HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Unverified record rejected with documented reason.",
    },
    ("SOURCE_CONFIRMED", "REJECTED"): {
        "allowed_roles": {"INTERNAL_AUTOMATED_VALIDATOR", "HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Source-confirmed record rejected with documented reason.",
    },
    ("DOCUMENT_VERIFIED", "REJECTED"): {
        "allowed_roles": {"HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Document-verified record rejected after failed corroboration or forgery finding.",
    },
    ("REGISTRATION_VERIFIED", "REJECTED"): {
        "allowed_roles": {"AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN"},
        "description": "Registration-verified record revoked/rejected upon registry cancellation or fraud proof.",
    },
    ("REJECTED", "UNVERIFIED"): {
        "allowed_roles": {"SENIOR_AUDIT_ADMIN"},
        "description": "Rejected record reopened to UNVERIFIED by senior audit admin for fresh review.",
    },
}


# Authoritative Odisha / Bhubaneswar locality hubs (centres + verified typical extent km).
# Municipal boundary GeoJSON polygons take precedence if provided; Khordha bounding box is strictly a preliminary filter.
BHUBANESWAR_AUTHORITATIVE_LOCALITIES: Dict[str, Tuple[float, float, float]] = {
    "patia": (20.3533, 85.8266, 5.5),
    "chandrasekharpur": (20.3267, 85.8189, 5.0),
    "khandagiri": (20.2569, 85.7792, 5.5),
    "jayadev vihar": (20.2994, 85.8245, 3.5),
    "saheed nagar": (20.2896, 85.8445, 3.5),
    "sahid nagar": (20.2896, 85.8445, 3.5),
    "nayapalli": (20.2950, 85.8065, 4.0),
    "kalinga nagar": (20.2682, 85.7478, 5.5),
    "tamando": (20.2330, 85.7450, 5.0),
    "sundarpada": (20.2289, 85.8095, 5.0),
    "rasulgarh": (20.2906, 85.8648, 4.0),
    "laxmisagar": (20.2720, 85.8485, 3.5),
    "old town": (20.2400, 85.8335, 4.0),
    "vss nagar": (20.3036, 85.8485, 3.5),
    "infocity": (20.3490, 85.8080, 4.5),
}

PRELIMINARY_BBSR_BBOX = (19.90, 20.65, 85.40, 86.25)  # (lat_min, lat_max, lon_min, lon_max)


@dataclass
class PPSFSanityConfig:
    """Configurable INR/sqft sanity thresholds by (locality_lower, property_type) with safe fallbacks."""
    default_bounds_by_type: Dict[str, Tuple[float, float]] = field(
        default_factory=lambda: {
            "apartment": (1800.0, 22000.0),
            "standalone_house": (2000.0, 28000.0),
            "villa": (2500.0, 32000.0),
            "builder_floor": (2000.0, 24000.0),
            "commercial": (3000.0, 45000.0),
            "residential_land": (500.0, 25000.0),
            "agricultural": (20.0, 3500.0),
            "industrial": (500.0, 18000.0),
        }
    )
    locality_overrides: Dict[Tuple[str, str], Tuple[float, float]] = field(
        default_factory=lambda: {
            ("patia", "apartment"): (3200.0, 14000.0),
            ("chandrasekharpur", "apartment"): (3200.0, 14000.0),
            ("saheed nagar", "apartment"): (4000.0, 16500.0),
            ("jayadev vihar", "apartment"): (4200.0, 17500.0),
            ("sundarpada", "apartment"): (2400.0, 9500.0),
            ("kalinga nagar", "apartment"): (2400.0, 9500.0),
        }
    )

    def get_bounds(self, locality: Optional[str], property_type: str) -> Tuple[float, float]:
        loc_key = (str(locality or "").strip().lower(), property_type.lower().strip())
        if loc_key in self.locality_overrides:
            return self.locality_overrides[loc_key]
        return self.default_bounds_by_type.get(property_type.lower().strip(), (100.0, 100000.0))


def _sha256_looks_valid(val: Optional[str]) -> bool:
    return bool(val and re.fullmatch(r"[0-9a-fA-F]{64}", val.strip()))


def _applicable_area(tx: CanonicalTransaction) -> Optional[float]:
    if tx.property_type in ("residential_land", "agricultural"):
        return tx.land_area_sqft or tx.builtup_area_sqft
    return tx.builtup_area_sqft or tx.carpet_area_sqft or tx.land_area_sqft


def detect_duplicate_candidates(
    db: Session,
    tx: CanonicalTransaction,
    close_date_window_days: int = 30,
) -> Dict[str, Any]:
    """
    Runs 4-signal non-destructive duplicate checks.
    Produces review flags and `probable_duplicate_of_tx_id` ONLY — never deletes or merges legal rows.
    """
    flags: List[Dict[str, Any]] = []
    candidate_ids: List[str] = []

    base_q = db.query(CanonicalTransaction).filter(CanonicalTransaction.transaction_id != tx.transaction_id)

    # 1. Duplicate registration identifier
    if tx.evidence_document_reference:
        same_ref = base_q.filter(
            CanonicalTransaction.evidence_document_reference == tx.evidence_document_reference
        ).all()
        for m in same_ref:
            candidate_ids.append(m.transaction_id)
            flags.append(
                {
                    "flag": "DUPLICATE_REGISTRATION_IDENTIFIER_REVIEW",
                    "matched_transaction_id": m.transaction_id,
                    "detail": f"Matching evidence_document_reference '{tx.evidence_document_reference}'.",
                }
            )

    # 2. Repeated source-document hash
    doc_hash = tx.source_document_hash or tx.evidence_document_hash
    if doc_hash:
        same_hash = base_q.filter(
            (CanonicalTransaction.source_document_hash == doc_hash)
            | (CanonicalTransaction.evidence_document_hash == doc_hash)
        ).all()
        for m in same_hash:
            if m.transaction_id not in candidate_ids:
                candidate_ids.append(m.transaction_id)
            flags.append(
                {
                    "flag": "REPEATED_SOURCE_DOCUMENT_HASH_REVIEW",
                    "matched_transaction_id": m.transaction_id,
                    "detail": f"Repeated evidence/source document hash '{doc_hash[:12]}...'.",
                }
            )

    # 3. Same property_id with closely spaced dates (review candidate, NOT assumed duplicate!)
    if tx.property_id and tx.transaction_date:
        same_prop = base_q.filter(
            CanonicalTransaction.property_id == tx.property_id,
            CanonicalTransaction.transaction_date.isnot(None),
        ).all()
        for m in same_prop:
            day_gap = abs((tx.transaction_date - m.transaction_date).days)
            if day_gap <= close_date_window_days:
                if m.transaction_id not in candidate_ids:
                    candidate_ids.append(m.transaction_id)
                flags.append(
                    {
                        "flag": "SAME_PROPERTY_CLOSE_DATES_REVIEW",
                        "matched_transaction_id": m.transaction_id,
                        "detail": (
                            f"Same property_id '{tx.property_id}' within {day_gap} days "
                            f"(<= {close_date_window_days}d window; requires review, could be distinct resale)."
                        ),
                    }
                )

    # 4. Near-identical price (<=2%), location (<=50m Haversine), and area (<=2%)
    my_area = _applicable_area(tx)
    if tx.latitude is not None and tx.longitude is not None and tx.sale_price_inr and my_area:
        geo_candidates = base_q.filter(
            CanonicalTransaction.latitude.isnot(None),
            CanonicalTransaction.longitude.isnot(None),
            CanonicalTransaction.sale_price_inr.isnot(None),
            CanonicalTransaction.property_type == tx.property_type,
        ).all()
        for m in geo_candidates:
            other_area = _applicable_area(m)
            if not other_area or m.sale_price_inr <= 0:
                continue
            dist_km = haversine_km(tx.latitude, tx.longitude, m.latitude, m.longitude)
            price_diff_pct = abs(tx.sale_price_inr - m.sale_price_inr) / max(tx.sale_price_inr, m.sale_price_inr)
            area_diff_pct = abs(my_area - other_area) / max(my_area, other_area)
            if dist_km <= 0.05 and price_diff_pct <= 0.02 and area_diff_pct <= 0.02:
                if m.transaction_id not in candidate_ids:
                    candidate_ids.append(m.transaction_id)
                flags.append(
                    {
                        "flag": "NEAR_IDENTICAL_PRICE_LOCATION_AREA_REVIEW",
                        "matched_transaction_id": m.transaction_id,
                        "detail": (
                            f"Within {dist_km * 1000:.1f}m, price delta {price_diff_pct * 100:.2f}%, "
                            f"area delta {area_diff_pct * 100:.2f}% — candidate duplicate for human review."
                        ),
                    }
                )

    return {
        "has_duplicate_flags": len(flags) > 0,
        "flags": flags,
        "probable_duplicate_of_tx_id": candidate_ids[0] if candidate_ids else None,
    }


def run_transaction_validation_checks(
    tx: CanonicalTransaction,
    db: Session,
    ppsf_config: Optional[PPSFSanityConfig] = None,
    currency: str = "INR",
    authoritative_polygons: Optional[Dict[str, List[Tuple[float, float]]]] = None,
) -> Dict[str, Any]:
    """
    Executes all 8 Phase 3 validation checks + configurable PPSF/circle-rate review flags.
    Distinguishes hard errors (must reject) from non-destructive review flags (requires human review).
    """
    cfg = ppsf_config or PPSFSanityConfig()
    loc_service = LocationIntelligenceService()
    hard_errors: List[str] = []
    review_flags: List[str] = []

    # 1. Currency & Sale Price
    curr_upper = str(currency or "INR").upper().strip()
    if curr_upper != "INR":
        hard_errors.append(f"Unsupported non-INR currency '{curr_upper}'.")
    if tx.sale_price_inr is not None and tx.sale_price_inr <= 0.0:
        hard_errors.append(f"Non-positive sale_price_inr ({tx.sale_price_inr}).")

    # 2. Dates validation
    today = date.today()
    min_allowed_date = date(1950, 1, 1)
    if tx.transaction_date is not None:
        if tx.transaction_date > today:
            hard_errors.append(f"Future transaction_date ({tx.transaction_date}).")
        elif tx.transaction_date < min_allowed_date:
            hard_errors.append(f"Implausible pre-1950 transaction_date ({tx.transaction_date}).")

    if tx.registration_date is not None:
        if tx.registration_date > today:
            hard_errors.append(f"Future registration_date ({tx.registration_date}).")
        elif tx.registration_date < min_allowed_date:
            hard_errors.append(f"Implausible pre-1950 registration_date ({tx.registration_date}).")
        elif tx.transaction_date is not None and (tx.transaction_date - tx.registration_date).days > 365:
            review_flags.append("REGISTRATION_EARLIER_THAN_TX_BY_GT_1Y_REVIEW")

    # 3. Area consistency (RERA carpet <= builtup)
    for col_name in ("land_area_sqft", "builtup_area_sqft", "carpet_area_sqft"):
        val = getattr(tx, col_name)
        if val is not None and val <= 0.0:
            hard_errors.append(f"Non-positive {col_name} ({val}).")

    if tx.carpet_area_sqft is not None and tx.builtup_area_sqft is not None:
        if tx.carpet_area_sqft > tx.builtup_area_sqft * 1.02:
            hard_errors.append(
                f"Impossible physical area ratio: carpet ({tx.carpet_area_sqft}) > built-up ({tx.builtup_area_sqft})."
            )

    # 4. Geographic consistency (authoritative polygon -> preliminary centroid / bbox filter)
    geo_check_mode = "NONE"
    geo_authority_level = "NONE"
    if tx.latitude is not None and tx.longitude is not None:
        if not loc_service.validate_coordinates(tx.latitude, tx.longitude):
            hard_errors.append(f"Invalid global GPS ({tx.latitude}, {tx.longitude}).")
        elif not loc_service.is_in_india_bounds(tx.latitude, tx.longitude):
            hard_errors.append(f"Coordinates ({tx.latitude}, {tx.longitude}) outside India bounds.")
        elif str(tx.city or "").strip().lower() == "bhubaneswar":
            loc_key = str(tx.locality or "").strip().lower()
            if authoritative_polygons and loc_key in authoritative_polygons:
                geo_check_mode = "AUTHORITATIVE_POLYGON"
                geo_authority_level = "AUTHORITATIVE_MUNICIPAL_POLYGON"
                # Ray casting point-in-polygon check (lat=y, lon=x)
                poly = authoritative_polygons[loc_key]
                inside = False
                n_pts = len(poly)
                j = n_pts - 1
                for i in range(n_pts):
                    xi, yi = poly[i]
                    xj, yj = poly[j]
                    if ((yi > tx.longitude) != (yj > tx.longitude)) and (
                        tx.latitude < (xj - xi) * (tx.longitude - yi) / ((yj - yi) or 1e-12) + xi
                    ):
                        inside = not inside
                    j = i
                if not inside:
                    review_flags.append("OUTSIDE_AUTHORITATIVE_LOCALITY_POLYGON_REVIEW")
            elif loc_key in BHUBANESWAR_AUTHORITATIVE_LOCALITIES:
                geo_check_mode = "AUTHORITATIVE_LOCALITY_CENTROID_FILTER"
                geo_authority_level = "PRELIMINARY_CENTROID_FILTER_ONLY"
                c_lat, c_lon, rad_km = BHUBANESWAR_AUTHORITATIVE_LOCALITIES[loc_key]
                if haversine_km(tx.latitude, tx.longitude, c_lat, c_lon) > rad_km:
                    review_flags.append("LOCALITY_GPS_CENTROID_MISMATCH_REVIEW")
            else:
                geo_check_mode = "PRELIMINARY_BBOX_FILTER"
                geo_authority_level = "PRELIMINARY_BBOX_FILTER_ONLY"
                lat_lo, lat_hi, lon_lo, lon_hi = PRELIMINARY_BBSR_BBOX
                if not (lat_lo <= tx.latitude <= lat_hi and lon_lo <= tx.longitude <= lon_hi):
                    review_flags.append("OUTSIDE_BHUBANESWAR_PRELIMINARY_BBOX_REVIEW")

    # 5. Evidence document & classification compatibility
    if tx.evidence_document_type not in EVIDENCE_DOCUMENT_TYPES:
        hard_errors.append(f"Unknown evidence_document_type '{tx.evidence_document_type}'.")
    if tx.transaction_classification not in TRANSACTION_CLASSIFICATIONS:
        hard_errors.append(f"Unknown transaction_classification '{tx.transaction_classification}'.")
    if tx.evidence_document_type == "AGREEMENT_FOR_SALE":
        review_flags.append("AGREEMENT_FOR_SALE_INCOMPLETE_TRANSACTION")

    # 6. Source category compatibility
    if tx.source_category not in CANONICAL_SOURCE_CATEGORIES:
        hard_errors.append(f"Invalid source_category '{tx.source_category}'.")
    if tx.source_type == "AUTHORIZED_BROKER_FEED" and tx.source_category in ("DOCUMENT_VERIFIED_TX", "REGISTRATION_VERIFIED_TX"):
        if tx.evidence_document_type not in COMPLETED_SALE_DOCUMENT_TYPES or not tx.evidence_document_hash:
            hard_errors.append("Broker feed cannot enter verified transaction category without completed deed document & hash.")
    if tx.source_type == "GOVT_CIRCLE_RATE" and tx.source_category != "GOVT_CIRCLE_RATE_REFERENCE":
        hard_errors.append("Government circle rate record must remain in GOVT_CIRCLE_RATE_REFERENCE.")
    if tx.source_type == "ADVERTISED_LISTING" and tx.source_category != "UNVERIFIED_BROKER_OR_LISTING":
        hard_errors.append("Advertised listing must remain in UNVERIFIED_BROKER_OR_LISTING.")

    # 7. Below-circle-rate check (REVIEW FLAG ONLY, never auto-reject!)
    if tx.circle_rate_inr is not None and tx.sale_price_inr is not None and tx.circle_rate_inr > 0.0:
        if tx.sale_price_inr < tx.circle_rate_inr:
            review_flags.append("BELOW_CIRCLE_RATE_REVIEW")

    # 8. Configurable PPSF anomaly check (REVIEW FLAG ONLY, never assumes fraud!)
    app_area = _applicable_area(tx)
    if tx.sale_price_inr and app_area and app_area > 0 and tx.source_category != "ORERA_BDA_ENRICHMENT":
        ppsf = tx.sale_price_inr / app_area
        lo_ppsf, hi_ppsf = cfg.get_bounds(tx.locality, tx.property_type)
        if ppsf < lo_ppsf or ppsf > hi_ppsf:
            review_flags.append("PPSF_OUTSIDE_CONFIGURED_RANGE_REVIEW")

    # 9. Duplicate candidate review detection (non-destructive)
    dup_res = detect_duplicate_candidates(db, tx)
    for dflag in dup_res["flags"]:
        review_flags.append(dflag["flag"])

    # Deduplicate flags while keeping deterministic order
    unique_flags = list(dict.fromkeys(review_flags))
    return {
        "hard_errors": hard_errors,
        "review_flags": unique_flags,
        "has_hard_errors": len(hard_errors) > 0,
        "has_duplicate_flags": dup_res["has_duplicate_flags"],
        "duplicate_details": dup_res["flags"],
        "probable_duplicate_of_tx_id": dup_res["probable_duplicate_of_tx_id"],
        "geo_check_mode": geo_check_mode,
        "geo_authority_level": geo_authority_level,
    }


class TransactionVerificationService:
    """Atomic evidence admission, state-machine transition enforcement, and immutable audit ledger."""

    def __init__(self, ppsf_config: Optional[PPSFSanityConfig] = None, enforce_server_auth: bool = False):
        self.ppsf_config = ppsf_config or PPSFSanityConfig()
        self.enforce_server_auth = enforce_server_auth

    def _resolve_actor(
        self,
        actor_id: Optional[str],
        actor_role: Optional[str],
        principal: Optional[VerifiedPrincipal] = None,
        auth_token: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Resolves actor identity and role. When `principal` or `auth_token` is supplied (or
        `enforce_server_auth=True`), ignores raw client-provided actor strings and trusts ONLY
        cryptographically verified server tokens.
        """
        if principal is not None:
            if not getattr(principal, "verified_by_server", False):
                raise UnauthorizedActorError("Principal must be verified by server token manager.")
            return principal.actor_id, principal.actor_role
        if auth_token is not None:
            try:
                verified = get_auth_manager().verify_token(auth_token)
            except AuthenticationError as exc:
                raise UnauthorizedActorError(str(exc)) from exc
            return verified.actor_id, verified.actor_role
        if self.enforce_server_auth:
            raise UnauthorizedActorError(
                "Server-verified principal or Bearer token is mandatory; client-supplied actor_id/actor_role rejected."
            )
        if not actor_id or not actor_role:
            raise UnauthorizedActorError("actor_id and actor_role are required.")
        return actor_id, actor_role

    @staticmethod
    def _enforce_actor_authorization(from_status: Optional[str], to_status: str, actor_role: str) -> None:
        if actor_role not in AUTHORIZED_ACTOR_ROLES:
            raise UnauthorizedActorError(
                f"Actor role '{actor_role}' is not authorized in verification workflow."
            )
        policy = EXPLICIT_TRANSITION_MATRIX.get((from_status, to_status))
        if policy is None:
            raise VerificationTransitionError(
                f"Illegal verification state transition: {from_status} -> {to_status} is not permitted."
            )
        if actor_role not in policy["allowed_roles"]:
            raise UnauthorizedActorError(
                f"Actor role '{actor_role}' is NOT authorized to transition {from_status} -> {to_status}."
            )

    @staticmethod
    def _derive_source_category(source_type: str, status: str) -> str:
        if source_type == "SYNTHETIC_TEST":
            return "SYNTHETIC_TEST"
        if source_type == "GOVT_CIRCLE_RATE":
            return "GOVT_CIRCLE_RATE_REFERENCE"
        if source_type in ("ORERA_DISCLOSURE", "BDA_PLANNING", "BHULEKH_ROR"):
            return "ORERA_BDA_ENRICHMENT"
        if source_type == "ADVERTISED_LISTING":
            return "UNVERIFIED_BROKER_OR_LISTING"
        if source_type == "AUTHORIZED_BROKER_FEED":
            return "SOURCE_CONFIRMED_BROKER" if status == "SOURCE_CONFIRMED" else "UNVERIFIED_BROKER_OR_LISTING"
        if status == "REGISTRATION_VERIFIED":
            return "REGISTRATION_VERIFIED_TX"
        if status == "DOCUMENT_VERIFIED":
            return "DOCUMENT_VERIFIED_TX"
        return "UNVERIFIED_BROKER_OR_LISTING"

    @staticmethod
    def _append_audit_log(
        db: Session,
        tx: CanonicalTransaction,
        from_status: Optional[str],
        to_status: str,
        actor_id: str,
        actor_role: str,
        verification_method: str,
        reason: str,
        checks_snapshot: Dict[str, Any],
        rejection_or_escalation_reason: Optional[str] = None,
    ) -> VerificationAuditLog:
        log_row = VerificationAuditLog(
            transaction_id=tx.transaction_id,
            from_status=from_status,
            to_status=to_status,
            evidence_document_type=tx.evidence_document_type,
            evidence_document_reference=tx.evidence_document_reference,
            evidence_document_hash=tx.evidence_document_hash or tx.source_document_hash,
            verification_method=verification_method,
            actor=actor_id,
            actor_role=actor_role,
            reason=reason,
            rejection_or_escalation_reason=rejection_or_escalation_reason,
            checks_snapshot_json=json.dumps(checks_snapshot, sort_keys=True, default=str),
        )
        db.add(log_row)
        return log_row

    def _sync_eligibility_and_flags(
        self,
        db: Session,
        tx: CanonicalTransaction,
        checks: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged_flags = list(checks["review_flags"])
        if tx.evidence_document_type == "AGREEMENT_FOR_SALE" and "AGREEMENT_FOR_SALE_INCOMPLETE_TRANSACTION" not in merged_flags:
            merged_flags.append("AGREEMENT_FOR_SALE_INCOMPLETE_TRANSACTION")

        # Unresolved review exists whenever human review flags remain OR non-empty duplicate candidates exist
        if merged_flags:
            tx.requires_human_review = True
        tx.review_flags_json = json.dumps(merged_flags)
        if checks.get("probable_duplicate_of_tx_id"):
            tx.probable_duplicate_of_tx_id = checks["probable_duplicate_of_tx_id"]

        # Dataset membership overlap check: never validate on any transaction/property in TRAINING or VALIDATION
        if sa_inspect(db.get_bind()).has_table(DatasetMembership.__tablename__):
            in_train_split = (
                db.query(DatasetMembership)
                .filter(DatasetMembership.dataset_role.in_(("TRAINING", "VALIDATION")))
                .filter(
                    (DatasetMembership.transaction_id == tx.transaction_id)
                    | ((DatasetMembership.property_id == tx.property_id) & (DatasetMembership.property_id.isnot(None)))
                )
                .first()
            )
            if in_train_split is not None:
                tx.used_in_model_training = True

        elig = evaluate_detailed_eligibility(
            verification_status=tx.verification_status,
            source_category=tx.source_category,
            transaction_classification=tx.transaction_classification,
            is_arms_length=tx.is_arms_length,
            sale_price_inr=tx.sale_price_inr,
            requires_human_review=tx.requires_human_review,
            evidence_document_type=tx.evidence_document_type,
            applicable_area_sqft=_applicable_area(tx),
            has_unresolved_duplicates=checks.get("has_duplicate_flags", False),
            used_in_model_training=bool(tx.used_in_model_training),
        )
        tx.eligible_for_ground_truth_validation = elig["eligible_for_ground_truth_validation"]
        tx.eligible_for_model_training = elig["eligible_for_model_training"]
        tx.validation_exclusion_reasons_json = json.dumps(elig["exclusion_reasons"])
        return elig

    def admit_record(
        self,
        db: Session,
        raw_payload: Dict[str, Any],
        source_type: str,
        source_reference: str,
        actor_id: Optional[str] = "ingestion_pipeline",
        actor_role: Optional[str] = "SYSTEM_INGESTION",
        currency: str = "INR",
        principal: Optional[VerifiedPrincipal] = None,
        auth_token: Optional[str] = None,
        auto_commit: bool = True,
    ) -> CanonicalTransaction:
        """
        Atomically archives raw immutable payload and admits a record STRICTLY as UNVERIFIED
        (or REJECTED if critical structural invariants fail). Never admits directly as verified.
        """
        if raw_payload.get("requested_status") and raw_payload.get("requested_status") not in ("UNVERIFIED", "REJECTED"):
            raise VerificationTransitionError(
                f"Direct admission as '{raw_payload.get('requested_status')}' is forbidden; records must enter UNVERIFIED."
            )

        resolved_actor_id, resolved_actor_role = self._resolve_actor(actor_id, actor_role, principal, auth_token)
        self._enforce_actor_authorization(None, "UNVERIFIED", resolved_actor_role)

        raw_row, _ = archive_raw_source_record(
            db,
            source_type=source_type,
            source_reference=source_reference,
            raw_payload=raw_payload,
            external_record_key=raw_payload.get("transaction_id"),
        )

        tx_id = str(raw_payload.get("transaction_id") or f"CANON-{raw_row.raw_record_id[:12].upper()}")
        evid_doc_type = str(raw_payload.get("evidence_document_type") or "NONE").upper().strip()
        tx_class = str(raw_payload.get("transaction_classification") or "ATYPICAL_UNCLASSIFIED").upper().strip()

        def _parse_date(val: Any) -> Optional[date]:
            if val is None or isinstance(val, date):
                return val
            return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()

        tx_date = _parse_date(raw_payload.get("transaction_date"))
        reg_date = _parse_date(raw_payload.get("registration_date"))
        lat = float(raw_payload["latitude"]) if raw_payload.get("latitude") is not None else None
        lon = float(raw_payload["longitude"]) if raw_payload.get("longitude") is not None else None
        price = float(raw_payload["sale_price_inr"]) if raw_payload.get("sale_price_inr") is not None else None
        land_area = float(raw_payload["land_area_sqft"]) if raw_payload.get("land_area_sqft") is not None else None
        builtup = float(raw_payload["builtup_area_sqft"]) if raw_payload.get("builtup_area_sqft") is not None else None
        carpet = float(raw_payload["carpet_area_sqft"]) if raw_payload.get("carpet_area_sqft") is not None else None

        dedup_sig = None
        if lat is not None and lon is not None and price is not None and tx_date is not None:
            dedup_sig = compute_dedup_signature(
                str(raw_payload["property_type"]),
                lat,
                lon,
                price,
                tx_date.isoformat(),
                builtup or land_area or carpet,
            )

        initial_category = self._derive_source_category(source_type, "UNVERIFIED")
        tx = CanonicalTransaction(
            transaction_id=tx_id,
            property_id=raw_payload.get("property_id"),
            property_type=str(raw_payload["property_type"]).lower().strip(),
            transaction_date=tx_date,
            registration_date=reg_date,
            sale_price_inr=price,
            land_area_sqft=land_area,
            builtup_area_sqft=builtup,
            carpet_area_sqft=carpet,
            locality=raw_payload.get("locality"),
            city=str(raw_payload.get("city") or "Bhubaneswar"),
            district=raw_payload.get("district") or "Khordha",
            state=str(raw_payload.get("state") or "Odisha"),
            latitude=lat,
            longitude=lon,
            source_type=source_type,
            source_reference=source_reference,
            verification_status="UNVERIFIED",
            evidence_document_reference=raw_payload.get("evidence_document_reference"),
            evidence_document_hash=raw_payload.get("evidence_document_hash"),
            source_document_hash=raw_payload.get("source_document_hash") or raw_payload.get("evidence_document_hash"),
            circle_rate_inr=float(raw_payload["circle_rate_inr"]) if raw_payload.get("circle_rate_inr") is not None else None,
            raw_record_id=raw_row.raw_record_id,
            source_category=initial_category,
            evidence_document_type=evid_doc_type,
            transaction_classification=tx_class,
            is_arms_length=raw_payload.get("is_arms_length"),
            requires_human_review=True,
            eligible_for_ground_truth_validation=False,
            eligible_for_model_training=False,
            dedup_signature=dedup_sig,
        )
        db.add(tx)
        db.flush()

        checks = run_transaction_validation_checks(tx, db, ppsf_config=self.ppsf_config, currency=currency)
        if checks["has_hard_errors"]:
            tx.verification_status = "REJECTED"
            tx.rejection_reason = "; ".join(checks["hard_errors"])

        self._sync_eligibility_and_flags(db, tx, checks)
        self._append_audit_log(
            db=db,
            tx=tx,
            from_status=None,
            to_status=tx.verification_status,
            actor_id=resolved_actor_id,
            actor_role=resolved_actor_role,
            verification_method="INITIAL_ADMISSION_SCREENING",
            reason=tx.rejection_reason or "Record admitted under UNVERIFIED quarantine.",
            checks_snapshot=checks,
            rejection_or_escalation_reason=tx.rejection_reason or (",".join(checks["review_flags"]) or None),
        )
        if auto_commit:
            db.commit()
            db.refresh(tx)
        else:
            db.flush()
        return tx

    def transition_status(
        self,
        db: Session,
        transaction_id: str,
        target_status: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        verification_method: str = "MANUAL_REVIEW",
        reason: str = "",
        evidence_document_type: Optional[str] = None,
        evidence_document_reference: Optional[str] = None,
        evidence_document_hash: Optional[str] = None,
        registration_date: Optional[date] = None,
        corroboration_reference: Optional[str] = None,
        transaction_classification: Optional[str] = None,
        is_arms_length: Optional[bool] = None,
        clear_human_review: bool = False,
        retain_on_incomplete: bool = False,
        principal: Optional[VerifiedPrincipal] = None,
        auth_token: Optional[str] = None,
        auto_commit: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes an authorized, evidence-gated state transition and writes an immutable audit log atomically.
        """
        if target_status not in CANONICAL_VERIFICATION_STATUSES:
            raise VerificationTransitionError(f"Unsupported verification_status '{target_status}'.")

        resolved_actor_id, resolved_actor_role = self._resolve_actor(actor_id, actor_role, principal, auth_token)

        tx = db.query(CanonicalTransaction).filter(CanonicalTransaction.transaction_id == transaction_id).first()
        if tx is None:
            raise VerificationTransitionError(f"CanonicalTransaction '{transaction_id}' not found.")

        prev_status = tx.verification_status

        try:
            self._enforce_actor_authorization(prev_status, target_status, resolved_actor_role)
        except (UnauthorizedActorError, VerificationTransitionError):
            raise

        # Tentative evidence metadata updates inspected before transition gates
        eff_doc_type = (evidence_document_type or tx.evidence_document_type or "NONE").upper().strip()
        eff_doc_ref = evidence_document_reference if evidence_document_reference is not None else tx.evidence_document_reference
        eff_doc_hash = evidence_document_hash if evidence_document_hash is not None else tx.evidence_document_hash
        eff_reg_date = registration_date if registration_date is not None else tx.registration_date
        eff_class = (transaction_classification or tx.transaction_classification).upper().strip()
        eff_arms = tx.is_arms_length if is_arms_length is None else is_arms_length

        gap_errors: List[str] = []

        if target_status == "SOURCE_CONFIRMED":
            if tx.source_type in ("ADVERTISED_LISTING", "SYNTHETIC_TEST"):
                gap_errors.append(f"Source type '{tx.source_type}' cannot transition to SOURCE_CONFIRMED.")

        elif target_status == "DOCUMENT_VERIFIED":
            if tx.source_type in ("ADVERTISED_LISTING", "GOVT_CIRCLE_RATE", "ORERA_DISCLOSURE", "BDA_PLANNING", "SYNTHETIC_TEST"):
                gap_errors.append(f"Non-sale/unverified source '{tx.source_type}' cannot reach DOCUMENT_VERIFIED.")
            if eff_doc_type in ("NONE", "BROKER_ATTESTATION", "LISTING_SNAPSHOT", "GOVT_BENCHMARK_CIRCULAR", "ORERA_QPR_FILING", "BDA_PERMIT_RECORD"):
                gap_errors.append(f"Evidence type '{eff_doc_type}' is insufficient for DOCUMENT_VERIFIED.")
            if not eff_doc_ref or not _sha256_looks_valid(eff_doc_hash):
                gap_errors.append("DOCUMENT_VERIFIED requires non-empty evidence_document_reference and valid 64-char SHA-256 hash.")

        elif target_status == "REGISTRATION_VERIFIED":
            if eff_doc_type == "AGREEMENT_FOR_SALE":
                gap_errors.append("AGREEMENT_FOR_SALE cannot establish REGISTRATION_VERIFIED completed sale.")
            elif eff_doc_type not in COMPLETED_SALE_DOCUMENT_TYPES:
                gap_errors.append(f"Evidence type '{eff_doc_type}' cannot establish REGISTRATION_VERIFIED.")

            if verification_method in UNTRUSTED_SHORTCUT_METHODS or verification_method not in TRUSTED_REGISTRATION_METHODS:
                gap_errors.append(
                    f"Method '{verification_method}' cannot establish REGISTRATION_VERIFIED; requires one of {sorted(TRUSTED_REGISTRATION_METHODS)}."
                )
            if not corroboration_reference or not str(corroboration_reference).strip():
                gap_errors.append("Independent external corroboration_reference is mandatory for REGISTRATION_VERIFIED.")
            if not eff_doc_ref or not _sha256_looks_valid(eff_doc_hash) or eff_reg_date is None:
                gap_errors.append("REGISTRATION_VERIFIED requires valid document ref, SHA-256 hash, and registration_date.")
            if tx.source_type in ("ADVERTISED_LISTING", "GOVT_CIRCLE_RATE", "ORERA_DISCLOSURE", "BDA_PLANNING", "SYNTHETIC_TEST"):
                gap_errors.append(f"Source type '{tx.source_type}' is permanently excluded from REGISTRATION_VERIFIED.")

        elif target_status == "REJECTED":
            if not reason or not str(reason).strip():
                gap_errors.append("Explicit rejection reason is required when transitioning to REJECTED.")

        if gap_errors:
            if retain_on_incomplete:
                # Retain record safely at current supported status & record held verification attempt
                checks = run_transaction_validation_checks(tx, db, ppsf_config=self.ppsf_config)
                checks["held_transition_target"] = target_status
                checks["incomplete_verification_gaps"] = gap_errors
                self._append_audit_log(
                    db=db,
                    tx=tx,
                    from_status=prev_status,
                    to_status=prev_status,
                    actor_id=resolved_actor_id,
                    actor_role=resolved_actor_role,
                    verification_method=verification_method,
                    reason=f"Verification incomplete ({target_status} denied); retained at {prev_status}.",
                    checks_snapshot=checks,
                    rejection_or_escalation_reason="; ".join(gap_errors),
                )
                if auto_commit:
                    db.commit()
                else:
                    db.flush()
                return {
                    "outcome": "RETAINED_AT_CURRENT_STATUS",
                    "verification_status": prev_status,
                    "gaps": gap_errors,
                }
            raise VerificationTransitionError("; ".join(gap_errors))

        # Apply validated metadata & target status atomically within transaction
        try:
            tx.evidence_document_type = eff_doc_type
            tx.evidence_document_reference = eff_doc_ref
            tx.evidence_document_hash = eff_doc_hash
            if eff_doc_hash and not tx.source_document_hash:
                tx.source_document_hash = eff_doc_hash
            tx.registration_date = eff_reg_date
            tx.transaction_classification = eff_class
            tx.is_arms_length = eff_arms
            tx.verification_method = verification_method
            tx.reviewer_identity = resolved_actor_id
            tx.verification_status = target_status
            tx.source_category = self._derive_source_category(tx.source_type, target_status)
            if target_status == "REJECTED":
                tx.rejection_reason = reason
                tx.requires_human_review = False

            checks = run_transaction_validation_checks(tx, db, ppsf_config=self.ppsf_config)
            if checks["has_hard_errors"] and target_status != "REJECTED":
                raise VerificationTransitionError(
                    f"Validation checks blocked promotion to {target_status}: {'; '.join(checks['hard_errors'])}"
                )

            if clear_human_review and not checks["review_flags"]:
                tx.requires_human_review = False

            elig = self._sync_eligibility_and_flags(db, tx, checks)
            self._append_audit_log(
                db=db,
                tx=tx,
                from_status=prev_status,
                to_status=target_status,
                actor_id=resolved_actor_id,
                actor_role=resolved_actor_role,
                verification_method=verification_method,
                reason=reason,
                checks_snapshot={"checks": checks, "eligibility": elig, "corroboration_reference": corroboration_reference},
                rejection_or_escalation_reason=reason if target_status == "REJECTED" else (",".join(checks["review_flags"]) or None),
            )
            if auto_commit:
                db.commit()
                db.refresh(tx)
            else:
                db.flush()
        except Exception:
            db.rollback()
            raise

        return {
            "outcome": "TRANSITIONED",
            "transaction_id": tx.transaction_id,
            "from_status": prev_status,
            "verification_status": tx.verification_status,
            "requires_human_review": tx.requires_human_review,
            "eligible_for_ground_truth_validation": tx.eligible_for_ground_truth_validation,
            "eligible_for_model_training": tx.eligible_for_model_training,
            "exclusion_reasons": json.loads(tx.validation_exclusion_reasons_json or "[]"),
            "review_flags": json.loads(tx.review_flags_json or "[]"),
        }
