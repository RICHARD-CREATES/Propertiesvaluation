"""
Independent Valuation Accuracy & Evidence Validation Engine (Milestone 7 - Task 3 & 5).

Evaluates ML Models, Sales Comparison, Cost Approach, Income Capitalization,
and Three-Way Reconciliation strictly against verified independent ground-truth
transactions held out spatially from training data.
"""
import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from src.core.ground_truth_db import (
    GroundTruthTransaction,
    ValidationEvaluationRun,
    init_ground_truth_db,
    validate_transaction_payload,
)
from src.core.rental_db import SessionLocal
from src.core.units import convert_area_to_sqm
from src.services.evidence_confidence import EvidenceConfidenceService
from src.services.location_intelligence import LocationIntelligenceService
from src.services.production_models import ProductionModelService
from src.services.spatial_split import create_spatial_splits


MIN_SAMPLES_FOR_METRIC_VALIDATION = 5
MIN_SAMPLES_FOR_INTERVAL_CALIBRATION = 10


def compute_regression_metrics(
    y_true: List[float],
    y_pred: List[float],
    lowers: Optional[List[Optional[float]]] = None,
    uppers: Optional[List[Optional[float]]] = None,
) -> Dict[str, Any]:
    """
    Computes MAE, RMSE, MedAPE, MAPE (with safe zero/small-denominator handling),
    R^2 (when meaningful), and empirical prediction interval coverage.
    """
    n = len(y_true)
    if n == 0:
        return {
            "sample_count": 0,
            "validation_status": "UNVALIDATED_INSUFFICIENT_GROUND_TRUTH",
            "mae": None,
            "rmse": None,
            "medape_pct": None,
            "mape_pct": None,
            "r2_score": None,
            "r2_note": "No verified ground-truth transactions available.",
            "interval_coverage_pct": None,
        }

    yt = np.array(y_true, dtype=float)
    yp = np.array(y_pred, dtype=float)
    errors = yp - yt
    abs_errors = np.abs(errors)

    mae = round(float(np.mean(abs_errors)), 2)
    rmse = round(float(np.sqrt(np.mean(errors ** 2))), 2)

    # Safe APE computation: exclude zero or small actual values (< 1000 INR) to prevent infinite MAPE
    valid_mask = np.abs(yt) >= 1000.0
    excluded_small = int(np.sum(~valid_mask))
    if np.any(valid_mask):
        apes = (abs_errors[valid_mask] / np.abs(yt[valid_mask])) * 100.0
        medape = round(float(np.median(apes)), 2)
        mape = round(float(np.mean(apes)), 2)
    else:
        medape = None
        mape = None

    # R^2 only meaningful when n >= 3 and ground truth has non-zero variance
    if n >= 3 and float(np.var(yt)) > 1e-6:
        ss_res = float(np.sum((yt - yp) ** 2))
        ss_tot = float(np.sum((yt - np.mean(yt)) ** 2))
        r2 = round(1.0 - (ss_res / ss_tot), 4)
        r2_note = None
    else:
        r2 = None
        r2_note = "R^2 undefined (requires >= 3 transactions with non-zero price variance)."

    coverage = None
    if lowers is not None and uppers is not None and len(lowers) == n and len(uppers) == n:
        cov_flags = [
            (lo <= actual <= hi)
            for actual, lo, hi in zip(yt, lowers, uppers)
            if lo is not None and hi is not None
        ]
        if cov_flags:
            coverage = round((sum(cov_flags) / len(cov_flags)) * 100.0, 2)

    status = (
        "VALIDATED"
        if n >= MIN_SAMPLES_FOR_METRIC_VALIDATION
        else "UNVALIDATED_INSUFFICIENT_GROUND_TRUTH"
    )

    return {
        "sample_count": n,
        "validation_status": status,
        "mae": mae,
        "rmse": rmse,
        "medape_pct": medape,
        "mape_pct": mape,
        "zero_or_small_actuals_excluded_from_mape": excluded_small,
        "r2_score": r2,
        "r2_note": r2_note,
        "interval_coverage_pct": coverage,
    }


class IndependentValidationEngine:
    """Manages Ground-Truth Ingestion, Spatial Splits, Accuracy Auditing, and Uncertainty Calibration."""

    def __init__(self, valuation_engine=None):
        init_ground_truth_db()
        self.location_service = LocationIntelligenceService()
        self.production_models = ProductionModelService()
        self.evidence_service = EvidenceConfidenceService()
        self._valuation_engine = valuation_engine

    @property
    def valuation_engine(self):
        if self._valuation_engine is None:
            from src.services.valuation_engine import GlobalPropertyValuationEngine
            self._valuation_engine = GlobalPropertyValuationEngine()
        return self._valuation_engine

    def ingest_transactions(
        self,
        records: List[Dict[str, Any]],
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Validates, deduplicates, segregates, and stores ground-truth transactions.
        Strictly rejects synthetic or asking records from becoming verified ground truth.
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            accepted = 0
            duplicates = 0
            rejected = 0
            segregated_non_gt = 0
            errors: List[str] = []

            for idx, raw in enumerate(records):
                try:
                    clean = validate_transaction_payload(raw)

                    # Duplicate check by transaction_id OR dedup_signature
                    existing_tx = (
                        db.query(GroundTruthTransaction)
                        .filter_by(transaction_id=clean["transaction_id"])
                        .first()
                    )
                    if existing_tx:
                        duplicates += 1
                        continue

                    dup_sig_match = (
                        db.query(GroundTruthTransaction)
                        .filter_by(dedup_signature=clean["dedup_signature"], is_duplicate=False)
                        .first()
                    )
                    is_dup = dup_sig_match is not None
                    if is_dup:
                        duplicates += 1

                    row = GroundTruthTransaction(
                        **clean,
                        is_duplicate=is_dup,
                        duplicate_of_id=dup_sig_match.id if dup_sig_match else None,
                    )
                    db.add(row)
                    db.flush()

                    if clean["data_category"] != "Verified_Registered_Transaction":
                        segregated_non_gt += 1
                    accepted += 1
                except Exception as exc:
                    rejected += 1
                    errors.append(f"Row {idx}: {exc}")

            db.commit()
            return {
                "submitted": len(records),
                "accepted": accepted,
                "duplicates_detected": duplicates,
                "segregated_non_ground_truth": segregated_non_gt,
                "rejected": rejected,
                "errors": errors,
            }
        finally:
            if close_db:
                db.close()

    def run_spatial_split_on_db(
        self,
        cluster_radius_km: float = 3.0,
        seed: int = 42,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Assigns zero-leakage Train/Val/Test spatial clusters across verified transactions."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            verified_rows = (
                db.query(GroundTruthTransaction)
                .filter(
                    GroundTruthTransaction.data_category == "Verified_Registered_Transaction",
                    GroundTruthTransaction.is_duplicate.is_(False),
                )
                .all()
            )
            if not verified_rows:
                return {
                    "status": "INSUFFICIENT_VERIFIED_GROUND_TRUTH",
                    "message": "No verified independent registered transactions found in ground_truth_transactions.",
                    "split_report": None,
                }

            payload_rows = [
                {
                    "id": r.id,
                    "transaction_id": r.transaction_id,
                    "property_type": r.property_type,
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                    "locality": r.locality,
                    "city": r.city,
                    "state": r.state,
                    "transaction_date": r.transaction_date.isoformat(),
                }
                for r in verified_rows
            ]

            split_res = create_spatial_splits(
                payload_rows, cluster_radius_km=cluster_radius_km, seed=seed
            )

            # Persist cluster and split assignments
            row_map = {r.id: r for r in verified_rows}
            for split_group_rows in (split_res["train"], split_res["validation"], split_res["test"]):
                for item in split_group_rows:
                    db_obj = row_map.get(item["id"])
                    if db_obj:
                        db_obj.geo_cluster_id = item.get("geo_cluster_id")
                        db_obj.split_group = item.get("split_group", "test")

            db.commit()
            return {
                "status": split_res["status"],
                "message": split_res.get("message", "Spatial splits assigned with zero geographic leakage."),
                "cluster_count": split_res.get("cluster_count", 1),
                "leakage_audit": split_res["leakage_audit"],
                "split_report": split_res["split_report"],
            }
        finally:
            if close_db:
                db.close()

    def _predict_all_approaches_for_tx(self, tx: GroundTruthTransaction) -> Dict[str, Any]:
        """Runs independent valuation approaches for a single verified ground-truth record."""
        intel = self.location_service.harvest(tx.latitude, tx.longitude, country_code=tx.country_code)

        if tx.property_type == "residential_land":
            asset_type = "land"
            structure_type = "land"
            area_val = tx.plot_area_sqft or tx.builtup_area_sqft or 1500.0
        elif tx.property_type == "commercial":
            asset_type = "commercial"
            structure_type = "office"
            area_val = tx.builtup_area_sqft or tx.carpet_area_sqft or 1000.0
        elif tx.property_type == "standalone_house":
            asset_type = "residential"
            structure_type = "standalone_house"
            area_val = tx.builtup_area_sqft or tx.carpet_area_sqft or 1500.0
        else:
            asset_type = "residential"
            structure_type = "apartment"
            area_val = tx.builtup_area_sqft or tx.carpet_area_sqft or 1000.0

        sqm_area = convert_area_to_sqm(area_val, "sqft")
        prop_dict = {
            "asset_type": asset_type,
            "structure_type": structure_type,
            "plot_area_sqft": tx.plot_area_sqft or (area_val * 1.2 if structure_type == "standalone_house" else 0.0),
            "built_area_sqm": sqm_area if asset_type != "land" else None,
            "land_area_sqm": sqm_area if asset_type == "land" else None,
            "bedrooms": tx.bhk or 2.0,
            "property_age_years": tx.construction_age_years if tx.construction_age_years is not None else 5.0,
            "construction_quality_code": "GRADE_B",
        }

        eval_res = self.valuation_engine.evaluate_property(prop_dict, intel)
        rec_bundle = eval_res.get("income_approach_and_reconciliation", {})
        rec = rec_bundle.get("three_way_reconciliation", {})
        approaches = rec.get("approaches", {})

        # Standalone ML production model inference
        ml_res = self.production_models.estimate(
            property_type=tx.property_type,
            latitude=tx.latitude,
            longitude=tx.longitude,
            builtup_area_sqft=tx.builtup_area_sqft or area_val,
            carpet_area_sqft=tx.carpet_area_sqft,
            plot_area_sqft=tx.plot_area_sqft,
            bedrooms=tx.bhk,
            property_age=tx.construction_age_years,
            state=tx.state,
            city=tx.city,
        )
        ml_pred = ml_res.get("estimated_value_inr") if ml_res.get("status") == "success" else None

        return {
            "actual": float(tx.sale_price),
            "ml_model": float(ml_pred) if ml_pred else None,
            "sales_comparison": float(approaches.get("approach_a_sales_comparison", {}).get("value", 0.0)),
            "cost_approach": float(approaches.get("approach_b_cost_approach", {}).get("value", 0.0)),
            "income_capitalization": float(approaches.get("approach_c_income_capitalization", {}).get("value", 0.0)),
            "three_way_reconciliation": float(rec.get("reconciled_fair_market_value", 0.0)),
            "confidence_score": float(eval_res.get("evidence_and_uncertainty", {}).get("evidence_quality", {}).get("composite_confidence_score", 0.5)),
        }

    def get_holdout_residuals_by_category(self, category: str, db: Optional[Session] = None) -> List[float]:
        """Retrieves historical empirical abs% errors on held-out verified transactions for calibration."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            latest = (
                db.query(ValidationEvaluationRun)
                .order_by(ValidationEvaluationRun.evaluated_at.desc())
                .first()
            )
            if not latest:
                return []
            cat_metrics = json.loads(latest.category_metrics_json or "{}")
            return cat_metrics.get(category, {}).get("_holdout_abs_pct_errors", [])
        finally:
            if close_db:
                db.close()

    def evaluate_ground_truth(
        self,
        include_splits: Optional[List[str]] = None,
        persist_run: bool = True,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates all approaches strictly on non-training verified ground-truth transactions.
        Never evaluates against training splits, synthetic rows, or advertised listings.
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            allowed_splits = include_splits or ["test", "validation", "unassigned"]
            if "train" in allowed_splits:
                raise ValueError("RULE VIOLATION: Training split ('train') cannot be used as evaluation test data.")

            all_rows = db.query(GroundTruthTransaction).all()
            source_breakdown = dict(Counter(r.data_category for r in all_rows))

            verified_eval_rows = [
                r
                for r in all_rows
                if r.data_category == "Verified_Registered_Transaction"
                and not r.is_duplicate
                and r.split_group in allowed_splits
            ]

            unvalidated_components: List[str] = []
            if not verified_eval_rows:
                unvalidated_components.extend([
                    "ml_models (0 independent ground-truth test deeds)",
                    "sales_comparison (0 independent ground-truth test deeds)",
                    "cost_approach (0 independent ground-truth test deeds)",
                    "income_capitalization (0 independent ground-truth test deeds)",
                    "three_way_reconciliation (0 independent ground-truth test deeds)",
                    "prediction_interval_calibration (0 holdout residuals)",
                ])
                summary = {
                    "validation_status": "INSUFFICIENT_VERIFIED_GROUND_TRUTH",
                    "evaluated_at": datetime.utcnow().isoformat() + "Z",
                    "verified_sample_count": 0,
                    "source_breakdown": source_breakdown,
                    "overall_metrics_by_approach": {},
                    "metrics_by_property_type": {},
                    "metrics_by_locality": {},
                    "actual_vs_predicted": [],
                    "error_distribution": [],
                    "confidence_distribution": {},
                    "geographic_validation_coverage": {"states": [], "cities": [], "localities": []},
                    "unvalidated_components": unvalidated_components,
                    "limitations_note": (
                        "Repository currently holds regional training benchmarks (datasets/training/*.parquet) "
                        "and ZERO verified independent registered sale deeds. Ingest verified deeds via "
                        "/api/validation/ground-truth/ingest to measure true out-of-sample accuracy."
                    ),
                }
                return summary

            # Run predictions across every held-out verified transaction
            predictions_table: List[Dict[str, Any]] = []
            for tx in verified_eval_rows:
                preds = self._predict_all_approaches_for_tx(tx)
                predictions_table.append({
                    "transaction_id": tx.transaction_id,
                    "property_type": tx.property_type,
                    "locality": tx.locality,
                    "city": tx.city,
                    "state": tx.state,
                    "split_group": tx.split_group,
                    "transaction_date": tx.transaction_date.isoformat(),
                    **preds,
                })

            # 1. Metrics by Approach (Overall)
            approaches_keys = [
                "three_way_reconciliation",
                "sales_comparison",
                "cost_approach",
                "income_capitalization",
                "ml_model",
            ]
            overall_metrics = {}
            for ak in approaches_keys:
                pairs = [(r["actual"], r[ak]) for r in predictions_table if r[ak] is not None and r[ak] > 0]
                if ak == "income_capitalization":
                    # Omit vacant land from income approach evaluation if 0
                    pairs = [p for p in pairs]
                y_t = [p[0] for p in pairs]
                y_p = [p[1] for p in pairs]

                # Compute empirical intervals if >= MIN_SAMPLES_FOR_INTERVAL_CALIBRATION
                abs_pct_errs = [abs(p - a) / a for a, p in pairs if a >= 1000.0]
                lows, highs = None, None
                if len(abs_pct_errs) >= MIN_SAMPLES_FOR_INTERVAL_CALIBRATION:
                    cal_q = float(np.quantile(abs_pct_errs, 0.90))
                    lows = [round(p * max(0.05, 1.0 - cal_q), 0) for p in y_p]
                    highs = [round(p * (1.0 + cal_q), 0) for p in y_p]

                m = compute_regression_metrics(y_t, y_p, lowers=lows, uppers=highs)
                overall_metrics[ak] = m
                if m["validation_status"] != "VALIDATED":
                    unvalidated_components.append(f"{ak} (only {m['sample_count']} verified samples < {MIN_SAMPLES_FOR_METRIC_VALIDATION})")

            # 2. Metrics by Property Category (evaluating primary Reconciled Value)
            by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in predictions_table:
                by_cat[row["property_type"]].append(row)

            category_metrics = {}
            for cat in ("apartment", "standalone_house", "commercial", "residential_land"):
                c_rows = by_cat.get(cat, [])
                y_t = [r["actual"] for r in c_rows]
                y_p = [r["three_way_reconciliation"] for r in c_rows]
                abs_pct_errs = [abs(p - a) / a for a, p in zip(y_t, y_p) if a >= 1000.0]

                cm = compute_regression_metrics(y_t, y_p)
                cm["_holdout_abs_pct_errors"] = [round(e, 4) for e in abs_pct_errs]
                category_metrics[cat] = cm
                if cm["validation_status"] != "VALIDATED":
                    unvalidated_components.append(f"category:{cat} ({cm['sample_count']} samples)")

            # 3. Metrics by Locality
            by_loc: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in predictions_table:
                by_loc[f"{row['locality']}, {row['city']}"].append(row)

            locality_metrics = {
                loc: compute_regression_metrics(
                    [r["actual"] for r in l_rows],
                    [r["three_way_reconciliation"] for r in l_rows],
                )
                for loc, l_rows in by_loc.items()
            }

            # 4. Actual vs Predicted & Error Distribution
            actual_vs_pred = []
            error_dist = []
            conf_buckets = Counter()
            for r in predictions_table:
                pred_val = r["three_way_reconciliation"]
                act_val = r["actual"]
                pct_err = round(((pred_val - act_val) / max(act_val, 1.0)) * 100.0, 2)
                actual_vs_pred.append({
                    "transaction_id": r["transaction_id"],
                    "property_type": r["property_type"],
                    "locality": r["locality"],
                    "actual": act_val,
                    "predicted": pred_val,
                    "pct_error": pct_err,
                })
                error_dist.append(pct_err)
                cs = r["confidence_score"]
                if cs >= 0.78:
                    conf_buckets["HIGH"] += 1
                elif cs >= 0.55:
                    conf_buckets["MODERATE"] += 1
                elif cs >= 0.35:
                    conf_buckets["LOW"] += 1
                else:
                    conf_buckets["INSUFFICIENT_EVIDENCE"] += 1

            geo_coverage = {
                "states": sorted({r["state"] for r in predictions_table}),
                "cities": sorted({r["city"] for r in predictions_table}),
                "localities": sorted({r["locality"] for r in predictions_table}),
                "splits_evaluated": sorted({r["split_group"] for r in predictions_table}),
            }

            n_eval = len(predictions_table)
            val_status = (
                "VALIDATED"
                if n_eval >= MIN_SAMPLES_FOR_INTERVAL_CALIBRATION and not unvalidated_components
                else ("PARTIALLY_VALIDATED" if n_eval >= MIN_SAMPLES_FOR_METRIC_VALIDATION else "INSUFFICIENT_VERIFIED_GROUND_TRUTH")
            )

            report = {
                "validation_status": val_status,
                "evaluated_at": datetime.utcnow().isoformat() + "Z",
                "verified_sample_count": n_eval,
                "source_breakdown": source_breakdown,
                "overall_metrics_by_approach": overall_metrics,
                "metrics_by_property_type": category_metrics,
                "metrics_by_locality": locality_metrics,
                "actual_vs_predicted": actual_vs_pred,
                "error_distribution": error_dist,
                "confidence_distribution": dict(conf_buckets),
                "geographic_validation_coverage": geo_coverage,
                "unvalidated_components": unvalidated_components,
            }

            if persist_run:
                run_row = ValidationEvaluationRun(
                    dataset_scope=",".join(allowed_splits),
                    validation_status=val_status,
                    verified_sample_count=n_eval,
                    overall_metrics_json=json.dumps(overall_metrics),
                    category_metrics_json=json.dumps(category_metrics),
                    locality_metrics_json=json.dumps(locality_metrics),
                    spatial_split_audit_json=json.dumps(geo_coverage),
                    source_breakdown_json=json.dumps(source_breakdown),
                    unvalidated_components_json=json.dumps(unvalidated_components),
                )
                db.add(run_row)
                db.commit()

            return report
        finally:
            if close_db:
                db.close()
