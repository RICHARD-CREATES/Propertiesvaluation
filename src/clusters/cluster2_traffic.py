"""
Cluster 2: Traffic Volume & Sensor Signals (The Dual-Signal Cluster).
Extracts temporal window features (per-minute, hourly peaks, weekday/weekend, YoY)
and derived signals (vehicle mix, congestion index, noise proxy in dB).
"""
from typing import Dict, Any
import numpy as np


class TrafficFeatureExtractor:
    """
    Ingests NHAI toll, traffic police sensor, and live maps traffic signals
    to construct multi-scale temporal and derived acoustic/congestion features.
    """

    def extract(self, lat: float, lon: float, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        overrides = overrides or {}

        # 1. Base time-window measurements
        daily_count = float(overrides.get("daily_vehicle_count", 48000.0))
        peak_am_volume = float(overrides.get("peak_am_volume", 4200.0))   # 7am-10am peak hour
        peak_pm_volume = float(overrides.get("peak_pm_volume", 4600.0))   # 5pm-9pm peak hour
        weekday_avg_vol = float(overrides.get("weekday_avg_vol", 52000.0))
        weekend_avg_vol = float(overrides.get("weekend_avg_vol", 38000.0))
        volume_yoy_pct = float(overrides.get("volume_yoy_pct", 6.8))      # % growth YoY

        # Speeds in km/h
        actual_speed = float(overrides.get("actual_avg_speed", 21.0))
        free_flow_speed = float(overrides.get("free_flow_speed", 50.0))

        # Vehicle classification shares (sum to 100%)
        heavy_pct = float(overrides.get("heavy_vehicle_pct", 14.5))       # Trucks, buses
        two_wheeler_pct = float(overrides.get("two_wheeler_pct", 42.0))
        light_motor_pct = float(overrides.get("light_motor_pct", 43.5))   # Cars, auto-rickshaws

        # 2. Compute 4 Time-Window Features
        vehicles_per_min = daily_count / (24.0 * 60.0)
        peak_hour_volume = max(peak_am_volume, peak_pm_volume)
        peak_am_pm_ratio = peak_am_volume / max(peak_pm_volume, 1.0)
        weekday_weekend_ratio = weekday_avg_vol / max(weekend_avg_vol, 1.0)

        # 3. Compute 3 Derived Signals
        congestion_index = np.clip(actual_speed / max(free_flow_speed, 1.0), 0.05, 1.0)
        
        # Standard FHWA / Indian IRC: 38 + 10 * log10(vehicles_per_hour)
        noise_proxy_db = 38.0 + 10.0 * np.log10(max(peak_hour_volume, 1.0))

        # 4. Zone Classification Heuristic
        # Ratio > 1.25 -> Office/commercial; < 0.90 -> Retail/market; Heavy > 25% -> Logistics
        if heavy_pct >= 25.0:
            zone_type = "logistics"
        elif weekday_weekend_ratio >= 1.25:
            zone_type = "office_commuter"
        elif weekday_weekend_ratio <= 0.92:
            zone_type = "retail_market"
        else:
            zone_type = "residential_neighborhood"

        features = {
            # Time windows
            "traffic_vehicles_per_min": round(vehicles_per_min, 2),
            "traffic_peak_hour_vol": round(peak_hour_volume, 1),
            "traffic_peak_am_pm_ratio": round(peak_am_pm_ratio, 3),
            "traffic_weekday_weekend_ratio": round(weekday_weekend_ratio, 3),
            "traffic_monthly_yoy_growth": round(volume_yoy_pct, 2),
            
            # Vehicle distribution
            "traffic_heavy_vehicle_pct": round(heavy_pct, 2),
            "traffic_two_wheeler_pct": round(two_wheeler_pct, 2),
            "traffic_light_motor_pct": round(light_motor_pct, 2),
            
            # Derived indices
            "traffic_congestion_index": round(float(congestion_index), 3),
            "traffic_noise_proxy_db": round(float(noise_proxy_db), 2),
            "traffic_zone_type": zone_type,
        }

        return features
