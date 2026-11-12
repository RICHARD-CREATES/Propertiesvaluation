import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '@/App';

const MOCK_CONFIG = {
  default_location: { label: 'Powai / IIT Bombay, Mumbai', latitude: 19.1254, longitude: 72.9157, country_code: 'IN' },
  region_filters: [
    { id: 'featured', label: 'Featured' },
    { id: 'metros', label: 'Pan-India Metros' },
  ],
  location_presets: [
    { label: 'Powai / IIT Bombay, Mumbai', latitude: 19.1254, longitude: 72.9157, country_code: 'IN', region: 'metros' },
    { label: 'Whitefield IT Corridor, Bengaluru', latitude: 12.9698, longitude: 77.7499, country_code: 'IN', region: 'metros' },
  ],
  countries: [{ value: 'IN', label: 'India (INR)', default: true }],
  map_layers: [{ id: 'groad', label: 'Streets' }],
  asset_types: [
    { value: 'residential', label: 'Residential' },
    { value: 'commercial', label: 'Commercial' },
    { value: 'land', label: 'Land / Plot' },
  ],
  shap_property_types: [{ value: 'apartment', label: 'Apartment (XGBoost)', default: true }],
  selectors: {
    structure_type: [{ value: 'standalone_house', label: 'Standalone House / Villa' }],
    area_unit: [{ value: 'sqft', label: 'Square Feet (sq ft)' }],
    construction_grade: [{ value: 'GRADE_B', label: 'Grade B' }],
    commercial_type: [{ value: 'retail', label: 'Retail' }],
    locality_tier: [{ value: 'prime', label: 'Prime Civic Sector' }],
    road_width_ft: [{ value: '30ft', label: '30 ft Standard Road' }],
    furnishing: [{ value: 'semi_furnished', label: 'Semi-Furnished' }],
    parking_slots: [{ value: '1_covered', label: '1 Covered Slot' }],
    approval_status: [{ value: 'approved_freehold', label: 'Approved Freehold' }],
    corner_plot: [{ value: 'standard', label: 'Standard Frontage' }],
    maintenance_state: [{ value: 'well_maintained', label: 'Well Maintained' }],
    flood_risk: [{ value: 'none_low', label: 'Elevated Ground' }],
    drainage_infra: [{ value: 'underground_storm', label: 'Storm Sewer' }],
    groundwater_availability: [{ value: 'abundant', label: 'Abundant' }],
    litigation_risk: [{ value: 'clear_verified', label: 'Clear Title' }],
  },
};

const MOCK_ZONES = {
  latitude: 20.3533,
  longitude: 85.8266,
  city: 'Bhubaneswar',
  locality: 'Patia',
  state: 'Odisha',
  currency: 'INR',
  density_tier: 'Urban Core',
  base_land_rate_sqft: 7500,
  circle_rate_sqft: 4350,
  zone_analysis: {
    in_any_zone: true,
    in_green_zone: true,
    zone_classification: 'GREEN_MEDICAL_ZONE',
    zone_summary: 'Property lies inside Green Zone (Hospital / Medical Facilities).',
    green_zone_land_uplift_pct: 7,
    total_zone_land_uplift_pct: 16,
    land_rate_multiplier: 1.16,
    active_green_facilities_count: 2,
    nearest_green_facility: { name: 'KIMS Hospital', category: 'hospital_medical', zone_color: 'green', hex_color: '#22c55e', latitude: 20.3536, longitude: 85.8145, distance_km: 1.26, core_radius_m: 1500, zone_radius_m: 5000, inside_zone: true },
    green_zones: [],
  },
};

describe('PropIntel Architectural Frontend Workflows', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/api/platform/config')) {
          return new Response(JSON.stringify(MOCK_CONFIG), { status: 200 });
        }
        if (url.includes('/api/health')) {
          return new Response(JSON.stringify({ status: 'healthy', specialist_models_registered: 10, production_models_loaded: ['apartment'], database_connected: true, database_tables_count: 14, private_evidence_vault_ready: true }), { status: 200 });
        }
        if (url.includes('/api/property/zones')) {
          return new Response(JSON.stringify(MOCK_ZONES), { status: 200 });
        }
        if (url.includes('/api/property/location')) {
          return new Response(JSON.stringify({ city: 'Bhubaneswar', state: 'Odisha', country_code: 'IN', display_address: 'Patia, Bhubaneswar' }), { status: 200 });
        }
        if (url.includes('/api/coverage/bhubaneswar')) {
          return new Response(JSON.stringify({ city: 'Bhubaneswar', verified_completed_sales_count: 0, unverified_or_broker_count: 0, data_quality_failures_or_reviews: 0, last_ingestion_run_at: null, sufficiency_summary: { sufficient_localities_count: 0, preliminary_localities_count: 0, insufficient_localities_count: 1 }, verification_status_distribution: {}, source_type_distribution: {}, property_type_distribution: {}, localities: [{ locality: 'Patia', sufficiency_status: 'INSUFFICIENT_DATA', verified_transaction_count: 0, unverified_or_broker_count: 0, limitations: ['Awaiting verified deeds.'] }] }), { status: 200 });
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );
  });

  it('renders the standalone 3D landing hero without sidebar chrome first', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Understand the value beneath the surface.')).toBeInTheDocument();
    });
    expect(screen.getByText('Explore a Property')).toBeInTheDocument();
    expect(screen.getByText('View Market Intelligence')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Toggle sidebar/i })).not.toBeInTheDocument();
  });

  it('transitions from landing page into main website valuation workspace & gamified quiz', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Explore a Property')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Explore a Property'));
    await waitFor(
      () => {
        expect(screen.getByRole('button', { name: /Toggle sidebar/i })).toBeInTheDocument();
        expect(screen.getByText('Whitefield IT Corridor, Bengaluru')).toBeInTheDocument();
        expect(screen.getByText(/GREEN_MEDICAL_ZONE/)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    expect(screen.queryByText(/yellow/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Proceed to Property Quiz/i }));
    await waitFor(
      () => {
        expect(screen.getByText(/Interactive Appraisal Quiz/i)).toBeInTheDocument();
        expect(screen.getByText(/GATES CLEARED/i)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
  });

  it('enters main website via sidebar links for Rental Intelligence and Coverage', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText('Explore a Property')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Explore a Property'));
    await waitFor(() => expect(screen.getByRole('button', { name: /Rental Intelligence/i })).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.click(screen.getByRole('button', { name: /Rental Intelligence/i }));
    await waitFor(
      () => {
        expect(screen.getByText(/Income Capitalization, NOI & Sensitivity Lab/i)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );

    fireEvent.click(screen.getByRole('button', { name: /Data Coverage/i }));
    await waitFor(
      () => {
        expect(screen.getByText(/Bhubaneswar Transaction Sufficiency/i)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
  });
});
