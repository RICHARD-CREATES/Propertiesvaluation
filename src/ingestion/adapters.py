"""
Controlled Source-Specific Ingestion Adapters (Milestone 8 — Phase 4 Steps 2–5)
==============================================================================
Adapters:
- BaseSourceAdapter
- UserDocumentEvidenceAdapter (consented deeds, certified copies, signed ECs + PrivateEvidenceVault)
- AuthorizedBrokerFeedAdapter (authorized CSV/JSON broker closing claims, strictly UNVERIFIED/SOURCE_CONFIRMED)
- GovtBMVReferenceAdapter (authorized manual/export IGR Odisha BMV benchmark values; never sale prices)
- ORERAProjectDisclosureAdapter (authorized manual/export ORERA disclosures; never unit sale prices)
"""
from __future__ import annotations

import csv
import io
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from src.analytics.data_quality import CANONICAL_PROPERTY_TYPES, normalize_area_to_sqft, normalize_currency_to_inr
from src.core.evidence_schema import TRANSACTION_CLASSIFICATIONS
from src.core.evidence_storage import PrivateEvidenceVault, redact_pii_dict
from src.core.security_auth import VerifiedPrincipal


class AdapterValidationError(ValueError):
    """Raised when an adapter rejects malformed input, missing consent/authorization, or invalid schema."""


@dataclass
class NormalizedIngestionItem:
    """Standardized output produced by every source adapter prior to pipeline admission."""
    source_type: str
    source_reference: str
    raw_payload_sanitized: Dict[str, Any]
    canonical_payload: Dict[str, Any]
    currency: str = "INR"
    document_metadata: Optional[Dict[str, Any]] = None
    consent_granted: bool = False
    consent_reference: Optional[str] = None
    post_admit_target_status: Optional[str] = None  # Never REGISTRATION_VERIFIED!
    review_notes: List[str] = field(default_factory=list)


def _normalize_property_type(raw_val: Any) -> str:
    clean = CANONICAL_PROPERTY_TYPES.get(str(raw_val or "").lower().strip())
    if not clean:
        raise AdapterValidationError(f"Unsupported property_type '{raw_val}'.")
    return clean


class BaseSourceAdapter(ABC):
    """Abstract contract for all controlled Phase 4 real-estate data adapters."""

    adapter_name: str = "BaseSourceAdapter"
    source_type: str = ""
    portal_access_policy: str = "DOCUMENTED_AUTHORIZED_CHANNEL"

    @staticmethod
    def parse_records(raw_input: Union[str, bytes, List[Dict[str, Any]], Dict[str, Any]], format_hint: str = "json") -> List[Dict[str, Any]]:
        """Parses raw JSON or CSV text/bytes/dicts strictly without swallowing malformed syntax."""
        if isinstance(raw_input, list):
            return [dict(r) for r in raw_input]
        if isinstance(raw_input, dict):
            return [dict(raw_input)]

        text_data = raw_input.decode("utf-8") if isinstance(raw_input, bytes) else str(raw_input)
        if not text_data.strip():
            raise AdapterValidationError("Input feed payload is empty.")

        fmt = format_hint.lower().strip()
        if fmt == "csv":
            reader = csv.DictReader(io.StringIO(text_data))
            if not reader.fieldnames:
                raise AdapterValidationError("Malformed CSV: missing header row.")
            rows = []
            for idx, row in enumerate(reader):
                if any(k is None or v is None for k, v in row.items()):
                    raise AdapterValidationError(f"Malformed CSV row {idx + 1}: inconsistent column count.")
                rows.append({k.strip(): v.strip() for k, v in row.items()})
            if not rows:
                raise AdapterValidationError("CSV contains header but zero data rows.")
            return rows

        if fmt == "json":
            try:
                parsed = json.loads(text_data)
            except json.JSONDecodeError as exc:
                raise AdapterValidationError(f"Malformed JSON payload: {exc}") from exc
            if isinstance(parsed, dict):
                return [parsed]
            if isinstance(parsed, list):
                if not all(isinstance(x, dict) for x in parsed):
                    raise AdapterValidationError("JSON array must contain object records.")
                return parsed
            raise AdapterValidationError("JSON payload must be an object or array of objects.")

        raise AdapterValidationError(f"Unsupported format_hint '{format_hint}'. Expected 'csv' or 'json'.")

    @abstractmethod
    def normalize_record(
        self,
        raw_rec: Dict[str, Any],
        principal: Optional[VerifiedPrincipal] = None,
        batch_metadata: Optional[Dict[str, Any]] = None,
    ) -> NormalizedIngestionItem:
        """Validates adapter authorization/consent and normalizes raw fields into canonical structure."""


class UserDocumentEvidenceAdapter(BaseSourceAdapter):
    """
    Consented user/institutional submission of Sale Deeds, Certified Copies, or signed IGR ECs.
    Enforces file/magic/malware scan + SHA-256 integrity + PII redaction via PrivateEvidenceVault.
    Never automatically promotes records to REGISTRATION_VERIFIED.
    """
    adapter_name = "UserDocumentEvidenceAdapter"
    source_type = "USER_SUBMITTED_DEED"
    ALLOWED_DOC_TYPES = {
        "EXECUTED_SALE_DEED",
        "AGREEMENT_FOR_SALE",
        "CERTIFIED_COPY_IGR",
        "DIGITALLY_SIGNED_EC",
        "INDEX_II_EXTRACT",
    }

    def __init__(self, vault: Optional[PrivateEvidenceVault] = None) -> None:
        self.vault = vault or PrivateEvidenceVault()

    def normalize_record(
        self,
        raw_rec: Dict[str, Any],
        principal: Optional[VerifiedPrincipal] = None,
        batch_metadata: Optional[Dict[str, Any]] = None,
    ) -> NormalizedIngestionItem:
        if principal is None:
            raise AdapterValidationError("VerifiedPrincipal is mandatory for UserDocumentEvidenceAdapter.")

        if raw_rec.get("consent_granted") is not True:
            raise AdapterValidationError("Explicit user consent (`consent_granted=True`) is mandatory.")
        consent_ref = str(raw_rec.get("consent_reference") or "").strip()
        if not consent_ref:
            raise AdapterValidationError("Non-empty `consent_reference` is mandatory.")

        doc_type = str(raw_rec.get("evidence_document_type") or "").upper().strip()
        if doc_type not in self.ALLOWED_DOC_TYPES:
            raise AdapterValidationError(
                f"Unsupported evidence_document_type '{doc_type}'. Allowed: {sorted(self.ALLOWED_DOC_TYPES)}."
            )

        doc_ref = str(raw_rec.get("evidence_document_reference") or "").strip()
        if not doc_ref:
            raise AdapterValidationError("`evidence_document_reference` (e.g. SRO Deed/Receipt No.) is required.")

        doc_bytes = raw_rec.get("document_bytes")
        filename = str(raw_rec.get("document_filename") or "")
        if not isinstance(doc_bytes, (bytes, bytearray)) or not filename:
            raise AdapterValidationError("Valid `document_bytes` and `document_filename` are required.")

        # Validate, quarantine-scan, verify expected SHA-256, and store privately before any admission
        vault_meta = self.vault.store_document(
            filename=filename,
            content=bytes(doc_bytes),
            principal=principal,
            expected_sha256=raw_rec.get("expected_sha256"),
        )

        prop_type = _normalize_property_type(raw_rec.get("property_type"))
        area_unit = str(raw_rec.get("area_unit") or "sqft")
        builtup = normalize_area_to_sqft(raw_rec.get("builtup_area_sqft") or raw_rec.get("builtup_area"), area_unit)
        carpet = normalize_area_to_sqft(raw_rec.get("carpet_area_sqft") or raw_rec.get("carpet_area"), area_unit)
        land = normalize_area_to_sqft(raw_rec.get("land_area_sqft") or raw_rec.get("plot_area_sqft"), area_unit)

        curr = str(raw_rec.get("currency") or "INR").upper().strip()
        price_inr = normalize_currency_to_inr(raw_rec.get("sale_price_inr") or raw_rec.get("sale_price"), curr)
        if price_inr is None or price_inr <= 0:
            raise AdapterValidationError("Positive INR `sale_price_inr` is required for deed evidence.")

        tx_class = str(raw_rec.get("transaction_classification") or "ATYPICAL_UNCLASSIFIED").upper().strip()
        if tx_class not in TRANSACTION_CLASSIFICATIONS:
            raise AdapterValidationError(f"Invalid transaction_classification '{tx_class}'.")

        extraction_conf = raw_rec.get("extraction_confidence")
        uncertain_fields = list(raw_rec.get("uncertain_fields") or [])
        review_notes: List[str] = []
        if extraction_conf is not None and float(extraction_conf) < 0.90:
            review_notes.append(f"LOW_EXTRACTION_CONFIDENCE:{float(extraction_conf):.2f}")
        if uncertain_fields:
            review_notes.append(f"UNCERTAIN_EXTRACTED_FIELDS:{','.join(map(str, uncertain_fields))}")

        # Strict PII redaction: raw archive keeps redacted fields + NEVER logs buyer/seller identity!
        raw_sanitized = redact_pii_dict({k: v for k, v in raw_rec.items() if k != "document_bytes"})
        raw_sanitized["document_sha256"] = vault_meta["sha256_digest"]
        raw_sanitized["document_storage_uri"] = vault_meta["storage_uri"]

        src_type = "OFFICIAL_REGISTRY_EC" if doc_type in ("DIGITALLY_SIGNED_EC", "CERTIFIED_COPY_IGR") and raw_rec.get("from_official_ec_download") else "USER_SUBMITTED_DEED"

        canonical_payload = {
            "transaction_id": raw_rec.get("transaction_id"),
            "property_id": raw_rec.get("property_id"),
            "property_type": prop_type,
            "transaction_date": raw_rec.get("transaction_date"),
            "registration_date": raw_rec.get("registration_date"),
            "sale_price_inr": price_inr,
            "land_area_sqft": land,
            "builtup_area_sqft": builtup,
            "carpet_area_sqft": carpet,
            "locality": raw_rec.get("locality"),
            "city": raw_rec.get("city") or "Bhubaneswar",
            "district": raw_rec.get("district") or "Khordha",
            "state": raw_rec.get("state") or "Odisha",
            "latitude": raw_rec.get("latitude"),
            "longitude": raw_rec.get("longitude"),
            "circle_rate_inr": raw_rec.get("circle_rate_inr"),
            "evidence_document_type": doc_type,
            "evidence_document_reference": doc_ref,
            "evidence_document_hash": vault_meta["sha256_digest"],
            "source_document_hash": vault_meta["sha256_digest"],
            "transaction_classification": tx_class,
            "is_arms_length": raw_rec.get("is_arms_length"),
        }

        return NormalizedIngestionItem(
            source_type=src_type,
            source_reference=str(raw_rec.get("source_reference") or f"user_vault:{vault_meta['evidence_id']}"),
            raw_payload_sanitized=raw_sanitized,
            canonical_payload=canonical_payload,
            currency="INR",
            document_metadata={
                **vault_meta,
                "evidence_document_type": doc_type,
                "consent_granted": True,
                "consent_reference": consent_ref,
                "pii_redacted_summary_json": json.dumps(raw_sanitized, sort_keys=True, default=str),
            },
            consent_granted=True,
            consent_reference=consent_ref,
            post_admit_target_status=None,  # Strictly remains UNVERIFIED until human/registry verification
            review_notes=review_notes,
        )


class AuthorizedBrokerFeedAdapter(BaseSourceAdapter):
    """
    Authorized CSV/JSON broker feed adapter.
    Strictly caps admitted records at UNVERIFIED / SOURCE_CONFIRMED (broker category);
    never promotes claimed closing prices into verified ground truth.
    """
    adapter_name = "AuthorizedBrokerFeedAdapter"
    source_type = "AUTHORIZED_BROKER_FEED"

    def normalize_record(
        self,
        raw_rec: Dict[str, Any],
        principal: Optional[VerifiedPrincipal] = None,
        batch_metadata: Optional[Dict[str, Any]] = None,
    ) -> NormalizedIngestionItem:
        meta = batch_metadata or {}
        partner_id = str(raw_rec.get("partner_id") or meta.get("partner_id") or "").strip()
        auth_ref = str(raw_rec.get("data_use_authorization_ref") or meta.get("data_use_authorization_ref") or "").strip()
        raw_auth = raw_rec.get("data_use_authorized") if "data_use_authorized" in raw_rec else meta.get("data_use_authorized")
        if isinstance(raw_auth, bool):
            authorized = raw_auth
        elif isinstance(raw_auth, str):
            authorized = raw_auth.strip().lower() in ("true", "1", "yes")
        else:
            authorized = False

        if not partner_id or not auth_ref or authorized is not True:
            raise AdapterValidationError(
                "AuthorizedBrokerFeedAdapter requires `partner_id`, `data_use_authorization_ref`, and `data_use_authorized=True`."
            )

        tx_date = raw_rec.get("claimed_transaction_date") or raw_rec.get("transaction_date")
        if not tx_date:
            raise AdapterValidationError("Broker feed record missing `claimed_transaction_date`.")

        curr = str(raw_rec.get("currency") or "INR").upper().strip()
        price_inr = normalize_currency_to_inr(
            raw_rec.get("claimed_closing_price") if raw_rec.get("claimed_closing_price") is not None else raw_rec.get("sale_price_inr"),
            curr,
        )
        if price_inr is None or price_inr <= 0:
            raise AdapterValidationError("Broker feed record requires positive `claimed_closing_price`.")

        prop_type = _normalize_property_type(raw_rec.get("property_type"))
        area_unit = str(raw_rec.get("area_unit") or "sqft")
        area_val = raw_rec.get("builtup_area_sqft") or raw_rec.get("area_sqft") or raw_rec.get("area_value")
        norm_area = normalize_area_to_sqft(area_val, area_unit)
        land_area = normalize_area_to_sqft(raw_rec.get("land_area_sqft") or raw_rec.get("plot_area_sqft"), area_unit)

        if prop_type == "residential_land" and (land_area is None or land_area <= 0):
            land_area = norm_area
        if (norm_area is None or norm_area <= 0) and (land_area is None or land_area <= 0):
            raise AdapterValidationError("Broker feed record requires positive property area.")

        raw_sanitized = redact_pii_dict(dict(raw_rec))
        raw_sanitized["partner_id"] = partner_id
        raw_sanitized["data_use_authorization_ref"] = auth_ref

        return NormalizedIngestionItem(
            source_type="AUTHORIZED_BROKER_FEED",
            source_reference=f"broker:{partner_id}:{auth_ref}",
            raw_payload_sanitized=raw_sanitized,
            canonical_payload={
                "transaction_id": raw_rec.get("transaction_id"),
                "property_id": raw_rec.get("property_id"),
                "property_type": prop_type,
                "transaction_date": tx_date,
                "registration_date": None,
                "sale_price_inr": price_inr,
                "land_area_sqft": land_area,
                "builtup_area_sqft": norm_area if prop_type != "residential_land" else None,
                "carpet_area_sqft": normalize_area_to_sqft(raw_rec.get("carpet_area_sqft"), area_unit),
                "locality": raw_rec.get("locality"),
                "city": raw_rec.get("city") or "Bhubaneswar",
                "district": raw_rec.get("district") or "Khordha",
                "state": raw_rec.get("state") or "Odisha",
                "latitude": raw_rec.get("latitude"),
                "longitude": raw_rec.get("longitude"),
                "evidence_document_type": "BROKER_ATTESTATION",
                "evidence_document_reference": raw_rec.get("broker_rera_id") or auth_ref,
                "transaction_classification": "ATYPICAL_UNCLASSIFIED",
                "is_arms_length": None,
            },
            currency="INR",
            post_admit_target_status="SOURCE_CONFIRMED" if raw_rec.get("broker_rera_id") else None,
            review_notes=["BROKER_CLAIMED_PRICE_NOT_GROUND_TRUTH"],
        )


class GovtBMVReferenceAdapter(BaseSourceAdapter):
    """
    Authorized manual/export adapter for IGR Odisha Benchmark Valuation (circle rates).
    `igrodisha.gov.in` exposes no public REST API; portal scraping is forbidden.
    Strictly preserves `sale_price_inr = None` so circle rates are NEVER confused with market sales.
    """
    adapter_name = "GovtBMVReferenceAdapter"
    source_type = "GOVT_CIRCLE_RATE"
    portal_access_policy = "AUTHORIZED_MANUAL_IMPORT_NO_PUBLIC_API_IGR_ODISHA"

    def normalize_record(
        self,
        raw_rec: Dict[str, Any],
        principal: Optional[VerifiedPrincipal] = None,
        batch_metadata: Optional[Dict[str, Any]] = None,
    ) -> NormalizedIngestionItem:
        bmv_ref = str(raw_rec.get("circular_or_query_ref") or raw_rec.get("evidence_document_reference") or "").strip()
        if not bmv_ref:
            raise AdapterValidationError("GovtBMVReferenceAdapter requires `circular_or_query_ref` provenance.")

        bmv_rate = raw_rec.get("benchmark_value_inr") if raw_rec.get("benchmark_value_inr") is not None else raw_rec.get("circle_rate_inr")
        bmv_inr = normalize_currency_to_inr(bmv_rate, str(raw_rec.get("currency") or "INR"))
        if bmv_inr is None or bmv_inr <= 0:
            raise AdapterValidationError("GovtBMVReferenceAdapter requires positive `benchmark_value_inr`.")

        prop_type = _normalize_property_type(raw_rec.get("property_type") or "residential_land")
        area_unit = str(raw_rec.get("area_unit") or "sqft")
        land_area = normalize_area_to_sqft(raw_rec.get("land_area_sqft") or raw_rec.get("area_sqft") or 1000.0, area_unit)

        return NormalizedIngestionItem(
            source_type="GOVT_CIRCLE_RATE",
            source_reference=str(raw_rec.get("source_reference") or f"igrodisha.gov.in:BMV:{bmv_ref}"),
            raw_payload_sanitized=redact_pii_dict(dict(raw_rec)),
            canonical_payload={
                "transaction_id": raw_rec.get("transaction_id"),
                "property_id": raw_rec.get("property_id"),
                "property_type": prop_type,
                "transaction_date": raw_rec.get("effective_date") or raw_rec.get("transaction_date"),
                "registration_date": None,
                "sale_price_inr": None,  # CRITICAL: Circle rates NEVER populate sale_price_inr!
                "circle_rate_inr": bmv_inr,
                "land_area_sqft": land_area,
                "locality": raw_rec.get("mouza") or raw_rec.get("locality"),
                "city": raw_rec.get("city") or "Bhubaneswar",
                "district": raw_rec.get("district") or "Khordha",
                "state": raw_rec.get("state") or "Odisha",
                "latitude": raw_rec.get("latitude"),
                "longitude": raw_rec.get("longitude"),
                "evidence_document_type": "GOVT_BENCHMARK_CIRCULAR",
                "evidence_document_reference": bmv_ref,
                "transaction_classification": "NON_SALE_REFERENCE",
                "is_arms_length": False,
            },
            currency="INR",
            review_notes=["CIRCLE_RATE_FLOOR_REFERENCE_ONLY"],
        )


class ORERAProjectDisclosureAdapter(BaseSourceAdapter):
    """
    Authorized manual/export adapter for ORERA (`rera.odisha.gov.in`) registered project disclosures.
    Provides RERA ID, sanctioned units, QPR progress, and Mouza/plot geometry without inventing unit prices.
    """
    adapter_name = "ORERAProjectDisclosureAdapter"
    source_type = "ORERA_DISCLOSURE"
    portal_access_policy = "AUTHORIZED_DISCLOSURE_EXPORT_NO_AUTOMATED_PORTAL_SCRAPING"

    def normalize_record(
        self,
        raw_rec: Dict[str, Any],
        principal: Optional[VerifiedPrincipal] = None,
        batch_metadata: Optional[Dict[str, Any]] = None,
    ) -> NormalizedIngestionItem:
        reg_no = str(raw_rec.get("orera_registration_no") or raw_rec.get("evidence_document_reference") or "").strip()
        if not reg_no:
            raise AdapterValidationError("ORERAProjectDisclosureAdapter requires `orera_registration_no`.")

        prop_type = _normalize_property_type(raw_rec.get("property_type") or "apartment")
        area_unit = str(raw_rec.get("area_unit") or "sqft")
        land_area = normalize_area_to_sqft(raw_rec.get("total_land_area_sqft") or raw_rec.get("land_area_sqft"), area_unit)

        return NormalizedIngestionItem(
            source_type="ORERA_DISCLOSURE",
            source_reference=str(raw_rec.get("source_reference") or f"rera.odisha.gov.in:{reg_no}"),
            raw_payload_sanitized=redact_pii_dict(dict(raw_rec)),
            canonical_payload={
                "transaction_id": raw_rec.get("transaction_id") or f"ORERA-{reg_no}",
                "property_id": raw_rec.get("property_id") or f"ORERA:{reg_no}",
                "property_type": prop_type,
                "transaction_date": raw_rec.get("qpr_period_end_date") or raw_rec.get("transaction_date"),
                "registration_date": raw_rec.get("registration_date"),
                "sale_price_inr": None,  # ORERA project filings never fabricate unit deed sale prices!
                "land_area_sqft": land_area,
                "locality": raw_rec.get("mouza") or raw_rec.get("locality"),
                "city": raw_rec.get("city") or "Bhubaneswar",
                "district": raw_rec.get("district") or "Khordha",
                "state": raw_rec.get("state") or "Odisha",
                "latitude": raw_rec.get("latitude"),
                "longitude": raw_rec.get("longitude"),
                "evidence_document_type": "ORERA_QPR_FILING",
                "evidence_document_reference": reg_no,
                "transaction_classification": "NON_SALE_REFERENCE",
                "is_arms_length": False,
            },
            currency="INR",
            review_notes=["ORERA_PROJECT_ENRICHMENT_NO_UNIT_PRICE"],
        )
