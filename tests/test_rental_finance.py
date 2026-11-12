"""
Comprehensive Unit Tests for Milestone 1: Core Financial Mathematics (src/core/rental_finance.py).
Covers normal Indian market benchmarks, zero/negative values, missing inputs, invalid yields,
unrealistic cap rates, negative NOI distress, cash flow summaries, and sensitivity analysis.
"""
import math
import pytest
from src.core.rental_finance import (
    calculate_gross_rental_yield,
    calculate_value_from_gross_yield,
    calculate_effective_gross_income,
    calculate_net_operating_income,
    calculate_net_rental_yield,
    calculate_cap_rate,
    calculate_direct_capitalization_value,
    calculate_grm,
    calculate_value_from_grm,
    analyze_rental_cash_flow,
    run_rental_sensitivity_analysis,
)


def test_gross_rental_yield_normal():
    # Patia, Bhubaneswar 3BHK example: Rs. 22,000/mo rent on Rs. 75,00,000 property
    gross_yield = calculate_gross_rental_yield(monthly_rent=22000.0, property_value=7500000.0)
    assert gross_yield == pytest.approx(3.52, abs=1e-4)

    # Commercial office example: Rs. 1,00,000/mo on Rs. 1.5 Cr
    com_yield = calculate_gross_rental_yield(monthly_rent=100000.0, property_value=15000000.0)
    assert com_yield == pytest.approx(8.0, abs=1e-4)


def test_value_from_gross_yield():
    # Rent Rs. 22,000/mo, market yield 3.52% -> Rs. 75,00,000
    val = calculate_value_from_gross_yield(monthly_rent=22000.0, gross_yield_pct=3.52)
    assert val == pytest.approx(7500000.0, abs=1.0)


def test_effective_gross_income():
    # GPR = 12,00,000, Vacancy 5% = 60,000, after vac = 11,40,000
    # Collection loss 2% of 11,40,000 = 22,800 -> EGI = 11,17,200 + 10,000 other = 11,27,200
    res = calculate_effective_gross_income(
        monthly_rent=100000.0,
        vacancy_rate_pct=5.0,
        collection_loss_pct=2.0,
        other_income_annual=10000.0,
    )
    assert res["gross_potential_rent_annual"] == 1200000.0
    assert res["vacancy_loss_annual"] == 60000.0
    assert res["collection_loss_annual"] == 22800.0
    assert res["effective_gross_income_annual"] == 1127200.0


def test_noi_calculation_chandrasekharpur_office():
    # Office rent Rs. 1,00,000/mo (GPR 12,00,000)
    # 5% vacancy -> EGI 11,40,000 (0% collection loss)
    # OpEx: tax 40k, maint 100k, ins 15k, util 25k -> total 180k
    # NOI = 11,40,000 - 1,80,000 = 9,60,000
    res = calculate_net_operating_income(
        monthly_rent=100000.0,
        vacancy_rate_pct=5.0,
        collection_loss_pct=0.0,
        property_tax_annual=40000.0,
        maintenance_annual=100000.0,
        insurance_annual=15000.0,
        utilities_annual=25000.0,
    )
    assert res["effective_gross_income_annual"] == 1140000.0
    assert res["total_operating_expenses_annual"] == 180000.0
    assert res["noi_annual"] == 960000.0
    assert res["noi_monthly"] == 80000.0
    assert res["is_negative_noi"] is False


def test_noi_management_fee_pct():
    # EGI = 1,00,000 * 12 * 0.95 = 11,40,000; 5% management fee = 57,000
    res = calculate_net_operating_income(
        monthly_rent=100000.0,
        vacancy_rate_pct=5.0,
        collection_loss_pct=0.0,
        management_fee_pct=5.0,
    )
    assert res["operating_expenses_breakdown"]["management_fee_annual"] == 57000.0
    assert res["noi_annual"] == 1083000.0


def test_cap_rate_and_direct_capitalization():
    # Derived Cap Rate = 9,60,000 / 1,16,36,364 = 8.25%
    cap = calculate_cap_rate(noi_annual=960000.0, property_value=11636363.64)
    assert cap == pytest.approx(8.25, abs=1e-2)

    # Direct Cap Valuation: 9,60,000 / 0.0825 = 1,16,36,363.64
    val = calculate_direct_capitalization_value(noi_annual=960000.0, cap_rate_pct=8.25)
    assert val == pytest.approx(11636363.64, abs=1.0)

    # Net yield matches cap rate on unlevered purchase
    net_y = calculate_net_rental_yield(noi_annual=960000.0, property_value=11636363.64)
    assert net_y == pytest.approx(8.25, abs=1e-2)


def test_grm_calculations():
    # Price 75,00,000 / (25,000 * 12 = 3,00,000) -> GRM = 25.0
    grm = calculate_grm(property_value=7500000.0, monthly_rent=25000.0)
    assert grm == 25.0

    # Value from comparable GRM = 25.0 * 3,00,000 = 75,00,000
    val = calculate_value_from_grm(monthly_rent=25000.0, comparable_grm=25.0)
    assert val == 7500000.0


def test_zero_rental_income():
    # Zero rent produces 0% yield and 0 EGI, not crash
    assert calculate_gross_rental_yield(monthly_rent=0.0, property_value=5000000.0) == 0.0
    egi = calculate_effective_gross_income(monthly_rent=0.0, vacancy_rate_pct=5.0)
    assert egi["effective_gross_income_annual"] == 0.0

    # Zero rent cannot compute GRM (division by zero) -> ValueError
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_grm(property_value=5000000.0, monthly_rent=0.0)


def test_negative_operating_income_handling():
    # Rent is 10,000/mo (1,20,000/yr), OpEx is 2,00,000/yr -> Negative NOI
    res = calculate_net_operating_income(
        monthly_rent=10000.0,
        vacancy_rate_pct=10.0,
        collection_loss_pct=0.0,
        maintenance_annual=150000.0,
        property_tax_annual=50000.0,
    )
    assert res["noi_annual"] == 108000.0 - 200000.0
    assert res["noi_annual"] == -92000.0
    assert res["is_negative_noi"] is True

    # Negative NOI cannot be valued as positive going-concern via Cap Rate
    with pytest.raises(ValueError, match="strictly positive NOI"):
        calculate_direct_capitalization_value(noi_annual=res["noi_annual"], cap_rate_pct=8.0)


def test_invalid_inputs_and_edge_cases():
    # Missing (None) inputs
    with pytest.raises(ValueError, match="Missing or invalid"):
        calculate_gross_rental_yield(monthly_rent=None, property_value=5000000.0)

    # NaN / Inf inputs
    with pytest.raises(ValueError, match="must be finite"):
        calculate_gross_rental_yield(monthly_rent=float("nan"), property_value=5000000.0)
    with pytest.raises(ValueError, match="must be finite"):
        calculate_net_operating_income(monthly_rent=float("inf"))

    # Negative prices / rents / expenses
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_gross_rental_yield(monthly_rent=-5000.0, property_value=5000000.0)
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_gross_rental_yield(monthly_rent=20000.0, property_value=0.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_net_operating_income(monthly_rent=20000.0, maintenance_annual=-1000.0)

    # Unrealistic yields and cap rates
    with pytest.raises(ValueError, match="must be > 0.0%"):
        calculate_value_from_gross_yield(monthly_rent=20000.0, gross_yield_pct=0.0)
    with pytest.raises(ValueError, match="exceeds realistic maximum"):
        calculate_value_from_gross_yield(monthly_rent=20000.0, gross_yield_pct=85.0)

    with pytest.raises(ValueError, match="must be >= 1.0%"):
        calculate_direct_capitalization_value(noi_annual=500000.0, cap_rate_pct=0.2)
    with pytest.raises(ValueError, match="exceeds realistic maximum"):
        calculate_direct_capitalization_value(noi_annual=500000.0, cap_rate_pct=45.0)
    with pytest.raises(ValueError, match="outside realistic bounds"):
        calculate_cap_rate(noi_annual=900000.0, property_value=1000000.0)  # 90% cap rate


def test_analyze_rental_cash_flow_summary():
    cf = analyze_rental_cash_flow(
        monthly_rent=100000.0,
        property_value=12000000.0,
        comparable_cap_rate_pct=8.0,
        comparable_grm=10.5,
        vacancy_rate_pct=5.0,
        collection_loss_pct=0.0,
        property_tax_annual=60000.0,
        maintenance_annual=120000.0,
    )
    assert cf["annual_gross_rent"] == 1200000.0
    assert cf["annual_noi"] == 960000.0
    assert cf["gross_rental_yield_pct"] == 10.0
    assert cf["net_rental_yield_pct"] == 8.0
    assert cf["implied_grm"] == 10.0
    assert cf["income_valuation_cap_rate"] == 12000000.0
    assert cf["income_valuation_grm"] == 12600000.0


def test_sensitivity_analysis():
    sens = run_rental_sensitivity_analysis(
        base_monthly_rent=100000.0,
        base_cap_rate_pct=8.0,
        vacancy_rate_pct=5.0,
        collection_loss_pct=0.0,
        annual_fixed_opex=180000.0,
    )
    rows = sens["rent_vs_cap_rate_matrix"]
    assert len(rows) == 7
    # Find 0% rent shift row
    base_row = [r for r in rows if r["rent_shift_pct"] == 0.0][0]
    assert base_row["simulated_annual_noi"] == 960000.0
    assert base_row["valuations_by_cap_rate"]["cap_8.00%"] == 12000000.0
    # Lower cap rate (7.00%) increases value; higher cap rate (9.00%) decreases value
    assert base_row["valuations_by_cap_rate"]["cap_7.00%"] > 12000000.0
    assert base_row["valuations_by_cap_rate"]["cap_9.00%"] < 12000000.0
    assert len(sens["vacancy_sensitivity"]) == 6
