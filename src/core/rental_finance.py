"""
Core Financial Mathematics for Rental Yield & Income-Based Property Valuation.

Implements standard institutional real estate income valuation models (RICS / USPAP / IVS):
- Model A: Gross Rental Yield
- Model B: Yield-Based Property Valuation
- Model C: Effective Gross Income (EGI) & Net Operating Income (NOI)
- Model D: Capitalization Rate & Direct Capitalization Valuation
- Model E: Gross Rent Multiplier (GRM)
- Model F: Comprehensive Pre-Financing Cash Flow & Sensitivity Analysis

Note: Property-level NOI strictly excludes debt service (EMI/interest), income taxes,
and non-cash depreciation. All rates expressed in percentages (e.g., 8.25 = 8.25%).
"""
import math
from typing import Any, Dict, List, Optional


def _validate_finite_float(value: Optional[float], field_name: str) -> float:
    """Validates that a numeric input is present, convertible to float, and finite."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"Missing or invalid required input: '{field_name}'.")
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Input '{field_name}' must be a valid number, got {value!r}.") from exc
    if not math.isfinite(num):
        raise ValueError(f"Input '{field_name}' must be finite, got {value!r}.")
    return num


def _validate_non_negative(value: Optional[float], field_name: str) -> float:
    """Validates that a numeric input is finite and >= 0."""
    num = _validate_finite_float(value, field_name)
    if num < 0.0:
        raise ValueError(f"Input '{field_name}' cannot be negative (got {num}).")
    return num


def _validate_positive(value: Optional[float], field_name: str) -> float:
    """Validates that a numeric input is finite and strictly > 0."""
    num = _validate_finite_float(value, field_name)
    if num <= 0.0:
        raise ValueError(f"Input '{field_name}' must be strictly positive (got {num}).")
    return num


def _validate_percentage(
    value: Optional[float],
    field_name: str,
    min_pct: float = 0.0,
    max_pct: float = 100.0,
    strict_min: bool = False,
) -> float:
    """Validates a percentage input falls inside [min_pct, max_pct] (or > min_pct if strict)."""
    num = _validate_finite_float(value, field_name)
    if strict_min and num <= min_pct:
        raise ValueError(f"Input '{field_name}' must be > {min_pct}% (got {num}%).")
    if not strict_min and num < min_pct:
        raise ValueError(f"Input '{field_name}' must be >= {min_pct}% (got {num}%).")
    if num > max_pct:
        raise ValueError(f"Input '{field_name}' exceeds realistic maximum {max_pct}% (got {num}%).")
    return num


def calculate_gross_rental_yield(monthly_rent: float, property_value: float) -> float:
    """
    Model A: Gross Rental Yield (%).

    Formula:
        Gross Rental Yield (%) = ((Monthly Rent * 12) / Property Value) * 100
    """
    rent = _validate_non_negative(monthly_rent, "monthly_rent")
    price = _validate_positive(property_value, "property_value")
    annual_rent = rent * 12.0
    return round((annual_rent / price) * 100.0, 4)


def calculate_value_from_gross_yield(
    monthly_rent: float,
    gross_yield_pct: float,
    max_valid_yield_pct: float = 50.0,
) -> float:
    """
    Model B: Rental-Based Property Valuation from comparable Gross Rental Yield.

    Formula:
        Property Value = (Monthly Rent * 12) / (Gross Rental Yield / 100)
    """
    rent = _validate_non_negative(monthly_rent, "monthly_rent")
    yield_pct = _validate_percentage(
        gross_yield_pct,
        "gross_yield_pct",
        min_pct=0.0,
        max_pct=max_valid_yield_pct,
        strict_min=True,
    )
    annual_rent = rent * 12.0
    return round(annual_rent / (yield_pct / 100.0), 2)


def calculate_effective_gross_income(
    monthly_rent: float,
    vacancy_rate_pct: float = 5.0,
    collection_loss_pct: float = 1.0,
    other_income_annual: float = 0.0,
) -> Dict[str, float]:
    """
    Effective Gross Income (EGI) Calculator.

    Formula:
        Gross Potential Rent (GPR) = Monthly Rent * 12
        Vacancy Loss = GPR * (Vacancy Rate / 100)
        Credit/Collection Loss = (GPR - Vacancy Loss) * (Collection Loss Rate / 100)
        EGI = GPR - Vacancy Loss - Collection Loss + Other Annual Income
    """
    rent = _validate_non_negative(monthly_rent, "monthly_rent")
    vac_pct = _validate_percentage(vacancy_rate_pct, "vacancy_rate_pct", 0.0, 100.0)
    coll_pct = _validate_percentage(collection_loss_pct, "collection_loss_pct", 0.0, 100.0)
    other_inc = _validate_non_negative(other_income_annual, "other_income_annual")

    gpr_annual = rent * 12.0
    vacancy_loss_annual = gpr_annual * (vac_pct / 100.0)
    after_vacancy = gpr_annual - vacancy_loss_annual
    collection_loss_annual = after_vacancy * (coll_pct / 100.0)
    egi_annual = after_vacancy - collection_loss_annual + other_inc

    return {
        "gross_potential_rent_annual": round(gpr_annual, 2),
        "vacancy_loss_annual": round(vacancy_loss_annual, 2),
        "collection_loss_annual": round(collection_loss_annual, 2),
        "other_income_annual": round(other_inc, 2),
        "effective_gross_income_annual": round(egi_annual, 2),
        "effective_gross_income_monthly": round(egi_annual / 12.0, 2),
    }


def calculate_net_operating_income(
    monthly_rent: float,
    vacancy_rate_pct: float = 5.0,
    collection_loss_pct: float = 1.0,
    property_tax_annual: float = 0.0,
    maintenance_annual: float = 0.0,
    insurance_annual: float = 0.0,
    utilities_annual: float = 0.0,
    management_fee_pct: float = 0.0,
    other_operating_expenses_annual: float = 0.0,
    other_income_annual: float = 0.0,
) -> Dict[str, Any]:
    """
    Model C: Net Operating Income (NOI) Calculator.

    Formula:
        NOI = Effective Gross Income - Total Operating Expenses

    Strictly excludes financing costs (EMI / loan interest), income tax, and depreciation.
    """
    egi_breakdown = calculate_effective_gross_income(
        monthly_rent=monthly_rent,
        vacancy_rate_pct=vacancy_rate_pct,
        collection_loss_pct=collection_loss_pct,
        other_income_annual=other_income_annual,
    )

    tax = _validate_non_negative(property_tax_annual, "property_tax_annual")
    maint = _validate_non_negative(maintenance_annual, "maintenance_annual")
    ins = _validate_non_negative(insurance_annual, "insurance_annual")
    util = _validate_non_negative(utilities_annual, "utilities_annual")
    mgmt_pct = _validate_percentage(management_fee_pct, "management_fee_pct", 0.0, 50.0)
    other_opex = _validate_non_negative(other_operating_expenses_annual, "other_operating_expenses_annual")

    egi_annual = egi_breakdown["effective_gross_income_annual"]
    management_fee_annual = egi_annual * (mgmt_pct / 100.0)
    total_opex_annual = tax + maint + ins + util + management_fee_annual + other_opex
    noi_annual = egi_annual - total_opex_annual
    oer_pct = (total_opex_annual / egi_annual * 100.0) if egi_annual > 0.0 else (100.0 if total_opex_annual > 0.0 else 0.0)

    return {
        **egi_breakdown,
        "operating_expenses_breakdown": {
            "property_tax_annual": round(tax, 2),
            "maintenance_annual": round(maint, 2),
            "insurance_annual": round(ins, 2),
            "utilities_annual": round(util, 2),
            "management_fee_annual": round(management_fee_annual, 2),
            "other_operating_expenses_annual": round(other_opex, 2),
        },
        "total_operating_expenses_annual": round(total_opex_annual, 2),
        "total_operating_expenses_monthly": round(total_opex_annual / 12.0, 2),
        "operating_expense_ratio_pct": round(oer_pct, 2),
        "noi_annual": round(noi_annual, 2),
        "noi_monthly": round(noi_annual / 12.0, 2),
        "is_negative_noi": noi_annual < 0.0,
    }


def calculate_net_rental_yield(noi_annual: float, property_value: float) -> float:
    """
    Net Rental Yield (%).

    Formula:
        Net Rental Yield (%) = (Annual NOI / Property Value) * 100
    """
    noi = _validate_finite_float(noi_annual, "noi_annual")
    price = _validate_positive(property_value, "property_value")
    return round((noi / price) * 100.0, 4)


def calculate_cap_rate(
    noi_annual: float,
    property_value: float,
    min_realistic_pct: float = 0.0,
    max_realistic_pct: float = 35.0,
) -> float:
    """
    Capitalization Rate (%) derived from comparable transaction NOI and sale price.

    Formula:
        Cap Rate (%) = (Comparable Property Annual NOI / Comparable Sale Price) * 100
    """
    noi = _validate_finite_float(noi_annual, "noi_annual")
    price = _validate_positive(property_value, "property_value")
    cap_rate_pct = (noi / price) * 100.0
    if cap_rate_pct < min_realistic_pct or cap_rate_pct > max_realistic_pct:
        raise ValueError(
            f"Derived capitalization rate ({cap_rate_pct:.2f}%) falls outside realistic bounds "
            f"[{min_realistic_pct}%, {max_realistic_pct}%]."
        )
    return round(cap_rate_pct, 4)


def calculate_direct_capitalization_value(
    noi_annual: float,
    cap_rate_pct: float,
    min_valid_cap_rate_pct: float = 1.0,
    max_valid_cap_rate_pct: float = 25.0,
) -> float:
    """
    Model D: Direct Capitalization Property Valuation.

    Formula:
        Property Value = Annual NOI / (Cap Rate / 100)
    """
    noi = _validate_finite_float(noi_annual, "noi_annual")
    if noi <= 0.0:
        raise ValueError(
            f"Direct capitalization valuation requires strictly positive NOI (got {noi}). "
            "Properties with zero or negative NOI cannot be valued as positive going-concern income assets."
        )
    cap_pct = _validate_percentage(
        cap_rate_pct,
        "cap_rate_pct",
        min_pct=min_valid_cap_rate_pct,
        max_pct=max_valid_cap_rate_pct,
        strict_min=False,
    )
    return round(noi / (cap_pct / 100.0), 2)


def calculate_grm(property_value: float, monthly_rent: float) -> float:
    """
    Model E: Gross Rent Multiplier (GRM).

    Formula:
        GRM = Property Sale Price / Annual Gross Rental Income
    """
    price = _validate_non_negative(property_value, "property_value")
    rent = _validate_positive(monthly_rent, "monthly_rent")
    annual_rent = rent * 12.0
    return round(price / annual_rent, 4)


def calculate_value_from_grm(monthly_rent: float, comparable_grm: float) -> float:
    """
    Model E: Income-Based Cross-Check Valuation using Comparable GRM.

    Formula:
        Property Value = Annual Gross Rental Income * Comparable GRM
    """
    rent = _validate_non_negative(monthly_rent, "monthly_rent")
    grm = _validate_positive(comparable_grm, "comparable_grm")
    if grm > 100.0:
        raise ValueError(f"Unrealistic comparable GRM ({grm}). Expected reasonable multiplier <= 100.")
    return round((rent * 12.0) * grm, 2)


def analyze_rental_cash_flow(
    monthly_rent: float,
    property_value: Optional[float] = None,
    comparable_cap_rate_pct: Optional[float] = None,
    comparable_grm: Optional[float] = None,
    vacancy_rate_pct: float = 5.0,
    collection_loss_pct: float = 1.0,
    property_tax_annual: float = 0.0,
    maintenance_annual: float = 0.0,
    insurance_annual: float = 0.0,
    utilities_annual: float = 0.0,
    management_fee_pct: float = 0.0,
    other_operating_expenses_annual: float = 0.0,
    other_income_annual: float = 0.0,
) -> Dict[str, Any]:
    """
    Model F: Full Rental Cash Flow & Cross-Metric Summary.
    Computes NOI breakdown, gross/net yields, capitalization rate, GRM, and
    implied property values where comparable market yield/cap-rate/GRM are supplied.
    """
    noi_res = calculate_net_operating_income(
        monthly_rent=monthly_rent,
        vacancy_rate_pct=vacancy_rate_pct,
        collection_loss_pct=collection_loss_pct,
        property_tax_annual=property_tax_annual,
        maintenance_annual=maintenance_annual,
        insurance_annual=insurance_annual,
        utilities_annual=utilities_annual,
        management_fee_pct=management_fee_pct,
        other_operating_expenses_annual=other_operating_expenses_annual,
        other_income_annual=other_income_annual,
    )

    noi_annual = noi_res["noi_annual"]
    gross_annual_rent = noi_res["gross_potential_rent_annual"]

    metrics: Dict[str, Any] = {
        "monthly_gross_rent": round(float(monthly_rent), 2),
        "annual_gross_rent": gross_annual_rent,
        "monthly_operating_expenses": noi_res["total_operating_expenses_monthly"],
        "annual_operating_expenses": noi_res["total_operating_expenses_annual"],
        "monthly_noi": noi_res["noi_monthly"],
        "annual_noi": noi_annual,
        "annual_cash_flow_before_financing": noi_annual,
        "operating_expense_ratio_pct": noi_res["operating_expense_ratio_pct"],
        "is_negative_noi": noi_res["is_negative_noi"],
        "gross_rental_yield_pct": None,
        "net_rental_yield_pct": None,
        "implied_cap_rate_pct": None,
        "implied_grm": None,
        "income_valuation_cap_rate": None,
        "income_valuation_grm": None,
        "noi_breakdown": noi_res,
    }

    if property_value is not None:
        price = _validate_positive(property_value, "property_value")
        metrics["gross_rental_yield_pct"] = calculate_gross_rental_yield(monthly_rent, price)
        metrics["net_rental_yield_pct"] = calculate_net_rental_yield(noi_annual, price)
        metrics["implied_cap_rate_pct"] = metrics["net_rental_yield_pct"]
        if monthly_rent > 0:
            metrics["implied_grm"] = calculate_grm(price, monthly_rent)

    if comparable_cap_rate_pct is not None and noi_annual > 0.0:
        metrics["income_valuation_cap_rate"] = calculate_direct_capitalization_value(
            noi_annual, comparable_cap_rate_pct
        )

    if comparable_grm is not None and monthly_rent > 0.0:
        metrics["income_valuation_grm"] = calculate_value_from_grm(monthly_rent, comparable_grm)

    return metrics


def run_rental_sensitivity_analysis(
    base_monthly_rent: float,
    base_cap_rate_pct: float,
    vacancy_rate_pct: float = 5.0,
    collection_loss_pct: float = 1.0,
    annual_fixed_opex: float = 0.0,
    management_fee_pct: float = 0.0,
    rent_pct_shifts: Optional[List[float]] = None,
    cap_rate_bps_shifts: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Evaluates valuation & NOI sensitivity across Rent shifts and Cap Rate shifts.
    cap_rate_bps_shifts expressed in percentage points (e.g., [-1.0, -0.5, 0.0, +0.5, +1.0]).
    """
    base_rent = _validate_positive(base_monthly_rent, "base_monthly_rent")
    base_cap = _validate_percentage(base_cap_rate_pct, "base_cap_rate_pct", 1.0, 25.0)
    fixed_opex = _validate_non_negative(annual_fixed_opex, "annual_fixed_opex")

    rent_shifts = rent_pct_shifts or [-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0]
    cap_shifts = cap_rate_bps_shifts or [-1.0, -0.5, 0.0, 0.5, 1.0]

    matrix: List[Dict[str, Any]] = []
    for r_delta in rent_shifts:
        sim_rent = base_rent * (1.0 + r_delta / 100.0)
        noi_info = calculate_net_operating_income(
            monthly_rent=sim_rent,
            vacancy_rate_pct=vacancy_rate_pct,
            collection_loss_pct=collection_loss_pct,
            other_operating_expenses_annual=fixed_opex,
            management_fee_pct=management_fee_pct,
        )
        sim_noi = noi_info["noi_annual"]

        cap_row = {}
        for c_delta in cap_shifts:
            sim_cap = round(base_cap + c_delta, 2)
            key = f"cap_{sim_cap:.2f}%"
            if sim_noi <= 0 or sim_cap < 1.0 or sim_cap > 25.0:
                cap_row[key] = None
            else:
                cap_row[key] = calculate_direct_capitalization_value(sim_noi, sim_cap)

        matrix.append({
            "rent_shift_pct": r_delta,
            "simulated_monthly_rent": round(sim_rent, 2),
            "simulated_annual_noi": sim_noi,
            "valuations_by_cap_rate": cap_row,
        })

    # Vacancy sensitivity at base rent and base cap rate
    vacancy_scenarios = []
    for vac in [0.0, 2.5, 5.0, 10.0, 15.0, 20.0]:
        noi_v = calculate_net_operating_income(
            monthly_rent=base_rent,
            vacancy_rate_pct=vac,
            collection_loss_pct=collection_loss_pct,
            other_operating_expenses_annual=fixed_opex,
            management_fee_pct=management_fee_pct,
        )
        val_v = None
        if noi_v["noi_annual"] > 0:
            val_v = calculate_direct_capitalization_value(noi_v["noi_annual"], base_cap)
        vacancy_scenarios.append({
            "vacancy_rate_pct": vac,
            "annual_noi": noi_v["noi_annual"],
            "estimated_value": val_v,
        })

    return {
        "base_monthly_rent": base_rent,
        "base_cap_rate_pct": base_cap,
        "rent_vs_cap_rate_matrix": matrix,
        "vacancy_sensitivity": vacancy_scenarios,
    }
