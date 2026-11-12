import React, { Suspense, lazy, useState } from 'react';
import { Crosshair, Loader2, MapPin, Search } from 'lucide-react';
import { usePlatform } from '@/context/PlatformContext';
import { api } from '@/lib/api';
import { HonestNotice, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';
import { ValuationSummary } from '@/components/valuation/ValuationSummary/ValuationSummary';
import { MethodologyBreakdown } from '@/components/valuation/MethodologyBreakdown/MethodologyBreakdown';
import { ComparableEvidence } from '@/components/valuation/ComparableEvidence/ComparableEvidence';
import { ConfidencePanel } from '@/components/valuation/ConfidencePanel/ConfidencePanel';
import { PropertyQuizWizard } from '@/components/valuation/PropertyQuiz/PropertyQuizWizard';
import type { AddressSearchResult, SelectOption } from '@/types/api';

const SpatialMap = lazy(() =>
  import('@/components/visualization/SpatialMap/SpatialMap').then((m) => ({ default: m.SpatialMap })),
);
const PropertyScene = lazy(() =>
  import('@/components/visualization/PropertyScene/PropertyScene').then((m) => ({ default: m.PropertyScene })),
);

function DynamicSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (val: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="tech-label block mb-1">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className="arch-input text-xs">
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function ValuationPage() {
  const {
    config,
    location,
    updateLocation,
    zoneResponse,
    propertyDetails,
    setPropertyDetails,
    valuationResult,
    valuationLoading,
    valuationError,
    executeValuation,
    addCurrentToPortfolio,
    mlBenchmarks,
  } = usePlatform();

  const [stage, setStage] = useState<1 | 2 | 3 | 4>(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<AddressSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [regionFilter, setRegionFilter] = useState('featured');
  const [portfolioMsg, setPortfolioMsg] = useState<string | null>(null);

  const za = zoneResponse?.zone_analysis;
  const presets = config?.location_presets || [];
  const filteredPresets =
    regionFilter === 'featured'
      ? presets.slice(0, 12)
      : regionFilter === 'all'
        ? presets
        : presets.filter((p) => p.region === regionFilter);

  const selectors = config?.selectors || {};

  const handleAddressSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchAddress(searchQuery.trim());
      setSearchResults(res.results || []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleUseGps = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      updateLocation(pos.coords.latitude, pos.coords.longitude, location.countryCode, 'Current Browser GPS');
    });
  };

  const handleRunValuation = async () => {
    const res = await executeValuation();
    if (res) setStage(4);
  };

  const effectiveFloors = propertyDetails.asset_type === 'land' ? 1 : Math.max(propertyDetails.total_floors, 1);

  return (
    <div id="workspace-valuation" className="space-y-6">
      <SectionHeader
        eyebrow="Workspace 02 · Property Valuation Terminal"
        title="Property Appraisal & 3D Geometry"
        subtitle="Locate any property, complete the interactive property & environment gate quiz, inspect 3D massing, and compute three-way valuation."
        right={
          <div className="flex flex-wrap gap-2">
            {stage !== 1 && (
              <button
                type="button"
                onClick={() => setStage(1)}
                className="arch-btn px-3 py-2 text-xs font-mono border border-[var(--border-strong)] bg-[var(--bg-elevated)]"
              >
                ← Locate Property
              </button>
            )}
            <button
              id="btn-run"
              type="button"
              disabled={valuationLoading}
              onClick={handleRunValuation}
              className="arch-btn px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider flex items-center gap-2 disabled:opacity-60"
              style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
            >
              {valuationLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{valuationLoading ? 'Computing Appraisal...' : 'Execute Full Valuation'}</span>
            </button>
          </div>
        }
      />

      {valuationError && <HonestNotice tone="warning" title="Valuation API Validation Error" message={valuationError} />}

      {/* STAGE 1 — LOCATE PROPERTY */}
      {stage === 1 && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <Panel className="lg:col-span-5 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                Step 1 · Coordinates &amp; Address
              </span>
              <button
                type="button"
                onClick={handleUseGps}
                className="arch-btn px-2.5 py-1 text-[11px] font-mono border border-[var(--border-strong)] bg-[var(--bg-elevated)] flex items-center gap-1"
              >
                <Crosshair className="w-3 h-3" /> Use GPS
              </button>
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddressSearch()}
                placeholder="Search address, locality, landmark..."
                className="arch-input flex-1"
              />
              <button
                type="button"
                onClick={handleAddressSearch}
                className="arch-btn px-3 border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-xs font-mono flex items-center gap-1"
              >
                <Search className="w-3.5 h-3.5" /> {searching ? '...' : 'Find'}
              </button>
            </div>

            {searchResults.length > 0 && (
              <div className="space-y-1 max-h-36 overflow-y-auto border border-[var(--border-hairline)] p-1.5 bg-[var(--bg-input)]">
                {searchResults.map((r, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      updateLocation(r.latitude, r.longitude, location.countryCode, r.display_name);
                      setSearchResults([]);
                    }}
                    className="w-full text-left p-1.5 text-xs hover:bg-[var(--bg-elevated)] flex items-center gap-1.5"
                  >
                    <MapPin className="w-3 h-3 shrink-0 text-[var(--accent-copper)]" />
                    <span className="truncate">{r.display_name}</span>
                  </button>
                ))}
              </div>
            )}

            {/* Backend Directory Region Filters & Presets */}
            <div className="space-y-2 pt-2 border-t border-[var(--border-hairline)]">
              <div className="tech-label">Backend Location Directory</div>
              <div className="flex flex-wrap gap-1">
                {(config?.region_filters || []).map((rf) => (
                  <button
                    key={rf.id}
                    type="button"
                    onClick={() => setRegionFilter(rf.id)}
                    className={`arch-btn px-2 py-0.5 text-[10px] font-mono border ${
                      regionFilter === rf.id
                        ? 'border-[var(--accent-copper)] text-[var(--accent-copper)] bg-[var(--bg-elevated)]'
                        : 'border-[var(--border-hairline)] text-[var(--text-secondary)]'
                    }`}
                  >
                    {rf.label}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto">
                {filteredPresets.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => updateLocation(p.latitude, p.longitude, p.country_code, p.label)}
                    className="arch-btn px-2 py-1 text-[11px] border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label htmlFor="input-lat" className="tech-label block mb-1">
                  Latitude
                </label>
                <input
                  id="input-lat"
                  type="number"
                  step="0.0001"
                  value={location.latitude}
                  onChange={(e) => updateLocation(parseFloat(e.target.value) || 0, location.longitude)}
                  className="arch-input font-mono text-xs"
                />
              </div>
              <div>
                <label htmlFor="input-lon" className="tech-label block mb-1">
                  Longitude
                </label>
                <input
                  id="input-lon"
                  type="number"
                  step="0.0001"
                  value={location.longitude}
                  onChange={(e) => updateLocation(location.latitude, parseFloat(e.target.value) || 0)}
                  className="arch-input font-mono text-xs"
                />
              </div>
              <DynamicSelect
                id="input-country"
                label="Jurisdiction"
                value={location.countryCode}
                options={config?.countries || [{ value: 'IN', label: 'India (INR)' }]}
                onChange={(cc) => updateLocation(location.latitude, location.longitude, cc)}
              />
            </div>

            {/* Live Backend Zone Status Bar */}
            <div id="map-zone-status-bar" className="panel-elevated p-3 space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="tech-label">Medical Green Zone Telemetry</span>
                <StatusTag tone={za?.in_green_zone ? 'verified' : 'insufficient'}>
                  {za ? `${za.zone_classification} (${za.active_green_facilities_count} active)` : 'SYNCING'}
                </StatusTag>
              </div>
              <p className="text-[11px] text-[var(--text-secondary)]">
                {za?.zone_summary || 'Querying backend Green Medical facilities for active coordinate...'}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setStage(2)}
                className="arch-btn w-full py-2 font-mono text-xs font-semibold border border-[var(--border-strong)] bg-[var(--bg-elevated)]"
              >
                Proceed to Property Quiz →
              </button>
              <button
                type="button"
                onClick={() => setStage(3)}
                className="arch-btn w-full py-2 font-mono text-xs border border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[var(--text-secondary)]"
              >
                Inspect 3D Model
              </button>
            </div>
          </Panel>

          <Panel className="lg:col-span-7 p-2">
            <Suspense fallback={<div className="h-[460px] flex items-center justify-center font-mono text-xs">Loading MapLibre 3D Map...</div>}>
              <SpatialMap
                latitude={location.latitude}
                longitude={location.longitude}
                zoneAnalysis={za}
                onSelectCoord={(lat, lon) => updateLocation(lat, lon)}
                heightClass="h-[480px]"
              />
            </Suspense>
          </Panel>
        </div>
      )}

      {/* STAGE 2 — GAMIFIED PROPERTY ATTRIBUTES, PROFILE & ENVIRONMENT GATE QUIZ */}
      {stage === 2 && (
        <PropertyQuizWizard
          details={propertyDetails}
          selectors={selectors}
          assetTypes={config?.asset_types || []}
          onChange={setPropertyDetails}
          onInspect3D={() => setStage(3)}
          onExecuteValuation={handleRunValuation}
        />
      )}

      {/* STAGE 3 — INTERACTIVE 3D PROPERTY VISUALIZATION */}
      {stage === 3 && (
        <Panel className="p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[var(--border-hairline)]">
            <div>
              <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                Step 3 · Interactive Parametric Architecture Viewer
              </span>
              <h3 className="font-serif text-xl mt-0.5">Parcel Boundary, Floor Plates &amp; Zone Infrastructure</h3>
            </div>
            <button
              type="button"
              onClick={handleRunValuation}
              className="arch-btn px-4 py-2 font-mono text-xs font-semibold"
              style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
            >
              Run Valuation on This Model →
            </button>
          </div>
          <Suspense fallback={<div className="h-[460px] flex items-center justify-center font-mono text-xs">Loading Three.js Viewer...</div>}>
            <PropertyScene
              plotAreaSqft={propertyDetails.plot_area_sqft || propertyDetails.area_value}
              builtupAreaSqft={propertyDetails.area_value}
              floors={effectiveFloors}
              assetType={propertyDetails.asset_type}
              roadWidthFt={propertyDetails.road_width_ft}
              zoneAnalysis={za}
              heightClass="h-[460px]"
            />
          </Suspense>
        </Panel>
      )}

      {/* STAGE 4 — PROFESSIONAL RESEARCH REPORT */}
      {stage === 4 && (
        <div className="space-y-5">
          {!valuationResult ? (
            <HonestNotice
              tone="info"
              title="No Valuation Run Executed Yet"
              message="Click Execute Full Valuation in the top-right toolbar to generate the complete A–F research report from live backend models."
            />
          ) : (
            <>
              {portfolioMsg && <HonestNotice tone="success" title="Portfolio Updated" message={portfolioMsg} />}
              <ValuationSummary
                data={valuationResult}
                onAddToPortfolio={() => {
                  addCurrentToPortfolio();
                  setPortfolioMsg(`Added ${valuationResult.valuation_id} (${location.displayAddress}) to Portfolio Comparison.`);
                }}
              />
              <MethodologyBreakdown data={valuationResult} />
              <ComparableEvidence data={valuationResult} />
              <ConfidencePanel data={valuationResult} />

              {Object.keys(mlBenchmarks).length > 0 && (
                <Panel className="p-5 space-y-3">
                  <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                    Production Champion Model Cross-Checks (/api/v1/valuation/estimate)
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 text-xs font-mono">
                    {Object.entries(mlBenchmarks).map(([k, v]: [string, any]) => (
                      <div key={k} className="panel-elevated p-3">
                        <div className="tech-label">{k.replace(/_/g, ' ')}</div>
                        <div className="mt-1 font-semibold tabular-nums">
                          {v?.estimated_value_inr ? `INR ${Math.round(v.estimated_value_inr).toLocaleString()}` : 'DATA NOT READY'}
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
