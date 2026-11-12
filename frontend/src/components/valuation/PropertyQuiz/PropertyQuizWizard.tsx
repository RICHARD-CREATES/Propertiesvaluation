import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Check, ChevronLeft, ChevronRight, ShieldAlert, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import type { PropertyDetailsPayload, SelectOption } from '@/types/api';

interface PropertyQuizWizardProps {
  details: PropertyDetailsPayload;
  selectors: Record<string, SelectOption[]>;
  assetTypes: SelectOption[];
  onChange: React.Dispatch<React.SetStateAction<PropertyDetailsPayload>>;
  onInspect3D: () => void;
  onExecuteValuation: () => void;
}

interface QuizChallenge {
  id: string;
  pillar: 'Attribute' | 'Profile' | 'Micro-Market Gate';
  title: string;
  prompt: string;
}

const CHALLENGES: QuizChallenge[] = [
  {
    id: 'asset',
    pillar: 'Attribute',
    title: 'Q1 · Asset Classification & Form',
    prompt: 'Select the underlying real estate asset category and structural form factor.',
  },
  {
    id: 'dimensions',
    pillar: 'Attribute',
    title: 'Q2 · Area Footprint & Vertical Scale',
    prompt: 'Dial in built-up area, exclusive land parcel area, total floors, and building age.',
  },
  {
    id: 'quality',
    pillar: 'Profile',
    title: 'Q3 · Structural Grade & Maintenance Profile',
    prompt: 'Pick the structural specification grade and observed physical upkeep condition.',
  },
  {
    id: 'fitout',
    pillar: 'Profile',
    title: 'Q4 · Interior Fit-Out & Parking Allocation',
    prompt: 'Specify turnkey interior finish level and reserved vehicle parking availability.',
  },
  {
    id: 'micromarket',
    pillar: 'Micro-Market Gate',
    title: 'Q5 · Micro-Market Tier & Frontage Positioning',
    prompt: 'Classify neighborhood sector maturity, frontage road width, and plot orientation.',
  },
  {
    id: 'environment',
    pillar: 'Micro-Market Gate',
    title: 'Q6 · Environmental Resilience Gate',
    prompt: 'Clear site flood exposure, municipal storm drainage, and water-table security checks.',
  },
  {
    id: 'legal',
    pillar: 'Micro-Market Gate',
    title: 'Q7 · Title Approval & Litigation Clearance Gate',
    prompt: 'Confirm statutory layout approvals and encumbrance status to unlock bankability clearance.',
  },
  {
    id: 'income',
    pillar: 'Profile',
    title: 'Q8 · Rental Yield Calibration',
    prompt: 'Provide actual achieved monthly rent or keep 0 for comparable rental estimation.',
  },
];

function ChoiceCards({
  options,
  value,
  onSelect,
  columns = 'grid-cols-1 sm:grid-cols-3',
}: {
  options: SelectOption[];
  value: string;
  onSelect: (v: string) => void;
  columns?: string;
}) {
  return (
    <div className={`grid ${columns} gap-2.5`}>
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onSelect(opt.value)}
            className={`arch-btn p-3 text-left border flex items-start justify-between gap-2 ${
              active
                ? 'border-[var(--accent-copper)] bg-[var(--bg-elevated)] text-[var(--text-primary)]'
                : 'border-[var(--border-hairline)] bg-[var(--bg-input)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]'
            }`}
          >
            <span className="text-xs font-medium leading-snug">{opt.label}</span>
            <span
              className={`w-4 h-4 shrink-0 flex items-center justify-center border ${
                active
                  ? 'border-[var(--accent-copper)] bg-[var(--accent-copper)] text-[var(--accent-copper-ink)]'
                  : 'border-[var(--border-strong)]'
              }`}
            >
              {active && <Check className="w-3 h-3" />}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function PropertyQuizWizard({
  details,
  selectors,
  assetTypes,
  onChange,
  onInspect3D,
  onExecuteValuation,
}: PropertyQuizWizardProps) {
  const [stepIdx, setStepIdx] = useState(0);
  const [visitedSteps, setVisitedSteps] = useState<number[]>([0]);
  const [compactView, setCompactView] = useState(false);

  const goTo = (next: number) => {
    const clamped = Math.max(0, Math.min(CHALLENGES.length - 1, next));
    setStepIdx(clamped);
    setVisitedSteps((prev) => (prev.includes(clamped) ? prev : [...prev, clamped]));
  };

  // Live Gate Readiness Scoring
  const envClear = details.flood_risk === 'none_low' && details.drainage_infra === 'underground_storm' && details.groundwater_availability === 'abundant';
  const titleClear = details.approval_status === 'approved_freehold' && details.litigation_risk === 'clear_verified';
  const dimsClear = details.area_value > 0 && (details.plot_area_sqft > 0 || details.asset_type !== 'land');
  const gatesPassed = [dimsClear, details.locality_tier !== 'outskirts', envClear, titleClear].filter(Boolean).length;
  const progressPct = Math.round(((visitedSteps.length) / CHALLENGES.length) * 100);

  const activeChallenge = CHALLENGES[stepIdx];

  const renderChallengeBody = (idx: number) => {
    switch (idx) {
      case 0:
        return (
          <div className="space-y-4">
            <div>
              <div className="tech-label mb-2">Asset Category</div>
              <ChoiceCards
                value={details.asset_type}
                options={assetTypes}
                onSelect={(v) => onChange((p) => ({ ...p, asset_type: v as any }))}
              />
            </div>
            {details.asset_type === 'residential' && (
              <div>
                <div className="tech-label mb-2">Residential Form Factor</div>
                <ChoiceCards
                  value={details.structure_type}
                  options={selectors.structure_type || []}
                  onSelect={(v) => onChange((p) => ({ ...p, structure_type: v }))}
                />
              </div>
            )}
            {details.asset_type === 'commercial' && (
              <div>
                <div className="tech-label mb-2">Commercial Format</div>
                <ChoiceCards
                  value={details.commercial_type}
                  options={selectors.commercial_type || []}
                  onSelect={(v) => onChange((p) => ({ ...p, commercial_type: v }))}
                />
              </div>
            )}
          </div>
        );

      case 1:
        return (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="panel-elevated p-3.5 space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="tech-label">Built-Up Area</span>
                  <strong className="font-mono">{details.area_value.toLocaleString()} {details.area_unit}</strong>
                </div>
                <input
                  type="range"
                  min={300}
                  max={10000}
                  step={50}
                  value={Math.min(10000, details.area_value)}
                  onChange={(e) => onChange((p) => ({ ...p, area_value: Number(e.target.value) }))}
                  className="w-full accent-[#c86d3b]"
                />
                <input
                  type="number"
                  value={details.area_value}
                  onChange={(e) => onChange((p) => ({ ...p, area_value: parseFloat(e.target.value) || 0 }))}
                  className="arch-input font-mono text-xs"
                />
              </div>

              <div className="panel-elevated p-3.5 space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="tech-label">Plot / Land Share (sq ft)</span>
                  <strong className="font-mono">{details.plot_area_sqft.toLocaleString()} sq ft</strong>
                </div>
                <input
                  type="range"
                  min={400}
                  max={15000}
                  step={100}
                  value={Math.min(15000, details.plot_area_sqft)}
                  onChange={(e) => onChange((p) => ({ ...p, plot_area_sqft: Number(e.target.value) }))}
                  className="w-full accent-[#c86d3b]"
                />
                <input
                  type="number"
                  value={details.plot_area_sqft}
                  onChange={(e) => onChange((p) => ({ ...p, plot_area_sqft: parseFloat(e.target.value) || 0 }))}
                  className="arch-input font-mono text-xs"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <label className="tech-label block mb-1">Unit</label>
                <select
                  value={details.area_unit}
                  onChange={(e) => onChange((p) => ({ ...p, area_unit: e.target.value }))}
                  className="arch-input text-xs"
                >
                  {(selectors.area_unit || []).map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="tech-label block mb-1">Floors</label>
                <input
                  type="number"
                  value={details.total_floors}
                  onChange={(e) => onChange((p) => ({ ...p, total_floors: parseInt(e.target.value, 10) || 1 }))}
                  className="arch-input font-mono text-xs"
                />
              </div>
              <div>
                <label className="tech-label block mb-1">Age (Years)</label>
                <input
                  type="number"
                  value={details.property_age_years}
                  onChange={(e) => onChange((p) => ({ ...p, property_age_years: parseFloat(e.target.value) || 0 }))}
                  className="arch-input font-mono text-xs"
                />
              </div>
              <div>
                <label className="tech-label block mb-1">Bedrooms</label>
                <input
                  type="number"
                  value={details.bedrooms}
                  onChange={(e) => onChange((p) => ({ ...p, bedrooms: parseInt(e.target.value, 10) || 1 }))}
                  className="arch-input font-mono text-xs"
                />
              </div>
            </div>
          </div>
        );

      case 2:
        return (
          <div className="space-y-4">
            <div>
              <div className="tech-label mb-2">Structural Grade</div>
              <ChoiceCards
                value={details.construction_grade}
                options={selectors.construction_grade || []}
                onSelect={(v) => onChange((p) => ({ ...p, construction_grade: v }))}
              />
            </div>
            <div>
              <div className="tech-label mb-2">Observed Maintenance Condition</div>
              <ChoiceCards
                value={details.maintenance_state}
                options={selectors.maintenance_state || []}
                onSelect={(v) => onChange((p) => ({ ...p, maintenance_state: v }))}
              />
            </div>
          </div>
        );

      case 3:
        return (
          <div className="space-y-4">
            <div>
              <div className="tech-label mb-2">Interior Fit-Out Specification</div>
              <ChoiceCards
                value={details.furnishing}
                options={selectors.furnishing || []}
                onSelect={(v) => onChange((p) => ({ ...p, furnishing: v }))}
              />
            </div>
            <div>
              <div className="tech-label mb-2">Parking Allocation</div>
              <ChoiceCards
                value={details.parking_slots}
                options={selectors.parking_slots || []}
                onSelect={(v) => onChange((p) => ({ ...p, parking_slots: v }))}
              />
            </div>
          </div>
        );

      case 4:
        return (
          <div className="space-y-4">
            <div>
              <div className="tech-label mb-2">Sector Tier Classification</div>
              <ChoiceCards
                value={details.locality_tier}
                options={selectors.locality_tier || []}
                columns="grid-cols-1 sm:grid-cols-2"
                onSelect={(v) => onChange((p) => ({ ...p, locality_tier: v }))}
              />
            </div>
            <div>
              <div className="tech-label mb-2">Access Road Width</div>
              <ChoiceCards
                value={details.road_width_ft}
                options={selectors.road_width_ft || []}
                columns="grid-cols-2 sm:grid-cols-4"
                onSelect={(v) => onChange((p) => ({ ...p, road_width_ft: v }))}
              />
            </div>
            <div>
              <div className="tech-label mb-2">Plot Frontage Orientation</div>
              <ChoiceCards
                value={details.corner_plot}
                options={selectors.corner_plot || []}
                columns="grid-cols-1 sm:grid-cols-2"
                onSelect={(v) => onChange((p) => ({ ...p, corner_plot: v }))}
              />
            </div>
          </div>
        );

      case 5:
        return (
          <div className="space-y-4">
            <div>
              <div className="tech-label mb-2">Flood Exposure Check</div>
              <ChoiceCards
                value={details.flood_risk}
                options={selectors.flood_risk || []}
                onSelect={(v) => onChange((p) => ({ ...p, flood_risk: v }))}
              />
            </div>
            <div>
              <div className="tech-label mb-2">Storm Drainage Network</div>
              <ChoiceCards
                value={details.drainage_infra}
                options={selectors.drainage_infra || []}
                onSelect={(v) => onChange((p) => ({ ...p, drainage_infra: v }))}
              />
            </div>
            <div>
              <div className="tech-label mb-2">Groundwater Availability</div>
              <ChoiceCards
                value={details.groundwater_availability}
                options={selectors.groundwater_availability || []}
                onSelect={(v) => onChange((p) => ({ ...p, groundwater_availability: v }))}
              />
            </div>
          </div>
        );

      case 6:
        return (
          <div className="space-y-4">
            <div>
              <div className="tech-label mb-2">Statutory Approval &amp; Freehold Status</div>
              <ChoiceCards
                value={details.approval_status}
                options={selectors.approval_status || []}
                columns="grid-cols-1 sm:grid-cols-2"
                onSelect={(v) => onChange((p) => ({ ...p, approval_status: v }))}
              />
            </div>
            <div>
              <div className="tech-label mb-2">Title &amp; Encumbrance Gate</div>
              <ChoiceCards
                value={details.litigation_risk}
                options={selectors.litigation_risk || []}
                columns="grid-cols-1 sm:grid-cols-2"
                onSelect={(v) => onChange((p) => ({ ...p, litigation_risk: v }))}
              />
            </div>
            <div className="panel-elevated p-3 flex items-center gap-2 text-xs">
              {titleClear ? (
                <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
              )}
              <span>
                Gate Status: <strong>{titleClear ? 'BANK LOAN READY · CLEAR TITLE' : 'TITLE REVIEW FLAGGED'}</strong>
              </span>
            </div>
          </div>
        );

      case 7:
      default:
        return (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="panel-elevated p-3.5 space-y-2">
                <label className="tech-label block">Achieved Monthly Rent (0 = Auto-Estimate)</label>
                <input
                  type="number"
                  value={details.monthly_rent_inr}
                  onChange={(e) => onChange((p) => ({ ...p, monthly_rent_inr: parseFloat(e.target.value) || 0 }))}
                  className="arch-input font-mono"
                />
              </div>
              <div className="panel-elevated p-3.5 space-y-2">
                <div className="flex justify-between">
                  <span className="tech-label">Vacancy Assumption (%)</span>
                  <strong className="font-mono text-xs">{details.vacancy_rate_pct ?? 5}%</strong>
                </div>
                <input
                  type="range"
                  min={0}
                  max={30}
                  step={0.5}
                  value={details.vacancy_rate_pct ?? 5}
                  onChange={(e) => onChange((p) => ({ ...p, vacancy_rate_pct: Number(e.target.value) }))}
                  className="w-full accent-[#c86d3b]"
                />
              </div>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="panel-surface p-5 sm:p-6 space-y-5">
      {/* Gamified Progress & Gate Readiness HUD */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-[var(--border-hairline)]">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              Interactive Appraisal Quiz · {activeChallenge.pillar}
            </span>
            <span className="px-2 py-0.5 border border-[var(--border-strong)] bg-[var(--bg-elevated)] font-mono text-[10px]">
              GATES CLEARED {gatesPassed}/4
            </span>
          </div>
          <div className="font-mono text-xs text-[var(--text-secondary)]">
            Profile Progress: <strong>{progressPct}%</strong> · Step {stepIdx + 1} / {CHALLENGES.length}
          </div>
        </div>

        <button
          type="button"
          onClick={() => setCompactView((v) => !v)}
          className="arch-btn px-3 py-1.5 border border-[var(--border-strong)] bg-[var(--bg-elevated)] font-mono text-[11px] flex items-center gap-1.5"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          {compactView ? 'Guided Quiz Mode' : 'Review All 8 Steps'}
        </button>
      </div>

      {/* Copper Progress Bar */}
      <div className="w-full h-1.5 bg-[var(--bg-elevated)] overflow-hidden">
        <div
          className="h-full transition-all duration-300"
          style={{ width: `${Math.max(12, ((stepIdx + 1) / CHALLENGES.length) * 100)}%`, backgroundColor: 'var(--accent-copper)' }}
        />
      </div>

      {/* Interactive Stepper Pills */}
      {!compactView && (
        <div className="flex flex-wrap gap-1.5">
          {CHALLENGES.map((ch, idx) => {
            const active = idx === stepIdx;
            const visited = visitedSteps.includes(idx);
            return (
              <button
                key={ch.id}
                type="button"
                onClick={() => goTo(idx)}
                className={`arch-btn px-2.5 py-1 font-mono text-[11px] border ${
                  active
                    ? 'border-[var(--accent-copper)] bg-[var(--accent-copper)] text-[var(--accent-copper-ink)] font-bold'
                    : visited
                      ? 'border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--text-primary)]'
                      : 'border-[var(--border-hairline)] bg-[var(--bg-input)] text-[var(--text-muted)]'
                }`}
              >
                0{idx + 1} · {ch.pillar}
              </button>
            );
          })}
        </div>
      )}

      {/* Body: Single Quiz Card OR Compact Multi-Question Review */}
      {!compactView ? (
        <motion.div
          key={stepIdx}
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.22 }}
          className="space-y-4"
        >
          <div>
            <h3 className="font-serif text-2xl">{activeChallenge.title}</h3>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">{activeChallenge.prompt}</p>
          </div>
          {renderChallengeBody(stepIdx)}
        </motion.div>
      ) : (
        <div className="space-y-6">
          {CHALLENGES.map((ch, idx) => (
            <div key={ch.id} className="pt-4 border-t border-[var(--border-hairline)] first:pt-0 first:border-t-0 space-y-3">
              <div className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-copper)' }}>
                {ch.title}
              </div>
              {renderChallengeBody(idx)}
            </div>
          ))}
        </div>
      )}

      {/* Navigation Footer */}
      <div className="pt-4 border-t border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-2">
          <button
            type="button"
            disabled={stepIdx === 0}
            onClick={() => goTo(stepIdx - 1)}
            className="arch-btn px-3 py-2 font-mono text-xs border border-[var(--border-strong)] bg-[var(--bg-elevated)] flex items-center gap-1 disabled:opacity-40"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Prev
          </button>
          {stepIdx < CHALLENGES.length - 1 && (
            <button
              type="button"
              onClick={() => goTo(stepIdx + 1)}
              className="arch-btn px-4 py-2 font-mono text-xs font-semibold border border-[var(--accent-copper)] text-[var(--accent-copper)] bg-[var(--bg-elevated)] flex items-center gap-1"
            >
              Next Challenge <ChevronRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onInspect3D}
            className="arch-btn px-4 py-2 font-mono text-xs border border-[var(--border-strong)] bg-[var(--bg-elevated)]"
          >
            Inspect 3D Model →
          </button>
          <button
            type="button"
            onClick={onExecuteValuation}
            className="arch-btn px-5 py-2 font-mono text-xs font-semibold"
            style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
          >
            Complete Quiz &amp; Compute Valuation →
          </button>
        </div>
      </div>
    </div>
  );
}
