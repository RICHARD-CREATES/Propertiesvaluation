import React, { useMemo, useState } from 'react';
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { usePlatform } from '@/context/PlatformContext';
import { HonestNotice, MetricCell, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';

export function RentalPage() {
  const { valuationResult } = usePlatform();
  const inc = valuationResult?.income_approach_and_reconciliation?.income_valuation;
  const propertyVal = valuationResult?.valuation?.fair_market_value || 10000000;

  const [monthlyRent, setMonthlyRent] = useState<number>(inc?.achievable_monthly_rent || 32000);
  const [vacancyPct, setVacancyPct] = useState<number>(inc?.vacancy_rate_pct ?? 5);
  const [opexAnnual, setOpexAnnual] = useState<number>(inc?.annual_operating_expenses || 42000);
  const [capRatePct, setCapRatePct] = useState<number>(inc?.market_cap_rate_pct || 3.8);

  const metrics = useMemo(() => {
    const annualGross = monthlyRent * 12;
    const effectiveGross = annualGross * (1 - vacancyPct / 100);
    const noi = effectiveGross - opexAnnual;
    const grossYield = propertyVal > 0 ? (annualGross / propertyVal) * 100 : 0;
    const capVal = noi > 0 && capRatePct > 0 ? noi / (capRatePct / 100) : 0;
    const grm = annualGross > 0 ? propertyVal / annualGross : 0;
    return { annualGross, effectiveGross, noi, grossYield, capVal, grm };
  }, [monthlyRent, vacancyPct, opexAnnual, capRatePct, propertyVal]);

  const sensitivityCurve = useMemo(() => {
    return [-1.0, -0.5, 0, 0.5, 1.0].map((delta) => {
      const r = Math.max(1.5, capRatePct + delta);
      const valCr = metrics.noi > 0 ? metrics.noi / (r / 100) / 1e7 : 0;
      return { capRate: `${r.toFixed(1)}%`, impliedCr: Number(valCr.toFixed(2)) };
    });
  }, [capRatePct, metrics.noi]);

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Workspace 06 · Rental Intelligence & Yield Modeling"
        title="Income Capitalization, NOI & Sensitivity Lab"
        subtitle="Separates backend-sourced achievable rent from editable investor assumptions."
        right={
          <StatusTag tone={inc?.rent_source_category === 'USER_ACHIEVED' ? 'verified' : 'preliminary'}>
            RENT SOURCE: {(inc?.rent_source_category || 'USER SCENARIO').replace(/_/g, ' ')}
          </StatusTag>
        }
      />

      {!valuationResult && (
        <HonestNotice
          tone="info"
          title="Showing Editable Sensitivity Defaults"
          message="Run an appraisal in Property Valuation first to seed monthly rent, OpEx, and market cap rates from your selected property."
        />
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCell label="Annual Gross Rent" value={`INR ${Math.round(metrics.annualGross).toLocaleString()}`} />
        <MetricCell label="Effective Gross Income" value={`INR ${Math.round(metrics.effectiveGross).toLocaleString()}`} />
        <MetricCell label="Net Operating Income" value={`INR ${Math.round(metrics.noi).toLocaleString()}`} accent={metrics.noi > 0 ? 'green' : 'rose'} />
        <MetricCell label="Implied Cap Value" value={`INR ${(metrics.capVal / 1e7).toFixed(2)} Cr`} accent="copper" subtext={`GRM: ${metrics.grm.toFixed(1)}x · Yield: ${metrics.grossYield.toFixed(2)}%`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <Panel className="lg:col-span-5 p-5 space-y-4 text-xs">
          <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
            Editable Underwriting Assumptions
          </span>
          <div>
            <div className="flex justify-between mb-1">
              <span>Achieved Monthly Rent (INR)</span>
              <strong className="font-mono">INR {monthlyRent.toLocaleString()}</strong>
            </div>
            <input
              id="sens-slider-rent"
              type="range"
              min={8000}
              max={250000}
              step={1000}
              value={monthlyRent}
              onChange={(e) => setMonthlyRent(Number(e.target.value))}
              className="w-full accent-[#c86d3b]"
            />
          </div>
          <div>
            <div className="flex justify-between mb-1">
              <span>Vacancy &amp; Collection Loss (%)</span>
              <strong className="font-mono">{vacancyPct.toFixed(1)}%</strong>
            </div>
            <input
              id="sens-slider-vac"
              type="range"
              min={0}
              max={30}
              step={0.5}
              value={vacancyPct}
              onChange={(e) => setVacancyPct(Number(e.target.value))}
              className="w-full accent-[#c86d3b]"
            />
          </div>
          <div>
            <div className="flex justify-between mb-1">
              <span>Annual Operating Expenses (INR)</span>
              <strong className="font-mono">INR {opexAnnual.toLocaleString()}</strong>
            </div>
            <input
              type="range"
              min={0}
              max={400000}
              step={2000}
              value={opexAnnual}
              onChange={(e) => setOpexAnnual(Number(e.target.value))}
              className="w-full accent-[#c86d3b]"
            />
          </div>
          <div>
            <div className="flex justify-between mb-1">
              <span>Target Capitalization Rate (%)</span>
              <strong className="font-mono">{capRatePct.toFixed(2)}%</strong>
            </div>
            <input
              id="sens-slider-cap"
              type="range"
              min={2.0}
              max={10.0}
              step={0.1}
              value={capRatePct}
              onChange={(e) => setCapRatePct(Number(e.target.value))}
              className="w-full accent-[#c86d3b]"
            />
          </div>
        </Panel>

        <Panel className="lg:col-span-7 p-5 space-y-3">
          <div className="flex justify-between items-center">
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              Cap Rate Valuation Sensitivity Curve (INR Cr)
            </span>
            <span className="font-mono text-[10px] text-[var(--text-muted)]">Three-Way Reconciliation Ready</span>
          </div>
          <div className="h-[260px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensitivityCurve} margin={{ left: 8, right: 16, top: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="capRate" tick={{ fill: '#9ba3ae', fontSize: 11 }} />
                <YAxis unit=" Cr" tick={{ fill: '#9ba3ae', fontSize: 11 }} />
                <Tooltip contentStyle={{ backgroundColor: '#111419', border: '1px solid rgba(255,255,255,0.16)', fontSize: 12 }} />
                <Line type="monotone" dataKey="impliedCr" stroke="#c86d3b" strokeWidth={2.5} dot={{ r: 4, fill: '#c86d3b' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
    </div>
  );
}
