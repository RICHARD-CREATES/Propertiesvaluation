# Existing Models Inventory

**Audit Date:** 2026-11-10  
**Scope:** Forensic evaluation of all existing models, estimators, heuristics, and pipelines in the repository.

---

## 1. Inventory Summary Across 7 Target Valuation Categories

| Category # | Target Property Category | Existing Model Code / Class | Algorithm | Current Training Status | Actual Trained Artifact on Disk? |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **M1** | **Residential Apartments** | `PropertyValuationModel` / `SpecialistModels` | Heuristic + XGB/GBM on synthetic | **UNTRAINED (Synthetic only)** | ❌ No (`.joblib` / `.cbm` missing) |
| **M2** | **Independent Houses & Villas** | Heuristic Land Residual formula | Cost Approach formula | **HEURISTIC CALCULATION** | ❌ No ML artifact on disk |
| **M3** | **Residential Land / Plots** | `location_intelligence.py` Land Rate | Micro-Market Base Rate Lookup | **LOOKUP TABLE ONLY** | ❌ No ML artifact on disk |
| **M4** | **Commercial Properties** | Dual-Signal Interaction in Assembler | Heuristic Multipliers | **UNTRAINED** | ❌ No ML artifact on disk |
| **M5** | **Agricultural Land** | None (Stub in schema) | Not implemented | **NOT IMPLEMENTED** | ❌ No ML artifact on disk |
| **M6** | **Industrial Land** | Cluster 4/5 SEZ proximity | Heuristic distance scoring | **NOT IMPLEMENTED** | ❌ No ML artifact on disk |
| **M7** | **Rental Properties** | `M10 RentalInvestmentAI` | Gross Yield Heuristic formula | **HEURISTIC CALCULATION** | ❌ No ML artifact on disk |

---

## 2. Detailed Technical Audit of Existing Model Implementations

### Model 1: `PropertyValuationModel` (`src/models/trainer.py`)
- **Model Name:** Unified Property Valuation Ensemble
- **Property Category:** Multi-category urban properties (Residential, Retail, Office, Industrial)
- **Algorithm:** Weighted Ensemble (0.55 XGBoost Regressor + 0.45 Sklearn GradientBoostingRegressor with Huber Loss)
- **Training Dataset:** Generated on the fly in `main.py` via `src/data_generator.py` (Powai synthetic generator)
- **Dataset Row Count:** 1,000 to 1,200 synthetic rows
- **Feature Count:** ~28 engineered features derived from the 7 clusters
- **Training Status:** **NOT PERSISTED**. Trains ephemerally during script execution, but weights are discarded upon script exit.
- **Existing Evaluation Metrics:**
  - Synthetic 5-Fold Cross Validation reported in `main.py`:
    - Mean CV MAE: ~₹24 Lakhs (on synthetic data)
    - Mean CV R²: ~0.94 (on synthetic data)
    - Mean CV MAPE: ~7.5% (on synthetic data)
    *Note: These metrics are on synthetic Powai data and do NOT reflect real-world all-India generalization.*
- **Model Artifact Location:** None. `models/` directory does not exist in root.
- **Missing Dependencies:** None (XGBoost, LightGBM, Sklearn, and CatBoost are installed).
- **Bugs and Required Improvements:**
  - Artifacts are never saved to disk with `joblib.dump()` or `model.save_model()`.
  - Target variable is raw price (`target_price_inr`) rather than `log1p(price_inr)`.
  - Splitting uses random `KFold(shuffle=True)` which causes spatial data leakage across neighboring properties.
  - No distinction between registered transaction prices, circle rates, and asking prices.

---

### Model 2: The Ten Specialist Models (`src/services/specialist_models.py`)
- **Model Name:** 10 Specialist AI Models (M01 to M10)
  1. *M01: Transaction Intelligence AI* (k-NN spatial anchor blend)
  2. *M02: Government & Cadastral AI* (FSI/FAR, zoning, title multipliers)
  3. *M03: Satellite & Building Intelligence AI* (Footprint, height, vegetation adjustments)
  4. *M04: Geospatial Connectivity AI* (Transit distance decay formulas)
  5. *M05: Traffic & Mobility AI* (Dual-signal commercial footfall boost vs residential noise penalty)
  6. *M06: Population & Demographic AI* (Income proxy & density scaling)
  7. *M07: Real Estate Market AI* (Price momentum & absorption multipliers)
  8. *M08: Physical Property AI* (Age depreciation & construction quality grading)
  9. *M09: Future Development AI* (Announced infrastructure uplift)
  10. *M10: Rental & Investment AI* (Gross yield & cap rate estimation)
- **Property Category:** General urban real estate
- **Algorithm:** Deterministic rule-based engines, non-linear physical formulas, and spatial blending
- **Training Dataset:** None (Parameterized rule engines calibrated to regional benchmark anchors)
- **Dataset Row Count:** 0
- **Feature Count:** 10 to 45 input covariates across the 10 models
- **Training Status:** **NOT AN ML TRAINED MODEL**. These are expert systems providing calibration constraints and SHAP explainability proxies.
- **Existing Evaluation Metrics:** N/A (Rule engines)
- **Model Artifact Location:** In-memory Python classes in `src/services/specialist_models.py`
- **Bugs and Required Improvements:**
  - Need to be backed by actual supervised ML estimators (CatBoost/LightGBM/XGBoost) trained on genuine deed transactions and benchmark tables.

---

### Model 3: Starter Cohort Trainer (`deteail/.../src/train.py`)
- **Model Name:** Global Cohort Specialist & Generalist Trainer
- **Property Category:** Filtered by `(country_code, asset_type)` cohorts
- **Algorithm:** CatBoostRegressor (`iterations=900, depth=8, loss='MAE'`) with HistGradientBoostingRegressor fallback
- **Training Dataset:** Points to `data/processed/property_training.csv` (which does not exist)
- **Dataset Row Count:** 0
- **Feature Count:** Configured via `configs/schema.yaml`
- **Training Status:** **NOT EXECUTED**. Cannot run because `property_training.csv` is missing.
- **Existing Evaluation Metrics:** None.
- **Model Artifact Location:** Targeted to `models/{country}_{asset}__{cluster}.joblib` (uncreated)
- **Bugs and Required Improvements:**
  - Missing real training data.
  - Requires integration into the main project root rather than sitting inside `deteail/`.
