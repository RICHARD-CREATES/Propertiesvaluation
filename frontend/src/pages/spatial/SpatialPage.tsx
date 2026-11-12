import React, { Suspense, lazy, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { usePlatform } from '@/context/PlatformContext';
import { HonestNotice, MetricCell, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';
import { MarketHeatmap } from '@/components/visualization/MarketHeatmap/MarketHeatmap';
import type { CoverageDashboardResponse, CoverageLocality } from '@/types/api';

const SpatialMap = lazy(() =>
  import('@/components/visualization/SpatialMap/SpatialMap').then((m) => ({ default: m.SpatialMap })),
);

export function SpatialPage() {
  const { location, updateLocation, zoneResponse } = usePlatform();
  const [coverage, setCoverage] = useState<CoverageDashboardResponse | null>(null);
  const [selectedLocality, setSelectedLocality] = useState<CoverageLocality | null>(null);
  const [rentalStats, setRentalStats] = useState<any>(null);
  const [show3D, setShow3D] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const cov = await api.getCoverageDashboard();
        if (!active) return;
        setCoverage(cov);
        if (cov.localities?.length > 0) setSelectedLocality(cov.localities[0]);
      } catch {}
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const rc = await api.getRentalComparables(location.latitude, location.longitude, 5);
        if (active) setRentalStats(rc);
      } catch {}
    })();
    return () => {
      active = false;
    };
  }, [location.latitude, location.longitude]);

  const handleSelectLocality = (loc: CoverageLocality) => {
    setSelectedLocality(loc);
    if (loc.coordinates) {
      updateLocation(loc.coordinates.latitude, loc.coordinates.longitude, 'IN', `${loc.locality}, Bhubaneswar`);
    }
  };

  const za = zoneResponse?.zone_analysis;
  const localityMarkers = (coverage?.localities || [])
    .filter((l) => l.coordinates)
    .map((l) => ({
      latitude: l.coordinates!.latitude,
      longitude: l.coordinates!.longitude,
      label: `${l.locality} (${l.sufficiency_status})`,
      color: l.sufficiency_status === 'SUFFICIENT_LOCAL_COVERAGE' ? '#22c55e' : '#eab308',
    }));

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Workspace 03 · 3D Spatial Intelligence"
        title="Urban Context, Zones & Locality Evidence Explorer"
        subtitle="Explore extruded spatial massing, medical and transit/education/working hub zones, and locality market sufficiency without fabricated spatial records."
        right={
          <button
            type="button"
            onClick={() => setShow3D((s) => !s)}
            className="arch-btn px-3 py-1.5 font-mono text-xs border border-[var(--border-strong)] bg-[var(--bg-surface)]"
          >
            3D Massing: {show3D ? 'ON' : 'OFF'}
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Main 3D MapLibre Explorer */}
        <Panel className="lg:col-span-8 p-2 space-y-3">
          <Suspense fallback={<div className="h-[480px] flex items-center justify-center font-mono text-xs">Loading MapLibre 3D Spatial Twin...</div>}>
            <SpatialMap
              latitude={location.latitude}
              longitude={location.longitude}
              zoneAnalysis={za}
              show3DBuildings={show3D}
              onSelectCoord={(lat, lon) => updateLocation(lat, lon)}
              extraMarkers={localityMarkers}
              heightClass="h-[480px]"
            />
          </Suspense>
          {coverage?.localities && (
            <div className="p-2">
              <MarketHeatmap
                localities={coverage.localities}
                selectedLocality={selectedLocality?.locality || null}
                onSelectLocality={handleSelectLocality}
              />
            </div>
          )}
        </Panel>

        {/* Right-Side Locality Information Panel */}
        <Panel className="lg:col-span-4 p-5 space-y-4">
          <div className="pb-3 border-b border-[var(--border-hairline)]">
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              Selected Locality Intelligence
            </span>
            <h3 className="font-serif text-2xl mt-0.5">{selectedLocality?.locality || zoneResponse?.city || 'Pin Location'}</h3>
            <p className="font-mono text-[11px] text-[var(--text-muted)] mt-0.5">
              {location.latitude.toFixed(4)}° N · {location.longitude.toFixed(4)}° E
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <MetricCell label="Verified Sales" value={selectedLocality?.verified_transaction_count ?? 0} accent="green" />
            <MetricCell label="Unverified Sources" value={selectedLocality?.unverified_or_broker_count ?? 0} accent="amber" />
            <MetricCell
              label="Verified Median PPSF"
              value={
                selectedLocality?.verified_ppsf_distribution
                  ? `INR ${selectedLocality.verified_ppsf_distribution.median.toLocaleString()}`
                  : 'SUPPRESSED (<5)'
              }
            />
            <MetricCell
              label="Zone Land Uplift"
              value={za?.in_any_zone ? `+${za.total_zone_land_uplift_pct}%` : '0.0%'}
              accent="copper"
            />
          </div>

          {/* Zone Breakdown */}
          <div className="panel-elevated p-3.5 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="tech-label">Medical Green Zone Context</span>
              <StatusTag tone={za?.in_green_zone ? 'verified' : 'insufficient'}>
                {za?.zone_classification || 'CHECKING'}
              </StatusTag>
            </div>
            <div className="flex justify-between text-[var(--text-secondary)]">
              <span>Nearest Medical (Green):</span>
              <strong className="font-mono text-right">{za?.nearest_green_facility?.name || 'None'}</strong>
            </div>
          </div>

          {/* Rental Indicators */}
          <div className="panel-elevated p-3.5 space-y-1.5 text-xs">
            <span className="tech-label block">Rental Indicators (5 km)</span>
            <div className="flex justify-between text-[var(--text-secondary)]">
              <span>Local Comps Count:</span>
              <strong className="font-mono">{rentalStats?.comparables?.length ?? 0}</strong>
            </div>
            <div className="flex justify-between text-[var(--text-secondary)]">
              <span>Data Confidence:</span>
              <strong className="font-mono">{rentalStats?.data_confidence_label || 'CHECKING'}</strong>
            </div>
            <div className="flex justify-between text-[var(--text-secondary)]">
              <span>Last Data Update:</span>
              <strong className="font-mono">{coverage?.last_ingestion_run_at?.slice(0, 10) || 'No runs yet'}</strong>
            </div>
          </div>

          {selectedLocality?.limitations && selectedLocality.limitations.length > 0 && (
            <HonestNotice
              tone="warning"
              title="Coverage & Data Sufficiency Warning"
              message={selectedLocality.limitations.join(' ')}
            />
          )}
        </Panel>
      </div>
    </div>
  );
}
