import React, { Suspense, lazy, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowUpRight, Compass, Database, Layers, Moon, Scale, ShieldCheck, SunMedium, TrendingUp } from 'lucide-react';
import { usePlatform } from '@/context/PlatformContext';
import { Panel, StatusTag } from '@/components/ui/Primitives';

const PropertyScene = lazy(() =>
  import('@/components/visualization/PropertyScene/PropertyScene').then((m) => ({ default: m.PropertyScene })),
);

const HERO_ARCHETYPES = [
  { id: 'villa', label: 'Standalone Villa · 3F', assetType: 'residential' as const, plot: 2400, built: 2600, floors: 3 },
  { id: 'tower', label: 'Residential Tower · 8F', assetType: 'residential' as const, plot: 6400, built: 12000, floors: 8 },
  { id: 'commercial', label: 'Commercial Core · 5F', assetType: 'commercial' as const, plot: 4800, built: 8500, floors: 5 },
];

const LANDING_METHODOLOGIES = [
  {
    code: 'METH-01',
    title: 'Comparable Sales',
    desc: 'Spatially weighted transaction comparables stratified by built-up area, UDS share, distance radius, and deed verification status.',
  },
  {
    code: 'METH-02',
    title: 'Depreciated Replacement Cost',
    desc: 'Two-stage separation: market land rate adjusted by backend geospatial zoning, plus CPWD-indexed depreciated structural cost.',
  },
  {
    code: 'METH-03',
    title: 'Income Capitalization',
    desc: 'Effective gross income modeling subtracting vacancy & OpEx, anchored to micro-market capitalization rates and GRM.',
  },
];

const CAPABILITIES = [
  { icon: Compass, label: '3D Spatial Digital Twin', text: 'MapLibre GL 3D massing & interactive Three.js parcel floor inspection across global hubs.' },
  { icon: Layers, label: 'Geospatial Zone Modeling', text: 'Backend distance-decay uplift from medical zones alongside confidential corridor intelligence.' },
  { icon: ShieldCheck, label: 'Immutable Evidence Ledger', text: 'SHA-256 document hashing separating Sub-Registrar deeds from unverified broker inputs.' },
  { icon: TrendingUp, label: 'Calibrated Uncertainty', text: 'Explicit OOD checks and empirical holdout quantile intervals instead of fake confidence.' },
];

export function OverviewPage() {
  const { setRoute, zoneResponse, theme, toggleTheme } = usePlatform();
  const [heroIdx, setHeroIdx] = useState(0);
  const activeHero = HERO_ARCHETYPES[heroIdx];

  return (
    <div className="min-h-[100dvh] bg-[var(--bg-canvas)] text-[var(--text-primary)] arch-grid-bg">
      {/* Standalone Landing Minimal Navigation (No Sidebar Overhead) */}
      <header className="max-w-[1440px] mx-auto px-4 sm:px-8 h-16 flex items-center justify-between border-b border-[var(--border-hairline)]">
        <div className="flex items-center gap-3">
          <span className="font-serif text-xl tracking-tight">PropIntel</span>
          <span className="hidden sm:inline-block tech-label px-2 py-0.5 border border-[var(--border-hairline)] bg-[var(--bg-surface)]">
            SPATIAL VALUATION STUDIO
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label="Toggle theme"
            className="arch-btn px-2.5 py-1.5 border border-[var(--border-strong)] bg-[var(--bg-surface)] font-mono text-[11px] flex items-center gap-1.5"
          >
            {theme === 'obsidian' ? <SunMedium className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{theme === 'obsidian' ? 'Stone' : 'Obsidian'}</span>
          </button>
          <button
            type="button"
            onClick={() => setRoute('valuation')}
            className="arch-btn px-4 py-1.5 font-mono text-xs font-semibold flex items-center gap-1.5"
            style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
          >
            <span>Enter Main Website</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      <main className="max-w-[1440px] mx-auto px-4 sm:px-8 py-10 sm:py-14 space-y-20">
        {/* 1. FULL-VIEWPORT 3D DYNAMIC ARCHITECTURAL HERO */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center min-h-[72vh]">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
            className="lg:col-span-5 space-y-6"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="tech-label px-2 py-1 border border-[var(--border-hairline)] bg-[var(--bg-surface)]" style={{ color: 'var(--accent-copper)' }}>
                ARCHITECTURAL PROPERTY INTELLIGENCE
              </span>
              <span className="tech-label px-2 py-1 border border-[var(--border-hairline)] bg-[var(--bg-surface)]">
                19.1254° N · 72.9157° E
              </span>
            </div>

            <h1 className="font-serif text-4xl sm:text-5xl xl:text-6xl leading-[1.03] tracking-tight">
              Understand the value beneath the surface.
            </h1>

            <p className="text-sm sm:text-base text-[var(--text-secondary)] leading-relaxed max-w-xl">
              Property valuation, spatial intelligence, and market evidence — brought into one analytical platform.
            </p>

            {/* Dynamic 3D Building Archetype Switcher */}
            <div className="space-y-2 pt-1">
              <div className="tech-label">Interactive 3D Massing Archetype</div>
              <div className="flex flex-wrap gap-1.5">
                {HERO_ARCHETYPES.map((arch, idx) => (
                  <button
                    key={arch.id}
                    type="button"
                    onClick={() => setHeroIdx(idx)}
                    className={`arch-btn px-3 py-1.5 font-mono text-[11px] border ${
                      heroIdx === idx
                        ? 'border-[var(--accent-copper)] bg-[var(--bg-elevated)] text-[var(--accent-copper)] font-semibold'
                        : 'border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[var(--text-secondary)]'
                    }`}
                  >
                    {arch.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap gap-3 pt-2">
              <button
                type="button"
                onClick={() => setRoute('valuation')}
                className="arch-btn px-5 py-2.5 text-xs font-mono font-semibold tracking-wider uppercase flex items-center gap-2 border border-[var(--accent-copper)]"
                style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
              >
                <span>Explore a Property</span>
                <ArrowUpRight className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setRoute('spatial')}
                className="arch-btn px-5 py-2.5 text-xs font-mono font-semibold tracking-wider uppercase border border-[var(--border-strong)] bg-[var(--bg-surface)] text-[var(--text-primary)]"
              >
                View Market Intelligence
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 pt-3 border-t border-[var(--border-hairline)] font-mono text-[11px]">
              <div>
                <span className="tech-label block">METHODOLOGY</span>
                <strong>3-Way Reconciled</strong>
              </div>
              <div>
                <span className="tech-label block">GAMIFIED QUIZ</span>
                <strong>8-Gate Profiling</strong>
              </div>
              <div>
                <span className="tech-label block">EVIDENCE VAULT</span>
                <strong>SHA-256 Audited</strong>
              </div>
            </div>
          </motion.div>

          <div className="lg:col-span-7">
            <Panel className="p-2">
              <Suspense
                fallback={
                  <div className="h-[520px] flex items-center justify-center font-mono text-xs text-[var(--text-muted)]">
                    INITIALIZING 3D ARCHITECTURAL MASSING SCENE...
                  </div>
                }
              >
                <PropertyScene
                  plotAreaSqft={activeHero.plot}
                  builtupAreaSqft={activeHero.built}
                  floors={activeHero.floors}
                  assetType={activeHero.assetType}
                  roadWidthFt="40ft_plus"
                  zoneAnalysis={zoneResponse?.zone_analysis}
                  heroMode
                  heightClass="h-[520px]"
                />
              </Suspense>
            </Panel>
          </div>
        </section>

        {/* 2. CAPABILITIES */}
        <section className="space-y-4">
          <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
            02 · Analytical Capabilities
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {CAPABILITIES.map((c) => (
              <Panel key={c.label} className="p-5 space-y-2">
                <c.icon className="w-4 h-4" style={{ color: 'var(--accent-copper)' }} />
                <h3 className="text-sm font-semibold">{c.label}</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{c.text}</p>
              </Panel>
            ))}
          </div>
        </section>

        {/* 3. THREE VALUATION METHODOLOGIES */}
        <section className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                03 · Valuation Framework
              </div>
              <h2 className="font-serif text-3xl mt-0.5">Three-Way Appraisal Triangulation</h2>
            </div>
            <button
              type="button"
              onClick={() => setRoute('valuation')}
              className="arch-btn px-3 py-1.5 text-xs font-mono border border-[var(--border-strong)] bg-[var(--bg-surface)]"
            >
              Open Appraisal Terminal →
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {LANDING_METHODOLOGIES.map((m) => (
              <Panel key={m.code} className="p-5 space-y-2.5">
                <span className="font-mono text-[10px] text-[var(--text-muted)]">{m.code}</span>
                <h3 className="font-serif text-2xl">{m.title}</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{m.desc}</p>
              </Panel>
            ))}
          </div>
        </section>

        {/* 4–7. WORKSPACE GATEWAYS + ILLUSTRATIVE METRO PREVIEW */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <Panel className="lg:col-span-7 p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
              <div>
                <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                  04 · Micro-Market Intelligence Preview
                </div>
                <h3 className="font-serif text-2xl mt-0.5">Metro Priority Corridors</h3>
              </div>
              <StatusTag tone="preliminary">ILLUSTRATIVE PREVIEW BENCHMARK · NOT LIVE DEEDS</StatusTag>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-mono tabular-nums">
                <thead>
                  <tr className="border-b border-[var(--border-hairline)] tech-label">
                    <th className="py-2 pr-3">Corridor</th>
                    <th className="py-2 pr-3">Zone Class</th>
                    <th className="py-2 pr-3 text-right">Indicative Land Floor</th>
                    <th className="py-2 text-right">Live Vault Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-hairline)]">
                  {[
                    ['Powai / IIT Bombay, Mumbai', 'GREEN MEDICAL', 'INR 24,000 / sqft', '0 VERIFIED DEEDS'],
                    ['Hinjawadi IT Hub, Pune', 'GREEN MEDICAL', 'INR 8,800 / sqft', '0 VERIFIED DEEDS'],
                    ['Whitefield IT, Bengaluru', 'GREEN MEDICAL', 'INR 10,200 / sqft', '0 VERIFIED DEEDS'],
                    ['Rural Taluka, Maharashtra', 'OUTSIDE ZONES', 'INR 2,200 / sqft', '0 VERIFIED DEEDS'],
                  ].map(([loc, zone, rate, st]) => (
                    <tr key={loc}>
                      <td className="py-2.5 pr-3 font-sans font-medium">{loc}</td>
                      <td className="py-2.5 pr-3 text-[11px]">{zone}</td>
                      <td className="py-2.5 pr-3 text-right">{rate}</td>
                      <td className="py-2.5 text-right text-[var(--text-muted)]">{st}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <div className="lg:col-span-5 grid grid-cols-1 gap-3">
            {[
              { route: 'comparables' as const, icon: Database, title: 'Evidence Verification & Ledger', desc: 'Inspect document hashes, Sub-Registrar segregation, and audit history.' },
              { route: 'rental' as const, icon: Scale, title: 'Rental Investment Lab', desc: 'Model NOI, cap rates, vacancy, GRM, and cash-flow sensitivity interactively.' },
            ].map((card) => (
              <Panel key={card.route} className="p-4 flex items-center justify-between gap-3">
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <card.icon className="w-4 h-4 shrink-0" style={{ color: 'var(--accent-copper)' }} />
                    <h4 className="text-sm font-semibold">{card.title}</h4>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)]">{card.desc}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setRoute(card.route)}
                  className="arch-btn px-3 py-1.5 shrink-0 border border-[var(--border-strong)] bg-[var(--bg-elevated)] font-mono text-[11px]"
                >
                  Open
                </button>
              </Panel>
            ))}
          </div>
        </section>

        {/* 8. FINAL CTA */}
        <Panel className="p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              08 · Launch Instrument
            </span>
            <h3 className="font-serif text-2xl sm:text-3xl mt-1">Enter the architectural valuation terminal.</h3>
          </div>
          <button
            type="button"
            onClick={() => setRoute('valuation')}
            className="arch-btn px-6 py-3 font-mono text-xs font-semibold uppercase tracking-wider shrink-0"
            style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
          >
            Launch Main Website →
          </button>
        </Panel>
      </main>
    </div>
  );
}
