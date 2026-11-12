"""
Milestone 8 — Phase 5: Geographic & Bhubaneswar Locality Coverage Intelligence
============================================================================
Computes read-only locality coverage metrics, strict data segregation counts,
sample-sufficiency gating, missing-data rates, and explicit limitations without
ever ranking localities or reporting medians on insufficient verified samples.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from src.core.evidence_schema import (
    COMPLETED_SALE_DOCUMENT_TYPES,
    CanonicalTransaction,
    IngestionRun,
)
from src.services.verification_engine import BHUBANESWAR_AUTHORITATIVE_LOCALITIES

MIN_VERIFIED_PRELIMINARY = 5
MIN_VERIFIED_RELIABLE_BENCHMARK = 15


def _applicable_area(tx: CanonicalTransaction) -> Optional[float]:
    if tx.property_type in ("residential_land", "agricultural"):
        return tx.land_area_sqft or tx.builtup_area_sqft
    return tx.builtup_area_sqft or tx.carpet_area_sqft or tx.land_area_sqft


def _is_verified_completed_sale(tx: CanonicalTransaction) -> bool:
    return (
        tx.verification_status in ("DOCUMENT_VERIFIED", "REGISTRATION_VERIFIED")
        and tx.source_category in ("REGISTRATION_VERIFIED_TX", "DOCUMENT_VERIFIED_TX")
        and tx.evidence_document_type in COMPLETED_SALE_DOCUMENT_TYPES
        and tx.transaction_classification == "ARMS_LENGTH_MARKET"
        and tx.sale_price_inr is not None
        and tx.sale_price_inr > 0
    )


class GeographicCoverageAnalyzer:
    """Read-only Bhubaneswar & pan-India ground-truth coverage and sufficiency engine."""

    def build_city_coverage_report(
        self,
        db: Session,
        city: str = "Bhubaneswar",
        min_preliminary: int = MIN_VERIFIED_PRELIMINARY,
        min_benchmark: int = MIN_VERIFIED_RELIABLE_BENCHMARK,
    ) -> Dict[str, Any]:
        all_rows = (
            db.query(CanonicalTransaction)
            .filter(CanonicalTransaction.city == city)
            .all()
        )
        latest_run = db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).first()

        # Global breakdowns (strictly segregated)
        status_counts = Counter(r.verification_status for r in all_rows)
        source_type_counts = Counter(r.source_type for r in all_rows)
        category_counts = Counter(r.source_category for r in all_rows)
        prop_type_counts = Counter(r.property_type for r in all_rows)

        # Group by canonical locality title (pre-seed known Bhubaneswar corridors so missing coverage is explicit!)
        locality_rows: Dict[str, List[CanonicalTransaction]] = defaultdict(list)
        known_display_names = {k: k.title() for k in BHUBANESWAR_AUTHORITATIVE_LOCALITIES}
        for k, disp in known_display_names.items():
            if city.lower() == "bhubaneswar":
                locality_rows[disp] = []

        for r in all_rows:
            raw_loc = str(r.locality or "Unspecified Locality").strip()
            key = known_display_names.get(raw_loc.lower(), raw_loc)
            locality_rows[key].append(r)

        locality_reports: List[Dict[str, Any]] = []
        total_verified = 0
        total_reg_verified = 0
        total_unverified = 0
        total_rejected = 0

        for loc_name, rows in sorted(locality_rows.items()):
            verified_sales = [r for r in rows if _is_verified_completed_sale(r)]
            reg_ver = [r for r in verified_sales if r.verification_status == "REGISTRATION_VERIFIED"]
            doc_ver = [r for r in verified_sales if r.verification_status == "DOCUMENT_VERIFIED"]
            unverified_or_broker = [
                r for r in rows
                if r.verification_status in ("UNVERIFIED", "SOURCE_CONFIRMED")
                and r.source_category not in ("GOVT_CIRCLE_RATE_REFERENCE", "ORERA_BDA_ENRICHMENT", "SYNTHETIC_TEST")
            ]
            circle_refs = [r for r in rows if r.source_category == "GOVT_CIRCLE_RATE_REFERENCE"]
            orera_refs = [r for r in rows if r.source_category == "ORERA_BDA_ENRICHMENT"]
            rejected_rows = [r for r in rows if r.verification_status == "REJECTED"]
            review_pending = [r for r in rows if r.requires_human_review]

            total_verified += len(verified_sales)
            total_reg_verified += len(reg_ver)
            total_unverified += len(unverified_or_broker)
            total_rejected += len(rejected_rows)

            loc_prop_mix = dict(Counter(r.property_type for r in verified_sales))
            dates = sorted(r.transaction_date.isoformat() for r in verified_sales if r.transaction_date)
            all_dates = sorted(r.transaction_date.isoformat() for r in rows if r.transaction_date)

            # Missing critical field percentage across locality records
            if rows:
                missing_checks = 0
                total_checks = len(rows) * 6
                for r in rows:
                    if r.transaction_date is None:
                        missing_checks += 1
                    if r.sale_price_inr is None and r.source_category not in ("GOVT_CIRCLE_RATE_REFERENCE", "ORERA_BDA_ENRICHMENT"):
                        missing_checks += 1
                    if _applicable_area(r) is None:
                        missing_checks += 1
                    if r.latitude is None or r.longitude is None:
                        missing_checks += 1
                    if not r.property_id:
                        missing_checks += 1
                    if not r.evidence_document_reference:
                        missing_checks += 1
                missing_pct = round((missing_checks / total_checks) * 100.0, 2)
            else:
                missing_pct = None

            # Coordinates for map pin (observed centroid or authoritative corridor hub)
            obs_coords = [(r.latitude, r.longitude) for r in rows if r.latitude is not None and r.longitude is not None]
            if obs_coords:
                lat_c = round(float(np.mean([c[0] for c in obs_coords])), 6)
                lon_c = round(float(np.mean([c[1] for c in obs_coords])), 6)
            elif loc_name.lower() in BHUBANESWAR_AUTHORITATIVE_LOCALITIES:
                la, lo, _ = BHUBANESWAR_AUTHORITATIVE_LOCALITIES[loc_name.lower()]
                lat_c, lon_c = la, lo
            else:
                lat_c, lon_c = None, None

            # Strict Sufficiency Gating — NEVER publish medians or rank with < min_preliminary
            v_cnt = len(verified_sales)
            prices = [float(r.sale_price_inr) for r in verified_sales]
            ppsf_vals = [
                float(r.sale_price_inr) / float(_applicable_area(r))
                for r in verified_sales
                if _applicable_area(r) and _applicable_area(r) > 0
            ]

            limitations: List[str] = []
            if v_cnt < min_preliminary:
                sufficiency_status = "INSUFFICIENT_VERIFIED_SAMPLE"
                median_price = None
                ppsf_stats = None
                limitations.append(
                    f"Only {v_cnt} verified completed arm's-length deeds (< {min_preliminary} minimum); "
                    "median price and PPSF are suppressed to prevent unreliable locality claims."
                )
            elif v_cnt < min_benchmark:
                sufficiency_status = "PRELIMINARY_DESCRIPTIVE_ONLY"
                median_price = round(float(np.median(prices)), 2)
                if ppsf_vals:
                    p25, p50, p75 = np.percentile(ppsf_vals, [25, 50, 75])
                    ppsf_stats = {
                        "count": len(ppsf_vals),
                        "median": round(float(p50), 2),
                        "p25": round(float(p25), 2),
                        "p75": round(float(p75), 2),
                        "iqr": round(float(p75 - p25), 2),
                    }
                else:
                    ppsf_stats = None
                limitations.append(
                    f"Preliminary descriptive sample ({v_cnt} verified deeds; < {min_benchmark} benchmark threshold). "
                    "Do NOT treat as robust valuation accuracy proof or rank against denser localities."
                )
            else:
                sufficiency_status = "SUFFICIENT_LOCAL_COVERAGE"
                median_price = round(float(np.median(prices)), 2)
                p25, p50, p75 = np.percentile(ppsf_vals, [25, 50, 75]) if ppsf_vals else (None, None, None)
                ppsf_stats = (
                    {
                        "count": len(ppsf_vals),
                        "median": round(float(p50), 2),
                        "p25": round(float(p25), 2),
                        "p75": round(float(p75), 2),
                        "iqr": round(float(p75 - p25), 2),
                    }
                    if ppsf_vals
                    else None
                )
                limitations.append("Subject to property-type composition mix and deed registration lag.")

            if len(circle_refs) > 0 and v_cnt == 0:
                limitations.append(
                    f"{len(circle_refs)} circle-rate benchmark reference(s) stored separately; excluded from market medians."
                )
            if len(unverified_or_broker) > 0:
                limitations.append(
                    f"{len(unverified_or_broker)} unverified/broker record(s) excluded from verified price metrics."
                )

            locality_reports.append(
                {
                    "locality": loc_name,
                    "city": city,
                    "coordinates": {"latitude": lat_c, "longitude": lon_c} if lat_c is not None else None,
                    "verified_transaction_count": v_cnt,
                    "registration_verified_count": len(reg_ver),
                    "document_verified_count": len(doc_ver),
                    "unverified_or_broker_count": len(unverified_or_broker),
                    "circle_rate_reference_count": len(circle_refs),
                    "orera_enrichment_count": len(orera_refs),
                    "rejected_count": len(rejected_rows),
                    "human_review_pending_count": len(review_pending),
                    "sufficiency_status": sufficiency_status,
                    "property_type_distribution": loc_prop_mix,
                    "transaction_date_range": {
                        "earliest": dates[0] if dates else None,
                        "latest": dates[-1] if dates else None,
                    },
                    "latest_observed_any_record_date": all_dates[-1] if all_dates else None,
                    "median_verified_price_inr": median_price,
                    "verified_ppsf_distribution": ppsf_stats,
                    "missing_data_pct": missing_pct,
                    "limitations": limitations,
                }
            )

        sufficient_localities = [l["locality"] for l in locality_reports if l["sufficiency_status"] == "SUFFICIENT_LOCAL_COVERAGE"]
        prelim_localities = [l["locality"] for l in locality_reports if l["sufficiency_status"] == "PRELIMINARY_DESCRIPTIVE_ONLY"]

        return {
            "read_only": True,
            "city": city,
            "total_canonical_records": len(all_rows),
            "verified_completed_sales_count": total_verified,
            "registration_verified_count": total_reg_verified,
            "unverified_or_broker_count": total_unverified,
            "rejected_count": total_rejected,
            "data_quality_failures_or_reviews": sum(1 for r in all_rows if r.requires_human_review or r.verification_status == "REJECTED"),
            "verification_status_distribution": dict(status_counts),
            "source_type_distribution": dict(source_type_counts),
            "source_category_distribution": dict(category_counts),
            "property_type_distribution": dict(prop_type_counts),
            "last_ingestion_run_at": (
                (latest_run.finished_at or latest_run.started_at).isoformat() if latest_run else None
            ),
            "sufficiency_summary": {
                "sufficient_localities_count": len(sufficient_localities),
                "preliminary_localities_count": len(prelim_localities),
                "insufficient_localities_count": len(locality_reports) - len(sufficient_localities) - len(prelim_localities),
                "thresholds": {
                    "min_preliminary_verified_deeds": min_preliminary,
                    "min_benchmark_verified_deeds": min_benchmark,
                },
                "ranking_suppressed_note": (
                    "Localities below minimum verified deed sufficiency are never ranked or assigned median prices."
                ),
            },
            "localities": locality_reports,
        }
