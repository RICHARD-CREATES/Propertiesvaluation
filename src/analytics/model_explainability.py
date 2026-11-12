"""
Module 5: Production Model TreeSHAP Explainability Engine
=========================================================
Integrates directly with ProductionModelService artifacts in `models/`:
- XGBRegressor + ColumnTransformer preprocessor (`apartment`, `rental`)
- CatBoostRegressor (`house`, `residential_land`, `commercial`)

Guarantees:
1. Exact feature column order matching `feature_schema.json` (`num_features + cat_features`).
2. One-hot / transformed columns from `preprocessor.joblib` are mapped and summed cleanly
   back to original source features without losing additivity.
3. Strict SHAP additivity verification in log-price space:
   | (base_value_log + sum(shap_values_log)) - model_pred_log | < 1e-3
4. Both log-space marginal effects (% multiplier exp(phi) - 1) and additive INR deltas.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import shap

try:
    from catboost import Pool as CatBoostPool
except ImportError:  # pragma: no cover
    CatBoostPool = None

from src.services.production_models import ProductionModelService


CATEGORY_ALIASES = {
    "flat": "apartment",
    "condo": "apartment",
    "high_rise": "apartment",
    "villa": "house",
    "bungalow": "house",
    "independent_house": "house",
    "standalone_house": "house",
    "plot": "residential_land",
    "land": "residential_land",
    "shop": "commercial",
    "office": "commercial",
    "retail": "commercial",
    "warehouse": "commercial",
    "lease": "rental",
    "rent": "rental",
}


def _resolve_category(property_type: str) -> str:
    clean = str(property_type or "").lower().strip()
    return CATEGORY_ALIASES.get(clean, clean)


def _map_transformed_to_source(transformed_name: str, source_cols: List[str]) -> str:
    """Maps ColumnTransformer output feature names (e.g. 'cat__state_Odisha') back to source feature names."""
    # Strip transformer prefix like 'num__', 'cat__', 'remainder__'
    stripped = transformed_name.split("__", 1)[-1] if "__" in transformed_name else transformed_name
    # Longest match first handles overlapping names cleanly (e.g. plot_area_sqft vs area_sqft)
    for col in sorted(source_cols, key=len, reverse=True):
        if stripped == col or stripped.startswith(col + "_"):
            return col
    return stripped


class ProductionModelSHAPExplainer:
    """Verified TreeSHAP explainer aligned with real trained ProductionModelService artifacts."""

    def __init__(self, model_service: Optional[ProductionModelService] = None) -> None:
        self.service = model_service or ProductionModelService()
        self._explainers: Dict[str, Any] = {}

    def _get_explainer(self, category: str) -> Any:
        if category not in self._explainers:
            _, model_obj = self.service.models[category]
            self._explainers[category] = shap.TreeExplainer(model_obj)
        return self._explainers[category]

    @staticmethod
    def _build_feature_row(payload: Dict[str, Any]) -> Dict[str, Any]:
        area = (
            payload.get("builtup_area_sqft")
            or payload.get("area_sqft")
            or payload.get("carpet_area_sqft")
            or payload.get("plot_area_sqft")
            or 1000.0
        )
        return {
            "latitude": float(payload.get("latitude", 20.296)),
            "longitude": float(payload.get("longitude", 85.824)),
            "area_sqft": float(area),
            "plot_area_sqft": float(payload.get("plot_area_sqft") or area),
            "bedrooms": float(payload.get("bedrooms") or 2.0),
            "bathrooms": float(payload.get("bathrooms") or 2.0),
            "floor_number": float(payload.get("floor_number") or 3.0),
            "total_floors": float(payload.get("total_floors") or 12.0),
            "property_age_years": float(payload.get("property_age_years") or payload.get("property_age") or 4.0),
            "gross_rental_yield_pct": float(payload.get("gross_rental_yield_pct") or 3.6),
            "state": str(payload.get("state") or "Odisha"),
            "city": str(payload.get("city") or "Bhubaneswar"),
            "construction_grade": str(payload.get("construction_grade") or "GRADE_B"),
            "commercial_type": str(payload.get("commercial_type") or "retail"),
            "road_width_ft": str(payload.get("road_width_ft") or "30ft"),
            "corner_plot": str(payload.get("corner_plot") or "standard"),
        }

    def explain_instance(
        self,
        payload: Dict[str, Any],
        top_k: int = 5,
        additivity_tol: float = 1e-3,
    ) -> Dict[str, Any]:
        """Compute verified TreeSHAP explanation for a single property against the production model."""
        raw_type = str(payload.get("property_type") or "apartment")
        category = _resolve_category(raw_type)

        if category in ("agricultural", "agricultural_land", "industrial", "industrial_land"):
            return {
                "status": "DATA_NOT_READY",
                "property_type": category,
                "message": "No production ML model trained for this asset class; explainability skipped.",
            }

        if category not in self.service.models:
            return {
                "status": "MODEL_UNAVAILABLE",
                "property_type": category,
                "message": f"Model artifact for '{category}' is not loaded.",
            }

        model_type, model_obj = self.service.models[category]
        schema = self.service.schemas.get(category, {})
        num_features = list(schema.get("num_features", []))
        cat_features = list(schema.get("cat_features", []))
        expected_cols = num_features + cat_features

        row_dict = self._build_feature_row(payload)
        df_in = pd.DataFrame([row_dict])
        for c in cat_features:
            df_in[c] = df_in[c].astype(str)

        aggregated_shap: Dict[str, float] = {col: 0.0 for col in expected_cols}

        if model_type == "catboost":
            X_cb = df_in[expected_cols]
            pred_log = float(model_obj.predict(X_cb)[0])
            if CatBoostPool is not None:
                cb_pool = CatBoostPool(X_cb, cat_features=cat_features)
                sv = np.asarray(model_obj.get_feature_importance(cb_pool, type="ShapValues"), dtype=float)[0]
                base_log = float(sv[-1])
                phi_arr = sv[:-1]
            else:
                explainer = self._get_explainer(category)
                base_log = float(np.asarray(explainer.expected_value).reshape(-1)[0])
                phi_arr = np.asarray(explainer.shap_values(X_cb), dtype=float).reshape(-1)
            if len(phi_arr) != len(expected_cols):
                raise RuntimeError(
                    f"CatBoost SHAP vector length {len(phi_arr)} != schema feature count {len(expected_cols)}."
                )
            for col, phi in zip(expected_cols, phi_arr):
                aggregated_shap[col] = float(phi)
            backend_name = "catboost"
        else:
            explainer = self._get_explainer(category)
            base_log = float(np.asarray(explainer.expected_value).reshape(-1)[0])
            preprocessor = self.service.preprocessors[category]
            X_raw = df_in[expected_cols]
            X_proc = preprocessor.transform(X_raw)
            X_dense = X_proc.toarray() if hasattr(X_proc, "toarray") else np.asarray(X_proc, dtype=float)
            pred_log = float(model_obj.predict(X_dense)[0])

            phi_proc = np.asarray(explainer.shap_values(X_dense), dtype=float).reshape(-1)
            try:
                transformed_names = list(preprocessor.get_feature_names_out())
            except Exception:
                transformed_names = [f"f{i}" for i in range(X_dense.shape[1])]

            if len(phi_proc) != len(transformed_names):
                raise RuntimeError(
                    f"Pipeline SHAP length {len(phi_proc)} != transformed columns {len(transformed_names)}."
                )

            for tname, phi in zip(transformed_names, phi_proc):
                src_col = _map_transformed_to_source(str(tname), expected_cols)
                aggregated_shap[src_col] = aggregated_shap.get(src_col, 0.0) + float(phi)
            backend_name = "xgboost_sklearn_pipeline"

        shap_sum_log = float(sum(aggregated_shap.values()))
        additivity_error_log = abs((base_log + shap_sum_log) - pred_log)
        additivity_verified = bool(additivity_error_log < additivity_tol)
        if not additivity_verified:
            raise AssertionError(
                f"SHAP additivity failed for '{category}': |({base_log:.6f} + {shap_sum_log:.6f}) - {pred_log:.6f}| = {additivity_error_log:.6f}"
            )

        base_inr = float(np.expm1(base_log))
        pred_inr = float(np.expm1(pred_log))
        total_delta_inr = pred_inr - base_inr

        attributions: List[Dict[str, Any]] = []
        for col, phi in aggregated_shap.items():
            mult = float(np.exp(phi))
            pct_effect = (mult - 1.0) * 100.0
            # Exact additive INR allocation preserving sum == (pred_inr - base_inr)
            if abs(shap_sum_log) > 1e-12:
                inr_delta = total_delta_inr * (phi / shap_sum_log)
            else:
                inr_delta = 0.0
            attributions.append(
                {
                    "feature": col,
                    "raw_value": row_dict.get(col),
                    "shap_log": round(float(phi), 6),
                    "multiplicative_factor": round(mult, 4),
                    "pct_impact_on_price": round(pct_effect, 2),
                    "allocated_inr_delta": round(float(inr_delta), 2),
                }
            )

        attributions.sort(key=lambda d: abs(d["shap_log"]), reverse=True)
        positive_drivers = [a for a in attributions if a["shap_log"] > 0][:top_k]
        negative_drivers = sorted(
            [a for a in attributions if a["shap_log"] < 0],
            key=lambda d: d["shap_log"],
        )[:top_k]

        return {
            "status": "OK",
            "property_type": category,
            "model_backend": backend_name,
            "expected_feature_order": expected_cols,
            "target_scale": "log1p(price_inr)",
            "base_value_log": round(base_log, 6),
            "predicted_log": round(pred_log, 6),
            "shap_sum_log": round(shap_sum_log, 6),
            "additivity_error_log": round(float(additivity_error_log), 8),
            "additivity_verified": additivity_verified,
            "base_value_inr": round(base_inr, 2),
            "predicted_value_inr": round(pred_inr, 2),
            "feature_attributions": attributions,
            "top_positive_drivers": positive_drivers,
            "top_negative_drivers": negative_drivers,
        }
