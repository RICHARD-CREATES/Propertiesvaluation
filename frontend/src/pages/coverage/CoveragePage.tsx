import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { MetricCell, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';
import { MarketHeatmap } from '@/components/visualization/MarketHeatmap/MarketHeatmap';
import type { CoverageDashboardResponse, CoverageLocality } from '@/types/api';

export function CoveragePage() {
  const [coverage, setCoverage] = useState<CoverageDashboardResponse | null>(null);
  const [selectedLoc, setSelectedLoc] = useState<CoverageLocality | null>(null);

  const loadCoverage = async () => {
    try {
      const d = await api.getCoverageDashboard();
      setCoverage(d);
      if (d.localities?.length) setSelectedLoc(d.localities[0]);
    } catch {}
  };

  useEffect(() => {
    loadCoverage();
  }, []);

  return (
    <div id="workspace-coverage" className="space-y-6">
      <SectionHeader
        eyebrow="Workspace 09 · Ground-Truth Coverage Audit"
        title="Bhubaneswar Transaction Sufficiency & Data Integrity"
        subtitle="Localities with fewer than 5 verified Sub-Registrar or document-verified sales suppress medians cleanly to avoid false precision."
        right={
          <button
            type="button"
            onClick={loadCoverage}
            className="arch-btn px-3.5 py-1.5 font-mono text-xs border border-[var(--border-strong)] bg-[var(--bg-surface)]"
          >
            Refresh Live Coverage
          </button>
        }
      />

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <MetricCell label="Verified Sales" value={coverage?.verified_completed_sales_count ?? 0} accent="green" />
        <MetricCell label="Unverified / Broker" value={coverage?.unverified_or_broker_count ?? 0} accent="amber" />
        <MetricCell label="Review Flags" value={coverage?.data_quality_failures_or_reviews ?? 0} accent="rose" />
        <MetricCell
          label="Sufficient Localities"
          value={`${(coverage?.sufficiency_summary?.sufficient_localities_count || 0) + (coverage?.sufficiency_summary?.preliminary_localities_count || 0)} / ${(coverage?.localities || []).length}`}
        />
        <MetricCell label="Last Ingestion Run" value={coverage?.last_ingestion_run_at?.slice(0, 10) || 'No runs yet'} />
      </div>

      {coverage?.localities && (
        <Panel className="p-5">
          <MarketHeatmap
            localities={coverage.localities}
            selectedLocality={selectedLoc?.locality || null}
            onSelectLocality={setSelectedLoc}
          />
        </Panel>
      )}

      <Panel className="p-5 overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse font-mono tabular-nums">
          <thead>
            <tr className="border-b border-[var(--border-hairline)] tech-label">
              <th className="py-2 pr-3">Locality</th>
              <th className="py-2 pr-3">Sufficiency Status</th>
              <th className="py-2 pr-3 text-right">Verified</th>
              <th className="py-2 pr-3 text-right">Unverified</th>
              <th className="py-2 pr-3">Median PPSF</th>
              <th className="py-2">Limitations</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-hairline)]">
            {(coverage?.localities || []).map((loc) => (
              <tr key={loc.locality}>
                <td className="py-2.5 pr-3 font-sans font-semibold">{loc.locality}</td>
                <td className="py-2.5 pr-3">
                  <StatusTag
                    tone={
                      loc.sufficiency_status === 'SUFFICIENT_LOCAL_COVERAGE'
                        ? 'verified'
                        : loc.sufficiency_status === 'PRELIMINARY_DESCRIPTIVE_ONLY'
                          ? 'preliminary'
                          : 'insufficient'
                    }
                  >
                    {loc.sufficiency_status}
                  </StatusTag>
                </td>
                <td className="py-2.5 pr-3 text-right text-emerald-400">{loc.verified_transaction_count}</td>
                <td className="py-2.5 pr-3 text-right text-amber-400">{loc.unverified_or_broker_count}</td>
                <td className="py-2.5 pr-3">
                  {loc.verified_ppsf_distribution ? `INR ${loc.verified_ppsf_distribution.median.toLocaleString()}` : 'Suppressed (<5)'}
                </td>
                <td className="py-2.5 font-sans text-[11px] text-[var(--text-secondary)]">{(loc.limitations || []).join(' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
