"""
Global Property Valuation Engine & Ensemble Orchestrator.
Combines predictions from the 10 Specialist AI Models, applies cohort calibration,
evaluates prediction intervals (Low, Mid, High), computes multi-horizon forecast scenarios,
and generates SHAP-based factor contributions.
"""
from typing import Dict, Any, List, Optional
import numpy as np

from src.services.specialist_models import (
    TransactionIntelligenceAI,
    GovernmentCadastralAI,
    SatelliteBuildingIntelligenceAI,
    GeospatialConnectivityAI,
    TrafficMobilityAI,
    PopulationDemographicAI,
    RealEstateMarketAI,
    PhysicalPropertyAI,
    FutureDevelopmentAI,
    RentalInvestmentAI,
)
from src.services.missing_detection import MissingFeatureDetectionService
from src.services.valuation_reconciliation import ThreeWayValuationReconciler
from src.services.evidence_confidence import EvidenceConfidenceService
from src.core.ground_truth_db import GroundTruthTransaction, ValidationEvaluationRun, init_ground_truth_db
from src.core.rental_db import SessionLocal
from src.core.units import convert_sqm_to_local, format_currency
from src.core.construction_cost import ConstructionCostEngine
from src.services.location_intelligence import haversine_km


class GlobalPropertyValuationEngine:
    """
    Orchestrates the 10 Specialist Models, computes the calibrated anchor ensemble,
    evaluates prediction intervals, and derives forward scenarios.
    """

    def __init__(self):
        init_ground_truth_db()
        self.m01_transaction = TransactionIntelligenceAI()
        self.m02_cadastral = GovernmentCadastralAI()
        self.m03_satellite = SatelliteBuildingIntelligenceAI()
        self.m04_connectivity = GeospatialConnectivityAI()
        self.m05_traffic = TrafficMobilityAI()
        self.m06_population = PopulationDemographicAI()
        self.m07_market = RealEstateMarketAI()
        self.m08_physical = PhysicalPropertyAI()
        self.m09_future = FutureDevelopmentAI()
        self.m10_rental = RentalInvestmentAI()
        self.missing_service = MissingFeatureDetectionService()
        self.cost_engine = ConstructionCostEngine()
        self.reconciler = ThreeWayValuationReconciler()
        self.evidence_service = EvidenceConfidenceService()

    def evaluate_property(
        self,
        property_input: Dict[str, Any],
        location_intelligence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executes full valuation workflow:
        1. Feature collation & missing-data audit.
        2. Specialist model predictions.
        3. Calibrated anchor blending.
        4. Prediction interval and horizon forecasting.
        5. Explainability drivers.
        """
        # Flatten raw harvested values into feature dictionary
        features = {}
        intel = location_intelligence.get("intelligence", {})
        for domain, signals in intel.items():
            for k, meta in signals.items():
                if isinstance(meta, dict) and "value" in meta:
                    features[k] = meta["value"]

        # Merge user confirmed inputs
        features.update(property_input)

        asset_type = str(property_input.get("asset_type", "residential")).lower().strip()
        country_code = str(location_intelligence.get("metadata", {}).get("country_code", "IN")).upper()
        currency = str(location_intelligence.get("metadata", {}).get("currency", "INR")).upper()

        # Step 1: Missing Feature Detection & Imputation
        audit_res = self.missing_service.audit_and_impute(features, asset_type=asset_type)
        if not audit_res["is_valid_for_valuation"]:
            return {
                "status": "error",
                "error_type": "MISSING_ESSENTIAL_INFORMATION",
                "message": f"Please provide required details: {audit_res['missing_essential_user_fields']}",
                "audit": audit_res,
            }

        imp_feat = audit_res["imputed_features"]

        # Step 2: Determine Area Basis (sqm and sqft)
        is_land = asset_type == "land"
        valuation_area_sqm = float(imp_feat.get("land_area_sqm" if is_land else "built_area_sqm", 100.0))
        valuation_area_sqft = convert_sqm_to_local(valuation_area_sqm, "sqft")

        # Step 3: Run Specialist Models
        # M01: Primary Anchor from Comparable Sales
        res_01 = self.m01_transaction.predict(imp_feat)
        if res_01["status"] == "active":
            raw_anchor = res_01["predicted_price_sqm"]
        else:
            raw_anchor = float(imp_feat.get("comparable_median_price_sqm_500m_12m", 180000.0))

        # Asset-Type Cohort Pricing Multiplier
        if asset_type == "commercial":
            com_type = str(property_input.get("commercial_type", imp_feat.get("commercial_type", "retail"))).lower()
            if "retail" in com_type or "shop" in com_type:
                anchor_price_sqm = raw_anchor * 1.85
            elif "warehouse" in com_type or "industrial" in com_type:
                anchor_price_sqm = raw_anchor * 0.72
            else:  # office
                anchor_price_sqm = raw_anchor * 1.28
        elif asset_type == "land":
            anchor_price_sqm = raw_anchor * 0.42
        else:
            anchor_price_sqm = raw_anchor

        # Run domain specialists
        res_02 = self.m02_cadastral.predict(imp_feat, anchor_price_sqm)
        res_03 = self.m03_satellite.predict(imp_feat, anchor_price_sqm)
        res_04 = self.m04_connectivity.predict(imp_feat, anchor_price_sqm)
        res_05 = self.m05_traffic.predict(imp_feat, anchor_price_sqm, asset_type=asset_type)
        res_06 = self.m06_population.predict(imp_feat, anchor_price_sqm)
        res_07 = self.m07_market.predict(imp_feat, anchor_price_sqm)
        res_08 = self.m08_physical.predict(imp_feat, anchor_price_sqm)
        res_09 = self.m09_future.predict(imp_feat, anchor_price_sqm)

        # Step 4: Calibrated Ensemble Blending
        # Transaction comps are primary anchor (40%), Physical (20%), Connectivity & Traffic (15%),
        # Market & Cadastral (15%), Satellite & Demographics (10%).
        weights = {
            "m01": 0.40,
            "m08": 0.20,
            "m04": 0.10,
            "m05": 0.08,
            "m07": 0.08,
            "m02": 0.06,
            "m09": 0.04,
            "m03": 0.02,
            "m06": 0.02,
        }

        ensemble_price_sqm = (
            weights["m01"] * res_01.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m08"] * res_08.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m04"] * res_04.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m05"] * res_05.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m07"] * res_07.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m02"] * res_02.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m09"] * res_09.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m03"] * res_03.get("predicted_price_sqm", anchor_price_sqm) +
            weights["m06"] * res_06.get("predicted_price_sqm", anchor_price_sqm)
        )

        # =========================================================================
        # THREE-STAGE VALUATION METHODOLOGY & 28-CRITERIA PRIORITIZATION ENGINE
        # =========================================================================

        # Extract Property & Market Driver Parameters
        loc_rating = str(property_input.get("locality_tier", "prime")).lower()
        road_width = str(property_input.get("road_width_ft", "30ft")).lower()
        corner_flag = str(property_input.get("corner_plot", "standard")).lower()
        furnishing = str(property_input.get("furnishing", "semi_furnished")).lower()
        parking = str(property_input.get("parking_slots", "1_covered")).lower()
        approval = str(property_input.get("approval_status", "approved_freehold")).lower()
        maintenance = str(property_input.get("maintenance_state", "well_maintained")).lower()

        # Environmental & Risk Gate Parameters
        flood_risk = str(property_input.get("flood_risk", "none_low")).lower()
        drainage_infra = str(property_input.get("drainage_infra", "underground_storm")).lower()
        groundwater = str(property_input.get("groundwater_availability", "abundant")).lower()
        litigation = str(property_input.get("litigation_risk", "clear_verified")).lower()

        structure_type = str(property_input.get("structure_type", "apartment")).lower().strip()
        plot_area_sqft = float(property_input.get("plot_area_sqft", 0.0) or 0.0)
        is_standalone = structure_type in ["standalone_house", "independent_house", "villa", "bungalow"]

        # Base land market rate & Government Circle Rate from regional intelligence
        meta_land_rate = float(location_intelligence.get("metadata", {}).get("land_rate_sqft", 0.0))
        meta_circle_rate = float(location_intelligence.get("metadata", {}).get("circle_rate_sqft", 0.0))

        if meta_land_rate > 0:
            base_land_rate_sqft = meta_land_rate
        else:
            base_land_rate_sqft = 4500.0 if currency == "INR" else 450.0

        if meta_circle_rate > 0:
            circle_rate_sqft = meta_circle_rate
        else:
            circle_rate_sqft = round(base_land_rate_sqft * 0.60, 0)

        # -------------------------------------------------------------------------
        # STAGE 1: LAND MARKET VALUATION: V_L = A_L * R_L
        # -------------------------------------------------------------------------
        # L3: Road width uplift
        road_pct = {"40ft_plus": 0.10, "30ft": 0.05, "20ft": 0.0, "15ft_narrow": -0.08}.get(road_width, 0.0)
        # L4: Frontage & orientation uplift
        corner_pct = 0.09 if ("corner" in corner_flag or "park" in corner_flag) else 0.0
        # L1: Locality tier uplift
        loc_pct = {"prime": 0.16, "developing": 0.08, "standard": 0.0, "outskirts": -0.10}.get(loc_rating, 0.0)
        # L6/L7/L8/L9/L10: Smooth Radial Proximity Uplift (0-1km Peak -> 5km High -> 10-15km Corridor Convenience)
        uplift_bd = res_04.get("uplift_breakdown", {})
        dist_metro = float(res_04.get("distance_metro_km", 2.5))
        dist_bus = float(res_04.get("distance_bus_stand_km", dist_metro))
        dist_rail = float(res_04.get("distance_rail_km", 4.0))
        dist_school = float(res_04.get("distance_school_km", 2.0))
        dist_hospital = float(res_04.get("distance_hospital_km", 2.5))
        dist_airport = float(res_04.get("distance_airport_km", 6.0))
        dist_cbd = float(res_04.get("distance_it_hub_km", location_intelligence.get("metadata", {}).get("distance_cbd_km", 10.0)))

        transit_pct = round(
            (float(uplift_bd.get("bus_and_transit_pct", 0.0)) + float(uplift_bd.get("railway_pct", 0.0))) / 100.0, 4
        )
        it_pct = round(float(uplift_bd.get("it_hub_cbd_pct", 0.0)) / 100.0, 4)
        social_infra_pct = round(
            (
                float(uplift_bd.get("school_pct", 0.0))
                + float(uplift_bd.get("hospital_pct", 0.0))
                + float(uplift_bd.get("airport_pct", 0.0))
            ) / 100.0,
            4,
        )
        # L14: Upcoming Government Projects
        govt_pct = 0.04 if res_09.get("project_status_code") == "UNDER_CONSTRUCTION" else 0.02
        # L12: Road Traffic High-Demand Merit (More traffic = higher demand & corridor activity)
        traffic_demand_pct = min(0.08, max(0.0, float(res_05.get("traffic_demand_multiplier", 1.0)) - 1.0))

        # Priority Zone Check (Backend Green Medical Zone & Yellow Rail/Metro/Bus/Edu/Work Zone)
        from src.services.location_zones import LocationZoneEngine

        zone_analysis = location_intelligence.get("zone_analysis")
        if not zone_analysis:
            lat_z = float(location_intelligence.get("metadata", {}).get("latitude", 20.2961))
            lon_z = float(location_intelligence.get("metadata", {}).get("longitude", 85.8245))
            zone_analysis = LocationZoneEngine.evaluate_zones_for_point(
                lat_z,
                lon_z,
                distance_hints={
                    "distance_hospital_km": dist_hospital,
                    "distance_rail_km": dist_rail,
                    "distance_metro_km": dist_metro,
                    "distance_bus_stand_km": dist_bus,
                    "distance_school_km": dist_school,
                    "distance_it_hub_km": dist_cbd,
                },
            )
        zone_land_uplift_pct = (
            float(zone_analysis.get("total_zone_land_uplift_pct", 0.0)) / 100.0
            if zone_analysis.get("in_any_zone")
            else 0.0
        )

        # Land Rate Modulator
        total_land_mod_pct = (
            loc_pct
            + road_pct
            + corner_pct
            + transit_pct
            + it_pct
            + social_infra_pct
            + govt_pct
            + traffic_demand_pct
            + zone_land_uplift_pct
        )
        market_land_rate_sqft = round(base_land_rate_sqft * (1.0 + total_land_mod_pct), 0)
        # Regulatory floor check: market rate shouldn't be under circle rate in normal transactions
        market_land_rate_sqft = max(market_land_rate_sqft, circle_rate_sqft)

        # Land Area Allocation (A_L):
        # Crucial: For Standalone House, 100% exclusive plot area.
        # For Apartments: Only Undivided Share of Land (UDS ~28% of built-up area) - NO double counting!
        if is_standalone:
            effective_plot_sqft = plot_area_sqft if plot_area_sqft > 0 else round(valuation_area_sqft * 1.25, 0)
            stage1_land_market_value = round(effective_plot_sqft * market_land_rate_sqft, 0)
            land_desc = f"Exclusive Plot Area: {effective_plot_sqft:,.0f} sq ft @ {currency} {market_land_rate_sqft:,.0f}/sq ft"
        elif asset_type == "land":
            effective_plot_sqft = valuation_area_sqft
            stage1_land_market_value = round(effective_plot_sqft * market_land_rate_sqft, 0)
            land_desc = f"Total Land Plot: {effective_plot_sqft:,.0f} sq ft @ {currency} {market_land_rate_sqft:,.0f}/sq ft"
        else:
            # High-rise apartment unit: Attributed Undivided Share of Land (UDS)
            effective_plot_sqft = round(valuation_area_sqft * 0.28, 1)
            stage1_land_market_value = round(effective_plot_sqft * market_land_rate_sqft, 0)
            land_desc = f"Attributed Land Share: {effective_plot_sqft:,.1f} sq ft UDS @ {currency} {market_land_rate_sqft:,.0f}/sq ft"

        # -------------------------------------------------------------------------
        # STAGE 2: DEPRECIATED BUILDING REPLACEMENT COST: V_B = A_B * C_B * (1 - D)
        # -------------------------------------------------------------------------
        prop_age = max(0.0, float(imp_feat.get("property_age_years", 5.0)))
        const_grade = str(imp_feat.get("construction_quality_code", "GRADE_B")).upper()

        cost_analysis = self.cost_engine.compute_cost_breakdown(
            built_area_sqft=valuation_area_sqft,
            structure_type=structure_type,
            property_age_years=prop_age,
            construction_grade=const_grade,
            plot_area_sqft=plot_area_sqft,
            current_land_rate_sqft=market_land_rate_sqft,
        )

        # Base replacement rate per sqft today from CPWD
        rate_today_sqft = cost_analysis["rate_today_per_sqft"]
        replacement_cost_new = round(valuation_area_sqft * rate_today_sqft, 0)

        # S5 & M4: Depreciation with maintenance condition
        raw_deprec = min(0.65, (prop_age / 60.0) * 0.90)
        maint_deprec_factor = {"recently_renovated": 0.65, "well_maintained": 1.0, "average": 1.15}.get(maintenance, 1.0)
        effective_deprec_pct = min(0.70, raw_deprec * maint_deprec_factor)
        depreciated_structure_value = round(replacement_cost_new * (1.0 - effective_deprec_pct), 0)

        # M2: Interior Fit-out & Woodwork
        furnish_add_per_sqft = 0.0
        if "fully" in furnishing:
            furnish_add_per_sqft = 1200.0 if currency == "INR" else 120.0
        elif "semi" in furnishing:
            furnish_add_per_sqft = 650.0 if currency == "INR" else 65.0
        house_fitout_cost = round(furnish_add_per_sqft * valuation_area_sqft, 0)

        # M3: Dedicated Car Parking Slot Value
        house_parking_cost = 0.0
        if "2" in parking:
            house_parking_cost = 800000.0 if currency == "INR" else 15000.0
        elif "1" in parking or "covered" in parking:
            house_parking_cost = 450000.0 if currency == "INR" else 8000.0

        if asset_type == "land":
            stage2_building_cost = 0.0
            replacement_cost_new = 0.0
            depreciated_structure_value = 0.0
            house_fitout_cost = 0.0
            house_parking_cost = 0.0
        else:
            stage2_building_cost = round(depreciated_structure_value + house_fitout_cost + house_parking_cost, 0)

        # -------------------------------------------------------------------------
        # STAGE 3: MARKET RECONCILIATION & RISK GATES (M1 & ENVIRONMENTAL)
        # -------------------------------------------------------------------------
        unadjusted_valuation = stage1_land_market_value + stage2_building_cost

        # M1: Legal Status & Title Risk Gate (Eligibility Gate)
        is_legal_approved = ("approved" in approval or "freehold" in approval)
        if is_legal_approved:
            legal_risk_pct = 0.06  # Approved BDA/RERA freehold liquidity premium
            bank_loan_eligible = True
            legal_status_desc = "Clear Freehold Title with BDA / Municipal / RERA Approved Layout"
        else:
            legal_risk_pct = -0.28  # 28% unapproved Gram Panchayat / unregularized layout risk discount
            bank_loan_eligible = False
            legal_status_desc = "Unapproved / Revenue / Gram Panchayat Layout (Bank Financing Restricted)"

        # Environmental & Geotechnical Risk Gate
        flood_pct = {"none_low": 0.0, "moderate_waterlogging": -0.06, "high_flood_zone": -0.14}.get(flood_risk, 0.0)
        drainage_pct = {"underground_storm": 0.0, "open_drain": -0.04, "poor_waterlogging": -0.08}.get(drainage_infra, 0.0)
        groundwater_pct = {"abundant": 0.0, "moderate": 0.0, "deep_boring_scarce": -0.03}.get(groundwater, 0.0)
        litigation_pct = -0.35 if "disputed" in litigation else 0.0

        total_env_risk_pct = flood_pct + drainage_pct + groundwater_pct + litigation_pct
        total_risk_gate_mult = (1.0 + legal_risk_pct) * (1.0 + total_env_risk_pct)

        # Approach B: Cost Approach Value (Stage 1 Land + Stage 2 Depreciated Building * Risk Gates)
        cost_approach_value = round(unadjusted_valuation * total_risk_gate_mult, 0)

        # Run M10: Rental & Investment baseline
        res_10 = self.m10_rental.predict(imp_feat, ensemble_price_sqm)

        # Approach A: Sales Comparison Value (respecting exclusive land plot value for standalone houses)
        raw_sales_comp = round(ensemble_price_sqm * valuation_area_sqm * total_risk_gate_mult, 0)
        if is_standalone:
            sales_comp_total = max(raw_sales_comp, round(cost_approach_value * 0.94, 0))
        else:
            sales_comp_total = raw_sales_comp

        # Stage 4: Income Capitalization & Three-Way Evidence-Based Reconciliation
        lat_coord = float(location_intelligence.get("metadata", {}).get("latitude", 20.2961))
        lon_coord = float(location_intelligence.get("metadata", {}).get("longitude", 85.8245))
        reconciliation_bundle = self.reconciler.evaluate_income_and_reconcile(
            latitude=lat_coord,
            longitude=lon_coord,
            asset_type=asset_type,
            structure_type=structure_type,
            commercial_type=str(property_input.get("commercial_type", "retail")),
            valuation_area_sqft=valuation_area_sqft,
            currency=currency,
            sales_comparison_value=sales_comp_total,
            cost_approach_value=cost_approach_value,
            m10_prediction=res_10,
            property_input=property_input,
            sales_comps_count=int(res_01.get("comparable_sales_count", 10)),
        )

        # Final Reconciled Fair Market Value incorporates Rental / Income Calculation for Residential & Commercial
        reconciled_val = float(
            reconciliation_bundle["three_way_reconciliation"].get("reconciled_fair_market_value", cost_approach_value)
        )
        if asset_type in ("residential", "commercial") and reconciled_val > 0.0:
            total_fair_market_value = round(reconciled_val, 0)
        else:
            total_fair_market_value = cost_approach_value

        price_per_sqft = round(total_fair_market_value / max(valuation_area_sqft, 1.0), 2)
        adjusted_price_sqm = round(price_per_sqft * 10.7639, 2)

        # 90% Model-Spread Range (non-calibrated spread indicator)
        model_estimates = [
            res_01.get("predicted_price_sqm", anchor_price_sqm),
            res_08.get("predicted_price_sqm", anchor_price_sqm),
            res_04.get("predicted_price_sqm", anchor_price_sqm),
            res_05.get("predicted_price_sqm", anchor_price_sqm),
            res_07.get("predicted_price_sqm", anchor_price_sqm),
        ]
        spread_ratio = float(np.std(model_estimates) / max(ensemble_price_sqm, 1.0))
        interval_margin = max(0.045, min(0.14, spread_ratio * 0.8))
        low_val = round(total_fair_market_value * (1.0 - interval_margin), 0)
        high_val = round(total_fair_market_value * (1.0 + interval_margin), 0)

        # S8: Historical Construction / Purchase Cost Analysis (Decoupled from current market pricing)
        user_cost = float(property_input.get("original_cost_of_house", 0.0) or 0.0)
        is_user_cost_provided = user_cost > 0.0
        cost_created_total = user_cost if is_user_cost_provided else cost_analysis["total_creation_cost_original"]
        wealth_created = max(0.0, total_fair_market_value - cost_created_total)
        appreciation_mult = round(total_fair_market_value / max(cost_created_total, 1.0), 2)
        historical_cagr = round(((total_fair_market_value / max(cost_created_total, 1.0)) ** (1.0 / max(1.0, prop_age)) - 1.0) * 100.0, 2)

        # Stage 5 (Milestone 7): Transparent Evidence Confidence & Statistically Calibrated Uncertainty
        gt_category = (
            "residential_land"
            if asset_type == "land"
            else ("commercial" if asset_type == "commercial" else ("standalone_house" if is_standalone else "apartment"))
        )
        evidence_and_uncertainty = self._assess_evidence_and_uncertainty(
            latitude=lat_coord,
            longitude=lon_coord,
            gt_category=gt_category,
            valuation_area_sqft=valuation_area_sqft,
            point_estimate=total_fair_market_value,
            audit_res=audit_res,
            location_intelligence=location_intelligence,
        )

        # Multi-Horizon Scenarios (1y, 3y, 5y)
        hist_growth_1y = float(imp_feat.get("local_price_growth_1y", 0.07))
        future_infra_uplift = float(res_09.get("future_infrastructure_uplift_pct", 3.0)) / 100.0
        cagr = np.clip(hist_growth_1y * 0.65 + future_infra_uplift * 0.5, 0.03, 0.16)

        scenario_1y = total_fair_market_value * (1.0 + cagr)
        scenario_3y = total_fair_market_value * ((1.0 + cagr * 0.92) ** 3)
        scenario_5y = total_fair_market_value * ((1.0 + cagr * 0.85) ** 5)

        # -------------------------------------------------------------------------
        # STRUCTURED 28-CRITERIA VALUATION AUDIT (ALL 4 PRIORITY TIERS + RISK GATES)
        # -------------------------------------------------------------------------
        criteria_audit_28 = {
            "summary": {
                "total_criteria_tracked": 28,
                "priority_1_critical_weight": "25% Model Attention",
                "priority_2_major_weight": "20% Model Attention",
                "priority_3_supporting_weight": "10% Model Attention",
                "priority_4_reference_weight": "5% Model Attention",
                "risk_gates_weight": "Eligibility & Environmental Multipliers",
            },
            "priority_1_critical": [
                {
                    "rank": 1, "id": "M5", "criterion": "Comparable Transaction Registry",
                    "value": f"{res_01.get('comparable_sales_count', 12)} Recent Registered Deeds",
                    "importance": "Extremely High (Market Anchor)",
                    "impact": f"Transacted 500m median: {currency} {res_01.get('predicted_price_sqm', 0)/10.7639:,.0f}/sqft"
                },
                {
                    "rank": 2, "id": "L1", "criterion": "Exact GPS & Micro-Market Tier",
                    "value": f"{location_intelligence.get('metadata', {}).get('locality', 'Urban Core')} ({location_intelligence.get('metadata', {}).get('density_tier', 'Urban')})",
                    "importance": "Extremely High",
                    "impact": f"Locality baseline: {currency} {base_land_rate_sqft:,.0f}/sqft land ({loc_rating.title()} tier: {loc_pct*100:+.0f}%)"
                },
                {
                    "rank": 3, "id": "L2", "criterion": "Government Circle Rate (Guideline Value)",
                    "value": f"{currency} {circle_rate_sqft:,.0f} / sq ft",
                    "importance": "Very High (Regulatory Benchmark Floor)",
                    "impact": f"State IGR benchmark floor (Market-to-Circle ratio: {market_land_rate_sqft/max(circle_rate_sqft, 1.0):.2f}x)"
                },
                {
                    "rank": 4, "id": "M1", "criterion": "Title & Legal Approval Status",
                    "value": legal_status_desc,
                    "importance": "Very High (Eligibility & Risk Gate)",
                    "impact": f"{legal_risk_pct*100:+.0f}% (Bank Loan Eligibility: {'ELIGIBLE' if bank_loan_eligible else 'RESTRICTED / HIGH RISK'})"
                },
                {
                    "rank": 5, "id": "S3", "criterion": "Exclusive Plot Area",
                    "value": f"{effective_plot_sqft:,.1f} sq ft",
                    "importance": "Very High",
                    "impact": f"{'100% Exclusive Land Footprint' if is_standalone else 'Attributed UDS Land Share (28% of built area)'}"
                },
                {
                    "rank": 6, "id": "S2", "criterion": "Built-Up Area & Carpet Area",
                    "value": f"{valuation_area_sqft:,.0f} sq ft",
                    "importance": "Very High",
                    "impact": f"Direct basis for Stage 2 structural replacement cost ({valuation_area_sqm:.1f} sq m)"
                },
                {
                    "rank": 7, "id": "L3", "criterion": "Road Width in Front of Property",
                    "value": f"{road_width.replace('_', ' ').title()}",
                    "importance": "Very High",
                    "impact": f"{road_pct*100:+.0f}% land price adjustment ({'40ft+ wide avenue premium' if road_pct>0 else ('Narrow street penalty' if road_pct<0 else 'Standard colony road')})"
                },
                {
                    "rank": 8, "id": "L4", "criterion": "Road Frontage & Plot Orientation",
                    "value": f"{'Corner Plot / Park Facing (2+ Sides Open)' if corner_pct>0 else 'Standard Single Road Facing'}",
                    "importance": "Very High",
                    "impact": f"{corner_pct*100:+.0f}% premium for ventilation and natural lighting"
                },
            ],
            "priority_2_major": [
                {
                    "rank": 9, "id": "S5", "criterion": "Building Age & Structural Depreciation",
                    "value": f"{prop_age:.0f} Years Old",
                    "importance": "High",
                    "impact": f"-{effective_deprec_pct*100:.1f}% cumulative structural depreciation (CPWD 60-year curve)"
                },
                {
                    "rank": 10, "id": "S4", "criterion": "Construction Quality & Structural Grade",
                    "value": f"{const_grade.replace('_', ' ')} (CPWD Plinth Schedule)",
                    "importance": "High",
                    "impact": f"Replacement cost new: {currency} {rate_today_sqft:,.0f}/sqft"
                },
                {
                    "rank": 11, "id": "L6", "criterion": "Bus Stand, Metro & Railway Proximity",
                    "value": f"Bus: {dist_bus:.1f} km | Rail: {dist_rail:.1f} km | Metro: {dist_metro:.1f} km",
                    "importance": "High",
                    "impact": f"{transit_pct*100:+.1f}% radial transit uplift (strongest within 1km, positive up to 15km)"
                },
                {
                    "rank": 12, "id": "L10", "criterion": "Commercial & IT Employment Hubs",
                    "value": f"{dist_cbd:.1f} km from Major CBD / IT Hub",
                    "importance": "High",
                    "impact": f"{it_pct*100:+.1f}% IT corridor proximity uplift (positive merit within 15–18km)"
                },
                {
                    "rank": 13, "id": "L12", "criterion": "Road Traffic & High-Demand Merit",
                    "value": f"{res_05.get('vehicles_per_minute_peak', 45)} veh/min (Congestion idx: {res_05.get('congestion_index', 0.5)})",
                    "importance": "High",
                    "impact": f"{res_05.get('traffic_impact_mode', 'Positive Merit (High Road Traffic = High Demand)')}"
                },
                {
                    "rank": 14, "id": "M4", "criterion": "Building Maintenance & Structural State",
                    "value": f"{maintenance.replace('_', ' ').title()}",
                    "importance": "High",
                    "impact": f"Depreciation modifier factor: {maint_deprec_factor:.2f}x"
                },
                {
                    "rank": 15, "id": "L13", "criterion": "Area Population Density & Demographics",
                    "value": f"{float(res_06.get('population_density_sqkm', 12000)):,.0f} people/sq km",
                    "importance": "High",
                    "impact": f"Sustained residential catchment & municipal civic infrastructure"
                },
                {
                    "rank": 16, "id": "L14", "criterion": "Upcoming Government Projects & Master Plan",
                    "value": f"Master Plan Status: {res_09.get('project_status_code', 'APPROVED')}",
                    "importance": "High",
                    "impact": f"{govt_pct*100:+.0f}% capital appreciation anticipation factor"
                },
            ],
            "priority_3_supporting": [
                {
                    "rank": 17, "id": "M6", "criterion": "Rental Yield & Investor Demand",
                    "value": f"{res_10.get('gross_rental_yield_pct', 3.8)}% Gross Annual Yield",
                    "importance": "Medium-High",
                    "impact": f"Estimated rent: {currency} {res_10.get('estimated_monthly_rent', 0):,.0f} / month"
                },
                {
                    "rank": 18, "id": "L5", "criterion": "National Highway & State Highway Distance",
                    "value": f"{res_04.get('distance_nh_km', 2.5):.1f} km to National Highway",
                    "importance": "Medium-High",
                    "impact": "Regional arterial logistics and inter-city connectivity"
                },
                {
                    "rank": 19, "id": "L9", "criterion": "Hospitals & Healthcare Proximity",
                    "value": f"{dist_hospital:.1f} km to Multi-Specialty Hospital",
                    "importance": "Medium",
                    "impact": f"+{float(uplift_bd.get('hospital_pct', 0.0)):.1f}% radial healthcare access merit"
                },
                {
                    "rank": 20, "id": "L8", "criterion": "Educational Hubs & Schools Proximity",
                    "value": f"{dist_school:.1f} km to Premier Schools/Institutes",
                    "importance": "Medium",
                    "impact": f"+{float(uplift_bd.get('school_pct', 0.0)):.1f}% radial school accessibility merit"
                },
                {
                    "rank": 21, "id": "L11", "criterion": "Commercial Density & High-Street Retail",
                    "value": f"{res_04.get('distance_mall_km', 2.0):.1f} km to Malls / Shopping Corridors",
                    "importance": "Medium",
                    "impact": "Retail footfall and daily lifestyle convenience"
                },
                {
                    "rank": 22, "id": "S1", "criterion": "House Form Factor",
                    "value": f"{structure_type.replace('_', ' ').title()}",
                    "importance": "Medium",
                    "impact": f"{'Exclusive land + structure separate appraisal' if is_standalone else 'High-rise apartment unit with UDS'}"
                },
                {
                    "rank": 23, "id": "M2", "criterion": "Interior Fit-Out & Furnishing",
                    "value": f"{furnishing.replace('_', ' ').title()}",
                    "importance": "Medium",
                    "impact": f"+{currency} {house_fitout_cost:,.0f} modular kitchen, woodwork, and ceiling capital addition"
                },
                {
                    "rank": 24, "id": "M3", "criterion": "Dedicated Car Parking",
                    "value": f"{parking.replace('_', ' ').title()}",
                    "importance": "Medium",
                    "impact": f"+{currency} {house_parking_cost:,.0f} reserved parking asset value"
                },
            ],
            "priority_4_reference": [
                {
                    "rank": 25, "id": "L7", "criterion": "Airport & Major Transport Terminals",
                    "value": f"{dist_airport:.1f} km to Airport",
                    "importance": "Low-Medium",
                    "impact": f"+{float(uplift_bd.get('airport_pct', 0.0)):.1f}% radial airport connectivity merit"
                },
                {
                    "rank": 26, "id": "S6", "criterion": "Number of Floors & Height",
                    "value": f"Floor {property_input.get('floor_number', 1)} of {property_input.get('total_floors', 4)} Floors",
                    "importance": "Low-Medium",
                    "impact": "Vertical accessibility, building load, and view orientation"
                },
                {
                    "rank": 27, "id": "S7", "criterion": "Room Configuration (BHK & Bathrooms)",
                    "value": f"{property_input.get('bedrooms', 3)} BHK, {property_input.get('bathrooms', 2)} Baths",
                    "importance": "Low",
                    "impact": "Captured inside built-up carpet area and standard room proportions"
                },
                {
                    "rank": 28, "id": "S8", "criterion": "Original Construction / Purchase Cost",
                    "value": f"{currency} {cost_created_total:,.0f} ({'User Verified' if is_user_cost_provided else 'CPWD Historical Index'})",
                    "importance": "Lowest Direct Influence on Current Market Value",
                    "impact": f"Decoupled from current market pricing; used purely for historical appreciation ({appreciation_mult:.2f}x, {historical_cagr:.1f}% CAGR)"
                },
            ],
            "environmental_risk_gate": {
                "flood_risk_level": flood_risk.replace('_', ' ').title(),
                "flood_risk_adjustment": f"{flood_pct*100:+.0f}%",
                "drainage_infrastructure": drainage_infra.replace('_', ' ').title(),
                "drainage_adjustment": f"{drainage_pct*100:+.0f}%",
                "groundwater_availability": groundwater.replace('_', ' ').title(),
                "groundwater_adjustment": f"{groundwater_pct*100:+.0f}%",
                "litigation_encumbrance_status": litigation.replace('_', ' ').title(),
                "litigation_adjustment": f"{litigation_pct*100:+.0f}%",
                "total_environmental_adjustment": f"{total_env_risk_pct*100:+.1f}%",
                "bank_loan_eligibility": bank_loan_eligible,
            }
        }

        # Explainable SHAP-style Factor Contributions
        factors_positive = []
        factors_negative = []

        # Comparable sales evidence
        comp_diff = res_01.get("predicted_price_sqm", anchor_price_sqm) - anchor_price_sqm
        factors_positive.append({
            "driver": "M5: Comparable Transaction Registry",
            "impact": f"+{abs(comp_diff) * valuation_area_sqm:,.0f} {currency}",
            "note": f"Based on {res_01.get('comparable_sales_count', 12)} nearby verified deeds in 500m buffer"
        })

        # Land location & road width
        if road_pct > 0:
            factors_positive.append({
                "driver": "L3: Road Width & Access Frontage",
                "impact": f"+{road_pct * base_land_rate_sqft * effective_plot_sqft:,.0f} {currency}",
                "note": f"{road_width.replace('_', ' ').title()} wide avenue access"
            })
        elif road_pct < 0:
            factors_negative.append({
                "driver": "L3: Narrow Access Road Discount",
                "impact": f"-{abs(road_pct) * base_land_rate_sqft * effective_plot_sqft:,.0f} {currency}",
                "note": "Narrow street access (<15 ft)"
            })

        # Corner plot
        if corner_pct > 0:
            factors_positive.append({
                "driver": "L4: Corner Plot & Dual Frontage",
                "impact": f"+{corner_pct * base_land_rate_sqft * effective_plot_sqft:,.0f} {currency}",
                "note": "Two sides open / park-facing ventilation"
            })

        # Road traffic as high-demand merit
        if traffic_demand_pct > 0:
            factors_positive.append({
                "driver": "L12: Road Traffic & Corridor Demand Merit",
                "impact": f"+{traffic_demand_pct * base_land_rate_sqft * effective_plot_sqft:,.0f} {currency}",
                "note": f"Higher road traffic ({res_05.get('vehicles_per_minute_peak', 45)} veh/min) indicates active neighborhood demand"
            })

        # Radial amenity & transit proximity merit
        total_radial_pct = transit_pct + it_pct + social_infra_pct
        if total_radial_pct > 0:
            factors_positive.append({
                "driver": "L6-L10: Radial Amenities & Transit Connectivity",
                "impact": f"+{total_radial_pct * base_land_rate_sqft * effective_plot_sqft:,.0f} {currency}",
                "note": f"School {dist_school:.1f}km, Hospital {dist_hospital:.1f}km, Bus {dist_bus:.1f}km, Airport {dist_airport:.1f}km, IT Hub {dist_cbd:.1f}km"
            })

        # Backend Priority Zone Land Uplift (public explainability omits internal yellow zone labels)
        public_zone_view = LocationZoneEngine.to_public_payload(zone_analysis)
        if zone_land_uplift_pct > 0:
            factors_positive.append({
                "driver": f"Zone Merit: {public_zone_view.get('zone_classification')}",
                "impact": f"+{zone_land_uplift_pct * base_land_rate_sqft * effective_plot_sqft:,.0f} {currency}",
                "note": f"Medical & Urban Accessibility Corridor (+{public_zone_view.get('total_zone_land_uplift_pct', 0)}%)"
            })

        # Title & legal status gate
        if is_legal_approved:
            factors_positive.append({
                "driver": "M1: Freehold Title & Layout Approval",
                "impact": f"+{legal_risk_pct * unadjusted_valuation:,.0f} {currency}",
                "note": "Clear title with BDA / Municipal / RERA approved layout"
            })
        else:
            factors_negative.append({
                "driver": "M1: Unapproved / Revenue Layout Risk",
                "impact": f"-{abs(legal_risk_pct) * unadjusted_valuation:,.0f} {currency}",
                "note": "Restricted bank loan eligibility and legal regularization cost"
            })

        # Environmental risk factors
        if flood_pct < 0:
            factors_negative.append({
                "driver": "Environmental: Flood & Waterlogging Risk",
                "impact": f"-{abs(flood_pct) * unadjusted_valuation:,.0f} {currency}",
                "note": f"Low-lying terrain / seasonal waterlogging exposure ({flood_risk})"
            })

        if drainage_pct < 0:
            factors_negative.append({
                "driver": "Environmental: Drainage Infrastructure Deficit",
                "impact": f"-{abs(drainage_pct) * unadjusted_valuation:,.0f} {currency}",
                "note": "Absence of municipal underground storm sewer system"
            })

        if house_fitout_cost > 0:
            factors_positive.append({
                "driver": "M2: Interior Fit-Out & Woodwork",
                "impact": f"+{house_fitout_cost:,.0f} {currency}",
                "note": f"{furnishing.replace('_', ' ').title()} modular woodwork & false ceiling"
            })

        if house_parking_cost > 0:
            factors_positive.append({
                "driver": "M3: Dedicated Reserved Parking",
                "impact": f"+{house_parking_cost:,.0f} {currency}",
                "note": f"{parking.replace('_', ' ').title()} reserved space"
            })

        return {
            "status": "success",
            "valuation": {
                "fair_market_value": round(total_fair_market_value, 0),
                "fair_market_value_formatted": format_currency(total_fair_market_value, currency),
                "valuation_interval": {
                    "low": round(low_val, 0),
                    "low_formatted": format_currency(low_val, currency),
                    "high": round(high_val, 0),
                    "high_formatted": format_currency(high_val, currency),
                    "margin_pct": round(interval_margin * 100.0, 1),
                },
                "price_per_sqm": round(adjusted_price_sqm, 2),
                "price_per_sqft": round(price_per_sqft, 2),
                "valuation_area_sqm": valuation_area_sqm,
                "valuation_area_sqft": round(valuation_area_sqft, 1),
                "currency": currency,
                "asset_type": asset_type,
            },
            "land_and_house_breakdown": {
                "calculation_sequence": "Stage 1: Land Market Valuation (V_L = A_L * R_L) -> Stage 2: Depreciated Building Cost (V_B = A_B * C_B * (1-D)) -> Stage 3: Market Reconciliation & Legal Gate",
                "structure_type": structure_type,
                "is_standalone_house": is_standalone,
                # Stage 1: Land Market Valuation
                "stage1_land_price": round(stage1_land_market_value, 0),
                "stage1_land_price_formatted": format_currency(stage1_land_market_value, currency),
                "step1_land_price": round(stage1_land_market_value, 0),
                "step1_land_price_formatted": format_currency(stage1_land_market_value, currency),
                "effective_land_area_sqft": effective_plot_sqft,
                "right_now_land_rate_sqft": market_land_rate_sqft,
                "circle_rate_sqft": circle_rate_sqft,
                "zone_classification": public_zone_view.get("zone_classification"),
                "zone_land_uplift_pct": zone_analysis.get("total_zone_land_uplift_pct", 0.0),
                "land_description": land_desc,
                # Stage 2: Depreciated Building Cost
                "stage2_cost_of_house": round(stage2_building_cost, 0),
                "stage2_cost_of_house_formatted": format_currency(stage2_building_cost, currency),
                "step2_cost_of_house": round(stage2_building_cost, 0),
                "step2_cost_of_house_formatted": format_currency(stage2_building_cost, currency),
                "house_structure_cost": round(depreciated_structure_value, 0),
                "house_structure_cost_formatted": format_currency(depreciated_structure_value, currency),
                "house_fitout_cost": round(house_fitout_cost, 0),
                "house_fitout_cost_formatted": format_currency(house_fitout_cost, currency),
                "house_parking_cost": round(house_parking_cost, 0),
                "house_parking_cost_formatted": format_currency(house_parking_cost, currency),
                # Stage 3: Market Reconciliation & Legal Gate
                "unadjusted_sum": round(unadjusted_valuation, 0),
                "legal_risk_adjustment": f"{legal_risk_pct*100:+.0f}%",
                "environmental_risk_adjustment": f"{total_env_risk_pct*100:+.1f}%",
                "bank_loan_eligibility": bank_loan_eligible,
                "total_property_price": round(total_fair_market_value, 0),
                "total_property_price_formatted": format_currency(total_fair_market_value, currency),
            },
            "criteria_audit_28": criteria_audit_28,
            "zone_analysis": public_zone_view,
            "creation_cost_vs_current_price": {
                "structure_type": structure_type,
                "is_standalone_house": structure_type in ["standalone_house", "independent_house", "villa", "bungalow"],
                "cost_source": "User Verified Known Cost" if is_user_cost_provided else "CPWD / PWD Historical Construction Index",
                "cost_of_house_created": round(cost_created_total, 0),
                "cost_of_house_created_formatted": format_currency(cost_created_total, currency),
                "original_creation_cost": round(cost_created_total, 0),
                "original_creation_cost_formatted": format_currency(cost_created_total, currency),
                "original_structure_cost": format_currency(cost_analysis["historical_structure_cost"], currency),
                "original_land_basis": format_currency(cost_analysis["historical_land_cost"], currency),
                "historical_construction_rate_sqft": f"{currency} {cost_analysis['rate_historical_per_sqft']:,.0f}/sqft",
                "right_now_market_price": round(total_fair_market_value, 0),
                "right_now_market_price_formatted": format_currency(total_fair_market_value, currency),
                "wealth_created": round(wealth_created, 0),
                "wealth_created_formatted": format_currency(wealth_created, currency),
                "appreciation_multiple": f"{appreciation_mult:.2f}x",
                "historical_cagr_pct": historical_cagr,
                "replacement_cost_new_today": format_currency(cost_analysis["replacement_cost_new_today"], currency),
                "current_construction_rate_sqft": f"{currency} {cost_analysis['rate_today_per_sqft']:,.0f}/sqft",
                "structural_depreciation_pct": f"{cost_analysis['depreciation_pct']}%",
            },
            "rental_and_yield": {
                "estimated_monthly_rent": reconciliation_bundle["income_valuation"].get("achievable_monthly_rent_formatted")
                or format_currency(res_10.get("estimated_monthly_rent", 0), currency),
                "gross_rental_yield_pct": reconciliation_bundle["income_valuation"].get("gross_rental_yield_pct")
                or res_10.get("gross_rental_yield_pct"),
                "net_rental_yield_pct": reconciliation_bundle["income_valuation"].get("net_rental_yield_pct")
                or res_10.get("net_rental_yield_pct"),
                "annual_noi_formatted": reconciliation_bundle["income_valuation"].get("annual_noi_formatted"),
                "market_cap_rate_pct": reconciliation_bundle["income_valuation"].get("market_cap_rate_pct"),
                "comparable_grm": reconciliation_bundle["income_valuation"].get("comparable_grm"),
                "rent_source_category": reconciliation_bundle["income_valuation"].get("rent_source_category"),
                "investment_attractiveness": res_10.get("investment_attractiveness"),
            },
            "income_approach_and_reconciliation": reconciliation_bundle,
            "evidence_and_uncertainty": evidence_and_uncertainty,
            "horizon_scenarios": {
                "projected_cagr_pct": round(cagr * 100.0, 2),
                "forecast_1_year": format_currency(scenario_1y, currency),
                "forecast_3_year": format_currency(scenario_3y, currency),
                "forecast_5_year": format_currency(scenario_5y, currency),
            },
            "explainability": {
                "top_positive_factors": factors_positive,
                "top_negative_factors": factors_negative,
                "market_cycle": res_07.get("market_cycle_classification"),
                "data_completeness_pct": audit_res.get("data_completeness_pct"),
                "specialist_models_contributed": [
                    {"code": "M01", "name": res_01["model"], "status": res_01["status"]},
                    {"code": "M02", "name": res_02["model"], "status": res_02["status"]},
                    {"code": "M03", "name": res_03["model"], "status": res_03["status"]},
                    {"code": "M04", "name": res_04["model"], "status": res_04["status"]},
                    {"code": "M05", "name": res_05["model"], "status": res_05["status"]},
                    {"code": "M06", "name": res_06["model"], "status": res_06["status"]},
                    {"code": "M07", "name": res_07["model"], "status": res_07["status"]},
                    {"code": "M08", "name": res_08["model"], "status": res_08["status"]},
                    {"code": "M09", "name": res_09["model"], "status": res_09["status"]},
                    {"code": "M10", "name": res_10["model"], "status": res_10["status"]},
                ],
            },
            "location_summary": location_intelligence.get("metadata", {}),
            "sources_status": location_intelligence.get("sources_status", {}),
        }

    def _assess_evidence_and_uncertainty(
        self,
        latitude: float,
        longitude: float,
        gt_category: str,
        valuation_area_sqft: float,
        point_estimate: float,
        audit_res: Dict[str, Any],
        location_intelligence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Computes transparent evidence confidence components and statistically calibrated prediction intervals."""
        import json
        from datetime import date

        search_radius_km = 5.0
        distances: List[float] = []
        similarities: List[float] = []
        age_days: List[float] = []
        source_cats: List[str] = []
        holdout_abs_pct_errors: List[float] = []

        with SessionLocal() as db:
            # 1. Inspect independent verified sale comparables within 5 km
            deg_pad = 0.06
            tx_candidates = db.query(GroundTruthTransaction).filter(
                GroundTruthTransaction.data_category == "Verified_Registered_Transaction",
                GroundTruthTransaction.is_duplicate.is_(False),
                GroundTruthTransaction.property_type == gt_category,
                GroundTruthTransaction.latitude.between(latitude - deg_pad, latitude + deg_pad),
                GroundTruthTransaction.longitude.between(longitude - deg_pad, longitude + deg_pad),
            ).all()

            today = date.today()
            for tx in tx_candidates:
                d = haversine_km(latitude, longitude, tx.latitude, tx.longitude)
                if d <= search_radius_km:
                    distances.append(d)
                    tx_area = tx.builtup_area_sqft or tx.plot_area_sqft or tx.carpet_area_sqft or valuation_area_sqft
                    area_diff = abs(tx_area - valuation_area_sqft) / max(valuation_area_sqft, 1.0)
                    sim = max(0.0, 100.0 * (1.0 - min(1.0, area_diff)) * 0.7 + 30.0 * (1.0 - d / search_radius_km))
                    similarities.append(min(100.0, sim))
                    if tx.transaction_date:
                        age_days.append(max(0.0, float((today - tx.transaction_date).days)))
                    source_cats.append("Verified_Registered_Transaction")

            # 2. Retrieve empirical holdout residuals from latest ValidationEvaluationRun
            latest_run = db.query(ValidationEvaluationRun).order_by(ValidationEvaluationRun.evaluated_at.desc()).first()
            if latest_run:
                cat_map = json.loads(latest_run.category_metrics_json or "{}")
                holdout_abs_pct_errors = cat_map.get(gt_category, {}).get("_holdout_abs_pct_errors", [])

        if not source_cats:
            # No verified independent sale deeds in radius: accurately attribute fallback to hub benchmark
            source_cats = ["Historical_Hub_Benchmark"]

        comp_pct = float(audit_res.get("data_completeness_pct", 80.0))
        observed_fields = int(round((comp_pct / 100.0) * 10))

        evidence_quality = self.evidence_service.compute_evidence_score(
            comparables_count=len(distances),
            median_distance_km=float(np.median(distances)) if distances else None,
            search_radius_km=search_radius_km,
            avg_similarity_0_100=float(np.mean(similarities)) if similarities else None,
            median_age_days=float(np.median(age_days)) if age_days else None,
            source_categories=source_cats,
            observed_critical_fields=observed_fields,
            total_critical_fields=10,
        )

        calibrated_interval = self.evidence_service.compute_calibrated_interval(
            point_estimate=point_estimate,
            holdout_abs_pct_errors=holdout_abs_pct_errors,
            confidence_level=0.90,
            min_calibration_samples=10,
        )

        return {
            "evidence_quality": evidence_quality,
            "calibrated_prediction_interval": calibrated_interval,
        }
