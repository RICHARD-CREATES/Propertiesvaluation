# Dataset Inventory & Source Audit Report

**Audit Date:** 2026-11-10  
**Scope:** Complete physical audit of all existing dataset files, data generators, and external data connectors.

---

## 1. Physical Dataset Files on Disk

A recursive filesystem scan across all extensions (`.csv`, `.parquet`, `.json`, `.geojson`, `.sqlite`, `.db`) reveals the following physical data files:

| File Path | Format | Size | Rows | Content / Description | Genuine Transactions? |
| :--- | :---: | :---: | :---: | :--- | :---: |
| `deteail/.../configs/example_property_row.csv` | CSV | 421 B | 1 | Single dummy template row (`GB, residential, 250000 GBP`) | ❌ No (Dummy Schema Row) |
| `src/data_generator.py` | Python Code | 7.3 KB | 1,200 | Synthetic random normal/exponential distribution generator for Powai, Mumbai | ❌ No (Synthetic Code) |
| `src/services/location_intelligence.py` | Python Code | 30.1 KB | 50+ hubs | Hardcoded geographical coordinates and base circle/market rate tuples for Indian metros and districts | ⚠️ Benchmark Hub Coordinates |

**Conclusion:** The repository currently contains **0 bytes of real historical property deed or transaction data**.

---

## 2. Audit of the 13 Required Official & Open Sources (Phase 3)

| # | Source Name | Official URL | Data Type | Access Method & Legality | Current Local Status |
| :-: | :--- | :--- | :--- | :--- | :---: |
| **1** | **NHB RESIDEX** | `https://residex.nhbonline.org.in/` | Housing Price Indices (HPI) for 50 Indian cities | Publicly downloadable quarterly indices by city and price band | ⚠️ Not downloaded locally |
| **2** | **RBI DBIE** | `https://data.rbi.org.in/DBIE/` | All-India House Price Index (Base 2010-11=100) | Public quarterly series across 10 major cities (Mumbai, Delhi, Bengaluru, etc.) | ⚠️ Not downloaded locally |
| **3** | **Dataful RBI HPI** | `https://dataful.in/datasets/17611/` | Cleaned longitudinal RBI HPI series | Open data portal (CSV download) | ⚠️ Not downloaded locally |
| **4** | **NGDRS** | `https://ngdrs.gov.in/NGDRS_Website/` | National Generic Document Registration System | Official portal; state-specific registration access controls apply | ⚠️ Requires state-specific credentials |
| **5** | **State Benchmark Portals** | `https://ngdrs.gov.in/NGDRS_Website/state_ut_links.php?lang=en` | Stamp duty benchmark values (circle rates) by state | State revenue departments (public guidance values) | ⚠️ Local hub constants in code |
| **6** | **Odisha IGR** | `https://www.igrodisha.gov.in/viewfeevalue.aspx` | Benchmark Value (BMV) by mouza/village/ward in Odisha | Public query form for registration fees and circle rates | ⚠️ Partially mapped in `location_intelligence.py` |
| **7** | **OpenStreetMap India** | `https://download.geofabrik.de/asia/india.html` | Road network, POIs, schools, hospitals, transit | Free open data (ODbL). Regional `.osm.pbf` extracts available | ⚠️ Real-time query via Nominatim / Overpass |
| **8** | **GOBS (Grid Open Buildings)** | `https://gobs.aeee.in/get-data` | Building energy & spatial footprints for Indian cities | Open access research dataset | ⚠️ Not downloaded locally |
| **9** | **ISRO Bhuvan** | `https://bhuvan.nrsc.gov.in/` | Indian land use, land cover, geomorphology | Public web GIS services & open shapefiles | ⚠️ Not downloaded locally |
| **10**| **GHSL (Copernicus)** | `https://human-settlement.emergency.copernicus.eu/download.php` | Built-up surface & settlement density (100m, 1km) | Open open-access GeoTIFF grids | ⚠️ Not downloaded locally |
| **11**| **WorldPop** | `https://www.worldpop.org/` | 100m population density raster for India | Open CC-BY 4.0 GeoTIFF / CSV | ⚠️ Density proxy used in code |
| **12**| **Copernicus DEM** | `https://registry.opendata.aws/copernicus-dem/` | 30m Digital Elevation Model (terrain, slope) | Free public dataset on AWS S3 | ⚠️ Not downloaded locally |
| **13**| **Census India** | `https://censusindia.gov.in/census.website/en/data` | District / Sub-district demographic tables | Public government tables (PCAs) | ⚠️ Not downloaded locally |

---

## 3. Data Integrity & Compliance Constraints

1. **Synthetic vs. Genuine:** The project must strictly differentiate between synthetic test harnesses and genuine property datasets.
2. **Circle Rate vs. Market Price:** Circle rates / government benchmark values (e.g. from IGR Odisha or Maharashtra e-ASR) are statutory minimum valuation floors for stamp duty calculation. They are typically 20% to 50% below actual market transactions in prime areas. They must be tagged as `target_type: government_benchmark` and never conflated with `registered_transaction_price`.
3. **Local Land Measurement Units:** A square foot is universal ($1\text{ sq ft} = 0.092903\text{ sqm}$), but land plot units differ across states:
   - Odisha: $1\text{ Guntha} = 2,400\text{ sq ft}$; $1\text{ Decimal} = 435.6\text{ sq ft}$; $1\text{ Acre} = 40\text{ Guntha} = 100\text{ Decimal}$.
   - Maharashtra: $1\text{ Guntha} = 1,089\text{ sq ft}$ ($33\text{ ft} \times 33\text{ ft}$); $1\text{ Bigha} = 20\text{ Guntha}$.
   - Uttar Pradesh / Bihar / Bengal: $1\text{ Bigha} \approx 27,225\text{ sq ft}$ (standard) or $6,800\text{ sq ft}$ (kaccha bigha); $1\text{ Katha} = \frac{1}{20}\text{ Bigha}$.
   - North India (Delhi / Haryana / Punjab): $1\text{ Gaj} = 9\text{ sq ft} = 1\text{ Sq Yard}$.
   All conversions must be state-parameterized in `processing/normalize_units.py`.
