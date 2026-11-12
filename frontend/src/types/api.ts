export interface SelectOption {
  value: string;
  label: string;
  default?: boolean;
}

export interface LocationPreset {
  label: string;
  latitude: number;
  longitude: number;
  country_code: string;
  region: string;
}

export interface PlatformConfigResponse {
  default_location: {
    label: string;
    latitude: number;
    longitude: number;
    country_code: string;
  };
  region_filters: { id: string; label: string }[];
  location_presets: LocationPreset[];
  countries: SelectOption[];
  map_layers: { id: string; label: string }[];
  asset_types: SelectOption[];
  shap_property_types: SelectOption[];
  selectors: Record<string, SelectOption[]>;
}

export interface ZoneMarkerItem {
  name: string;
  category: string;
  zone_color: 'green';
  hex_color: string;
  latitude: number;
  longitude: number;
  distance_km: number;
  core_radius_m: number;
  zone_radius_m: number;
  inside_zone: boolean;
}

export interface ZoneAnalysis {
  in_any_zone: boolean;
  in_green_zone: boolean;
  zone_classification: string;
  zone_summary: string;
  green_zone_land_uplift_pct: number;
  total_zone_land_uplift_pct: number;
  land_rate_multiplier: number;
  active_green_facilities_count: number;
  nearest_green_facility: ZoneMarkerItem | null;
  green_zones: ZoneMarkerItem[];
  zone_discovery_mode?: string;
}

export interface ZonesApiResponse {
  latitude: number;
  longitude: number;
  city: string;
  locality: string;
  state: string;
  currency: string;
  density_tier: string;
  base_land_rate_sqft: number;
  circle_rate_sqft: number;
  zone_analysis: ZoneAnalysis;
}

export interface AddressSearchResult {
  display_name: string;
  latitude: number;
  longitude: number;
  city?: string;
  state?: string;
}

export interface PropertyDetailsPayload {
  asset_type: 'residential' | 'commercial' | 'land';
  structure_type: string;
  area_value: number;
  area_unit: string;
  plot_area_sqft: number;
  bedrooms: number;
  bathrooms: number;
  property_age_years: number;
  construction_grade: string;
  floor_number: number;
  total_floors: number;
  commercial_type: string;
  locality_tier: string;
  road_width_ft: string;
  corner_plot: string;
  furnishing: string;
  parking_slots: string;
  approval_status: string;
  maintenance_state: string;
  original_cost_of_house: number;
  flood_risk: string;
  drainage_infra: string;
  groundwater_availability: string;
  litigation_risk: string;
  monthly_rent_inr: number;
  operating_expenses_annual: number;
  vacancy_rate_pct: number | null;
}

export interface ValuationRequestPayload {
  location: {
    latitude: number;
    longitude: number;
    accuracy: number;
    country_code: string;
  };
  property_details: PropertyDetailsPayload;
}

export interface ReconciliationApproach {
  value_inr: number;
  value_formatted: string;
  weight_pct: number;
  confidence: number;
  method_notes?: string;
}

export interface ValuationResponse {
  status: string;
  valuation_id: string;
  valuation: {
    fair_market_value: number;
    fair_market_value_formatted: string;
    valuation_interval: {
      low: number;
      low_formatted: string;
      high: number;
      high_formatted: string;
      margin_pct: number;
    };
    price_per_sqm: number;
    price_per_sqft: number;
    valuation_area_sqm: number;
    valuation_area_sqft: number;
    currency: string;
    asset_type: string;
  };
  land_and_house_breakdown: {
    calculation_sequence: string;
    structure_type: string;
    is_standalone_house: boolean;
    stage1_land_price: number;
    stage1_land_price_formatted: string;
    effective_land_area_sqft: number;
    right_now_land_rate_sqft: number;
    circle_rate_sqft: number;
    zone_classification: string;
    zone_land_uplift_pct: number;
    land_description: string;
    stage2_cost_of_house: number;
    stage2_cost_of_house_formatted: string;
    house_structure_cost_formatted: string;
    house_fitout_cost_formatted: string;
    house_parking_cost_formatted: string;
    legal_risk_adjustment: string;
    environmental_risk_adjustment: string;
    bank_loan_eligibility: boolean;
    total_property_price_formatted: string;
  };
  zone_analysis: ZoneAnalysis;
  criteria_audit_28: {
    priority_1_critical?: Array<{ rank: number; id: string; criterion: string; value: string; importance: string; impact: string }>;
    priority_2_major?: Array<{ rank: number; id: string; criterion: string; value: string; importance: string; impact: string }>;
    environmental_risk_gate?: {
      flood_risk_level: string;
      flood_risk_adjustment: string;
      drainage_infrastructure: string;
      drainage_adjustment: string;
      groundwater_availability: string;
      groundwater_adjustment: string;
      litigation_encumbrance_status: string;
      litigation_adjustment: string;
      bank_loan_eligibility: boolean;
      total_environmental_adjustment: string;
    };
  };
  creation_cost_vs_current_price: {
    structure_type: string;
    cost_source: string;
    original_creation_cost_formatted: string;
    original_structure_cost: string;
    original_land_basis: string;
    historical_construction_rate_sqft: string;
    right_now_market_price_formatted: string;
    wealth_created_formatted: string;
    appreciation_multiple: string;
    historical_cagr_pct: number;
    replacement_cost_new_today: string;
  };
  rental_and_yield: {
    estimated_monthly_rent: string;
    gross_rental_yield_pct: number;
    net_rental_yield_pct: number;
  };
  income_approach_and_reconciliation: {
    income_valuation: {
      achievable_monthly_rent: number;
      achievable_monthly_rent_formatted: string;
      annual_gross_rent_formatted: string;
      annual_noi: number;
      annual_noi_formatted: string;
      annual_operating_expenses: number;
      gross_rental_yield_pct: number;
      net_rental_yield_pct: number;
      vacancy_rate_pct: number;
      market_cap_rate_pct: number;
      comparable_grm: number;
      grm_property_value_formatted: string;
      rent_source_category: string;
      cap_rate_justification?: string;
    };
    three_way_reconciliation: {
      reconciled_fair_market_value: number;
      reconciled_fair_market_value_formatted: string;
      weighting_policy: string;
      approach_divergence_pct: number;
      divergence_explanations: string[];
      approaches: {
        approach_a_sales_comparison?: ReconciliationApproach;
        approach_b_cost_approach?: ReconciliationApproach;
        approach_c_income_capitalization?: ReconciliationApproach;
      };
    };
    rental_comparables?: {
      data_confidence_score: number;
      data_confidence_label: string;
      comparables: Array<{
        locality: string;
        distance_km: number;
        builtup_area_sqft: number;
        monthly_rent_inr: number;
        data_category: string;
      }>;
    };
    rental_forecast?: {
      scenarios: {
        base: { horizons: Record<string, { nominal_monthly_rent: number; real_monthly_rent_today_inr: number }> };
        conservative: { horizons: Record<string, { nominal_monthly_rent: number }> };
        optimistic: { horizons: Record<string, { nominal_monthly_rent: number }> };
      };
    };
  };
  evidence_and_uncertainty: {
    evidence_quality: {
      composite_confidence_score: number;
      confidence_tier: string;
      score_components: Record<string, number>;
      reasons_for_low_confidence: string[];
    };
    calibrated_prediction_interval: {
      point_estimate: number;
      lower_estimate: number | null;
      upper_estimate: number | null;
      status: string;
      calibration_sample_count: number;
      empirical_quantile_margin_pct: number | null;
      evidence_limitations: string[];
    };
    ood_assessment: {
      is_ood: boolean;
      ood_severity: string;
      ood_flags: string[];
      recommended_fallback: string;
    };
  };
  horizon_scenarios: {
    projected_cagr_pct: number;
    forecast_1_year: string;
    forecast_3_year: string;
    forecast_5_year: string;
  };
  explainability: {
    top_positive_factors: Array<{ driver: string; impact: string; note: string }>;
    top_negative_factors: Array<{ driver: string; impact: string; note: string }>;
    market_cycle: string;
    data_completeness_pct: number;
    specialist_models_contributed: Array<{ code: string; name: string; status: string }>;
  };
  location_summary: {
    latitude: number;
    longitude: number;
    city: string;
    locality: string;
    state: string;
    currency: string;
    land_rate_sqft: number;
    circle_rate_sqft: number;
    density_tier: string;
    harvest_timestamp: string;
  };
  sources_status: Record<string, { status: string; provider: string }>;
}

export interface CoverageLocality {
  locality: string;
  sufficiency_status: string;
  verified_transaction_count: number;
  unverified_or_broker_count: number;
  transaction_date_range?: { earliest?: string; latest?: string };
  verified_ppsf_distribution?: { median: number; p25: number; p75: number; iqr: number } | null;
  missing_data_pct?: number | null;
  limitations?: string[];
  coordinates?: { latitude: number; longitude: number };
}

export interface CoverageDashboardResponse {
  city: string;
  verified_completed_sales_count: number;
  unverified_or_broker_count: number;
  data_quality_failures_or_reviews: number;
  last_ingestion_run_at: string | null;
  sufficiency_summary: {
    sufficient_localities_count: number;
    preliminary_localities_count: number;
    insufficient_localities_count: number;
  };
  verification_status_distribution: Record<string, number>;
  source_type_distribution: Record<string, number>;
  property_type_distribution: Record<string, number>;
  localities: CoverageLocality[];
}

export interface HealthResponse {
  status: string;
  service: string;
  specialist_models_registered: number;
  production_models_loaded: string[];
  database_connected: boolean;
  database_tables_count: number;
  private_evidence_vault_ready: boolean;
}

export interface AdminLoginResponse {
  access_token: string;
  actor_id: string;
  actor_role: string;
}

export interface AdminQueueItem {
  transaction_id: string;
  locality: string | null;
  property_type: string;
  verification_status: string;
  source_category: string;
  review_flags?: string[];
  evidence_hash?: string;
}

export type WorkspaceRoute =
  | 'overview'
  | 'valuation'
  | 'spatial'
  | 'market'
  | 'comparables'
  | 'rental'
  | 'portfolio'
  | 'reports'
  | 'coverage'
  | 'admin';

export interface PortfolioPropertyItem {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  assetType: 'residential' | 'commercial' | 'land';
  areaSqft: number;
  fairMarketValue: number;
  fairMarketValueFormatted: string;
  pricePerSqft: number;
  monthlyRent: number;
  grossYieldPct: number;
  zoneClassification: string;
  confidenceTier: string;
  sourceBasis: 'Sourced Valuation Engine' | 'User Scenario';
  appreciationAssumptionPct: number;
}
