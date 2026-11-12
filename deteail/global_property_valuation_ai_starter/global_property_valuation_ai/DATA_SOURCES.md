# Dataset catalogue — global property valuation

The world does not have one unified, open, property-level sale transaction database. Build a federated country-by-country transaction layer, then enrich it with global covariates.

## A. Closed-sale / transaction labels (highest priority)

| Source | Coverage / content | Use | Access / caveat |
|---|---|---|---|
| UK HM Land Registry Price Paid Data | England & Wales residential sales; price, date, address/property metadata | Core supervised transaction labels | Free CSV; Open Government Licence. https://use-land-property-data.service.gov.uk/datasets/td |
| France DVF | Recorded sales for much of France; price, date, property and parcel information | Core supervised labels; parcel joins | Open Licence 2.0; excludes Alsace, Moselle and Mayotte. https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres |
| France DVF+ | Geolocated and structured DVF transaction records | Geospatial comparable-sales model | Open Licence 2.0. https://www.data.gouv.fr/datasets/dvf-open-data |
| US county assessor / recorder open data | County-specific sale deeds, assessments, parcel and building characteristics | Residential, commercial and land labels | Highly fragmented; check each county licence, definitions and completeness. |
| India state registration / IGR and circle-rate portals | State-specific registered deeds, guidance values and stamp-duty data | India transaction/benchmark layer | Access and reuse vary by state; circle rates are not market sale prices. Do not treat guidance values as transaction labels. |
| Global Property Metrics | Country/city official price, rent and yield aggregates | Market-level calibration and macro context | Not property-level comparable sales; review source methodology and terms. https://globalpropertymetrics.com/data |

## B. Government, cadastral, parcels and planning

- OpenAddresses: global address points, source-specific licensing — https://openaddresses.io/
- OpenStreetMap: roads, land use, amenities, POIs and some buildings; ODbL attribution/share-alike obligations — https://planet.openstreetmap.org/
- Overture Maps: global buildings, places, addresses, transport and administrative boundaries — https://docs.overturemaps.org/
- National cadastral/land registry portals: source by country; legal access varies. Do not assume global open access.
- UK planning / local authority open data and France cadastre/DVF+ can support market-specific parcel joins.

## C. Satellite, building footprints and physical context

- Microsoft Global ML Building Footprints: 1.4B+ detected building footprints across 225 regions; CDLA Permissive 2.0 per source repository. https://github.com/microsoft/GlobalMLBuildingFootprints/
- Google Open Buildings: 1.8B building detections, particularly Global South; footprint geometry and confidence. https://sites.research.google/gr/open-buildings/
- OpenBuildingMap: global footprint, occupancy, height and floorspace aggregation; ODbL 1.0. https://www.openbuildingmap.org/
- Copernicus Sentinel-2: global multispectral imagery; free access via Copernicus Data Space. https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2
- USGS Landsat: free archive and access tools. https://www.usgs.gov/landsat-missions/landsat-data-access
- GHSL: built-up surface, settlement and population-related layers. https://ghsl.jrc.ec.europa.eu/

Satellite-derived signals can estimate neighbourhood built-up change, vegetation, impervious surface and broad land-use context. They cannot prove ownership, title, internal condition or legal floor area.

## D. Geospatial, transport, accessibility and amenities

- OpenStreetMap / Geofabrik regional extracts: roads, rail, transit, POIs, amenities and land use. https://download.geofabrik.de/
- Overture Maps: transport network, places, buildings and divisions. https://docs.overturemaps.org/
- OpenRouteService: routing and travel-time matrices; API/service limits apply. https://openrouteservice.org/
- GTFS feeds: public transit routes, stops and schedules; obtain from each transit agency or catalogue. https://gtfs.org/
- Airport, rail and public infrastructure datasets: use national transport agencies and local open-data portals.

## E. Traffic and mobility

- TomTom Traffic Index: city congestion, speeds and travel-time indicators; selected hourly city CSV downloads. https://www.tomtom.com/downloads/traffic-index/
- TomTom Area Analytics / commercial mobility products: broader granular historical data may require a licence.
- City and national transport open-data portals: traffic counts, loop detectors, road sensors and vehicle classifications; coverage varies.
- OpenStreetMap road network: useful road density/connectivity proxy, not observed vehicle counts.

Do not invent vehicle/minute or vehicle/hour values from road class alone. Store traffic count, time window, direction, sensor location, vehicle classes, source and observation timestamp.

## F. Population, demographics and income proxies

- WorldPop Global2: global 1km and country 100m population grids, annual 2015–2030 estimates; inspect release methodology. https://hub.worldpop.org/project/categories?id=3
- GHSL population and built-up layers: https://ghsl.jrc.ec.europa.eu/
- UN World Population Prospects 2024: national population estimates/projections for 237 countries/areas. https://population.un.org/wpp/
- World Bank geospatial population platform catalogue: https://datacatalog.worldbank.org/search/dataset/0037809/world-external-geospatial-platforms-population
- Income: national statistical agencies, census tables and World Bank indicators. Use spatially appropriate, licensed aggregates; do not infer individual household income.

## G. Market trends, macro and yields

- OECD Analytical House Price Indicators: quarterly/annual residential price, rent, price-to-rent and price-to-income series. https://data-explorer.oecd.org/
- BIS Commercial Property Price Statistics: commercial price series for 20+ countries, with varying coverage/definitions. https://data.bis.org/topics/CPP
- Global Property Metrics: official-source country/city price, rent and yield aggregates. https://globalpropertymetrics.com/data
- Central banks / national statistics offices: policy rates, mortgage rates, CPI, employment and construction indices.

## Suggested first training markets

1. England & Wales: Land Registry transaction labels + OSM + WorldPop + Sentinel-2.
2. France: DVF/DVF+ labels + cadastral/geospatial joins + OSM + WorldPop.
3. Selected US counties: county deed/assessor data + parcel geometry + census + roads.
4. Expand to other countries only after confirming label quality, licensing, currency, property type and feature definitions.

## Source validation checklist

For every imported dataset record:
`source_id, source_url, provider, licence, attribution, country, spatial_resolution, temporal_coverage, update_frequency, extraction_date, schema_version, permitted_purpose`.
