# PropAI — Valuation Engine Deep Dive

- **Project:** PropAI — AI-Powered Property Valuation & Spatial Intelligence Platform  
- **Team Name:** GROWMAP  
- **Team Member:** Omm Priyanshu Pati  
- **PowerPoint Decks:**
  - [PropAI_Valuation_Engine_DeepDive.pptx](PropAI_Valuation_Engine_DeepDive.pptx)
  - [PropAI_ECellIITBombay.pptx](PropAI_ECellIITBombay.pptx)
- **Live Website Demo Video:** [PropAI_Website_Demo.mp4](PropAI_Website_Demo.mp4)

---

## Slide 1 — Title Overview
**PropAI Valuation Engine — Team GROWMAP (Omm Priyanshu Pati)**  
Seven signal clusters powering explainable property valuation:
`Connectivity` · `Traffic Volume` · `Population` · `Future Scope` · `Govt Projects` · `Live Market` · `Physical`

---

## Slide 2 — Engine Architecture: How All Clusters Flow Together
7 signal clusters feed a unified feature matrix $\rightarrow$ ML ensemble + comparables $\rightarrow$ explainable appraisal output:
- **Inputs (32 total signals):** `dist_nh_km`, `peak_hour_vol`, `colony_density`, `fsi_allowed`, `smart_city_flag`, `price_6m_delta`, `sqft`, and physical/title attributes.
- **Core Stack:** Gradient Boosted Trees (`XGBoost` + `CatBoost`/`LightGBM`) + Spatial Comparables + Geospatial Zone Layer + **TreeSHAP** explainability.
- **Outputs:** Fair Market Value, Quantile Confidence Band, 1Y / 3Y / 5Y Outlook, Top Value Drivers, and OOD / Title Risk Flags.

---

## Slide 3 — Cluster 1: Connectivity & Infrastructure Distance
- **`dist_nh_km`** — Distance to nearest National / State Highway (0.5–2 km optimal band `+8–12%`).
- **`dist_metro_km`** — Distance to metro / suburban rail (<500 m transit premium `+15–22%`).
- **`dist_civic_km`** — Composite weighted proximity to hospitals (`40%`), schools (`30%`), markets (`20%`), police (`10%`).
- **`dist_airport_km`** — Distance to international/domestic airport & SEZ / industrial corridors.

---

## Slide 4 & 5 — Cluster 2: Traffic Volume Signals & Dual Interpretation Rule
- **`vehicles_per_min`**, **`peak_hour_volume`**, **`weekday_weekend_ratio`**, **`monthly_yoy_growth`**
- **`heavy_vehicle_pct`**, **`congestion_index`**, **`noise_proxy_db`**, **`zone_type_classifier`**
- **Conditional Rule:** Sustained traffic & arterial throughput act as a positive commercial demand indicator while excess noise (>65 dB) is discounted specifically for residential setbacks.

---

## Slide 6 — Cluster 3: Population & Colony Profile
- **`colony_density`** (ward population per sq km)
- **`income_cluster`** (HIGH / MID-HIGH / MID / LOW-MID / LOW quintiles)
- **`pop_growth_rate`** (10-year ward CAGR)
- **`amenity_score`** (0–100 neighborhood liveability index within 1 km)

---

## Slide 7 & 8 — Cluster 4: Future Development Scope (Parts 1 & 2)
- **`master_plan_zone`**, **`fsi_allowed`** (Development Control Regulations / buildable floor area potential)
- **`upcoming_corridor_flag`**, **`years_to_completion`** (8% annual time-discount factor)
- **`it_park_dist_km`**, **`sez_township_flag`**, **`job_creation_potential`**, **`land_acquisition_risk`**

---

## Slide 9 — Cluster 5: Government Project Signals
- **`smart_city_flag`** (MoHUA Smart Cities Mission status)
- **`rera_density_2km`** (active RERA-registered developments within 2 km)
- **`pmay_zone_flag`** (affordable housing policy zones)
- **`infra_spend_score`** (0–100 district infrastructure capital expenditure score)

---

## Slide 10 — Cluster 6: Current Market Conditions (Live Pulse)
- **`price_sqft_6m_delta`** (micro-market rolling momentum)
- **`transaction_velocity`** (registered deals/month trend)
- **`inventory_overhang_months`** (unsold stock vs monthly absorption)
- **`rental_yield_pct`** (`(monthly_rent × 12) / market_value × 100` capitalization anchor)

---

## Slide 11 — Cluster 7: Physical Property Attributes
- **`built_up_area_sqft`** & BHK configuration + carpet ratio
- **`construction_quality`** (`Grade A / B / C`, CPWD replacement basis minus age depreciation)
- **`title_status`** (`CLEAR` / `DISPUTED` / `ENCUMBERED` / `AGRICULTURAL`)
- **`floor_view_premium`** (elevation level, directional orientation, open-view clearance)

---

## Slides 12–19 — Model Ensemble, TreeSHAP Explainability & Compliance
- **Geographic Weight Calibration:** Re-weights transit/FSI in Mumbai MMR, highway/SEZ in Delhi NCR, IT proximity in Bengaluru/Hyderabad, and infra spend in Tier-2 hubs.
- **SHAP Waterfall & Global Feature Ranking:** Transparent `+₹` / `−₹` feature contributions reconciling exact log-space base values to appraised output.
- **Governance & Honest Uncertainty Safeguards:**
  - Strict separation of unverified quotes/broker records from Sub-Registrar executed Sale Deeds.
  - Explicit `INSUFFICIENT_VERIFIED_GROUND_TRUTH` / `INSUFFICIENT_EVIDENCE` / `DATA NOT READY` safeguards (`agricultural` & `industrial` cohorts) so sparse local data never fabricates confidence.
