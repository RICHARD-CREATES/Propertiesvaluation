import React from 'react';
import type { CoverageLocality } from '@/types/api';

interface MarketHeatmapProps {
  localities: CoverageLocality[];
  selectedLocality: string | null;
  onSelectLocality: (loc: CoverageLocality) => void;
}

export function MarketHeatmap({ localities, selectedLocality, onSelectLocality }: MarketHeatmapProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px] font-mono text-[var(--text-secondary)]">
        <span>LOCALITY EVIDENCE SUFFICIENCY MATRIX</span>
        <span>{localities.length} TRACKED ZONES</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
        {localities.map((loc) => {
          const isSelected = selectedLocality === loc.locality;
          const color =
            loc.sufficiency_status === 'SUFFICIENT_LOCAL_COVERAGE'
              ? '#22c55e'
              : loc.sufficiency_status === 'PRELIMINARY_DESCRIPTIVE_ONLY'
                ? '#eab308'
                : '#6e7681';
          return (
            <button
              key={loc.locality}
              type="button"
              onClick={() => onSelectLocality(loc)}
              className={`arch-btn p-2.5 text-left border ${
                isSelected
                  ? 'border-[var(--accent-copper)] bg-[var(--bg-elevated)]'
                  : 'border-[var(--border-hairline)] bg-[var(--bg-surface)] hover:border-[var(--border-strong)]'
              }`}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-xs font-semibold truncate">{loc.locality}</span>
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
              </div>
              <div className="mt-1.5 font-mono text-[10px] text-[var(--text-muted)] tabular-nums">
                VERIFIED: {loc.verified_transaction_count} · UNVER: {loc.unverified_or_broker_count}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
