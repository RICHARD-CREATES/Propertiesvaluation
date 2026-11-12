"""
Three-Way Valuation Reconciliation Engine.

Integrates the three institutional property valuation approaches:
- Approach A: Sales Comparison (Comparable Transactions & Spatial ML Ensemble)
- Approach B: Cost Approach (Stage 1 Land Market Valuation + Stage 2 Depreciated Replacement Cost)
- Approach C: Income Capitalization (NOI / Market Cap Rate + GRM + Gross Rental Yield)

Uses evidence-based dynamic weighting, outlier detection, and transparent divergence narratives.
"""
from typing import Any, Dict, List, Optional
import numpy as np

from src.core.rental_finance import (
    analyze_rental_cash_flow,
    calculate_direct_capitalization_value,
    calculate_value_from_grm,
    calculate_value_from_gross_yield,
    run_rental_sensitivity_analysis,
)
from src.core.units import format_currency
from src.services.rental_comparables import RentalComparableEngine, _normalize_property_category


# Initial property-category hypothesis weights (adapted dynamically by observed evidence quality)
INITIAL_CATEGORY_WEIGHT_HYPOTHESES = {
    "apartment": {"sales": 0.48, "cost": 0.30, "income": 0.22},
    "builder_floor": {"sales": 0.45, "cost": 0.35, "income": 0.20},
    "standalone_house": {"sales": 0.35, "cost": 0.50, "income": 0.15},
    "villa": {"sales": 0.35, "cost": 0.50, "income": 0.15},
    "office": {"sales": 0.25, "cost": 0.15, "income": 0.60},
    "retail": {"sales": 0.25, "cost": 0.15, "income": 0.60},
    "warehouse": {"sales": 0.25, "cost": 0.20, "income": 0.55},
    "industrial": {"sales": 0.25, "cost": 0.25, "income": 0.50},
    "mixed_use": {"sales": 0.30, "cost": 0.20, "income": 0.50},
    "land": {"sales": 0.65, "cost": 0.35, "income": 0.00},
}


class ThreeWayValuationReconciler:
    """Computes the Income Capitalization valuation and reconciles Approaches A, B, and C."""

    def __init__(self):
        self.rental_comp_engine = RentalComparableEngine()

    def evaluate_income_and_reconcile(
        self,
        latitude: float,
        longitude: float,
        asset_type: str,
        structure_type: str,
        commercial_type: str,
        valuation_area_sqft: float,
        currency: str,
        sales_comparison_value: float,
        cost_approach_value: float,
        m10_prediction: Dict[str, Any],
        property_input: Dict[str, Any],
        sales_comps_count: int = 10,
    ) -> Dict[str, Any]:
        """
        Executes Approach C (Income Capitalization) and reconciles it with Approaches A & B.
        """
        if asset_type == "land":
            rental_cat = "land"
        elif asset_type == "commercial":
            rental_cat = _normalize_property_category(commercial_type)
        else:
            rental_cat = _normalize_property_category(structure_type)

        # Vacant land without an active lease generates zero going-concern rental income
        user_monthly_rent = float(property_input.get("monthly_rent_inr", 0.0) or 0.0)
        if asset_type == "land" and user_monthly_rent <= 0.0:
            return self._reconcile_non_income_land(
                sales_comparison_value=sales_comparison_value,
                cost_approach_value=cost_approach_value,
                currency=currency,
                sales_comps_count=sales_comps_count,
            )

        # 1. Derive Market Cap Rate, Gross Yield & GRM from Comparable Engine
        market_rates = self.rental_comp_engine.derive_market_yield_and_cap_rate(
            latitude=latitude,
            longitude=longitude,
            property_type=rental_cat if rental_cat != "land" else "retail",
            radius_km=10.0,
        )
        comp_search = self.rental_comp_engine.find_comparables(
            latitude=latitude,
            longitude=longitude,
            radius_km=5.0,
            property_type=rental_cat if rental_cat != "land" else "retail",
            area_sqft=valuation_area_sqft,
            limit=10,
        )

        # 2. Determine Achievable Monthly Rent & Strict Provenance Label
        verified_stats = comp_search["segregated_statistics"]["verified_achieved_stats"]
        benchmark_stats = comp_search["segregated_statistics"]["historical_benchmark_stats"]

        if user_monthly_rent > 0.0:
            achievable_rent = user_monthly_rent
            rent_source_type = "User_Verified"
            rent_confidence = 0.92
            rent_justification = "User-supplied executed / verified monthly lease rent."
        elif verified_stats["count"] >= 2 and verified_stats["median_rent_per_sqft"]:
            achievable_rent = round(verified_stats["median_rent_per_sqft"] * valuation_area_sqft, 0)
            rent_source_type = "Recently_Observed_Verified"
            rent_confidence = comp_search["data_confidence_score"]
            rent_justification = (
                f"Median verified lease rate (Rs. {verified_stats['median_rent_per_sqft']}/sqft/mo) "
                f"from {verified_stats['count']} nearby executed rentals."
            )
        elif benchmark_stats["count"] >= 1 and benchmark_stats["median_rent_per_sqft"] and rental_cat == "apartment":
            achievable_rent = round(benchmark_stats["median_rent_per_sqft"] * valuation_area_sqft, 0)
            rent_source_type = "Historical_Regional_Benchmark"
            rent_confidence = max(0.58, comp_search["data_confidence_score"])
            rent_justification = (
                f"Pan-India regional benchmark rate (Rs. {benchmark_stats['median_rent_per_sqft']}/sqft/mo) "
                f"from {benchmark_stats['count']} historical hub observations."
            )
        else:
            # Estimate conservatively from M10 gross yield applied to Sales Comparison value
            derived_yield = market_rates["derived_gross_yield_pct"] / 100.0
            achievable_rent = round((sales_comparison_value * derived_yield) / 12.0, 0)
            rent_source_type = "Estimated_From_Yield"
            rent_confidence = 0.50
            rent_justification = (
                f"Estimated from {market_rates['derived_gross_yield_pct']}% category yield "
                f"({market_rates['justification_source']})."
            )

        # 3. Operating Expenses & Vacancy Parameters
        vacancy_pct = float(property_input.get("vacancy_rate_pct", market_rates["assumed_vacancy_rate_pct"]))
        collection_loss_pct = float(property_input.get("collection_loss_pct", 1.0))
        opex_annual_user = float(property_input.get("operating_expenses_annual", 0.0) or 0.0)
        property_tax_annual = float(property_input.get("property_tax_annual", 0.0) or 0.0)
        maintenance_annual = float(property_input.get("maintenance_annual", 0.0) or 0.0)
        insurance_annual = float(property_input.get("insurance_annual", 0.0) or 0.0)
        mgmt_fee_pct = float(property_input.get("management_fee_pct", 0.0) or 0.0)

        # If user didn't specify operating expenses, derive category-appropriate OpEx allowance
        total_explicit_opex = opex_annual_user + property_tax_annual + maintenance_annual + insurance_annual
        if total_explicit_opex <= 0.0 and achievable_rent > 0.0:
            annual_gpr = achievable_rent * 12.0
            assumed_opex = round(annual_gpr * (market_rates["assumed_opex_ratio_pct"] / 100.0), 0)
            property_tax_annual = round(assumed_opex * 0.25, 0)
            maintenance_annual = round(assumed_opex * 0.65, 0)
            insurance_annual = round(assumed_opex * 0.10, 0)
            opex_source = f"Estimated Indian {rental_cat.replace('_', ' ')} OpEx ratio ({market_rates['assumed_opex_ratio_pct']}% of GPR)"
        else:
            maintenance_annual += opex_annual_user
            opex_source = "User-Specified Annual Operating Expenses"

        cap_rate_pct = float(property_input.get("cap_rate_pct", market_rates["derived_cap_rate_pct"]) or market_rates["derived_cap_rate_pct"])
        cap_rate_pct = max(1.0, min(25.0, cap_rate_pct))
        comparable_grm = float(property_input.get("comparable_grm", market_rates["derived_grm"]) or market_rates["derived_grm"])

        # 4. Run Institutional Cash Flow & Income Valuation Models (Models A-F)
        cash_flow = analyze_rental_cash_flow(
            monthly_rent=achievable_rent,
            property_value=cost_approach_value,
            comparable_cap_rate_pct=cap_rate_pct,
            comparable_grm=comparable_grm,
            vacancy_rate_pct=vacancy_pct,
            collection_loss_pct=collection_loss_pct,
            property_tax_annual=property_tax_annual,
            maintenance_annual=maintenance_annual,
            insurance_annual=insurance_annual,
            management_fee_pct=mgmt_fee_pct,
        )

        noi_annual = cash_flow["annual_noi"]
        if noi_annual > 0:
            income_val_cap = cash_flow["income_valuation_cap_rate"]
            income_val_grm = cash_flow["income_valuation_grm"] or income_val_cap
            income_val_gross_yield = calculate_value_from_gross_yield(
                achievable_rent, market_rates["derived_gross_yield_pct"]
            )
            # Blend Direct Cap (75%) and GRM Cross-Check (25%) for Income Approach estimate
            income_approach_value = round(0.75 * income_val_cap + 0.25 * income_val_grm, 0)
        else:
            income_val_cap = 0.0
            income_val_grm = 0.0
            income_val_gross_yield = 0.0
            income_approach_value = 0.0

        # 5. Forecast & Sensitivity Matrix
        forecast = self.rental_comp_engine.forecast_rental_income(
            current_monthly_rent=achievable_rent,
            property_type=rental_cat,
            vacancy_rate_pct=vacancy_pct,
        )
        sensitivity = (
            run_rental_sensitivity_analysis(
                base_monthly_rent=max(1.0, achievable_rent),
                base_cap_rate_pct=cap_rate_pct,
                vacancy_rate_pct=vacancy_pct,
                collection_loss_pct=collection_loss_pct,
                annual_fixed_opex=property_tax_annual + maintenance_annual + insurance_annual,
                management_fee_pct=mgmt_fee_pct,
            )
            if achievable_rent > 0
            else None
        )

        # 6. Evidence-Based Three-Way Reconciliation
        sales_conf = min(0.95, 0.55 + 0.025 * min(sales_comps_count, 16))
        cost_conf = 0.85 if rental_cat in ("standalone_house", "villa") else 0.78
        income_conf = rent_confidence if income_approach_value > 0 else 0.0

        base_weights = INITIAL_CATEGORY_WEIGHT_HYPOTHESES.get(
            rental_cat, INITIAL_CATEGORY_WEIGHT_HYPOTHESES["apartment"]
        ).copy()

        # Modulate weights dynamically by approach confidence (Evidence-Based Weighting)
        raw_w = {
            "sales": base_weights["sales"] * sales_conf,
            "cost": base_weights["cost"] * cost_conf,
            "income": base_weights["income"] * income_conf if income_approach_value > 0 else 0.0,
        }
        w_sum = sum(raw_w.values()) or 1.0
        norm_weights = {k: round(v / w_sum, 4) for k, v in raw_w.items()}
        # Ensure exact 1.00 sum
        norm_weights["sales"] = round(1.0 - norm_weights["cost"] - norm_weights["income"], 4)

        reconciled_value = round(
            norm_weights["sales"] * sales_comparison_value
            + norm_weights["cost"] * cost_approach_value
            + norm_weights["income"] * income_approach_value,
            0,
        )

        # Divergence & Outlier Detection across the 3 Approaches
        active_vals = [v for v in (sales_comparison_value, cost_approach_value, income_approach_value) if v > 0]
        mean_val = float(np.mean(active_vals))
        max_div_pct = round(((max(active_vals) - min(active_vals)) / max(mean_val, 1.0)) * 100.0, 1) if len(active_vals) > 1 else 0.0
        outlier_warning = max_div_pct > 35.0

        divergence_explanations = self._explain_approach_divergence(
            rental_cat=rental_cat,
            sales_val=sales_comparison_value,
            cost_val=cost_approach_value,
            income_val=income_approach_value,
            gross_yield=cash_flow["gross_rental_yield_pct"] or market_rates["derived_gross_yield_pct"],
            cap_rate=cap_rate_pct,
        )

        return {
            "income_valuation": {
                "achievable_monthly_rent": achievable_rent,
                "achievable_monthly_rent_formatted": format_currency(achievable_rent, currency),
                "annual_gross_rent": cash_flow["annual_gross_rent"],
                "annual_gross_rent_formatted": format_currency(cash_flow["annual_gross_rent"], currency),
                "annual_noi": noi_annual,
                "annual_noi_formatted": format_currency(noi_annual, currency),
                "annual_operating_expenses": cash_flow["annual_operating_expenses"],
                "operating_expense_source": opex_source,
                "vacancy_rate_pct": vacancy_pct,
                "gross_rental_yield_pct": cash_flow["gross_rental_yield_pct"],
                "net_rental_yield_pct": cash_flow["net_rental_yield_pct"],
                "market_cap_rate_pct": cap_rate_pct,
                "comparable_grm": comparable_grm,
                "direct_cap_property_value": income_val_cap,
                "direct_cap_property_value_formatted": format_currency(income_val_cap, currency),
                "grm_property_value": income_val_grm,
                "grm_property_value_formatted": format_currency(income_val_grm, currency),
                "gross_yield_property_value": income_val_gross_yield,
                "income_approach_value": income_approach_value,
                "income_approach_value_formatted": format_currency(income_approach_value, currency),
                "rent_source_category": rent_source_type,
                "rent_justification": rent_justification,
                "rental_confidence_score": rent_confidence,
                "cap_rate_justification": market_rates["justification_source"],
                "cash_flow_summary": cash_flow,
            },
            "three_way_reconciliation": {
                "approaches": {
                    "approach_a_sales_comparison": {
                        "value": round(sales_comparison_value, 0),
                        "value_formatted": format_currency(sales_comparison_value, currency),
                        "confidence": round(sales_conf, 2),
                        "weight_pct": round(norm_weights["sales"] * 100.0, 1),
                    },
                    "approach_b_cost_approach": {
                        "value": round(cost_approach_value, 0),
                        "value_formatted": format_currency(cost_approach_value, currency),
                        "confidence": round(cost_conf, 2),
                        "weight_pct": round(norm_weights["cost"] * 100.0, 1),
                    },
                    "approach_c_income_capitalization": {
                        "value": round(income_approach_value, 0),
                        "value_formatted": format_currency(income_approach_value, currency),
                        "confidence": round(income_conf, 2),
                        "weight_pct": round(norm_weights["income"] * 100.0, 1),
                    },
                },
                "reconciled_fair_market_value": reconciled_value,
                "reconciled_fair_market_value_formatted": format_currency(reconciled_value, currency),
                "weighting_policy": "Evidence-Based Adaptive Weights (Validated per Property Category & Comparable Density)",
                "approach_divergence_pct": max_div_pct,
                "outlier_flag": outlier_warning,
                "divergence_explanations": divergence_explanations,
            },
            "rental_comparables": comp_search,
            "rental_forecast": forecast,
            "sensitivity_analysis": sensitivity,
        }

    def _reconcile_non_income_land(
        self,
        sales_comparison_value: float,
        cost_approach_value: float,
        currency: str,
        sales_comps_count: int,
    ) -> Dict[str, Any]:
        """Reconciliation path when evaluating vacant land with no rental cash flow."""
        sales_conf = min(0.95, 0.55 + 0.025 * min(sales_comps_count, 16))
        cost_conf = 0.80
        w_sales = round((0.65 * sales_conf) / (0.65 * sales_conf + 0.35 * cost_conf), 4)
        w_cost = round(1.0 - w_sales, 4)
        reconciled = round(w_sales * sales_comparison_value + w_cost * cost_approach_value, 0)

        return {
            "income_valuation": {
                "status": "NOT_APPLICABLE_VACANT_LAND",
                "achievable_monthly_rent": 0.0,
                "achievable_monthly_rent_formatted": format_currency(0.0, currency),
                "income_approach_value": 0.0,
                "income_approach_value_formatted": "N/A (Vacant Land)",
                "rent_source_category": "Non_Income_Generating",
                "rent_justification": "Vacant land has zero rental income unless an active commercial/parking lease is supplied.",
                "rental_confidence_score": 0.0,
            },
            "three_way_reconciliation": {
                "approaches": {
                    "approach_a_sales_comparison": {
                        "value": round(sales_comparison_value, 0),
                        "value_formatted": format_currency(sales_comparison_value, currency),
                        "confidence": round(sales_conf, 2),
                        "weight_pct": round(w_sales * 100.0, 1),
                    },
                    "approach_b_cost_approach": {
                        "value": round(cost_approach_value, 0),
                        "value_formatted": format_currency(cost_approach_value, currency),
                        "confidence": round(cost_conf, 2),
                        "weight_pct": round(w_cost * 100.0, 1),
                    },
                    "approach_c_income_capitalization": {
                        "value": 0.0,
                        "value_formatted": "N/A (Vacant Land)",
                        "confidence": 0.0,
                        "weight_pct": 0.0,
                    },
                },
                "reconciled_fair_market_value": reconciled,
                "reconciled_fair_market_value_formatted": format_currency(reconciled, currency),
                "weighting_policy": "Vacant Land Residual & Sales Comparison (0% Income Weight)",
                "approach_divergence_pct": round(
                    abs(sales_comparison_value - cost_approach_value) / max(sales_comparison_value, 1.0) * 100.0, 1
                ),
                "outlier_flag": False,
                "divergence_explanations": [
                    "Vacant land is priced directly by Sales Comparison (M5) and Micro-Market Land Rate (Stage 1); Income Capitalization is omitted."
                ],
            },
            "rental_comparables": {"total_matched": 0, "comparables": []},
            "rental_forecast": None,
            "sensitivity_analysis": None,
        }

    def _explain_approach_divergence(
        self,
        rental_cat: str,
        sales_val: float,
        cost_val: float,
        income_val: float,
        gross_yield: float,
        cap_rate: float,
    ) -> List[str]:
        """Explains economically why Sales, Cost, and Income approaches differ."""
        notes: List[str] = []
        if income_val > 0 and cost_val > 0:
            ratio = income_val / cost_val
            if ratio < 0.85 and rental_cat in ("standalone_house", "villa", "apartment"):
                notes.append(
                    f"In Indian residential markets, capital values price in long-term land appreciation and end-user utility, "
                    f"resulting in compressed rental yields ({gross_yield:.2f}%). Thus Cost/Sales approaches remain higher-weighted than Income Cap ({cap_rate:.2f}%)."
                )
            elif rental_cat in ("office", "retail", "warehouse", "industrial"):
                notes.append(
                    f"Income-producing {rental_cat.replace('_', ' ')} assets are priced primarily by institutional investors on Net Operating Income "
                    f"and Market Cap Rate ({cap_rate:.2f}%), justifying higher evidence weight for Income Capitalization."
                )
        if abs(sales_val - cost_val) / max(cost_val, 1.0) > 0.20:
            notes.append(
                "Sales Comparison vs. Cost Approach divergence reflects micro-market land scarcity premium versus CPWD depreciated structure cost."
            )
        if not notes:
            notes.append("Sales Comparison, Cost Approach, and Income Capitalization align closely within expected local dispersion.")
        return notes
