"""Focused tests for Module 5: ProductionModelSHAPExplainer against real trained artifacts."""
import pytest
from src.analytics.model_explainability import ProductionModelSHAPExplainer
from src.services.production_models import ProductionModelService


@pytest.mark.parametrize(
    "payload",
    [
        {"property_type": "apartment", "latitude": 20.353, "longitude": 85.826, "builtup_area_sqft": 1450, "bedrooms": 3, "bathrooms": 2, "state": "Odisha"},
        {"property_type": "house", "latitude": 20.296, "longitude": 85.824, "builtup_area_sqft": 2100, "plot_area_sqft": 2400, "bedrooms": 4, "bathrooms": 3, "state": "Odisha"},
        {"property_type": "residential_land", "latitude": 20.320, "longitude": 85.800, "plot_area_sqft": 2400, "road_width_ft": "30ft", "corner_plot": "corner", "state": "Odisha"},
        {"property_type": "commercial", "latitude": 20.270, "longitude": 85.840, "builtup_area_sqft": 1800, "commercial_type": "office", "state": "Odisha"},
        {"property_type": "rental", "latitude": 20.340, "longitude": 85.820, "builtup_area_sqft": 1200, "gross_rental_yield_pct": 3.8, "state": "Odisha"},
    ],
)
def test_treeshap_all_real_production_models_additivity_and_alignment(payload):
    service = ProductionModelService()
    explainer = ProductionModelSHAPExplainer(model_service=service)

    res = explainer.explain_instance(payload)
    assert res["status"] == "OK"
    assert res["additivity_verified"] is True
    assert res["additivity_error_log"] < 1e-3

    # Verify INR allocated deltas reconstruct predicted_value_inr - base_value_inr accurately
    sum_inr_deltas = sum(a["allocated_inr_delta"] for a in res["feature_attributions"])
    expected_delta = res["predicted_value_inr"] - res["base_value_inr"]
    assert abs(sum_inr_deltas - expected_delta) < 5.0  # rounding tolerance across features

    # For non-rental asset valuation, cross-check predicted_value_inr matches ProductionModelService.estimate()
    if payload["property_type"] != "rental":
        est = service.estimate(
            property_type=payload["property_type"],
            latitude=payload["latitude"],
            longitude=payload["longitude"],
            builtup_area_sqft=payload.get("builtup_area_sqft"),
            plot_area_sqft=payload.get("plot_area_sqft"),
            bedrooms=payload.get("bedrooms"),
            bathrooms=payload.get("bathrooms"),
            state=payload.get("state"),
            road_width_ft=payload.get("road_width_ft"),
            corner_plot=payload.get("corner_plot"),
            commercial_type=payload.get("commercial_type"),
        )
        assert abs(res["predicted_value_inr"] - est["estimated_value_inr"]) < 10.0


def test_treeshap_data_not_ready_category():
    explainer = ProductionModelSHAPExplainer()
    res = explainer.explain_instance({"property_type": "agricultural", "latitude": 20.3, "longitude": 85.8})
    assert res["status"] == "DATA_NOT_READY"
