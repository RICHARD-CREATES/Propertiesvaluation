import type {
  AddressSearchResult,
  AdminLoginResponse,
  AdminQueueItem,
  CoverageDashboardResponse,
  HealthResponse,
  PlatformConfigResponse,
  ValuationRequestPayload,
  ValuationResponse,
  ZonesApiResponse,
} from '@/types/api';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const text = await res.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = body?.detail ? (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)) : res.statusText;
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return body as T;
}

export const api = {
  getHealth: () => requestJson<HealthResponse>('/api/health'),

  getPlatformConfig: () => requestJson<PlatformConfigResponse>('/api/platform/config'),

  searchAddress: (query: string) =>
    requestJson<{ results: AddressSearchResult[] }>(`/api/property/search?query=${encodeURIComponent(query)}`),

  getZones: (latitude: number, longitude: number, countryCode = 'IN') =>
    requestJson<ZonesApiResponse>(
      `/api/property/zones?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}&country_code=${encodeURIComponent(countryCode)}`,
    ),

  resolveLocation: (latitude: number, longitude: number, countryCode = 'IN') =>
    requestJson<any>('/api/property/location', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latitude, longitude, country_code: countryCode }),
    }),

  runValuation: (payload: ValuationRequestPayload) =>
    requestJson<ValuationResponse>('/api/property/valuation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  getCoverageDashboard: () => requestJson<CoverageDashboardResponse>('/api/coverage/bhubaneswar'),

  getValidationDashboard: () => requestJson<any>('/api/validation/dashboard'),

  getAnalyticsDataQuality: () => requestJson<any>('/api/analytics/data-quality'),
  getAnalyticsEda: () => requestJson<any>('/api/analytics/eda'),
  getAnalyticsMicroMarkets: () => requestJson<any>('/api/analytics/micro-markets'),
  getAnalyticsDrivers: () => requestJson<any>('/api/analytics/drivers'),
  getAnalyticsSeasonality: () => requestJson<any>('/api/analytics/seasonality'),
  getAnalyticsExplain: (propertyType: string, areaSqft = 1450, plotSqft = 2400) =>
    requestJson<any>(
      `/api/analytics/explain?property_type=${encodeURIComponent(propertyType)}&builtup_area_sqft=${areaSqft}&plot_area_sqft=${plotSqft}`,
    ),

  getRentalComparables: (latitude: number, longitude: number, radiusKm = 5) =>
    requestJson<any>(
      `/api/rental/comparables?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}&radius_km=${radiusKm}`,
    ),

  getRentalSourceHealth: () => requestJson<any>('/api/rental/source-health'),

  getGroundTruthTransactions: () => requestJson<any>('/api/validation/ground-truth'),

  estimateV1: (params: {
    latitude: number;
    longitude: number;
    property_type: string;
    builtup_area_sqft: number;
    plot_area_sqft: number | null;
    state: string;
    city: string;
  }) =>
    requestJson<any>('/api/v1/valuation/estimate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),

  adminLogin: (username: string, password: string) =>
    requestJson<AdminLoginResponse>('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),

  getAdminReviewQueue: (token: string) =>
    requestJson<{ items: AdminQueueItem[] }>('/api/admin/review-queue', {
      headers: { Authorization: `Bearer ${token}` },
    }),

  getIngestionRuns: () => requestJson<any>('/api/ingestion/runs'),

  transitionVerification: (token: string, transactionId: string, targetStatus: string) =>
    requestJson<any>('/api/verification/transition', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        transaction_id: transactionId,
        target_status: targetStatus,
        verification_method: 'MANUAL_DEED_REVIEW',
        reason: `Reviewer action -> ${targetStatus}`,
      }),
    }),

  syncGroundTruth: (token: string) =>
    requestJson<any>('/api/admin/sync-ground-truth', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    }),

  ingestGovtBmv: (
    token: string,
    payload: { circular_or_query_ref: string; mouza: string; benchmark_value_inr: number; latitude: number; longitude: number },
  ) =>
    requestJson<any>('/api/ingestion/runs/govt-bmv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        source_reference: 'admin_manual_igrodisha_bmv',
        format_hint: 'json',
        payload: [
          {
            circular_or_query_ref: payload.circular_or_query_ref,
            mouza: payload.mouza,
            property_type: 'residential_land',
            benchmark_value_inr: payload.benchmark_value_inr,
            land_area_sqft: 2400,
            latitude: payload.latitude,
            longitude: payload.longitude,
          },
        ],
      }),
    }),
};
