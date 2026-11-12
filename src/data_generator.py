"""
Data Generator for Real Estate Asset Valuation.
Generates realistic training datasets reflecting Mumbai / Powai (IIT Bombay)
urban economics across residential, retail, office, and industrial properties.
"""
from typing import List, Dict, Any
import numpy as np


def generate_synthetic_real_estate_dataset(n_samples: int = 1200, random_seed: int = 42) -> List[Dict[str, Any]]:
    np.random.seed(random_seed)
    property_types = ["residential", "commercial_retail", "commercial_office", "warehouse_industrial"]
    type_probs = [0.65, 0.15, 0.12, 0.08]

    records = []

    for i in range(n_samples):
        p_type = np.random.choice(property_types, p=type_probs)
        
        # Coordinates around Powai / Kanjurmarg / IIT Bombay vicinity (19.11 to 19.14 N, 72.89 to 72.93 E)
        lat = 19.1254 + np.random.normal(0, 0.015)
        lon = 72.9157 + np.random.normal(0, 0.015)

        # Distances (km)
        dist_nh = float(np.clip(np.random.exponential(2.2), 0.3, 10.0))
        dist_metro = float(np.clip(np.random.exponential(1.5), 0.2, 6.0))
        dist_rail = float(np.clip(np.random.normal(3.0, 1.0), 0.8, 8.0))
        dist_sez = float(np.clip(np.random.normal(3.5, 1.5), 0.5, 12.0))

        # Traffic parameters
        is_on_arterial = np.random.rand() > 0.45
        if is_on_arterial:
            daily_vehicles = np.random.uniform(35000, 85000)
            avg_speed = np.random.uniform(15, 28)
            heavy_pct = np.random.uniform(12, 32) if p_type == "warehouse_industrial" else np.random.uniform(8, 20)
        else:
            daily_vehicles = np.random.uniform(8000, 25000)
            avg_speed = np.random.uniform(25, 45)
            heavy_pct = np.random.uniform(3, 10)

        free_flow_speed = 50.0
        peak_am = daily_vehicles * np.random.uniform(0.08, 0.12)
        peak_pm = daily_vehicles * np.random.uniform(0.09, 0.13)
        
        if p_type in ["commercial_office"]:
            weekday_avg = daily_vehicles * 1.15
            weekend_avg = daily_vehicles * 0.75
        elif p_type == "commercial_retail":
            weekday_avg = daily_vehicles * 0.90
            weekend_avg = daily_vehicles * 1.25
        else:
            weekday_avg = daily_vehicles * 1.02
            weekend_avg = daily_vehicles * 0.96

        # Physical specs
        if p_type == "residential":
            bhk = float(np.random.choice([1.0, 2.0, 3.0, 4.0], p=[0.25, 0.45, 0.25, 0.05]))
            carpet_area = bhk * np.random.uniform(420, 580)
            total_floors = np.random.choice([14, 22, 28, 36])
            floor_num = int(np.random.randint(1, total_floors + 1))
            grade = np.random.choice(["Grade_A", "Grade_B", "Grade_C"], p=[0.4, 0.45, 0.15])
            base_psqft = 22000 if grade == "Grade_A" else (18000 if grade == "Grade_B" else 14500)
        elif p_type == "commercial_retail":
            bhk = 0.0
            carpet_area = np.random.uniform(350, 2800)
            total_floors = np.random.choice([4, 12, 20])
            floor_num = int(np.random.choice([0, 1, 2], p=[0.7, 0.2, 0.1])) # Ground / 1st floor
            grade = np.random.choice(["Grade_A", "Grade_B"], p=[0.6, 0.4])
            base_psqft = 45000 if floor_num == 0 else 32000
        elif p_type == "commercial_office":
            bhk = 0.0
            carpet_area = np.random.uniform(1500, 12000)
            total_floors = np.random.choice([12, 24, 32])
            floor_num = int(np.random.randint(2, total_floors))
            grade = np.random.choice(["Grade_A", "Grade_B"], p=[0.75, 0.25])
            base_psqft = 26000 if grade == "Grade_A" else 20000
        else: # warehouse_industrial
            bhk = 0.0
            carpet_area = np.random.uniform(4000, 25000)
            total_floors = 2
            floor_num = 1
            grade = np.random.choice(["Grade_B", "Grade_C"], p=[0.5, 0.5])
            base_psqft = 8500

        age_years = float(np.random.uniform(0.5, 18.0))
        clear_title = int(np.random.choice([1, 0], p=[0.94, 0.06]))
        fsi = float(np.random.choice([2.0, 2.5, 2.75, 3.5]))

        # Calculate Realistic Target Price with Traffic Dual Signal Physics
        congestion_ratio = avg_speed / free_flow_speed
        peak_hr = max(peak_am, peak_pm)
        noise_db = 38.0 + 10.0 * np.log10(max(peak_hr, 1.0))

        # Adjust price per sqft based on market dynamics
        price_psqft = base_psqft

        # Metro benefit (all types)
        price_psqft *= (1.0 + max(0.0, (3.0 - dist_metro) * 0.04))

        # DUAL SIGNAL TRAFFIC EFFECT:
        if p_type == "residential":
            # Noise & heavy traffic discount
            if noise_db > 70.0:
                price_psqft *= 0.94 # -6% noise discount
            elif noise_db < 60.0:
                price_psqft *= 1.03 # +3% quiet leafier pocket
            if congestion_ratio < 0.45:
                price_psqft *= 0.96 # -4% severe crawl discount
            # Floor view premium
            price_psqft *= (1.0 + (floor_num / total_floors) * 0.08)
        elif p_type == "commercial_retail":
            # Footfall premium
            if daily_vehicles > 45000:
                price_psqft *= 1.18 # +18% storefront footfall premium
            else:
                price_psqft *= 0.92
        elif p_type == "commercial_office":
            # Commuter corridor premium
            if (weekday_avg / weekend_avg) > 1.25:
                price_psqft *= 1.10 # +10% corporate corridor
        elif p_type == "warehouse_industrial":
            # Heavy vehicle & NH proximity premium
            if dist_nh < 1.5 and heavy_pct > 18.0:
                price_psqft *= 1.22 # +22% logistics super-corridor

        # Age depreciation: ~1.2% per year
        price_psqft *= max(0.65, (1.0 - 0.012 * age_years))

        # Title encumbrance penalty
        if not clear_title:
            price_psqft *= 0.78 # -22% litigation / encumbrance discount

        # Final target total price in INR
        noise_mult = np.random.normal(1.0, 0.025)
        total_price_inr = carpet_area * price_psqft * noise_mult

        records.append({
            "property_id": f"PROP_{i+1:05d}",
            "property_type": p_type,
            "latitude": lat,
            "longitude": lon,
            "carpet_area_sqft": round(carpet_area, 1),
            "bhk_count": bhk,
            "floor_number": floor_num,
            "total_floors": total_floors,
            "property_age_years": round(age_years, 1),
            "construction_grade": grade,
            "clear_title_flag": clear_title,
            "dist_nh_km": round(dist_nh, 2),
            "dist_metro_station_km": round(dist_metro, 2),
            "dist_railway_stn_km": round(dist_rail, 2),
            "dist_upcoming_sez_km": round(dist_sez, 2),
            "fsi_far_allowable": fsi,
            "daily_vehicle_count": round(daily_vehicles, 0),
            "actual_avg_speed": round(avg_speed, 1),
            "free_flow_speed": free_flow_speed,
            "heavy_vehicle_pct": round(heavy_pct, 1),
            "peak_am_volume": round(peak_am, 1),
            "peak_pm_volume": round(peak_pm, 1),
            "weekday_avg_vol": round(weekday_avg, 1),
            "weekend_avg_vol": round(weekend_avg, 1),
            "target_price_inr": round(total_price_inr, 0),
        })

    return records
