"""
Property-Type Conditional Interaction Layer.
Computes explicit cross-cluster interaction features to capture the dual nature
of traffic, noise, and commercial proximity across different property types.
"""
from typing import Dict, Any
import numpy as np


class PropertyTypeInteractionEngine:
    """
    Transforms traffic and spatial clusters according to property category:
    - Residential: Noise & congestion penalty vs. quiet & green premium.
    - Commercial Shop / Retail: Footfall multiplier & high passage volume premium.
    - Office Space: Commuter accessibility & weekday flow alignment.
    - Warehouse / Industrial: Logistics heavy-freight & highway proximity synergy.
    """

    ALLOWED_TYPES = ["residential", "commercial_retail", "commercial_office", "warehouse_industrial"]

    def compute_interactions(self, base_features: Dict[str, Any], property_type: str) -> Dict[str, float]:
        norm_type = str(property_type).lower().strip()
        if norm_type not in self.ALLOWED_TYPES:
            # Default to residential if unknown
            norm_type = "residential"

        # Indicators
        is_res = 1.0 if norm_type == "residential" else 0.0
        is_retail = 1.0 if norm_type == "commercial_retail" else 0.0
        is_office = 1.0 if norm_type == "commercial_office" else 0.0
        is_wh = 1.0 if norm_type == "warehouse_industrial" else 0.0

        # Extract underlying metrics
        traffic_vol = float(base_features.get("traffic_vehicles_per_min", 30.0))
        congestion = float(base_features.get("traffic_congestion_index", 0.5))
        noise_db = float(base_features.get("traffic_noise_proxy_db", 65.0))
        heavy_pct = float(base_features.get("traffic_heavy_vehicle_pct", 10.0))
        weekday_ratio = float(base_features.get("traffic_weekday_weekend_ratio", 1.1))
        dist_nh = float(base_features.get("dist_nh_km", 2.0))
        dist_metro = float(base_features.get("dist_metro_station_km", 1.5))
        fsi = float(base_features.get("fsi_far_allowable", 2.5))

        interactions = {}

        # 1. Residential Traffic Discount / Quiet Premium
        # Severe congestion (<0.5) and high noise (>70dB) trigger exponential friction
        noise_excess = max(0.0, noise_db - 65.0)
        congestion_friction = max(0.0, 0.6 - congestion)
        interactions["residential_traffic_friction"] = is_res * (
            (noise_excess * 0.08) + (congestion_friction * 2.5) + (heavy_pct * 0.03)
        )
        
        # Quiet premium: Low noise (<60 dB) + low congestion friction
        interactions["residential_quiet_premium"] = is_res * (
            max(0.0, (65.0 - noise_db) / 10.0) * (congestion ** 0.5)
        )

        # 2. Commercial Retail / Shop Footfall Premium
        # High throughput + high congestion (slower traffic = higher storefront visibility)
        storefront_visibility = 1.0 / max(congestion, 0.25)
        # Retail prefers busier weekends (weekday_ratio < 1.0)
        weekend_shopper_boost = max(0.0, 1.2 - weekday_ratio)
        interactions["commercial_retail_footfall_score"] = is_retail * (
            (np.log1p(traffic_vol) * 1.8) + (storefront_visibility * 0.4) + (weekend_shopper_boost * 1.5)
        )

        # 3. Office Commuter Transit Velocity
        # Office thrives on rapid transit + high weekday commuter volume
        commuter_flow = max(0.0, weekday_ratio - 1.0)
        interactions["office_transit_synergy"] = is_office * (
            (1.0 / (dist_metro + 0.3)) * 2.0 + (commuter_flow * 1.4)
        )

        # 4. Logistics / Industrial Freight Corridor Multiplier
        # Heavy vehicles % + close proximity to National Highway
        highway_accessibility = 1.0 / (dist_nh + 0.2)
        interactions["logistics_freight_affinity"] = is_wh * (
            (heavy_pct * 0.25) * highway_accessibility
        )

        # 5. Commercial Density Leverage (FSI × Commercial/Office Flag)
        interactions["commercial_fsi_leverage"] = (is_retail + is_office) * fsi

        # 6. One-hot encoded property types
        interactions["is_residential"] = is_res
        interactions["is_commercial_retail"] = is_retail
        interactions["is_commercial_office"] = is_office
        interactions["is_warehouse_industrial"] = is_wh

        return interactions
