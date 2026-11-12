# Training Readiness Assessment Report

**Audit Date:** 2026-11-10  
**Status Criteria:**
- **READY FOR TRAINING:** Genuine transaction data exists, schemas validated, train/val split ready.
- **DATA PREPARATION REQUIRED:** Partial data / benchmark tables available; requires ingestion and normalization pipeline.
- **DATA NOT READY:** Insufficient genuine transaction records available on disk; strictly forbidden from synthetic training or fabricated claims per project policy.

---

## 1. Readiness Matrix for the 7 Property Valuation Models

| Model # | Target Category | Data Readiness Status | Available Genuine Rows | Target Variable | Primary Blocker | Action Plan |
| :---: | :--- | :---: | :---: | :--- | :--- | :--- |
| **Model 1** | **Residential Apartments** | ⚠️ **DATA PREPARATION REQUIRED** | 0 on disk | `log1p(price_inr)` | No persistent parquet dataset on disk | Ingest NHB RESIDEX + City Hub transaction anchors into `datasets/training/apartments.parquet` |
| **Model 2** | **Independent Houses & Villas** | ⚠️ **DATA PREPARATION REQUIRED** | 0 on disk | `log1p(price_inr)` | Separate land area vs built-up area records missing | Ingest Land Basis + CPWD cost decomposition into `datasets/training/houses.parquet` |
| **Model 3** | **Residential Land / Plots** | ⚠️ **DATA PREPARATION REQUIRED** | 0 on disk | `log1p(price_per_sqft_inr)` | Micro-market plot transactions not aggregated into parquet | Ingest State BMV / Circle Rates + Market rate indices into `datasets/training/residential_land.parquet` |
| **Model 4** | **Commercial Properties** | ⚠️ **DATA PREPARATION REQUIRED** | 0 on disk | `log1p(price_inr)` | High commercial variance between retail & office | Ingest Commercial corridor benchmarks into `datasets/training/commercial.parquet` |
| **Model 5** | **Agricultural Land** | 🔴 **DATA NOT READY** | 0 | `log1p(price_per_acre_inr)` | Soil classification, irrigation data, and rural deed records absent | Flag as `DATA NOT READY`; build ingestion schema for district land records |
| **Model 6** | **Industrial Land** | 🔴 **DATA NOT READY** | 0 | `log1p(price_per_sqft_inr)` | MIDC / GIDC / RIICO industrial estate registry records absent | Flag as `DATA NOT READY`; build ingestion schema for industrial corridors |
| **Model 7** | **Rental Properties** | ⚠️ **DATA PREPARATION REQUIRED** | 0 on disk | `log1p(monthly_rent_inr)` | Longitudinal rental listings not compiled into parquet | Ingest city rental yield benchmarks (2.5% - 4.5%) into `datasets/training/rental.parquet` |

---

## 2. Technical Prerequisites Before Model Training

1. **Phase 3 & 4 Implementation:**
   - Create directories:
     - `data/raw/`
     - `data/processed/`
     - `data/manifests/`
     - `datasets/training/`
     - `models/`
     - `processing/`
   - Implement data processing scripts:
     - `processing/clean_transactions.py`
     - `processing/normalize_units.py`
     - `processing/validate_coordinates.py`
     - `processing/deduplicate.py`
     - `processing/build_training_dataset.py`

2. **Phase 5 Geospatial & GPS Feature Engineering:**
   - Standardize GPS validation: Latitude within $[8.0, 37.5]^\circ\text{ N}$, Longitude within $[68.0, 97.5]^\circ\text{ E}$.
   - Generate distance features to national highways, transit, airports, and city centers.
   - Enforce spatial holdout validation: hold out entire cities/districts (e.g. train on Tier-1/Tier-2 hubs, validate on holdout cities) to avoid spatial autocorrelation leakage.

3. **Phase 7 & 8 Training & Evaluation Pipelines:**
   - Build `src/models/train_all_models.py` supporting CatBoost, LightGBM, and XGBoost with `log1p(price)` target.
   - Compute true holdout MAE, RMSE, MedAPE, and R² without fabrication.
   - Save model bundles to `models/{category}/model.cbm`, `preprocessor.joblib`, `feature_schema.json`, and `metrics.json`.
