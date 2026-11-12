import React, { Suspense, lazy, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { usePlatform } from '@/context/PlatformContext';
import { HonestNotice, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';

const SpatialMap = lazy(() =>
  import('@/components/visualization/SpatialMap/SpatialMap').then((m) => ({ default: m.SpatialMap })),
);

function verificationStyle(status: string): 'verified' | 'preliminary' | 'insufficient' {
  const s = (status || '').toUpperCase();
  if (s.includes('REGISTRATION_VERIFIED') || s.includes('DOCUMENT_VERIFIED')) return 'verified';
  if (s.includes('SOURCE_CONFIRMED') || s.includes('BROKER') || s.includes('BENCHMARK')) return 'preliminary';
  return 'insufficient';
}

export function ComparablesPage() {
  const { location, zoneResponse, valuationResult } = usePlatform();
  const [groundTruth, setGroundTruth] = useState<any[]>([]);
  const [rentalComps, setRentalComps] = useState<any[]>([]);
  const [selectedCoord, setSelectedCoord] = useState<{ latitude: number; longitude: number } | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [gt, rc] = await Promise.all([
          api.getGroundTruthTransactions(),
          api.getRentalComparables(location.latitude, location.longitude, 10),
        ]);
        if (!active) return;
        setGroundTruth(gt?.records || gt?.transactions || []);
        setRentalComps(rc?.comparables || []);
      } catch {}
    })();
    return () => {
      active = false;
    };
  }, [location.latitude, location.longitude]);

  const combinedRows = [
    ...groundTruth.map((g: any, idx: number) => ({
      id: g.id || `GT-${idx}`,
      type: g.property_type || 'residential',
      locality: g.locality || 'Unknown',
      distanceKm: g.distance_km ?? '--',
      priceLabel: g.sale_price ? `INR ${Number(g.sale_price).toLocaleString()}` : 'N/A (Benchmark Ref)',
      areaSqft: g.builtup_area_sqft || g.land_area_sqft || '--',
      ppsf: g.price_per_sqft ? `INR ${Math.round(g.price_per_sqft).toLocaleString()}` : '--',
      date: g.transaction_date || '--',
      sourceType: g.source_name || 'Ground Truth',
      status: g.verification_status || 'UNVERIFIED',
      reference: g.document_reference || 'Pending',
      lat: g.latitude,
      lon: g.longitude,
    })),
    ...rentalComps.map((r: any, idx: number) => ({
      id: `RENT-${idx}`,
      type: r.property_type || 'rental',
      locality: r.locality || 'Local Comp',
      distanceKm: r.distance_km ?? '--',
      priceLabel: `INR ${Number(r.monthly_rent_inr || 0).toLocaleString()}/mo`,
      areaSqft: r.builtup_area_sqft || '--',
      ppsf: r.rent_per_sqft ? `INR ${r.rent_per_sqft}/sqft` : '--',
      date: r.observed_at?.slice(0, 10) || 'Recent',
      sourceType: r.source_name || 'Rental Registry',
      status: r.data_category || 'UNVERIFIED_LISTING',
      reference: r.source_id || 'RMDC-Lease',
      lat: r.latitude,
      lon: r.longitude,
    })),
  ];

  const markers = combinedRows
    .filter((r) => typeof r.lat === 'number' && typeof r.lon === 'number')
    .map((r) => ({
      latitude: r.lat,
      longitude: r.lon,
      label: `${r.locality} · ${r.priceLabel} (${r.status})`,
      color: verificationStyle(r.status) === 'verified' ? '#22c55e' : '#eab308',
    }));

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Workspace 05 · Comparable Evidence Explorer"
        title="Source-Segregated Evidence Map & Registry Table"
        subtitle="Inspect every sales deed, government benchmark reference, or lease record by verification status, distance, and source provenance."
      />

      {combinedRows.length === 0 && (
        <HonestNotice
          tone="warning"
          title="Zero Sourced Comparables in Vault for Current Radius"
          message={`Active ground-truth deeds: ${groundTruth.length}. Valuation ID ${valuationResult?.valuation_id || 'N/A'} relies on backend circle-rate ratios and municipal anchor schedules rather than synthetic comparables.`}
        />
      )}

      <Panel className="p-2">
        <Suspense fallback={<div className="h-[340px] flex items-center justify-center font-mono text-xs">Loading Evidence Map...</div>}>
          <SpatialMap
            latitude={location.latitude}
            longitude={location.longitude}
            zoneAnalysis={zoneResponse?.zone_analysis}
            highlightedCoord={selectedCoord}
            extraMarkers={markers}
            show3DBuildings={false}
            heightClass="h-[340px]"
          />
        </Suspense>
      </Panel>

      <Panel className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
          <span className="tech-label">Comparable Evidence Ledger ({combinedRows.length} Records)</span>
          <div className="flex flex-wrap gap-2">
            <StatusTag tone="verified">Registration / Document Verified</StatusTag>
            <StatusTag tone="preliminary">Broker / Govt Reference</StatusTag>
            <StatusTag tone="insufficient">Unverified Listing</StatusTag>
          </div>
        </div>
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-left text-xs border-collapse font-mono tabular-nums">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] tech-label">
                <th className="py-2 pr-3">Property Type</th>
                <th className="py-2 pr-3">Locality</th>
                <th className="py-2 pr-3 text-right">Distance</th>
                <th className="py-2 pr-3 text-right">Price / Rent</th>
                <th className="py-2 pr-3 text-right">Area</th>
                <th className="py-2 pr-3">Date</th>
                <th className="py-2 pr-3">Verification Tier</th>
                <th className="py-2">Reference</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-hairline)]">
              {combinedRows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center font-sans text-[var(--text-muted)]">
                    No comparable rows ingested for this coordinate yet.
                  </td>
                </tr>
              ) : (
                combinedRows.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => {
                      if (typeof row.lat === 'number' && typeof row.lon === 'number') {
                        setSelectedCoord({ latitude: row.lat, longitude: row.lon });
                      }
                    }}
                    className="cursor-pointer hover:bg-[var(--bg-elevated)]"
                  >
                    <td className="py-2.5 pr-3 font-sans">{row.type}</td>
                    <td className="py-2.5 pr-3 font-sans font-medium">{row.locality}</td>
                    <td className="py-2.5 pr-3 text-right">{row.distanceKm} km</td>
                    <td className="py-2.5 pr-3 text-right">{row.priceLabel}</td>
                    <td className="py-2.5 pr-3 text-right">{row.areaSqft}</td>
                    <td className="py-2.5 pr-3">{row.date}</td>
                    <td className="py-2.5 pr-3">
                      <StatusTag tone={verificationStyle(row.status)}>{row.status}</StatusTag>
                    </td>
                    <td className="py-2.5 text-[var(--text-muted)]">{row.reference}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
