import React from 'react';
import { MetricCell, Panel, StatusTag } from '@/components/ui/Primitives';
import type { ValuationResponse } from '@/types/api';

export function ValuationSummary({ data, onAddToPortfolio }: { data: ValuationResponse; onAddToPortfolio?: () => void }) {
  const { valuation: v, land_and_house_breakdown: bd, creation_cost_vs_current_price: c, explainability: ex } = data;
  const valDate = data.location_summary?.harvest_timestamp?.slice(0, 10) || new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-4">
      <Panel className="p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 pb-5 border-b border-[var(--border-hairline)]">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                A. Estimated Fair Market Value
              </span>
              <StatusTag tone="neutral">{v.currency}</StatusTag>
              <StatusTag tone="neutral">AS OF {valDate}</StatusTag>
            </div>
            <div id="res-fair-value" className="font-serif text-4xl sm:text-5xl tracking-tight tabular-nums">
              {v.fair_market_value_formatted}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-xs text-[var(--text-secondary)] tabular-nums">
              <span>LOWER: {v.valuation_interval.low_formatted}</span>
              <span className="text-[var(--text-muted)]">|</span>
              <span>UPPER: {v.valuation_interval.high_formatted}</span>
              <span className="text-[var(--text-muted)]">|</span>
              <span>SPREAD: ±{v.valuation_interval.margin_pct}%</span>
            </div>
          </div>

          <div className="flex flex-col items-start md:items-end gap-2">
            <div className="font-mono text-sm font-semibold tabular-nums" style={{ color: 'var(--accent-copper)' }}>
              {v.currency} {v.price_per_sqft.toLocaleString()} / sq ft
            </div>
            <div className="font-mono text-xs text-[var(--text-muted)] tabular-nums">
              {v.currency} {v.price_per_sqm.toLocaleString()} / sq m · {v.valuation_area_sqft.toLocaleString()} sq ft
            </div>
            <div className="flex flex-wrap gap-2 mt-1">
              {onAddToPortfolio && (
                <button
                  type="button"
                  onClick={onAddToPortfolio}
                  className="arch-btn px-3 py-1.5 text-[11px] font-mono border border-[var(--accent-copper)] text-[var(--accent-copper)] bg-[var(--bg-elevated)]"
                >
                  + Add to Portfolio
                </button>
              )}
              <a
                id="btn-download-html-report"
                href={`/api/property/valuation/${data.valuation_id}/report?format=html`}
                target="_blank"
                rel="noreferrer"
                className="arch-btn px-3 py-1.5 text-[11px] font-mono border border-[var(--border-strong)] bg-[var(--bg-elevated)] inline-flex items-center"
              >
                HTML Dossier
              </a>
              <a
                id="btn-download-json-report"
                href={`/api/property/valuation/${data.valuation_id}/report?format=json`}
                target="_blank"
                rel="noreferrer"
                className="arch-btn px-3 py-1.5 text-[11px] font-mono border border-[var(--border-strong)] bg-[var(--bg-elevated)] inline-flex items-center"
              >
                JSON Export
              </a>
            </div>
          </div>
        </div>

        {/* Stage 1 Land + Stage 2 Depreciated Building Decomposition */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-5">
          <div className="panel-elevated p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="tech-label">Stage 1 · Land Market Value</span>
              <span className="font-mono text-[11px] text-[var(--text-secondary)]">
                {v.currency} {bd.right_now_land_rate_sqft.toLocaleString()}/sqft
              </span>
            </div>
            <div className="font-mono text-2xl font-semibold tabular-nums">{bd.stage1_land_price_formatted}</div>
            <div className="text-[11px] text-[var(--text-secondary)] space-y-1 pt-2 border-t border-[var(--border-hairline)]">
              <div className="flex justify-between">
                <span>Effective Land Area:</span>
                <strong className="font-mono">{bd.effective_land_area_sqft} sq ft</strong>
              </div>
              <div className="flex justify-between">
                <span>Circle Rate Floor:</span>
                <strong className="font-mono">{v.currency} {bd.circle_rate_sqft.toLocaleString()}/sqft</strong>
              </div>
              <div className="flex justify-between">
                <span>Priority Zone Uplift:</span>
                <strong className="font-mono text-emerald-400">
                  {bd.zone_classification} (+{bd.zone_land_uplift_pct}%)
                </strong>
              </div>
            </div>
          </div>

          <div className="panel-elevated p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="tech-label">Stage 2 · Depreciated Structure</span>
              <span className="font-mono text-[11px] text-[var(--text-secondary)]">{bd.structure_type}</span>
            </div>
            <div className="font-mono text-2xl font-semibold tabular-nums">{bd.stage2_cost_of_house_formatted}</div>
            <div className="text-[11px] text-[var(--text-secondary)] space-y-1 pt-2 border-t border-[var(--border-hairline)]">
              <div className="flex justify-between">
                <span>Structure Replacement:</span>
                <strong className="font-mono">{bd.house_structure_cost_formatted}</strong>
              </div>
              <div className="flex justify-between">
                <span>Interiors &amp; Fit-Out:</span>
                <strong className="font-mono">{bd.house_fitout_cost_formatted}</strong>
              </div>
              <div className="flex justify-between">
                <span>Reserved Parking:</span>
                <strong className="font-mono">{bd.house_parking_cost_formatted}</strong>
              </div>
            </div>
          </div>
        </div>

        {/* Key Analytical Ratios */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4">
          <MetricCell label="Gross Rental Yield" value={`${data.rental_and_yield.gross_rental_yield_pct}%`} accent="green" />
          <MetricCell label="Est. Monthly Rent" value={data.rental_and_yield.estimated_monthly_rent} />
          <MetricCell label="3-Yr Outlook" value={`+${data.horizon_scenarios.projected_cagr_pct}% CAGR`} accent="copper" />
          <MetricCell label="Input Completeness" value={`${ex.data_completeness_pct}%`} />
        </div>
      </Panel>

      {/* Historical Cost vs Market Wealth */}
      <Panel className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
          <span className="tech-label">Historical Cost Basis vs Current Appraisal</span>
          <span className="font-mono text-[10px] text-[var(--text-muted)]">{c.cost_source}</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4">
          <MetricCell label="Creation Cost" value={c.original_creation_cost_formatted} subtext={c.historical_construction_rate_sqft} />
          <MetricCell label="Market Value Today" value={c.right_now_market_price_formatted} accent="green" />
          <MetricCell label="Capital Gain" value={`+${c.wealth_created_formatted}`} subtext={`${c.appreciation_multiple} (${c.historical_cagr_pct}% CAGR)`} />
          <MetricCell label="Rebuild Cost Today" value={c.replacement_cost_new_today} />
        </div>
      </Panel>
    </div>
  );
}
