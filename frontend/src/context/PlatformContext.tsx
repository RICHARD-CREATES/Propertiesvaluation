import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type {
  HealthResponse,
  PlatformConfigResponse,
  PortfolioPropertyItem,
  PropertyDetailsPayload,
  ValuationResponse,
  WorkspaceRoute,
  ZonesApiResponse,
} from '@/types/api';

interface LocationState {
  latitude: number;
  longitude: number;
  countryCode: string;
  accuracy: number;
  displayAddress: string;
}

interface PlatformContextValue {
  route: WorkspaceRoute;
  setRoute: (r: WorkspaceRoute) => void;
  theme: 'obsidian' | 'stone';
  toggleTheme: () => void;
  config: PlatformConfigResponse | null;
  health: HealthResponse | null;
  location: LocationState;
  updateLocation: (lat: number, lon: number, countryCode?: string, displayAddress?: string) => Promise<void>;
  zoneResponse: ZonesApiResponse | null;
  zoneLoading: boolean;
  propertyDetails: PropertyDetailsPayload;
  setPropertyDetails: React.Dispatch<React.SetStateAction<PropertyDetailsPayload>>;
  valuationResult: ValuationResponse | null;
  valuationLoading: boolean;
  valuationError: string | null;
  executeValuation: () => Promise<ValuationResponse | null>;
  portfolio: PortfolioPropertyItem[];
  addCurrentToPortfolio: (customLabel?: string) => void;
  updatePortfolioAppreciation: (id: string, pct: number) => void;
  removeFromPortfolio: (id: string) => void;
  adminToken: string | null;
  adminActor: { id: string; role: string } | null;
  setAdminSession: (token: string | null, actor: { id: string; role: string } | null) => void;
  mlBenchmarks: Record<string, any>;
}

const DEFAULT_DETAILS: PropertyDetailsPayload = {
  asset_type: 'residential',
  structure_type: 'standalone_house',
  area_value: 2000,
  area_unit: 'sqft',
  plot_area_sqft: 2400,
  bedrooms: 3,
  bathrooms: 3,
  property_age_years: 4,
  construction_grade: 'GRADE_B',
  floor_number: 1,
  total_floors: 3,
  commercial_type: 'retail',
  locality_tier: 'prime',
  road_width_ft: '30ft',
  corner_plot: 'standard',
  furnishing: 'semi_furnished',
  parking_slots: '1_covered',
  approval_status: 'approved_freehold',
  maintenance_state: 'well_maintained',
  original_cost_of_house: 0,
  flood_risk: 'none_low',
  drainage_infra: 'underground_storm',
  groundwater_availability: 'abundant',
  litigation_risk: 'clear_verified',
  monthly_rent_inr: 0,
  operating_expenses_annual: 0,
  vacancy_rate_pct: 5,
};

const PlatformContext = createContext<PlatformContextValue | null>(null);

export function PlatformProvider({ children }: { children: React.ReactNode }) {
  const [route, setRoute] = useState<WorkspaceRoute>('overview');
  const [theme, setTheme] = useState<'obsidian' | 'stone'>(() => {
    const saved =
      typeof window !== 'undefined'
        ? window.localStorage.getItem('propai_theme') || window.localStorage.getItem('propintel_theme')
        : null;
    return saved === 'stone' ? 'stone' : 'obsidian';
  });
  const [config, setConfig] = useState<PlatformConfigResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [location, setLocation] = useState<LocationState>({
    latitude: 19.1254,
    longitude: 72.9157,
    countryCode: 'IN',
    accuracy: 15,
    displayAddress: 'Powai / IIT Bombay, Mumbai, Maharashtra',
  });
  const [zoneResponse, setZoneResponse] = useState<ZonesApiResponse | null>(null);
  const [zoneLoading, setZoneLoading] = useState(false);
  const [propertyDetails, setPropertyDetails] = useState<PropertyDetailsPayload>(DEFAULT_DETAILS);
  const [valuationResult, setValuationResult] = useState<ValuationResponse | null>(null);
  const [valuationLoading, setValuationLoading] = useState(false);
  const [valuationError, setValuationError] = useState<string | null>(null);
  const [mlBenchmarks, setMlBenchmarks] = useState<Record<string, any>>({});
  const [portfolio, setPortfolio] = useState<PortfolioPropertyItem[]>([]);
  const [adminToken, setAdminToken] = useState<string | null>(null);
  const [adminActor, setAdminActor] = useState<{ id: string; role: string } | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    window.localStorage.setItem('propai_theme', theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'obsidian' ? 'stone' : 'obsidian'));
  }, []);

  const refreshZonesForCoords = useCallback(async (lat: number, lon: number, countryCode: string) => {
    setZoneLoading(true);
    try {
      const z = await api.getZones(lat, lon, countryCode);
      setZoneResponse(z);
    } catch {
      // keep previous state silently on abort/network hiccup
    } finally {
      setZoneLoading(false);
    }
  }, []);

  const updateLocation = useCallback(
    async (lat: number, lon: number, countryCode?: string, customLabel?: string) => {
      const cc = countryCode || location.countryCode || 'IN';
      setLocation((prev) => ({
        ...prev,
        latitude: Number(lat.toFixed(5)),
        longitude: Number(lon.toFixed(5)),
        countryCode: cc,
        displayAddress: customLabel || prev.displayAddress,
      }));
      await refreshZonesForCoords(lat, lon, cc);
      try {
        const resolved = await api.resolveLocation(lat, lon, cc);
        setLocation((prev) => ({
          ...prev,
          countryCode: resolved.country_code || cc,
          displayAddress: customLabel || resolved.display_address || `${resolved.city}, ${resolved.state}`,
        }));
      } catch {
        // fallback handled by zoneResponse
      }
    },
    [location.countryCode, refreshZonesForCoords],
  );

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [cfg, hlth] = await Promise.all([api.getPlatformConfig(), api.getHealth()]);
        if (!active) return;
        setConfig(cfg);
        setHealth(hlth);
        const def = cfg.default_location;
        if (def) {
          setLocation({
            latitude: def.latitude,
            longitude: def.longitude,
            countryCode: def.country_code,
            accuracy: 15,
            displayAddress: def.label,
          });
          refreshZonesForCoords(def.latitude, def.longitude, def.country_code);
        }
      } catch {
        // initial offline guard
      }
    })();
    return () => {
      active = false;
    };
  }, [refreshZonesForCoords]);

  const executeValuation = useCallback(async (): Promise<ValuationResponse | null> => {
    setValuationLoading(true);
    setValuationError(null);
    try {
      const res = await api.runValuation({
        location: {
          latitude: location.latitude,
          longitude: location.longitude,
          accuracy: location.accuracy,
          country_code: location.countryCode,
        },
        property_details: {
          ...propertyDetails,
          vacancy_rate_pct: propertyDetails.asset_type === 'land' ? null : propertyDetails.vacancy_rate_pct,
          monthly_rent_inr: propertyDetails.asset_type === 'land' ? 0 : propertyDetails.monthly_rent_inr,
          operating_expenses_annual: propertyDetails.asset_type === 'land' ? 0 : propertyDetails.operating_expenses_annual,
        },
      });
      setValuationResult(res);
      if (res.zone_analysis) {
        setZoneResponse((prev) =>
          prev
            ? { ...prev, zone_analysis: res.zone_analysis }
            : {
                latitude: location.latitude,
                longitude: location.longitude,
                city: res.location_summary.city,
                locality: res.location_summary.locality,
                state: res.location_summary.state,
                currency: res.location_summary.currency,
                density_tier: res.location_summary.density_tier,
                base_land_rate_sqft: res.location_summary.land_rate_sqft,
                circle_rate_sqft: res.location_summary.circle_rate_sqft,
                zone_analysis: res.zone_analysis,
              },
        );
      }

      // Query category ML benchmarks concurrently
      const catList = ['apartment', 'house', 'residential_land', 'commercial', 'rental'];
      const benchEntries = await Promise.all(
        catList.map(async (cat) => {
          try {
            const b = await api.estimateV1({
              latitude: location.latitude,
              longitude: location.longitude,
              property_type: cat,
              builtup_area_sqft: propertyDetails.area_value,
              plot_area_sqft: propertyDetails.plot_area_sqft || propertyDetails.area_value,
              state: res.location_summary?.state || 'Odisha',
              city: res.location_summary?.city || 'Bhubaneswar',
            });
            return [cat, b] as const;
          } catch {
            return [cat, null] as const;
          }
        }),
      );
      setMlBenchmarks(Object.fromEntries(benchEntries.filter(([, v]) => v !== null)));
      return res;
    } catch (e: any) {
      setValuationError(e?.message || 'Valuation API error');
      return null;
    } finally {
      setValuationLoading(false);
    }
  }, [location, propertyDetails]);

  const addCurrentToPortfolio = useCallback(
    (customLabel?: string) => {
      if (!valuationResult) return;
      const item: PortfolioPropertyItem = {
        id: valuationResult.valuation_id,
        label: customLabel || location.displayAddress,
        latitude: location.latitude,
        longitude: location.longitude,
        assetType: propertyDetails.asset_type,
        areaSqft: valuationResult.valuation.valuation_area_sqft,
        fairMarketValue: valuationResult.valuation.fair_market_value,
        fairMarketValueFormatted: valuationResult.valuation.fair_market_value_formatted,
        pricePerSqft: valuationResult.valuation.price_per_sqft,
        monthlyRent: valuationResult.income_approach_and_reconciliation.income_valuation.achievable_monthly_rent,
        grossYieldPct: valuationResult.rental_and_yield.gross_rental_yield_pct,
        zoneClassification: valuationResult.zone_analysis.zone_classification,
        confidenceTier: valuationResult.evidence_and_uncertainty.evidence_quality.confidence_tier,
        sourceBasis: 'Sourced Valuation Engine',
        appreciationAssumptionPct: valuationResult.horizon_scenarios.projected_cagr_pct || 8.0,
      };
      setPortfolio((prev) => {
        if (prev.some((p) => p.id === item.id)) return prev;
        return [item, ...prev];
      });
    },
    [location, propertyDetails.asset_type, valuationResult],
  );

  const updatePortfolioAppreciation = useCallback((id: string, pct: number) => {
    setPortfolio((prev) =>
      prev.map((p) => (p.id === id ? { ...p, appreciationAssumptionPct: pct, sourceBasis: 'User Scenario' } : p)),
    );
  }, []);

  const removeFromPortfolio = useCallback((id: string) => {
    setPortfolio((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const setAdminSession = useCallback((token: string | null, actor: { id: string; role: string } | null) => {
    setAdminToken(token);
    setAdminActor(actor);
  }, []);

  return (
    <PlatformContext.Provider
      value={{
        route,
        setRoute,
        theme,
        toggleTheme,
        config,
        health,
        location,
        updateLocation,
        zoneResponse,
        zoneLoading,
        propertyDetails,
        setPropertyDetails,
        valuationResult,
        valuationLoading,
        valuationError,
        executeValuation,
        portfolio,
        addCurrentToPortfolio,
        updatePortfolioAppreciation,
        removeFromPortfolio,
        adminToken,
        adminActor,
        setAdminSession,
        mlBenchmarks,
      }}
    >
      {children}
    </PlatformContext.Provider>
  );
}

export function usePlatform() {
  const ctx = useContext(PlatformContext);
  if (!ctx) throw new Error('usePlatform must be used inside PlatformProvider');
  return ctx;
}
