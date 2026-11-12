# Project Audit Report — India Property Valuation ML System

**Audit Date:** 2026-11-10  
**Auditor:** Senior ML & Geospatial Infrastructure Engineer  
**Workspace Root:** `E:\project\iit bombay house valutuion`  

---

## 1. Executive Summary

This comprehensive codebase audit evaluates the repository against the production-grade requirements of an all-India GPS-based property valuation system covering seven distinct property categories:
1. Residential Apartments
2. Independent Houses & Villas
3. Residential Land / Plots
4. Commercial Properties
5. Agricultural Land
6. Industrial Land
7. Rental Properties

### Key Audit Findings:
1. **Architecture Quality:** The codebase possesses a well-structured domain foundation (`src/pipeline/feature_assembler.py`, `src/clusters/`, `src/services/valuation_engine.py`, `src/services/location_intelligence.py`) and a working FastAPI web application (`src/api/app.py`, `src/api/static/index.html`) running on port 8000.
2. **Current Model Implementation Reality:** There are **zero saved ML model weight artifacts** (`.joblib`, `.cbm`, `.pkl`, `.onnx`) on disk. The 10 "specialist AI models" currently operating in `src/services/specialist_models.py` are heuristic expert algorithms and spatial anchor blends, **not models trained on actual property transaction records**.
3. **Dataset Reality:** There are **no real-world transaction datasets** (`.csv`, `.parquet`, `.sqlite`) stored in the repository. The only data files are a 1-row template in `deteail/.../configs/example_property_row.csv` and an in-memory synthetic generator (`src/data_generator.py`) simulating Powai (Mumbai) coordinates.
4. **Starter Pack In `deteail/`:** An extracted starter package exists in `deteail/global_property_valuation_ai_starter/global_property_valuation_ai/` with scripts for cohort-based CatBoost/HistGradientBoosting training (`src/train.py`, `src/evaluate.py`), but it was never integrated into the primary training pipeline.
5. **Dependencies:** `xgboost`, `lightgbm`, `scikit-learn`, `shap`, `pandas`, `fastapi`, and now `catboost` (v1.2.10) are installed and verified. Geospatial tools (`geopandas`, `pyrosm`, `osmnx`) are currently missing.

---

## 2. Directory & Component Inventory

```
E:\project\iit bombay house valutuion
├── configs/
│   └── schema.yaml                     # Unified 10-cluster schema and categorical column definitions
├── deteail/
│   ├── global_property_valuation_ai_starter.zip
│   └── global_property_valuation_ai_starter/global_property_valuation_ai/
│       ├── configs/ (schema.yaml, example_property_row.csv [1 row dummy])
│       ├── data/ (raw/.gitkeep, processed/.gitkeep)
│       ├── models/ (.gitkeep)
│       ├── reports/ (.gitkeep)
│       └── src/ (common.py, train.py, evaluate.py, predict.py)
├── reports/                            # Created for Phase 1 audit deliverables
├── src/
│   ├── api/
│   │   ├── app.py                      # FastAPI server (location, search, valuation, audit endpoints)
│   │   └── static/index.html           # Full Leaflet + Google Maps single-page valuation UI
│   ├── clusters/                       # 7 Cluster feature extractors
│   │   ├── cluster1_connectivity.py    # Highway, metro, rail, transit accessibility scoring
│   │   ├── cluster2_traffic.py         # Dual-signal traffic volume, congestion, noise DB proxies
│   │   ├── cluster3_population.py      # Population density and income proxy scoring
│   │   ├── cluster4_development.py     # Infrastructure completion and smart city uplift
│   │   ├── cluster5_government.py      # FSI/FAR headroom, title clearance, zoning multipliers
│   │   ├── cluster6_market.py          # Price index momentum, inventory absorption, market cycle
│   │   └── cluster7_physical.py        # Physical condition, quality grade, age depreciation
│   ├── core/
│   │   ├── cohort.py                   # Country and asset type routing logic
│   │   ├── construction_cost.py        # CPWD / State PWD historical cost index & structural depreciation
│   │   └── units.py                    # Multi-unit conversions (sqft, sqm, local currency formatting)
│   ├── models/
│   │   ├── explainability.py           # TreeSHAP factor contribution & multi-horizon forecast
│   │   └── trainer.py                  # XGBoost + GradientBoostingRegressor 5-fold CV trainer
│   ├── pipeline/
│   │   ├── feature_assembler.py        # Multi-cluster matrix assembler (7 clusters + interactions)
│   │   └── interaction_layer.py        # Dual-signal interactions (e.g. traffic vs retail/residential)
│   ├── services/
│   │   ├── location_intelligence.py    # 50+ Pan-India hubs, micro-market resolver, OSM Nominatim/Photon
│   │   ├── missing_detection.py        # Data completeness and validation auditor
│   │   ├── specialist_models.py        # 10 heuristic domain models (M01 to M10)
│   │   └── valuation_engine.py         # Orchestrator with two-step Land First + House Cost calculation
│   └── data_generator.py               # In-memory synthetic generator for Powai (1,200 rows)
├── tests/
│   ├── test_global_engine.py           # 6 unit tests for valuation engine
│   └── test_pipeline.py                # 4 unit tests for feature assembler & trainer
├── main.py                             # CLI test pipeline execution script
├── requirements.txt                    # Project dependencies
├── README.md                           # Documentation
└── serve.py                            # Production Uvicorn server launcher
```

---

## 3. Technology Stack & Environment

| Component | Tool / Library | Version / Status | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | CPython | 3.11.x (Windows x64) | Active environment |
| **Tabular ML** | `xgboost` | >= 2.0.0 (Installed) | Functional |
| **Tabular ML** | `lightgbm` | Installed | Functional |
| **Tabular ML** | `catboost` | 1.2.10 (Installed) | Newly installed & verified |
| **General ML** | `scikit-learn` | >= 1.3.0 (Installed) | Pipelines, KFold, metrics |
| **Explainability** | `shap` | >= 0.42.0 (Installed) | TreeSHAP explainer |
| **Web Server** | `fastapi`, `uvicorn` | Installed | Running on `http://0.0.0.0:8000` |
| **Parquet / Arrow**| `pyarrow` | Installed | Ready for parquet read/write |
| **Geospatial Tools**| `geopandas`, `osmnx` | **NOT Installed** | Standard `urllib` + OSM used |

---

## 4. Key Gaps & Action Items for 7-Model System

1. **Model Persistence:** Model weights must be saved in standard serialized formats (`models/<category>/model.cbm`, `preprocessor.joblib`, `feature_schema.json`, `metrics.json`).
2. **Real Data Acquisition:** Real-world benchmark rate sheets, NHB RESIDEX indices, RBI housing price data, and state benchmark value (BMV) tables must be acquired legally and stored systematically.
3. **Local Land Unit Standardization:** State-specific conversions for **Guntha** (Odisha/MH = 2,400 sq ft), **Decimal** (435.6 sq ft), **Gaj / Sq Yards**, and **Bigha** must be formally codified in `processing/normalize_units.py`.
4. **Data Leakage & Spatial Splits:** Training must avoid random train/test splits. Spatially separated validation (by district/pincode) and temporal holdouts must be enforced.
5. **Separation of Target Types:** Benchmark values (circle rates), actual registered transaction prices, asking prices, and rental yields must not be artificially merged without explicit target type tracking.
