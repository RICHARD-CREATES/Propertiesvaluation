import React, { useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { usePlatform } from '@/context/PlatformContext';
import { HonestNotice, MetricCell, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';

export function PortfolioPage() {
  const { portfolio, valuationResult, addCurrentToPortfolio, updatePortfolioAppreciation, removeFromPortfolio } = usePlatform();
  const [horizonYears, setHorizonYears] = useState(5);

  const totalCapital = portfolio.reduce((sum, p) => sum + p.fairMarketValue, 0);
  const weightedYield =
    totalCapital > 0 ? portfolio.reduce((sum, p) => sum + p.fairMarketValue * p.grossYieldPct, 0) / totalCapital : 0;

  const chartData = portfolio.map((p) => {
    const projected = p.fairMarketValue * Math.pow(1 + p.appreciationAssumptionPct / 100, horizonYears);
    return {
      name: p.label.split(',')[0].slice(0, 18),
      currentCr: Number((p.fairMarketValue / 1e7).toFixed(2)),
      projectedCr: Number((projected / 1e7).toFixed(2)),
    };
  });

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Workspace 07 · Multi-Asset Portfolio Analysis"
        title="Cross-Market Property Comparison & Exposure Scenarios"
        subtitle="Compare multiple appraised properties side by side with explicit badges distinguishing sourced engine values from user-edited scenario assumptions."
        right={
          valuationResult && (
            <button
              type="button"
              onClick={() => addCurrentToPortfolio()}
              className="arch-btn px-4 py-2 font-mono text-xs font-semibold"
              style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
            >
              + Add Active Appraisal
            </button>
          )
        }
      />

      {portfolio.length === 0 ? (
        <HonestNotice
          tone="info"
          title="Portfolio Comparison Basket Is Empty"
          message="Appraise properties in Property Valuation and click '+ Add to Portfolio' to compare capital allocation, rental yields, zone classification, and multi-year scenarios."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCell label="Assets Tracked" value={portfolio.length} />
            <MetricCell label="Total Portfolio Value" value={`INR ${(totalCapital / 1e7).toFixed(2)} Cr`} accent="copper" />
            <MetricCell label="Weighted Gross Yield" value={`${weightedYield.toFixed(2)}%`} accent="green" />
            <MetricCell
              label="Scenario Horizon"
              value={`${horizonYears} Years`}
              subtext="User scenario editable below"
            />
          </div>

          <Panel className="p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
              <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                Current Valuation vs {horizonYears}-Year Scenario (INR Cr)
              </span>
              <div className="flex items-center gap-2 text-xs font-mono">
                <span>Horizon:</span>
                {[1, 3, 5].map((y) => (
                  <button
                    key={y}
                    type="button"
                    onClick={() => setHorizonYears(y)}
                    className={`arch-btn px-2 py-0.5 border ${
                      horizonYears === y ? 'border-[var(--accent-copper)] text-[var(--accent-copper)]' : 'border-[var(--border-hairline)]'
                    }`}
                  >
                    {y}Y
                  </button>
                ))}
              </div>
            </div>

            <div className="h-[260px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis dataKey="name" tick={{ fill: '#9ba3ae', fontSize: 11 }} />
                  <YAxis unit=" Cr" tick={{ fill: '#9ba3ae', fontSize: 11 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#111419', border: '1px solid rgba(255,255,255,0.16)', fontSize: 12 }} />
                  <Bar dataKey="currentCr" name="Engine Value" fill="#6b7280" />
                  <Bar dataKey="projectedCr" name="Projected Scenario" fill="#c86d3b" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel className="p-5 overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse font-mono tabular-nums">
              <thead>
                <tr className="border-b border-[var(--border-hairline)] tech-label">
                  <th className="py-2 pr-3">Property</th>
                  <th className="py-2 pr-3">Basis Tag</th>
                  <th className="py-2 pr-3 text-right">Engine Value</th>
                  <th className="py-2 pr-3 text-right">Yield</th>
                  <th className="py-2 pr-3">Zone Tier</th>
                  <th className="py-2 pr-3 text-right">CAGR Assumption (%)</th>
                  <th className="py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-hairline)]">
                {portfolio.map((p) => (
                  <tr key={p.id}>
                    <td className="py-2.5 pr-3 font-sans font-medium">{p.label}</td>
                    <td className="py-2.5 pr-3">
                      <StatusTag tone={p.sourceBasis === 'Sourced Valuation Engine' ? 'verified' : 'preliminary'}>
                        {p.sourceBasis}
                      </StatusTag>
                    </td>
                    <td className="py-2.5 pr-3 text-right">{p.fairMarketValueFormatted}</td>
                    <td className="py-2.5 pr-3 text-right text-emerald-400">{p.grossYieldPct}%</td>
                    <td className="py-2.5 pr-3 text-[10px]">{p.zoneClassification}</td>
                    <td className="py-2.5 pr-3 text-right">
                      <input
                        type="number"
                        step="0.5"
                        value={p.appreciationAssumptionPct}
                        onChange={(e) => updatePortfolioAppreciation(p.id, parseFloat(e.target.value) || 0)}
                        className="arch-input w-20 text-right inline-block font-mono text-xs"
                      />
                    </td>
                    <td className="py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => removeFromPortfolio(p.id)}
                        className="text-rose-400 hover:underline font-sans text-[11px]"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </>
      )}
    </div>
  );
}
