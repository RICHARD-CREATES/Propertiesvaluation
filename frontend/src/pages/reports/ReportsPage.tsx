import React, { Suspense, lazy } from 'react';
import { Printer } from 'lucide-react';
import { usePlatform } from '@/context/PlatformContext';
import { HonestNotice, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';

const PropertyScene = lazy(() =>
  import('@/components/visualization/PropertyScene/PropertyScene').then((m) => ({ default: m.PropertyScene })),
);

export function ReportsPage() {
  const { valuationResult, propertyDetails, location, setRoute } = usePlatform();

  if (!valuationResult) {
    return (
      <div className="space-y-6">
        <SectionHeader
          eyebrow="Workspace 08 · Research Valuation Dossier"
          title="Downloadable Property Valuation Report"
          subtitle="Structured institutional appraisal memorandum with methodology reconciliation, risk disclosures, and evidence audit."
        />
        <HonestNotice
          tone="info"
          title="No Active Valuation Dossier"
          message="Execute a property valuation first to preview the structured research report and export signed HTML or JSON records."
        />
        <button
          type="button"
          onClick={() => setRoute('valuation')}
          className="arch-btn px-4 py-2 font-mono text-xs font-semibold"
          style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
        >
          Go to Property Valuation →
        </button>
      </div>
    );
  }

  const v = valuationResult.valuation;
  const bd = valuationResult.land_and_house_breakdown;
  const eu = valuationResult.evidence_and_uncertainty;
  const valDate = valuationResult.location_summary?.harvest_timestamp?.slice(0, 10) || new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow={`Dossier · ${valuationResult.valuation_id}`}
        title="Institutional Property Valuation Research Report"
        subtitle={`Prepared ${valDate} · ${location.displayAddress}`}
        right={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => window.print()}
              className="arch-btn px-3 py-1.5 font-mono text-xs border border-[var(--border-strong)] bg-[var(--bg-surface)] flex items-center gap-1.5"
            >
              <Printer className="w-3.5 h-3.5" /> Print / Save PDF
            </button>
            <a
              id="btn-download-html-report"
              href={`/api/property/valuation/${valuationResult.valuation_id}/report?format=html`}
              target="_blank"
              rel="noreferrer"
              className="arch-btn px-3 py-1.5 font-mono text-xs border border-[var(--accent-copper)] text-[var(--accent-copper)] bg-[var(--bg-surface)] inline-flex items-center"
            >
              Download HTML
            </a>
            <a
              id="btn-download-json-report"
              href={`/api/property/valuation/${valuationResult.valuation_id}/report?format=json`}
              target="_blank"
              rel="noreferrer"
              className="arch-btn px-3 py-1.5 font-mono text-xs border border-[var(--border-strong)] bg-[var(--bg-surface)] inline-flex items-center"
            >
              JSON Dossier
            </a>
          </div>
        }
      />

      <Panel className="p-6 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-5 border-b border-[var(--border-hairline)]">
          <div>
            <div className="tech-label">VALUATION OPINION</div>
            <div className="font-serif text-4xl sm:text-5xl mt-1 tabular-nums">{v.fair_market_value_formatted}</div>
            <p className="font-mono text-xs text-[var(--text-secondary)] mt-1">
              Range: {v.valuation_interval.low_formatted} — {v.valuation_interval.high_formatted} ({v.currency})
            </p>
          </div>
          <div className="text-xs font-mono space-y-1 sm:text-right">
            <div>VALUATION DATE: {valDate}</div>
            <div>COORDINATES: {location.latitude.toFixed(5)}° N, {location.longitude.toFixed(5)}° E</div>
            <StatusTag tone={eu.evidence_quality.confidence_tier === 'HIGH' ? 'verified' : 'insufficient'}>
              {eu.evidence_quality.confidence_tier}
            </StatusTag>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-6">
            <Suspense fallback={<div className="h-[300px] flex items-center justify-center font-mono text-xs">Loading 3D Exhibit...</div>}>
              <PropertyScene
                plotAreaSqft={propertyDetails.plot_area_sqft || propertyDetails.area_value}
                builtupAreaSqft={propertyDetails.area_value}
                floors={Math.max(propertyDetails.total_floors, 1)}
                assetType={propertyDetails.asset_type}
                roadWidthFt={propertyDetails.road_width_ft}
                zoneAnalysis={valuationResult.zone_analysis}
                heroMode
                heightClass="h-[300px]"
              />
            </Suspense>
          </div>

          <div className="lg:col-span-6 space-y-3 text-xs">
            <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              Property &amp; Financial Exhibit
            </div>
            <div className="divide-y divide-[var(--border-hairline)] font-mono">
              {[
                ['Asset Classification', `${v.asset_type} (${bd.structure_type})`],
                ['Effective Land Area', `${bd.effective_land_area_sqft} sq ft`],
                ['Built-Up Valuation Area', `${v.valuation_area_sqft.toLocaleString()} sq ft (${v.valuation_area_sqm} sq m)`],
                ['Stage 1 Land Price', `${bd.stage1_land_price_formatted} @ ${v.currency} ${bd.right_now_land_rate_sqft}/sqft`],
                ['Stage 2 Building Cost', bd.stage2_cost_of_house_formatted],
                ['Zone Classification', `${bd.zone_classification} (+${bd.zone_land_uplift_pct}%)`],
                ['Gross Rental Yield', `${valuationResult.rental_and_yield.gross_rental_yield_pct}% (${valuationResult.rental_and_yield.estimated_monthly_rent}/mo)`],
                ['Bank Loan Eligibility', bd.bank_loan_eligibility ? 'ELIGIBLE' : 'RESTRICTED'],
              ].map(([k, val]) => (
                <div key={k} className="py-2 flex justify-between gap-2">
                  <span className="font-sans text-[var(--text-secondary)]">{k}</span>
                  <strong className="text-right">{val}</strong>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Data Sources & Limitations */}
        <div className="pt-4 border-t border-[var(--border-hairline)] grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div>
            <div className="tech-label mb-2">Sources Queried</div>
            <div className="grid grid-cols-2 gap-1.5 font-mono text-[11px]">
              {Object.entries(valuationResult.sources_status || {}).map(([k, s]) => (
                <div key={k} className="panel-elevated p-2 flex justify-between">
                  <span>{k}</span>
                  <span className="text-emerald-400 uppercase">{s.status}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="tech-label mb-2">Confidence &amp; Limitations Disclosure</div>
            <p className="text-[var(--text-secondary)] leading-relaxed">
              {(eu.evidence_quality.reasons_for_low_confidence || []).join(' ') || 'Verified sources satisfied.'}{' '}
              {(eu.calibrated_prediction_interval.evidence_limitations || []).join(' ')}
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
