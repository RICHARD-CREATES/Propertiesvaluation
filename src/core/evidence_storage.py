"""
Private Evidence Vault, Quarantine Scanner & PII Redaction Utilities
====================================================================
Milestone 8 — Phase 4 Steps 1 & 3

Enforces:
- Extension + magic-byte validation (.pdf, .png, .jpg/.jpeg, .txt, .json)
- Maximum file size caps (10 MB default) and non-empty check
- Staging quarantine + malware/script signature scanning (with pluggable AV hook)
- Exact SHA-256 checksum computation and verification
- Private non-static disk vault storage (never under src/api/static/)
- RBAC read authorization (no buyer/seller PII or document contents in ordinary logs)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from src.core.security_auth import VerifiedPrincipal

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_VAULT_ROOT = (
    Path("/tmp/private_evidence_vault")
    if os.environ.get("VERCEL")
    else BASE_DIR / "data" / "private_evidence_vault"
)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".json"}
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

PII_FIELD_NAMES = {
    "buyer_name",
    "seller_name",
    "owner_name",
    "pattadar_name",
    "co_sharer_names",
    "pan",
    "pan_number",
    "aadhaar",
    "aadhaar_number",
    "phone",
    "mobile",
    "email",
    "address_line",
    "street_address",
}

EVIDENCE_READ_ROLES = {
    "HUMAN_REVIEWER",
    "AUTHORIZED_REGISTRY_VERIFIER",
    "SENIOR_AUDIT_ADMIN",
}


class DocumentValidationError(ValueError):
    """Raised when uploaded file type, size, or magic signature is rejected."""


class DocumentQuarantinedError(SecurityError if hasattr(__builtins__, "SecurityError") else RuntimeError):
    """Raised when malware/script scanning flags and quarantines a document."""


class DocumentIntegrityError(ValueError):
    """Raised when expected SHA-256 digest does not match actual document bytes."""


class EvidenceAccessDeniedError(PermissionError):
    """Raised when an unauthorized role attempts to read raw evidence files."""


def redact_pii_text(text_val: str) -> str:
    """Masks Indian PAN, Aadhaar, email, and 10-digit phone numbers in free text."""
    s = str(text_val or "")
    s = re.sub(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "[REDACTED_PAN]", s)
    s = re.sub(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[REDACTED_AADHAAR]", s)
    s = re.sub(r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b", "[REDACTED_PHONE]", s)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", s)
    return s


def redact_pii_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Produces a sanitized copy safe for analytics/audit inspection without buyer/seller identities."""
    clean: Dict[str, Any] = {}
    for k, v in payload.items():
        if str(k).lower().strip() in PII_FIELD_NAMES:
            clean[k] = "[REDACTED_PII]"
        elif isinstance(v, dict):
            clean[k] = redact_pii_dict(v)
        elif isinstance(v, str):
            clean[k] = redact_pii_text(v)
        else:
            clean[k] = v
    return clean


def _validate_extension_and_magic(filename: str, content: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentValidationError(
            f"Unsupported evidence extension '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}."
        )
    if ext == ".pdf" and not content.startswith(b"%PDF-"):
        raise DocumentValidationError("File extension '.pdf' does not match %PDF- magic header.")
    if ext == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DocumentValidationError("File extension '.png' does not match PNG magic header.")
    if ext in (".jpg", ".jpeg") and not content.startswith(b"\xff\xd8\xff"):
        raise DocumentValidationError("File extension '.jpg/.jpeg' does not match JPEG magic header.")
    if ext == ".json":
        try:
            json.loads(content.decode("utf-8"))
        except Exception as exc:
            raise DocumentValidationError("File extension '.json' is not valid UTF-8 JSON.") from exc
    if ext == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentValidationError("File extension '.txt' must be valid UTF-8 text.") from exc
    return ext


def default_malware_scan(content: bytes, ext: str) -> Tuple[bool, str]:
    """
    Deterministic byte-level inspection blocking executable binaries and active script payloads
    before admission into private vault. Designed to pair with external ClamAV hooks.
    """
    if content.startswith(b"MZ") or content.startswith(b"\x7fELF") or content.startswith(b"#!"):
        return False, "EXECUTABLE_HEADER_DETECTED"

    lowered = content.lower()
    if b"<script" in lowered or b"powershell " in lowered:
        return False, "ACTIVE_SCRIPT_MARKER_DETECTED"

    if ext == ".pdf":
        for risky_pdf_tag in (b"/javascript", b"/js ", b"/launch", b"/openaction", b"/embeddedfile"):
            if risky_pdf_tag in lowered:
                return False, f"RISKY_PDF_ACTION_{risky_pdf_tag.decode('ascii', errors='ignore').strip('/').upper()}"

    return True, "CLEAN"


class PrivateEvidenceVault:
    """Quarantine-first private evidence store with SHA-256 integrity checks and RBAC retrieval."""

    def __init__(
        self,
        vault_root: Optional[Path] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        scanner_fn: Optional[Callable[[bytes, str], Tuple[bool, str]]] = None,
    ) -> None:
        self.root = Path(vault_root) if vault_root else DEFAULT_VAULT_ROOT
        self.quarantine_dir = self.root / "quarantine"
        self.rejected_dir = self.root / "quarantine_rejected"
        self.store_dir = self.root / "vault"
        for d in (self.quarantine_dir, self.rejected_dir, self.store_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.scanner_fn = scanner_fn or default_malware_scan

    def store_document(
        self,
        filename: str,
        content: bytes,
        principal: VerifiedPrincipal,
        expected_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validates, scans in quarantine, verifies SHA-256, and commits raw document privately."""
        if not content:
            raise DocumentValidationError("Uploaded document is empty (0 bytes).")
        if len(content) > self.max_bytes:
            raise DocumentValidationError(
                f"Document size {len(content)} bytes exceeds maximum limit of {self.max_bytes} bytes."
            )

        ext = _validate_extension_and_magic(filename, content)
        actual_sha256 = hashlib.sha256(content).hexdigest()

        if expected_sha256 and expected_sha256.strip().lower() != actual_sha256:
            raise DocumentIntegrityError(
                f"Document SHA-256 mismatch: expected '{expected_sha256[:12]}...', got '{actual_sha256[:12]}...'."
            )

        # Stage in quarantine first before scanning
        stage_id = uuid.uuid4().hex
        stage_path = self.quarantine_dir / f"{stage_id}{ext}"
        stage_path.write_bytes(content)

        is_clean, scan_reason = self.scanner_fn(content, ext)
        if not is_clean:
            quarantined_path = self.rejected_dir / f"{actual_sha256}_{stage_id}{ext}"
            stage_path.replace(quarantined_path)
            raise DocumentQuarantinedError(f"Document quarantined prior to admission: {scan_reason}")

        # Move clean document into hash-addressed private vault
        shard_dir = self.store_dir / actual_sha256[:2]
        shard_dir.mkdir(parents=True, exist_ok=True)
        final_path = shard_dir / f"{actual_sha256}{ext}"
        if final_path.exists():
            stage_path.unlink(missing_ok=True)
        else:
            stage_path.replace(final_path)
            try:
                os.chmod(final_path, 0o600)
            except OSError:
                pass

        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".txt": "text/plain",
            ".json": "application/json",
        }

        return {
            "evidence_id": f"EVD-{uuid.uuid4().hex[:14].upper()}",
            "storage_uri": f"vault://{actual_sha256[:2]}/{actual_sha256}{ext}",
            "sha256_digest": actual_sha256,
            "mime_type": mime_map[ext],
            "file_size_bytes": len(content),
            "scan_status": scan_reason,
            "uploaded_by_actor": principal.actor_id,
        }

    def read_document_bytes(
        self,
        storage_uri: str,
        expected_sha256: str,
        principal: VerifiedPrincipal,
    ) -> bytes:
        """RBAC-protected retrieval verifying stored bytes against archived SHA-256 hash."""
        if principal.actor_role not in EVIDENCE_READ_ROLES:
            raise EvidenceAccessDeniedError(
                f"Role '{principal.actor_role}' is not authorized to read raw evidence documents."
            )
        if not storage_uri.startswith("vault://"):
            raise ValueError("Invalid vault storage URI.")
        rel = storage_uri[len("vault://"):]
        full_path = (self.store_dir / rel).resolve()
        if not str(full_path).startswith(str(self.store_dir.resolve())):
            raise EvidenceAccessDeniedError("Path traversal attempt rejected.")
        if not full_path.exists():
            raise FileNotFoundError(f"Evidence object '{storage_uri}' not found in private vault.")

        data = full_path.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != expected_sha256:
            raise DocumentIntegrityError(
                f"Vault integrity failure for '{storage_uri}': hash mismatch detected."
            )
        return data
