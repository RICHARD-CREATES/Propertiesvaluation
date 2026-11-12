# Model Evaluation Report — All-India Property Valuation Engine

**Evaluation Date:** 2026-11-10 22:20:25  
**Validation Methodology:** Spatially Separated Geographic Holdout (held-out states and districts to evaluate cross-region generalization).  
**Target Transformation:** $\log(1 + y)$ target fitting with inverse exponential back-transformation $\exp(p) - 1$.

---

## 1. Summary of Champion Models

| Property Category | Champion Algorithm | Training Samples | Holdout Samples | Holdout $R^2$ | MedAPE (%) | Holdout MAE (INR) | Interval Coverage (±15%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Apartment** | XGBoost | 552 | 324 | **-0.2173** | **59.22%** | Rs. 19,181,203 | 7.41% |
| **House** | CatBoost | 184 | 108 | **-0.2854** | **45.07%** | Rs. 31,428,332 | 16.67% |
| **Residential_Land** | CatBoost | 276 | 162 | **-0.2414** | **62.47%** | Rs. 33,443,462 | 13.58% |
| **Commercial** | CatBoost | 184 | 108 | **-0.1005** | **55.87%** | Rs. 43,958,317 | 12.96% |
| **Rental** | XGBoost | 138 | 81 | **0.2664** | **32.49%** | Rs. 27,281 | 19.75% |
| **Agricultural Land** | *None* | 0 | 0 | N/A | N/A | N/A | **DATA NOT READY** |
| **Industrial Land** | *None* | 0 | 0 | N/A | N/A | N/A | **DATA NOT READY** |

---

## 2. Multi-Algorithm Validation Comparison

### Apartment Models Comparison

| Algorithm | Holdout $R^2$ | MedAPE (%) | MAPE (%) | Holdout MAE (INR) |
| :--- | :---: | :---: | :---: | :---: |
| CatBoost | -0.1901 | 60.43% | 52.05% | Rs. 18,535,876 |
| XGBoost ★ (Champion) | -0.2173 | 59.22% | 54.73% | Rs. 19,181,203 |

### House Models Comparison

| Algorithm | Holdout $R^2$ | MedAPE (%) | MAPE (%) | Holdout MAE (INR) |
| :--- | :---: | :---: | :---: | :---: |
| CatBoost ★ (Champion) | -0.2854 | 45.07% | 45.74% | Rs. 31,428,332 |
| XGBoost | -0.3288 | 46.09% | 47.06% | Rs. 32,501,070 |

### Residential_Land Models Comparison

| Algorithm | Holdout $R^2$ | MedAPE (%) | MAPE (%) | Holdout MAE (INR) |
| :--- | :---: | :---: | :---: | :---: |
| CatBoost ★ (Champion) | -0.2414 | 62.47% | 54.23% | Rs. 33,443,462 |
| XGBoost | -0.3075 | 64.37% | 56.49% | Rs. 35,395,988 |

### Commercial Models Comparison

| Algorithm | Holdout $R^2$ | MedAPE (%) | MAPE (%) | Holdout MAE (INR) |
| :--- | :---: | :---: | :---: | :---: |
| CatBoost ★ (Champion) | -0.1005 | 55.87% | 52.69% | Rs. 43,958,317 |
| XGBoost | -0.1938 | 61.68% | 58.38% | Rs. 47,496,556 |

### Rental Models Comparison

| Algorithm | Holdout $R^2$ | MedAPE (%) | MAPE (%) | Holdout MAE (INR) |
| :--- | :---: | :---: | :---: | :---: |
| CatBoost | 0.0423 | 35.36% | 39.1% | Rs. 30,579 |
| XGBoost ★ (Champion) | 0.2664 | 32.49% | 39.09% | Rs. 27,281 |

---

## 3. Data Integrity & Verification Standard

- **No Synthetic Label Inflation:** Models are evaluated strictly on real spatial holdouts.
- **Agricultural & Industrial Categories:** Explicitly flagged as `DATA NOT READY` per strict compliance directives until genuine state land deed registers are ingested.
- **Spatially Separated Performance:** Detailed state-wise and city-wise metrics are exported to [`reports/STATE_WISE_PERFORMANCE.csv`](file:///e:/project/iit%20bombay%20house%20valutuion/reports/STATE_WISE_PERFORMANCE.csv) and [`reports/LOCALITY_WISE_PERFORMANCE.csv`](file:///e:/project/iit%20bombay%20house%20valutuion/reports/LOCALITY_WISE_PERFORMANCE.csv).
