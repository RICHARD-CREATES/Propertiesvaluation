# Data Acquisition & Provenance Report

**Date:** 2026-11-10  
**Compliance Protocol:** Legal data acquisition strictly following public access boundaries without CAPTCHA bypass, unauthorized scraping, or credential circumvention.

---

## 1. Data Sources Acquired & Processed

| Source ID | Name | Type | Records Acquired | Local Destination | Provenance & Validation |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `nhb_residex` | NHB RESIDEX 50-City HPI | Government Price Index | 50 cities $\times$ quarterly indices | `data/raw/nhb_residex_indices.csv` | Official NHB quarterly releases compiled |
| `rbi_dbie_hpi` | RBI 10-City House Price Index | Central Bank Series | 10 metros longitudinal | `data/raw/rbi_hpi_series.csv` | Official RBI DBIE base index series |
| `odisha_igr_bmv` | Odisha IGR Benchmark Rates | Government BMV Table | Mouza/Ward benchmarks | `data/raw/odisha_bmv_rates.csv` | Public revenue guidance values |
| `cpwd_cost_index`| CPWD PAR Construction Cost | Standard Schedule Rates | 1995–2026 historical rate index | Ingested into `src/core/construction_cost.py` | Official MoHUA CPWD Plinth Area Rates |
| `openstreetmap` | OSM Geocoding & POI API | Spatial features | Live geospatial queries | Interfaced via Overpass & Nominatim | OpenStreetMap ODbL compliance |

---

## 2. Ingestion & Preprocessing Verification

All acquired price and benchmark series are passed through the Phase 4 pipeline:
1. Currency is standardized to **INR**.
2. Coordinate ranges are validated to within official Indian bounding boxes ($[8.0, 37.5]^\circ\text{ N}$, $[68.0, 97.5]^\circ\text{ E}$).
3. Area units are rigorously parsed and converted to **Square Feet** (`area_sqft`) while recording the original unit.
4. Target types are strictly partitioned into:
   - `registered_transaction_price`
   - `government_benchmark` (Circle rate / BMV)
   - `market_asking_price`
   - `rental_observation`
5. Agricultural and Industrial models are classified as `DATA NOT READY` due to lack of verified state deed transaction level registries on disk.
