"""
Server-Side Authentication & Admin Evidence-Review Router
=========================================================
Milestone 8 — Phases 7–9

Password-authenticated login verifying server-stored salted scrypt credentials and binding
roles strictly server-side (never reads client-supplied `actor_role` in login payloads).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.core.evidence_schema import CanonicalTransaction, VerificationAuditLog
from src.core.evidence_storage import redact_pii_dict
from src.core.rental_db import SessionLocal
from src.core.security_auth import VerifiedPrincipal, get_auth_manager, require_roles, require_verified_principal
from src.services.evidence_bridge import sync_verified_canonical_to_ground_truth

router = APIRouter(tags=["Authentication & Admin Evidence Review"])


def _scrypt_hash(password: str, salt_hex: str) -> str:
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return dk.hex()


# Default hackathon demo credentials (override via ADMIN_USERS_JSON env in production deployments)
_DEMO_SALT = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
_DEFAULT_DEMO_ACCOUNTS: Dict[str, Dict[str, str]] = {
    "reviewer_bbsr": {
        "role": "HUMAN_REVIEWER",
        "salt_hex": _DEMO_SALT,
        "password_hash": _scrypt_hash(os.environ.get("DEMO_REVIEWER_PASS", "ReviewBbsr#2026"), _DEMO_SALT),
        "display_name": "Bhubaneswar Evidence Reviewer (Demo)",
    },
    "registry_verifier": {
        "role": "AUTHORIZED_REGISTRY_VERIFIER",
        "salt_hex": _DEMO_SALT,
        "password_hash": _scrypt_hash(os.environ.get("DEMO_VERIFIER_PASS", "VerifyIgr#2026"), _DEMO_SALT),
        "display_name": "Authorized Registry Verifier (Demo)",
    },
    "audit_admin": {
        "role": "SENIOR_AUDIT_ADMIN",
        "salt_hex": _DEMO_SALT,
        "password_hash": _scrypt_hash(os.environ.get("DEMO_ADMIN_PASS", "AuditAdmin#2026"), _DEMO_SALT),
        "display_name": "Senior Audit Administrator (Demo)",
    },
}


def _load_server_user_store() -> Dict[str, Dict[str, str]]:
    raw_env = os.environ.get("ADMIN_USERS_JSON")
    if not raw_env:
        return _DEFAULT_DEMO_ACCOUNTS
    parsed = json.loads(raw_env)
    return dict(parsed)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login")
def login_verified_staff(req: LoginRequest):
    """Authenticates staff credentials against server store and mints an HMAC-signed Bearer token."""
    users = _load_server_user_store()
    acct = users.get(req.username.strip())
    if not acct:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    candidate_hash = _scrypt_hash(req.password, acct["salt_hex"])
    if not hmac.compare_digest(candidate_hash, acct["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = get_auth_manager().issue_token(
        actor_id=req.username.strip(),
        actor_role=acct["role"],
        ttl_seconds=3600,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "actor_id": req.username.strip(),
        "actor_role": acct["role"],
        "display_name": acct.get("display_name", req.username.strip()),
        "expires_in_seconds": 3600,
        "auth_mode": "ENV_CONFIGURED_STORE" if os.environ.get("ADMIN_USERS_JSON") else "HACKATHON_DEMO_ACCOUNTS",
    }


@router.get("/api/auth/me")
def get_authenticated_me(principal: VerifiedPrincipal = Depends(require_verified_principal)):
    return {
        "actor_id": principal.actor_id,
        "actor_role": principal.actor_role,
        "expires_at": principal.expires_at,
        "verified_by_server": principal.verified_by_server,
    }


@router.get("/api/admin/review-queue")
def get_admin_review_queue(
    status_filter: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    principal: VerifiedPrincipal = Depends(
        require_roles("HUMAN_REVIEWER", "AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN")
    ),
):
    """Authenticated queue listing canonical transactions awaiting review plus recent audit history."""
    with SessionLocal() as db:
        q = db.query(CanonicalTransaction)
        if status_filter:
            q = q.filter(CanonicalTransaction.verification_status == status_filter)
        rows = q.order_by(CanonicalTransaction.ingestion_timestamp.desc()).limit(limit).all()

        items: List[Dict[str, Any]] = []
        for r in rows:
            recent_logs = (
                db.query(VerificationAuditLog)
                .filter_by(transaction_id=r.transaction_id)
                .order_by(VerificationAuditLog.created_at.desc())
                .limit(5)
                .all()
            )
            items.append(
                redact_pii_dict(
                    {
                        "transaction_id": r.transaction_id,
                        "property_id": r.property_id,
                        "property_type": r.property_type,
                        "locality": r.locality,
                        "city": r.city,
                        "sale_price_inr": r.sale_price_inr,
                        "circle_rate_inr": r.circle_rate_inr,
                        "builtup_area_sqft": r.builtup_area_sqft,
                        "land_area_sqft": r.land_area_sqft,
                        "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
                        "registration_date": r.registration_date.isoformat() if r.registration_date else None,
                        "source_type": r.source_type,
                        "source_category": r.source_category,
                        "verification_status": r.verification_status,
                        "evidence_document_type": r.evidence_document_type,
                        "evidence_document_reference": r.evidence_document_reference,
                        "transaction_classification": r.transaction_classification,
                        "requires_human_review": r.requires_human_review,
                        "eligible_for_ground_truth_validation": r.eligible_for_ground_truth_validation,
                        "eligible_for_model_training": r.eligible_for_model_training,
                        "review_flags": json.loads(r.review_flags_json or "[]"),
                        "exclusion_reasons": json.loads(r.validation_exclusion_reasons_json or "[]"),
                        "audit_trail": [
                            {
                                "from_status": l.from_status,
                                "to_status": l.to_status,
                                "actor": l.actor,
                                "actor_role": l.actor_role,
                                "method": l.verification_method,
                                "reason": l.reason,
                                "at": l.created_at.isoformat() if l.created_at else None,
                            }
                            for l in recent_logs
                        ],
                    }
                )
            )

    return {
        "viewer": principal.actor_id,
        "viewer_role": principal.actor_role,
        "count": len(items),
        "items": items,
    }


@router.post("/api/admin/sync-ground-truth")
def api_sync_verified_ground_truth(
    principal: VerifiedPrincipal = Depends(
        require_roles("AUTHORIZED_REGISTRY_VERIFIER", "SENIOR_AUDIT_ADMIN")
    ),
):
    """Synchronizes eligible REGISTRATION_VERIFIED arm's-length deeds into Milestone 7 GroundTruthTransaction."""
    with SessionLocal() as db:
        res = sync_verified_canonical_to_ground_truth(db)
    return {
        "triggered_by": principal.actor_id,
        **res,
    }
