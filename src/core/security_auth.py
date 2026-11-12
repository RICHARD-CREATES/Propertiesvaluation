"""
Server-Side Verification & Ingestion Authentication Guard
=======================================================
Milestone 8 — Phase 4 Step 1

Replaces trust in client-supplied `actor_id` / `actor_role` fields with cryptographically
signed HMAC-SHA256 Bearer tokens issued only by trusted server-side credentials.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from fastapi import Depends, Header, HTTPException


class AuthenticationError(PermissionError):
    """Raised when a verification or ingestion token is missing, malformed, forged, or expired."""


@dataclass(frozen=True)
class VerifiedPrincipal:
    """Trusted server-verified identity derived solely from a verified cryptographic token."""
    actor_id: str
    actor_role: str
    issued_at: int
    expires_at: int
    token_id: str
    verified_by_server: bool = True


_PROCESS_EPHEMERAL_SECRET: bytes = secrets.token_bytes(32)


class VerificationAuthManager:
    """Issues and verifies HMAC-SHA256 server-side verification & ingestion session tokens."""

    def __init__(self, secret_key: Optional[bytes] = None) -> None:
        env_secret = os.environ.get("VERIFICATION_HMAC_SECRET")
        if secret_key is not None:
            self._secret = secret_key
        elif env_secret:
            self._secret = env_secret.encode("utf-8")
        else:
            # Cryptographically random per-process fallback; never uses a predictable static secret.
            self._secret = _PROCESS_EPHEMERAL_SECRET

    def issue_token(
        self,
        actor_id: str,
        actor_role: str,
        ttl_seconds: int = 3600,
    ) -> str:
        """Server-side helper to mint a time-bounded signed principal token."""
        if not actor_id or not actor_id.strip():
            raise ValueError("actor_id is required to issue a verified principal token.")
        from src.services.verification_engine import AUTHORIZED_ACTOR_ROLES

        if actor_role not in AUTHORIZED_ACTOR_ROLES:
            raise ValueError(f"Unsupported actor_role '{actor_role}'.")

        now = int(time.time())
        payload = {
            "sub": actor_id.strip(),
            "role": actor_role,
            "iat": now,
            "exp": now + int(ttl_seconds),
            "jti": secrets.token_hex(12),
        }
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).decode("ascii").rstrip("=")

        sig = hmac.new(self._secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
        return f"v1.{payload_b64}.{sig_b64}"

    def verify_token(self, token: str) -> VerifiedPrincipal:
        """Verifies HMAC signature, structural integrity, and expiration timestamp."""
        if not token or not isinstance(token, str):
            raise AuthenticationError("Missing authentication token.")
        parts = token.strip().split(".")
        if len(parts) != 3 or parts[0] != "v1":
            raise AuthenticationError("Malformed verification token format.")

        _, payload_b64, sig_b64 = parts
        expected_sig = hmac.new(self._secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")
        if not hmac.compare_digest(sig_b64, expected_b64):
            raise AuthenticationError("Invalid token signature.")

        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        except Exception as exc:
            raise AuthenticationError("Corrupted token payload.") from exc

        now = int(time.time())
        exp = int(payload.get("exp", 0))
        if now > exp:
            raise AuthenticationError("Verification token has expired.")

        from src.services.verification_engine import AUTHORIZED_ACTOR_ROLES

        role = str(payload.get("role") or "")
        if role not in AUTHORIZED_ACTOR_ROLES:
            raise AuthenticationError(f"Token carries unauthorized role '{role}'.")

        return VerifiedPrincipal(
            actor_id=str(payload["sub"]),
            actor_role=role,
            issued_at=int(payload["iat"]),
            expires_at=exp,
            token_id=str(payload["jti"]),
            verified_by_server=True,
        )


_DEFAULT_AUTH_MANAGER = VerificationAuthManager()


def get_auth_manager() -> VerificationAuthManager:
    """Returns process-wide auth manager (respects runtime VERIFICATION_HMAC_SECRET overrides safely)."""
    return _DEFAULT_AUTH_MANAGER


def require_verified_principal(
    authorization: Optional[str] = Header(default=None),
) -> VerifiedPrincipal:
    """FastAPI dependency requiring `Authorization: Bearer <token>` on protected routes."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer authentication token.")
    raw_token = authorization.split(" ", 1)[1].strip()
    try:
        return get_auth_manager().verify_token(raw_token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_roles(*allowed_roles: str) -> Callable[..., VerifiedPrincipal]:
    """FastAPI dependency factory enforcing RBAC role authorization on verified principals."""
    allowed_set = set(allowed_roles)

    def _checker(principal: VerifiedPrincipal = Depends(require_verified_principal)) -> VerifiedPrincipal:
        if principal.actor_role not in allowed_set:
            raise HTTPException(
                status_code=403,
                detail=f"Actor role '{principal.actor_role}' lacks required permissions: {sorted(allowed_set)}.",
            )
        return principal

    return _checker
