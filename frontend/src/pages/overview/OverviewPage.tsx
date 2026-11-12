import React, { Suspense, lazy, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  ArrowUpRight,
  Building2,
  Compass,
  Cpu,
  Database,
  FileSpreadsheet,
  Layers,
  MapPin,
  Moon,
  Scale,
  ShieldCheck,
  SlidersHorizontal,
  SunMedium,
  TrendingUp,
} from 'lucide-react';
import { usePlatform } from '@/context/PlatformContext';
import { Panel, StatusTag } from '@/components/ui/Primitives';

const PropertyScene = lazy(() =>
  import('@/components/visualization/PropertyScene/PropertyScene').then((m) => ({ default: m.PropertyScene })),
);

const HERO_ARCHETYPES = [
  {
    id: 'villa',
    label: 'Standalone Villa · 3F',
    assetType: 'residential' as const,
    plot: 2400,
    built: 2600,
    floors: 3,
    fsi: '1.08×',
    frontage: '40 ft+ Civic Avenue',
  },
  {
    id: 'tower',
    label: 'Residential Tower · 8F',
    assetType: 'residential' as const,
    plot: 6400,
    built: 12000,
    floors: 8,
    fsi: '1.88×',
    frontage: '60 ft Arterial Boulevard',
  },
  {
    id: 'commercial',
    label: 'Commercial Core · 5F',
    assetType: 'commercial' as const,
    plot: 4800,
    built: 8500,
    floors: 5,
    fsi: '1.77×',
    frontage: 'Corner Commercial Spine',
  },
];

const PIPELINE_STAGES = [
  {
    step: '01',
    title: 'Geo-Pin & Zone Lookup',
    detail: 'Resolves coordinates, municipal density tier, circle-rate floor, and medical corridor distance decay.',
  },
  {
    step: '02',
    title: '7-Cluster Feature Matrix',
    detail: 'Synthesizes transit access, corridor demand, demographics, zoning FSI, RERA stability, liquidity & physical spec.',
  },
  {
    step: '03',
    title: '8-Gate Property Quiz',
    detail: 'Captures asset class, built/land footprint, CPWD grade, fit-out, flood/drainage risk & title encumbrance gates.',
  },
  {
    step: '04',
    title: 'Three-Way Reconciliation',
    detail: 'Blends Comparable Sales, Land + Depreciated Cost, and NOI Capitalization into weighted Fair Market Value.',
  },
  {
    step: '05',
    title: 'Uncertainty & TreeSHAP',
    detail: 'Validates feature drift via OOD distance checks, TreeSHAP log-space attributions & quantile intervals.',
  },
];

const SPATIAL_CLUSTERS = [
  {
    code: 'C1',
    name: 'Connectivity & Transit',
    keys: 'dist_nh_km · dist_metro_station_km · dist_railway_stn_km · civic_proximity_score · dist_airport_hub_km',
    impact: 'Models radial accessibility decay across national highways, metro stations, rail heads, and airport hubs.',
  },
  {
    code: 'C2',
    name: 'Corridor Demand & Traffic Merit',
    keys: 'traffic_vehicles_per_min · traffic_peak_hour_vol · traffic_peak_am_pm_ratio · traffic_congestion_index',
    impact: 'Treats sustained corridor throughput as commercial/urban demand strength rather than a flat penalty.',
  },
  {
    code: 'C3',
    name: 'Population & Socio-Economics',
    keys: 'colony_density_sqkm · pincode_income_tier · pop_growth_cagr_10yr · amenity_density_score',
    impact: 'Captures micro-market household purchasing power, neighborhood maturity, and 10-year catchment growth.',
  },
  {
    code: 'C4',
    name: 'Development & Zoning Potential',
    keys: 'master_plan_zoning · fsi_far_allowable · dist_upcoming_sez_km · job_creation_potential_score',
    impact: 'Quantifies redevelopment headroom via allowable Floor Space Index (FSI/FAR) and employment node proximity.',
  },
  {
    code: 'C5',
    name: 'Civic & RERA Governance',
    keys: 'is_smart_city_mission · rera_projects_within_2km · rera_delayed_project_pct · public_infra_capex_cr',
    impact: 'Evaluates delivery reliability through local RERA completion ratios and sanctioned public capital outlays.',
  },
  {
    code: 'C6',
    name: 'Market Liquidity & Yield',
    keys: 'tx_velocity_deals_per_month · price_psqft_12m_delta_pct · inventory_overhang_months · gross_rental_yield_pct',
    impact: 'Measures transaction absorption speed, 12-month price momentum, unsold inventory pressure, and rental yield.',
  },
  {
    code: 'C7',
    name: 'Physical Structure & Spec',
    keys: 'carpet_area_sqft · bhk_count · floor_relative_ratio · property_age_years · construction_grade · clear_title_flag',
    impact: 'Balances unit efficiency, floor elevation premium, remaining structural life, construction finish, and title clarity.',
  },
];

const QUIZ_PARAMETERS = [
  {
    gate: 'Q1 – Q2 · ASSET & FOOTPRINT',
    title: 'Asset Class, Built Area & Exclusive Land Parcel',
    params: 'asset_type · structure_type · carpet_area_sqft · plot_area_sqft · total_floors · property_age_years',
    explanation:
      'Decouples depreciating brick-and-mortar superstructure from appreciating freehold land parcel. Separates apartment undivided share (UDS) from standalone villa plot ratios.',
  },
  {
    gate: 'Q3 – Q4 · SPECIFICATION & FIT-OUT',
    title: 'CPWD Construction Grade, Upkeep & Interiors',
    params: 'construction_grade (GRADE_A / B / C) · maintenance_state · furnishing · parking_slots',
    explanation:
      'Applies structural replacement unit rates indexed by finish quality (Italian marble / smart HVAC vs standard RCC) minus curved age depreciation.',
  },
  {
    gate: 'Q5 · MICRO-MARKET POSITIONING',
    title: 'Locality Tier, Frontage Road Width & Orientation',
    params: 'locality_tier · road_width_ft (20ft–40ft+) · corner_plot (corner / standard)',
    explanation:
      'Wide 40ft+ arterial frontage and dual-side corner access command measurable commercial conversion & FSI utilization premiums.',
  },
  {
    gate: 'Q6 – Q7 · RISK & BANKABILITY GATES',
    title: 'Flood Elevation, Drainage, Water Table & Freehold Title',
    params: 'flood_risk · drainage_infra · groundwater_availability · approval_status · litigation_risk',
    explanation:
      'Mandatory underwriting gates: low-lying waterlogging risk, missing storm drainage, or unapproved/litigated titles apply direct liquidity discounts and flag mortgage risk.',
  },
  {
    gate: 'Q8 · INCOME CAPITALIZATION INPUT',
    title: 'Achieved Monthly Rent vs Benchmark Rental Estimation',
    params: 'monthly_rent_inr · vacancy_pct · opex_pct · target_cap_rate_pct',
    explanation:
      'Uses lease-backed achieved rent where supplied (or predicts via specialist rental XGBoost when 0) to compute Net Operating Income (NOI), gross yield, and Gross Rent Multiplier.',
  },
];

const SPECIALIST_MODELS = [
  { cohort: 'Apartments', algo: 'XGBoost', samples: '552 train / 324 spatial holdout', policy: 'Primary hedonic + residual UDS calibration', status: 'TRAINED' },
  { cohort: 'Standalone Houses / Villas', algo: 'CatBoost', samples: '184 train / 108 spatial holdout', policy: 'Two-stage land + depreciated structure blend', status: 'TRAINED' },
  { cohort: 'Residential Land / Plots', algo: 'CatBoost', samples: '276 train / 162 spatial holdout', policy: 'Frontage, FSI, road width & zone multiplier', status: 'TRAINED' },
  { cohort: 'Commercial Assets', algo: 'CatBoost', samples: '184 train / 108 spatial holdout', policy: 'Corridor footfall, arterial frontage & NOI yield', status: 'TRAINED' },
  { cohort: 'Rental Market', algo: 'XGBoost', samples: '138 train / 81 spatial holdout', policy: 'Monthly lease prediction & yield benchmarking', status: 'TRAINED' },
  { cohort: 'Agricultural & Industrial', algo: 'Strict Gate', samples: '0 verified deed cohorts', policy: 'Refuses estimation until verified deeds are ingested', status: 'DATA NOT READY' },
];

const LANDING_METHODOLOGIES = [
  {
    code: 'METH-01 · WEIGHTED COMPS',
    title: 'Comparable Sales Approach',
    formula: 'P_comp = Σ (w_spatial · w_spec · w_verify · Price_i) / Σ w',
    desc: 'Spatially weighted transaction comparables stratified by carpet area, undivided land share, distance radius, and Sub-Registrar verification status.',
  },
  {
    code: 'METH-02 · SUMMATION COST',
    title: 'Land + Depreciated Replacement Cost',
    formula: 'V_cost = (Area_plot × Rate_land × Mult_zone) + (Area_built × Rate_CPWD × (1 − δ_age))',
    desc: 'Isolates intrinsic land value (backed by municipal circle-rate floors and geospatial medical zone proximity) from depreciated physical reconstruction value.',
  },
  {
    code: 'METH-03 · INCOME APPROACH',
    title: 'Rental & NOI Capitalization',
    formula: 'NOI = (Rent_monthly × 12 × (1 − Vacancy)) − OpEx   |   V_income = NOI / CapRate',
    desc: 'Separates verified achieved leases from asking listings, incorporating operating maintenance ratios and sensitivity across interest/yield regimes.',
  },
];

const CAPABILITIES = [
  { icon: Compass, label: '3D Spatial Digital Twin', text: 'Interactive Three.js parcel & floor-slab visualizer paired with MapLibre GL 3D urban building extrusion.' },
  { icon: Layers, label: 'Geospatial Zone Economics', text: 'Distance-decay uplift modeling around Green Medical Zones paired with private corridor pricing intelligence.' },
  { icon: ShieldCheck, label: 'Immutable SHA-256 Vault', text: 'Quarantine-scanned evidence locker separating executed Sale Deeds from agreements and broker quotes.' },
  { icon: TrendingUp, label: 'Out-of-Distribution Guard', text: 'Automatic Mahalanobis/feature-drift detection and wide conformal uncertainty bands when local data is sparse.' },
];

export function OverviewPage() {
  const { setRoute, zoneResponse, theme, toggleTheme } = usePlatform();
  const [heroIdx, setHeroIdx] = useState(0);
  const [paramTab, setParamTab] = useState<'clusters' | 'quiz' | 'models'>('clusters');
  const activeHero = HERO_ARCHETYPES[heroIdx];

  return (
    <div className="min-h-[100dvh] bg-[var(--bg-canvas)] text-[var(--text-primary)] arch-grid-bg">
      {/* Standalone Landing Minimal Navigation (No Sidebar Overhead) */}
      <header className="sticky top-0 z-30 backdrop-blur-md bg-[var(--bg-canvas)]/90 border-b border-[var(--border-hairline)]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 shrink-0">
            <span className="font-serif text-xl tracking-tight whitespace-nowrap">PropIntel</span>
            <span className="hidden lg:inline-block tech-label whitespace-nowrap px-2 py-0.5 border border-[var(--border-hairline)] bg-[var(--bg-surface)]">
              SPATIAL VALUATION STUDIO
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-5 font-mono text-[11px] uppercase tracking-wider text-[var(--text-secondary)] whitespace-nowrap">
            <a href="#pipeline" className="hover:text-[var(--text-primary)] transition-colors">Architecture</a>
            <a href="#parameters" className="hover:text-[var(--text-primary)] transition-colors">Parameters</a>
            <a href="#methodologies" className="hover:text-[var(--text-primary)] transition-colors">Valuation Math</a>
            <a href="#corridors" className="hover:text-[var(--text-primary)] transition-colors">Benchmarks</a>
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label="Toggle theme"
              className="arch-btn whitespace-nowrap px-2.5 py-1.5 border border-[var(--border-strong)] bg-[var(--bg-surface)] font-mono text-[11px] flex items-center gap-1.5"
            >
              {theme === 'obsidian' ? <SunMedium className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{theme === 'obsidian' ? 'Stone' : 'Obsidian'}</span>
            </button>
            <button
              type="button"
              onClick={() => setRoute('valuation')}
              className="arch-btn whitespace-nowrap px-4 py-1.5 font-mono text-xs font-semibold flex items-center gap-1.5"
              style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
            >
              <span>Enter Main Website</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1440px] mx-auto px-4 sm:px-8 py-10 sm:py-14 space-y-24">
        {/* 1. FULL-VIEWPORT 3D DYNAMIC ARCHITECTURAL HERO */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 items-center min-h-[72vh]">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
            className="lg:col-span-5 space-y-6"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="tech-label px-2.5 py-1 border border-[var(--border-hairline)] bg-[var(--bg-surface)]"
                style={{ color: 'var(--accent-copper)' }}
              >
                ARCHITECTURAL PROPERTY INTELLIGENCE
              </span>
              <span className="tech-label px-2.5 py-1 border border-[var(--border-hairline)] bg-[var(--bg-surface)]">
                19.1254° N · 72.9157° E
              </span>
            </div>

            <h1 className="font-serif text-4xl sm:text-5xl xl:text-[3.5rem] leading-[1.03] tracking-tight">
              Understand the value beneath the surface.
            </h1>

            <p className="text-sm sm:text-base text-[var(--text-secondary)] leading-relaxed max-w-xl">
              Property valuation, spatial intelligence, and market evidence — brought into one analytical platform.
              Every appraisal separates appreciating land from depreciating structure across seven spatial feature
              clusters and eight physical underwriting gates.
            </p>

            {/* Dynamic 3D Building Archetype Switcher */}
            <div className="space-y-2.5 pt-1">
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
              <div className="grid grid-cols-4 gap-2 p-2.5 border border-[var(--border-hairline)] bg-[var(--bg-surface)] font-mono text-[10px] tabular-nums">
                <div>
                  <span className="tech-label block">PLOT</span>
                  <strong>{activeHero.plot.toLocaleString()} sqft</strong>
                </div>
                <div>
                  <span className="tech-label block">BUILT-UP</span>
                  <strong>{activeHero.built.toLocaleString()} sqft</strong>
                </div>
                <div>
                  <span className="tech-label block">ACHIEVED FSI</span>
                  <strong>{activeHero.fsi}</strong>
                </div>
                <div>
                  <span className="tech-label block">ACCESS</span>
                  <strong className="truncate block">{activeHero.frontage.split(' ')[0]} {activeHero.frontage.split(' ')[1]}</strong>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-3 pt-1">
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

            <div className="grid grid-cols-4 gap-2 pt-3 border-t border-[var(--border-hairline)] font-mono text-[11px]">
              <div>
                <span className="tech-label block">METHODOLOGY</span>
                <strong>3-Way Blend</strong>
              </div>
              <div>
                <span className="tech-label block">FEATURES</span>
                <strong>7 Clusters</strong>
              </div>
              <div>
                <span className="tech-label block">UNDERWRITING</span>
                <strong>8 Quiz Gates</strong>
              </div>
              <div>
                <span className="tech-label block">VAULT</span>
                <strong>SHA-256</strong>
              </div>
            </div>
          </motion.div>

          <div className="lg:col-span-7">
            <Panel className="p-2">
              <Suspense
                fallback={
                  <div className="h-[540px] flex items-center justify-center font-mono text-xs text-[var(--text-muted)]">
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
                  heightClass="h-[540px]"
                />
              </Suspense>
            </Panel>
          </div>
        </section>

        {/* 2. CAPABILITIES & END-TO-END ENGINE PIPELINE */}
        <section id="pipeline" className="space-y-8 scroll-mt-20">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-hairline)] pb-4">
            <div>
              <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                02 · System Architecture & Capabilities
              </div>
              <h2 className="font-serif text-3xl mt-1">Five-Stage Valuation Execution Pipeline</h2>
            </div>
            <p className="text-xs text-[var(--text-secondary)] max-w-md">
              Built to keep synthetic benchmarks strictly segregated from verified Sub-Registrar deeds while running
              real-time Three.js massing, spatial zoning, and TreeSHAP explainability.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {PIPELINE_STAGES.map((stage) => (
              <Panel key={stage.step} className="p-4 space-y-2 border-t-2 border-t-[var(--accent-copper)]">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold" style={{ color: 'var(--accent-copper)' }}>
                    STAGE {stage.step}
                  </span>
                </div>
                <h3 className="text-sm font-semibold">{stage.title}</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{stage.detail}</p>
              </Panel>
            ))}
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

        {/* 3. INTERACTIVE PARAMETER & FEATURE ENGINEERING REFERENCE */}
        <section id="parameters" className="space-y-6 scroll-mt-20">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-hairline)] pb-4">
            <div>
              <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                03 · Underwriting Inputs & Feature Specification
              </div>
              <h2 className="font-serif text-3xl mt-1">Every Parameter Explained</h2>
              <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-2xl">
                Inspect the exact geospatial clusters, physical quiz gates, risk discounts, and specialist ML models
                evaluated during a live appraisal.
              </p>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {[
                { id: 'clusters' as const, label: '7 Spatial Clusters (C1–C7)', icon: MapPin },
                { id: 'quiz' as const, label: '8-Gate Quiz Inputs (Q1–Q8)', icon: SlidersHorizontal },
                { id: 'models' as const, label: 'Specialist ML & Holdouts', icon: Cpu },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setParamTab(t.id)}
                  className={`arch-btn px-3 py-1.5 font-mono text-[11px] border flex items-center gap-1.5 ${
                    paramTab === t.id
                      ? 'border-[var(--accent-copper)] bg-[var(--bg-elevated)] text-[var(--accent-copper)] font-semibold'
                      : 'border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[var(--text-secondary)]'
                  }`}
                >
                  <t.icon className="w-3.5 h-3.5" />
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          </div>

          {paramTab === 'clusters' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {SPATIAL_CLUSTERS.map((cluster) => (
                <Panel key={cluster.code} className="p-5 space-y-2.5 flex flex-col justify-between">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] font-bold px-2 py-0.5 border border-[var(--border-strong)] bg-[var(--bg-elevated)]">
                        {cluster.code}
                      </span>
                      <span className="tech-label">BACKEND CLUSTER</span>
                    </div>
                    <h3 className="text-base font-semibold">{cluster.name}</h3>
                    <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{cluster.impact}</p>
                  </div>
                  <div className="pt-2 border-t border-[var(--border-hairline)] font-mono text-[10px] text-[var(--text-muted)] break-words">
                    {cluster.keys}
                  </div>
                </Panel>
              ))}
            </div>
          )}

          {paramTab === 'quiz' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {QUIZ_PARAMETERS.map((item) => (
                <Panel key={item.gate} className="p-5 space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                      {item.gate}
                    </span>
                  </div>
                  <h3 className="text-base font-semibold">{item.title}</h3>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{item.explanation}</p>
                  <div className="pt-2 border-t border-[var(--border-hairline)] font-mono text-[10px] text-[var(--text-muted)] break-words">
                    {item.params}
                  </div>
                </Panel>
              ))}
            </div>
          )}

          {paramTab === 'models' && (
            <Panel className="p-5 overflow-x-auto space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs text-[var(--text-secondary)]">
                  Champion gradient-boosted ensembles evaluated via <strong>Spatially Separated Geographic Holdout</strong> (<code className="font-mono text-[11px] text-[var(--text-primary)]">log1p(price)</code>).
                </div>
                <StatusTag tone="verified">SHAP LOG-SPACE EXPLAINABLE</StatusTag>
              </div>
              <table className="w-full text-left text-xs border-collapse font-mono tabular-nums">
                <thead>
                  <tr className="border-b border-[var(--border-hairline)] tech-label">
                    <th className="py-2 pr-4">Asset Cohort</th>
                    <th className="py-2 pr-4">Algorithm</th>
                    <th className="py-2 pr-4">Validation Split</th>
                    <th className="py-2 pr-4">Valuation Policy</th>
                    <th className="py-2 text-right">Registry Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-hairline)]">
                  {SPECIALIST_MODELS.map((m) => (
                    <tr key={m.cohort}>
                      <td className="py-2.5 pr-4 font-sans font-semibold">{m.cohort}</td>
                      <td className="py-2.5 pr-4 text-[var(--accent-copper)]">{m.algo}</td>
                      <td className="py-2.5 pr-4">{m.samples}</td>
                      <td className="py-2.5 pr-4 font-sans text-[var(--text-secondary)]">{m.policy}</td>
                      <td className="py-2.5 text-right">{m.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </section>

        {/* 4. THREE VALUATION METHODOLOGIES & FORMULAS */}
        <section id="methodologies" className="space-y-5 scroll-mt-20">
          <div className="flex flex-wrap items-end justify-between gap-2 border-b border-[var(--border-hairline)] pb-4">
            <div>
              <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                04 · Valuation Framework & Math
              </div>
              <h2 className="font-serif text-3xl mt-1">Three-Way Appraisal Triangulation</h2>
            </div>
            <button
              type="button"
              onClick={() => setRoute('valuation')}
              className="arch-btn px-3.5 py-1.5 text-xs font-mono border border-[var(--border-strong)] bg-[var(--bg-surface)]"
            >
              Open Appraisal Terminal →
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {LANDING_METHODOLOGIES.map((m) => (
              <Panel key={m.code} className="p-5 space-y-3 flex flex-col justify-between">
                <div className="space-y-2">
                  <span className="font-mono text-[10px] text-[var(--text-muted)]">{m.code}</span>
                  <h3 className="font-serif text-2xl">{m.title}</h3>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{m.desc}</p>
                </div>
                <div className="p-2.5 border border-[var(--border-hairline)] bg-[var(--bg-input)] font-mono text-[10px] text-[var(--text-primary)] break-words">
                  {m.formula}
                </div>
              </Panel>
            ))}
          </div>
        </section>

        {/* 5. WORKSPACE GATEWAYS + ILLUSTRATIVE METRO PREVIEW */}
        <section id="corridors" className="grid grid-cols-1 lg:grid-cols-12 gap-4 scroll-mt-20">
          <Panel className="lg:col-span-7 p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
              <div>
                <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
                  05 · Micro-Market Intelligence Preview
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
              {
                route: 'comparables' as const,
                icon: Database,
                title: 'Evidence Verification & Ledger',
                desc: 'Inspect SHA-256 document hashes, Sub-Registrar deed segregation, and verification audit history.',
              },
              {
                route: 'rental' as const,
                icon: Scale,
                title: 'Rental Investment & NOI Lab',
                desc: 'Model NOI, cap rates, vacancy allowance, GRM, and cash-flow sensitivity interactively.',
              },
              {
                route: 'market' as const,
                icon: Activity,
                title: 'Market Analytics & TreeSHAP',
                desc: 'Explore city-tier drivers, seasonality gates, and live feature attributions across trained models.',
              },
              {
                route: 'reports' as const,
                icon: FileSpreadsheet,
                title: 'Downloadable Dossiers',
                desc: 'Export complete printable HTML appraisal certificates and structured JSON valuation ledgers.',
              },
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

        {/* 6. FINAL CTA */}
        <Panel className="p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              06 · Launch Instrument
            </span>
            <h3 className="font-serif text-2xl sm:text-3xl">Enter the architectural valuation terminal.</h3>
            <p className="text-xs text-[var(--text-secondary)]">
              Run interactive 3D site inspection, 8-gate underwriting, and full three-way appraisal reconciliation.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setRoute('valuation')}
            className="arch-btn px-6 py-3 font-mono text-xs font-semibold uppercase tracking-wider shrink-0 flex items-center gap-2"
            style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
          >
            <Building2 className="w-4 h-4" />
            <span>Launch Main Website →</span>
          </button>
        </Panel>
      </main>
    </div>
  );
}
