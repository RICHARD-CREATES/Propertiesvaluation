"""
Backend Platform Configuration & Dynamic List Catalog
=====================================================
Centralizes all UI selection lists, location presets, country jurisdictions,
asset classes, property selectors, and map layers in the backend so no static
catalogs, dropdown options, or pricing rule weights are hardcoded in frontend HTML/JS.
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.services.location_intelligence import LocationIntelligenceService


def _classify_preset_region(state: str, country: str, tier: str) -> str:
    if country != "IN":
        return "global"
    if tier.startswith("Tier_1"):
        return "metros"
    return "tier2_rural"


def _build_location_presets() -> List[Dict[str, Any]]:
    """Derives curated Pan-India & Global location presets without Bhubaneswar/Odisha directory entries."""
    presets: List[Dict[str, Any]] = []
    featured = [
        ("Powai / IIT Bombay, Mumbai", 19.1254, 72.9157, "IN", "metros"),
        ("South Mumbai (Malabar / Fort)", 18.9300, 72.8250, "IN", "metros"),
        ("Hinjawadi IT Hub, Pune", 18.5913, 73.7389, "IN", "metros"),
        ("Cyber City, Gurgaon (NCR)", 28.4595, 77.0266, "IN", "metros"),
        ("Whitefield IT Corridor, Bengaluru", 12.9698, 77.7499, "IN", "metros"),
        ("HITEC City / Gachibowli, Hyderabad", 17.4435, 78.3772, "IN", "metros"),
        ("OMR IT Corridor, Chennai", 12.9249, 80.2272, "IN", "metros"),
        ("Salt Lake Sector V, Kolkata", 22.5735, 88.4331, "IN", "metros"),
        ("GIFT City, Gandhinagar", 23.1636, 72.6836, "IN", "tier2_rural"),
        ("Gomti Nagar, Lucknow", 26.8467, 80.9462, "IN", "tier2_rural"),
        ("Kakkanad Infopark, Kochi", 10.0099, 76.3616, "IN", "tier2_rural"),
        ("Rural Taluka, Maharashtra", 19.5500, 74.5000, "IN", "tier2_rural"),
        ("Central London, UK", 51.5074, -0.1278, "GB", "global"),
        ("Lower Manhattan, New York", 40.7128, -74.0060, "US", "global"),
    ]
    seen_coords = set()
    for label, lat, lon, cc, region in featured:
        seen_coords.add((round(lat, 3), round(lon, 3)))
        presets.append(
            {
                "label": label,
                "latitude": lat,
                "longitude": lon,
                "country_code": cc,
                "region": region,
            }
        )

    # Append remaining backend HUBS excluding Odisha / Bhubaneswar micro-markets
    for h_lat, h_lon, h_city, h_state, h_country, _curr, _sqm, _sqft, h_tier in LocationIntelligenceService.HUBS:
        if h_state.strip().lower() == "odisha" or "bhubaneswar" in h_city.lower():
            continue
        key = (round(h_lat, 3), round(h_lon, 3))
        if key in seen_coords:
            continue
        seen_coords.add(key)
        presets.append(
            {
                "label": f"{h_city}, {h_state}" if h_country == "IN" else f"{h_city}, {h_country}",
                "latitude": h_lat,
                "longitude": h_lon,
                "country_code": h_country,
                "region": _classify_preset_region(h_state, h_country, h_tier),
            }
        )
    return presets


class PlatformCatalogService:
    """Backend source of truth for dynamic UI dropdowns, location lists, and navigation options."""

    @staticmethod
    def get_frontend_bootstrap_catalog() -> Dict[str, Any]:
        return {
            "default_location": {
                "label": "Powai / IIT Bombay, Mumbai",
                "latitude": 19.1254,
                "longitude": 72.9157,
                "country_code": "IN",
            },
            "region_filters": [
                {"id": "featured", "label": "Featured"},
                {"id": "metros", "label": "Pan-India Metros"},
                {"id": "tier2_rural", "label": "Tier-2 / Emerging"},
                {"id": "global", "label": "Global Hubs"},
                {"id": "all", "label": "All Locations"},
            ],
            "location_presets": _build_location_presets(),
            "countries": [
                {"value": "IN", "label": "India (INR)", "default": True},
                {"value": "GB", "label": "United Kingdom (GBP)"},
                {"value": "US", "label": "United States (USD)"},
                {"value": "FR", "label": "France (EUR)"},
            ],
            "map_layers": [
                {"id": "groad", "label": "Streets"},
                {"id": "gsat", "label": "Satellite"},
                {"id": "osm", "label": "OpenStreetMap"},
            ],
            "asset_types": [
                {"value": "residential", "label": "Residential"},
                {"value": "commercial", "label": "Commercial"},
                {"value": "land", "label": "Land / Plot"},
            ],
            "shap_property_types": [
                {"value": "apartment", "label": "Apartment (XGBoost)", "default": True},
                {"value": "house", "label": "Standalone House (CatBoost)"},
                {"value": "residential_land", "label": "Residential Land (CatBoost)"},
                {"value": "commercial", "label": "Commercial (CatBoost)"},
                {"value": "rental", "label": "Rental Yield (XGBoost)"},
            ],
            # Clean descriptive options only — zero backend weights/percentages exposed in frontend HTML
            "selectors": {
                "structure_type": [
                    {"value": "apartment", "label": "Apartment / Flat in High-Rise", "default": True},
                    {"value": "standalone_house", "label": "Standalone House / Villa / Bungalow"},
                    {"value": "builder_floor", "label": "Independent Builder Floor (Low-Rise)"},
                ],
                "area_unit": [
                    {"value": "sqft", "label": "Square Feet (sq ft)", "default": True},
                    {"value": "sqm", "label": "Square Meters (sq m)"},
                    {"value": "acre", "label": "Acres"},
                    {"value": "hectare", "label": "Hectares"},
                ],
                "construction_grade": [
                    {"value": "GRADE_A", "label": "Grade A (Luxury / Premium RCC)"},
                    {"value": "GRADE_B", "label": "Grade B (Standard Brick / RCC)", "default": True},
                    {"value": "GRADE_C", "label": "Grade C (Economy / Basic)"},
                ],
                "commercial_type": [
                    {"value": "retail", "label": "High-Street Retail Showroom", "default": True},
                    {"value": "office", "label": "Grade-A Corporate Office"},
                    {"value": "warehouse", "label": "Logistics Warehouse / Industrial"},
                ],
                "locality_tier": [
                    {"value": "prime", "label": "Prime Developed Civic Sector", "default": True},
                    {"value": "developing", "label": "Active Growth & IT Corridor"},
                    {"value": "standard", "label": "Standard Urban Neighborhood"},
                    {"value": "outskirts", "label": "Outer Periphery / Peri-Urban"},
                ],
                "road_width_ft": [
                    {"value": "40ft_plus", "label": "40+ ft Wide Main Avenue"},
                    {"value": "30ft", "label": "30 ft Standard Sector Road", "default": True},
                    {"value": "20ft", "label": "20 ft Internal Street"},
                    {"value": "15ft_narrow", "label": "Under 15 ft Narrow Lane"},
                ],
                "furnishing": [
                    {"value": "semi_furnished", "label": "Semi-Furnished (Modular & Woodwork)", "default": True},
                    {"value": "fully_furnished", "label": "Fully Furnished (Turnkey Premium)"},
                    {"value": "unfurnished", "label": "Unfurnished / Bare Shell"},
                ],
                "parking_slots": [
                    {"value": "1_covered", "label": "1 Covered Reserved Slot", "default": True},
                    {"value": "2_covered", "label": "2 Covered Reserved Slots"},
                    {"value": "open", "label": "Open / Street Parking"},
                ],
                "approval_status": [
                    {"value": "approved_freehold", "label": "Municipal / RERA Approved Freehold", "default": True},
                    {"value": "regular", "label": "Revenue / Gram Panchayat Layout"},
                ],
                "corner_plot": [
                    {"value": "corner_park", "label": "Corner Plot / Park Facing (Dual Frontage)", "default": True},
                    {"value": "standard", "label": "Standard Single-Road Frontage"},
                ],
                "maintenance_state": [
                    {"value": "well_maintained", "label": "Well Maintained Structure", "default": True},
                    {"value": "recently_renovated", "label": "Recently Renovated / Like New"},
                    {"value": "average", "label": "Standard / Original Condition"},
                ],
                "flood_risk": [
                    {"value": "none_low", "label": "Elevated Ground / Low Flood Exposure", "default": True},
                    {"value": "moderate_waterlogging", "label": "Seasonal Surface Waterlogging"},
                    {"value": "high_flood_zone", "label": "Low-Lying High Flood Zone"},
                ],
                "drainage_infra": [
                    {"value": "underground_storm", "label": "Underground Storm Sewer Network", "default": True},
                    {"value": "open_drain", "label": "Open Surface Runoff Drainage"},
                    {"value": "poor_waterlogging", "label": "Unplanned / Inadequate Drainage"},
                ],
                "groundwater_availability": [
                    {"value": "abundant", "label": "Abundant Municipal & Borewell Supply", "default": True},
                    {"value": "moderate", "label": "Moderate Seasonal Supply"},
                    {"value": "deep_boring_scarce", "label": "Scarce / Deep Boring Required"},
                ],
                "litigation_risk": [
                    {"value": "clear_verified", "label": "Clear Title / Verified Encumbrance-Free", "default": True},
                    {"value": "disputed_encumbered", "label": "Disputed / Active Legal Encumbrance"},
                ],
            },
        }
