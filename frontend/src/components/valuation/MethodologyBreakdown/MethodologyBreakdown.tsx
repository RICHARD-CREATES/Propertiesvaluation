import React from 'react';
import { Panel, StatusTag } from '@/components/ui/Primitives';
import type { ValuationResponse } from '@/types/api';

export function MethodologyBreakdown({ data }: { data: ValuationResponse }) {
  const rec = data.income_approach_and_reconciliation.three_way_reconciliation;
  const app = rec.approaches || {};
  const erg = data.criteria_audit_28?.environmental_risk_gate;
  const za = data.zone_analysis;
  const loc = data.location_summary;

  const rows = [
    { name: 'Comparable Sales Approach', obj: app.approach_a_sales_comparison },
    { name: 'Depreciated Replacement Cost', obj: app.approach_b_cost_approach },
    { name: 'Income Capitalization Approach', obj: app.approach_c_income_capitalization },
  ];

  return (
    <div className="space-y-4">
      <Panel className="p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
          <div>
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              B. Methodology &amp; Three-Way Reconciliation
            </span>
            <h3 className="font-serif text-xl mt-0.5">Approach Weighting &amp; Divergence</h3>
          </div>
          <StatusTag tone="neutral">SPREAD: {rec.approach_divergence_pct}%</StatusTag>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] tech-label">
                <th className="py-2 pr-4">Valuation Approach</th>
                <th className="py-2 pr-4 text-right">Indicated Value</th>
                <th className="py-2 pr-4 text-right">Weight</th>
                <th className="py-2 text-right">Approach Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-hairline)] font-mono tabular-nums">
              {rows.map((r) => (
                <tr key={r.name}>
                  <td className="py-2.5 pr-4 font-sans font-medium text-[var(--text-primary)]">{r.name}</td>
                  <td className="py-2.5 pr-4 text-right">{r.obj?.value_formatted || 'N/A'}</td>
                  <td className="py-2.5 pr-4 text-right" style={{ color: 'var(--accent-copper)' }}>
                    {r.obj ? `${r.obj.weight_pct}%` : '--'}
                  </td>
                  <td className="py-2.5 text-right">{r.obj ? `${Math.round(r.obj.confidence * 100)}%` : '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel-elevated p-3 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <span>
            Reconciliation Anchor: <strong className="font-mono">{rec.reconciled_fair_market_value_formatted}</strong>
          </span>
          <span className="text-[11px] text-[var(--text-secondary)]">{rec.weighting_policy}</span>
        </div>
        {rec.divergence_explanations?.length > 0 && (
          <p className="text-[11px] text-[var(--text-secondary)]">{rec.divergence_explanations.join(' ')}</p>
        )}
      </Panel>

      {/* D. Location & Zoning + E. Risk Factors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Panel className="p-5 space-y-3 text-xs">
          <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
            D. Location &amp; Zoning Context
          </span>
          <div className="space-y-1.5 text-[var(--text-secondary)]">
            <div className="flex justify-between">
              <span>Micro-Market:</span>
              <strong className="text-[var(--text-primary)] text-right">{loc.locality}</strong>
            </div>
            <div className="flex justify-between">
              <span>Urban Density Tier:</span>
              <strong className="font-mono text-[var(--text-primary)]">{loc.density_tier}</strong>
            </div>
            <div className="flex justify-between">
              <span>Zone Status:</span>
              <strong className="font-mono text-emerald-400">{za.zone_classification}</strong>
            </div>
            <div className="flex justify-between">
              <span>Medical (Green) Active:</span>
              <strong className="font-mono">{za.active_green_facilities_count} (+{za.green_zone_land_uplift_pct}%)</strong>
            </div>
            <div className="flex justify-between">
              <span>Combined Corridor Adjustment:</span>
              <strong className="font-mono">+{za.total_zone_land_uplift_pct}%</strong>
            </div>
          </div>
          <p className="text-[11px] text-[var(--text-muted)] pt-2 border-t border-[var(--border-hairline)]">{za.zone_summary}</p>
        </Panel>

        <Panel className="p-5 space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              E. Risk Assessment &amp; Eligibility
            </span>
            {erg && (
              <StatusTag tone={erg.bank_loan_eligibility ? 'verified' : 'danger'}>
                {erg.bank_loan_eligibility ? 'LOAN ELIGIBLE' : 'HIGH RISK'}
              </StatusTag>
            )}
          </div>
          {erg && (
            <div className="space-y-1.5 text-[var(--text-secondary)]">
              <div className="flex justify-between">
                <span>Flood &amp; Waterlogging:</span>
                <strong className="font-mono">{erg.flood_risk_level} ({erg.flood_risk_adjustment})</strong>
              </div>
              <div className="flex justify-between">
                <span>Drainage Infrastructure:</span>
                <strong className="font-mono">{erg.drainage_infrastructure} ({erg.drainage_adjustment})</strong>
              </div>
              <div className="flex justify-between">
                <span>Groundwater Access:</span>
                <strong className="font-mono">{erg.groundwater_availability} ({erg.groundwater_adjustment})</strong>
              </div>
              <div className="flex justify-between">
                <span>Legal &amp; Litigation Gate:</span>
                <strong className="font-mono">{erg.litigation_encumbrance_status} ({erg.litigation_adjustment})</strong>
              </div>
            </div>
          )}
          <div className="pt-2 border-t border-[var(--border-hairline)] text-[11px] text-[var(--text-muted)]">
            {data.explainability.top_negative_factors?.length
              ? data.explainability.top_negative_factors.map((f) => `${f.driver} (${f.impact})`).join(' · ')
              : 'No negative structural or environmental deductions flagged.'}
          </div>
        </Panel>
      </div>
    </div>
  );
}
