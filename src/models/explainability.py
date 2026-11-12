"""
Model Explainability & Horizon Forecasting.
Computes TreeSHAP explanations for individual property valuations, identifying
the top value-accretive drivers and value-discounting factors. Also generates
1-year, 3-year, and 5-year capital value outlooks.
"""
from typing import Dict, Any, List
import numpy as np
import pandas as pd
import shap


class ValuationExplainer:
    """Explains model decisions using TreeSHAP and generates forward forecast bands."""

    def __init__(self, model_wrapper):
        self.model_wrapper = model_wrapper
        # Use TreeExplainer on fitted XGBoost model
        self.explainer = shap.TreeExplainer(self.model_wrapper.xgb_model)
        self.feature_names = self.model_wrapper.feature_names

    def explain_instance(self, single_feature_df: pd.DataFrame, top_k: int = 5) -> Dict[str, Any]:
        """
        Calculates SHAP values for a single valuation and returns top positive
        and top negative drivers.
        """
        X = single_feature_df[self.feature_names].values
        shap_values = self.explainer.shap_values(X)[0]
        base_value = float(self.explainer.expected_value)

        feature_effects = []
        for name, val, effect in zip(self.feature_names, X[0], shap_values):
            feature_effects.append({
                "feature": name,
                "feature_value": float(val),
                "shap_impact_inr": float(effect),
            })

        # Sort drivers
        positive_drivers = sorted(
            [f for f in feature_effects if f["shap_impact_inr"] > 0],
            key=lambda x: x["shap_impact_inr"],
            reverse=True,
        )[:top_k]

        negative_drivers = sorted(
            [f for f in feature_effects if f["shap_impact_inr"] < 0],
            key=lambda x: x["shap_impact_inr"],
        )[:top_k]

        return {
            "base_value_inr": base_value,
            "top_positive_drivers": positive_drivers,
            "top_negative_drivers": negative_drivers,
            "net_shap_adjustment_inr": float(np.sum(shap_values)),
        }

    def forecast_horizons(
        self,
        current_fair_value_inr: float,
        features: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Forecasts 1-year, 3-year, and 5-year valuations based on:
        - 12m historic price delta
        - Infrastructure capex momentum
        - Public transit expansion & upcoming SEZ proximity
        """
        base_yoy = float(features.get("price_psqft_12m_delta_pct", 7.0)) / 100.0
        infra_boost = min(0.04, float(features.get("public_infra_capex_cr", 1000.0)) / 50000.0)
        sez_boost = 0.02 if float(features.get("dist_upcoming_sez_km", 5.0)) < 3.0 else 0.008

        # Blended annualized growth rate
        cagr = np.clip(base_yoy * 0.65 + infra_boost + sez_boost, 0.03, 0.18)

        v_1yr = current_fair_value_inr * (1.0 + cagr)
        v_3yr = current_fair_value_inr * ((1.0 + cagr * 0.92) ** 3)
        v_5yr = current_fair_value_inr * ((1.0 + cagr * 0.85) ** 5)

        return {
            "projected_cagr_pct": round(cagr * 100.0, 2),
            "forecast_1_year_inr": round(v_1yr, 0),
            "forecast_3_year_inr": round(v_3yr, 0),
            "forecast_5_year_inr": round(v_5yr, 0),
        }
