"""
Cluster 1: Connectivity & Infrastructure Distance Features.
Computes straight-line and network approximations to critical transport
and civic infrastructure for Indian urban/semi-urban contexts.
"""
from typing import Dict, Any
import numpy as np


class ConnectivityFeatureExtractor:
    """Extracts proximity features for highway, metro, rail, airport, and civic hubs."""

    def extract(self, lat: float, lon: float, overrides: Dict[str, Any] = None) -> Dict[str, float]:
        """
        Extract connectivity metrics for given coordinates.
        In production, this queries OpenStreetMap / spatial GIS indexes.
        Fallback/mock values simulate realistic Mumbai/Powai (IIT Bombay) metro topography.
        """
        overrides = overrides or {}

        # Default spatial estimates for Indian tier-1/tier-2 urban nodes
        features = {
            "dist_nh_km": float(overrides.get("dist_nh_km", 2.4)),            # Dist to nearest NH (e.g. JVLR / Eastern Express)
            "dist_sh_km": float(overrides.get("dist_sh_km", 0.8)),            # Dist to State Highway / Major Arterial
            "dist_metro_station_km": float(overrides.get("dist_metro_station_km", 1.1)), # Dist to nearest Metro station
            "dist_railway_stn_km": float(overrides.get("dist_railway_stn_km", 3.2)),     # Dist to suburban rail (Kanjurmarg / Vikhroli)
            "civic_proximity_score": float(overrides.get("civic_proximity_score", 8.2)), # Composite index (0-10) of hospitals/schools
            "dist_airport_hub_km": float(overrides.get("dist_airport_hub_km", 9.5)),     # Distance to civil airport (BOM)
        }

        # Derived connectivity index: closer to mass transit = higher index
        features["mass_transit_accessibility"] = 1.0 / (
            0.5 * features["dist_metro_station_km"] + 0.5 * features["dist_railway_stn_km"] + 0.2
        )

        return features
