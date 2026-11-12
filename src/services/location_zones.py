"""
Backend Geographic Zone Engine — Green (Medical) & Yellow (Transit / Education / Work)
======================================================================================
Computes zone membership, overlay markings (Green & Yellow circles/pins), and land cost
uplift figures strictly in the backend for ANY location globally.

Zone Definitions:
- GREEN ZONE: Hospitals & Medical Facilities (`hospital_medical`)
- YELLOW ZONE: Railway Stations (`railway_station`), Metro Stations (`metro_station`),
  Public Transport / Bus Hubs (`public_transport`), Schools & Colleges (`school_college`),
  and Commercial / IT Working Hubs (`working_hub`).

Pricing Rule:
1. First determines whether the coordinate lies inside any Green or Yellow zone using
   real Pan-India & Global geo-anchors (plus optional bounded OpenStreetMap Overpass
   discovery in live runtime, or backend distance hints in rural/remote terrain).
2. Computes land cost uplift figures (`green_zone_land_uplift_pct`,
   `yellow_zone_land_uplift_pct`, `total_zone_land_uplift_pct`) ONLY when `in_any_zone`
   is True. Outside priority zones -> 0.0% uplift.
"""
from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from src.services.location_intelligence import haversine_km


def _g(name: str, lat: float, lon: float, core_km: float = 1.5, zone_km: float = 5.0) -> Dict[str, Any]:
    return {"name": name, "category": "hospital_medical", "zone_color": "green", "lat": lat, "lon": lon, "core_km": core_km, "zone_km": zone_km}


def _y(name: str, category: str, lat: float, lon: float, core_km: float = 1.5, zone_km: float = 5.0) -> Dict[str, Any]:
    return {"name": name, "category": category, "zone_color": "yellow", "lat": lat, "lon": lon, "core_km": core_km, "zone_km": zone_km}


# Verified Pan-India & Global Green (Medical) + Yellow (Transit / Edu / Working Hub) Anchors
GLOBAL_ZONE_ANCHORS: List[Dict[str, Any]] = [
    # --- ODISHA (Bhubaneswar, Cuttack, Puri, Rourkela) ---
    _g("AIIMS Bhubaneswar", 20.2314, 85.7751),
    _g("Apollo Hospital (Sainik School Rd)", 20.3059, 85.8318),
    _g("KIMS Medical College & Hospital", 20.3536, 85.8145),
    _g("CARE Hospital (Chandrasekharpur)", 20.3204, 85.8147),
    _g("Capital Hospital (Unit 6)", 20.2587, 85.8281),
    _g("AMRI Hospital (Khandagiri)", 20.2585, 85.7731),
    _g("SUM Ultimate Medicare (Ghatikia)", 20.2815, 85.7736),
    _g("SCB Medical College & Hospital (Cuttack)", 20.4694, 85.8936),
    _g("Ispat General Hospital (Rourkela)", 22.2518, 84.8819),
    _y("Bhubaneswar Railway Station (Master Canteen)", "railway_station", 20.2669, 85.8435),
    _y("Baramunda ISBT Bus Terminal", "public_transport", 20.2759, 85.7995),
    _y("Jayadev Vihar Metro / Transit Hub", "metro_station", 20.2994, 85.8245),
    _y("Patia Square Transit Corridor", "public_transport", 20.3545, 85.8260),
    _y("Vani Vihar Rail / Transit Node", "metro_station", 20.2917, 85.8437),
    _y("KIIT University & Campus", "school_college", 20.3555, 85.8189),
    _y("XIMB (Xavier Institute)", "school_college", 20.3081, 85.8165),
    _y("SAI International School", "school_college", 20.3638, 85.8176),
    _y("Utkal University (Vani Vihar)", "school_college", 20.2952, 85.8407),
    _y("DAV Public School (Chandrasekharpur)", "school_college", 20.3210, 85.8205),
    _y("OUTR / CET Technical University", "school_college", 20.2758, 85.7767),
    _y("Infocity IT Working Hub (Patia)", "working_hub", 20.3490, 85.8080, core_km=2.0, zone_km=12.0),
    _y("Saheed Nagar Corporate District", "working_hub", 20.2925, 85.8439, core_km=1.5, zone_km=8.0),
    _y("Infovalley / Chandaka Tech Zone", "working_hub", 20.2202, 85.7366, core_km=2.0, zone_km=12.0),
    _y("Cuttack Railway Station", "railway_station", 20.4646, 85.8994),
    _y("Ravenshaw University (Cuttack)", "school_college", 20.4638, 85.8950),
    _y("Puri Railway Terminus", "railway_station", 19.8087, 85.8390),
    _y("NIT Rourkela Campus", "school_college", 22.2530, 84.9012),

    # --- MUMBAI & MMR ---
    _g("Dr. L H Hiranandani Hospital (Powai)", 19.1204, 72.9114),
    _g("Fortis Hospital (Mulund)", 19.1636, 72.9422),
    _g("Kokilaben Dhirubhai Ambani Hospital (Andheri W)", 19.1313, 72.8250),
    _g("Lilavati Hospital (Bandra West)", 19.0510, 72.8292),
    _g("Bombay Hospital (Marine Lines)", 18.9409, 72.8286),
    _g("KEM Hospital (Parel)", 19.0028, 72.8421),
    _g("Apollo Hospital (Navi Mumbai)", 19.0209, 73.0294),
    _y("IIT Bombay Main Campus (Powai)", "school_college", 19.1334, 72.9133),
    _y("Kanjurmarg / Powai JVLR Metro & Rail", "metro_station", 19.1288, 72.9284),
    _y("Ghatkopar Metro & Rail Interchange", "metro_station", 19.0866, 72.9081),
    _y("Andheri Rail & Aqua/Blue Metro Hub", "railway_station", 19.1197, 72.8464),
    _y("CSMT Central Railway Terminus", "railway_station", 18.9398, 72.8355),
    _y("Churchgate & Marine Lines Transit", "public_transport", 18.9352, 72.8272),
    _y("Vashi Harbour Line & Bus Terminus", "public_transport", 19.0630, 72.9990),
    _y("Mumbai University (Kalina Campus)", "school_college", 19.0731, 72.8542),
    _y("Bandra Kurla Complex (BKC) Financial Hub", "working_hub", 19.0653, 72.8682, core_km=2.0, zone_km=12.0),
    _y("Powai Supreme Business Park / SEZ", "working_hub", 19.1180, 72.9090, core_km=2.0, zone_km=10.0),
    _y("SEEPZ & MIDC Working District (Andheri E)", "working_hub", 19.1243, 72.8742, core_km=2.0, zone_km=10.0),
    _y("Nariman Point & Fort Commercial CBD", "working_hub", 18.9256, 72.8242, core_km=2.0, zone_km=10.0),

    # --- PUNE ---
    _g("Ruby Hall Clinic (Pune Central)", 18.5335, 73.8772),
    _g("Sahyadri Super Speciality Hospital (Deccan)", 18.5141, 73.8354),
    _g("Jehangir Hospital (Bund Garden)", 18.5297, 73.8763),
    _g("Aditya Birla Memorial Hospital (Wakad/Thergaon)", 18.6251, 73.7753),
    _y("Pune Junction Railway Station", "railway_station", 18.5289, 73.8744),
    _y("Shivajinagar Metro & Bus Hub", "metro_station", 18.5314, 73.8446),
    _y("Hinjawadi Phase II Transit & Bus Terminal", "public_transport", 18.5912, 73.7195),
    _y("Savitribai Phule Pune University", "school_college", 18.5529, 73.8266),
    _y("COEP Technological University", "school_college", 18.5293, 73.8565),
    _y("Rajiv Gandhi Infotech Park (Hinjawadi)", "working_hub", 18.5913, 73.7389, core_km=2.0, zone_km=12.0),
    _y("Magarpatta & EON IT Park Corridor", "working_hub", 18.5158, 73.9272, core_km=2.0, zone_km=12.0),

    # --- DELHI NCR ---
    _g("AIIMS New Delhi", 28.5672, 77.2100),
    _g("Max Super Speciality Hospital (Saket)", 28.5275, 77.2121),
    _g("Medanta The Medicity (Gurgaon)", 28.4395, 77.0405),
    _g("Fortis Memorial Research Institute (Gurgaon)", 28.4567, 77.0725),
    _g("Apollo Hospital (Sarita Vihar / Indraprastha)", 28.5416, 77.2836),
    _g("Fortis Hospital Noida (Sector 62)", 28.6186, 77.3728),
    _y("New Delhi Railway Station", "railway_station", 28.6429, 77.2191),
    _y("Rajiv Chowk Metro Interchange", "metro_station", 28.6328, 77.2197),
    _y("HUDA City Centre / Millennium Metro (Gurgaon)", "metro_station", 28.4593, 77.0724),
    _y("Noida Sector 18 / Botanical Garden Metro", "metro_station", 28.5644, 77.3342),
    _y("Kashmere Gate ISBT Bus Terminus", "public_transport", 28.6675, 77.2282),
    _y("IIT Delhi (Hauz Khas)", "school_college", 28.5450, 77.1926),
    _y("Delhi University (North Campus)", "school_college", 28.6880, 77.2090),
    _y("DLF Cyber City (Gurgaon)", "working_hub", 28.4950, 77.0895, core_km=2.0, zone_km=12.0),
    _y("Connaught Place Financial CBD", "working_hub", 28.6315, 77.2167, core_km=2.0, zone_km=10.0),
    _y("Noida Sector 62 & Expressway Tech Hub", "working_hub", 28.6279, 77.3649, core_km=2.0, zone_km=12.0),

    # --- BENGALURU ---
    _g("Manipal Hospital (Old Airport Rd)", 12.9585, 77.6489),
    _g("Manipal Hospital (Whitefield)", 12.9854, 77.7289),
    _g("St. John's Medical College Hospital (Koramangala)", 12.9293, 77.6203),
    _g("Apollo Hospitals (Bannerghatta Rd)", 12.8959, 77.5985),
    _g("Narayana Health City (Electronic City)", 12.8053, 77.6960),
    _y("KSR Bengaluru City Railway Station", "railway_station", 12.9781, 77.5697),
    _y("Nadaprabhu Kempegowda / Majestic Metro", "metro_station", 12.9756, 77.5728),
    _y("Whitefield (Kadugodi) Purple Line Metro", "metro_station", 12.9955, 77.7580),
    _y("Silk Board / Electronic City Transit Node", "public_transport", 12.9177, 77.6238),
    _y("Indian Institute of Science (IISc)", "school_college", 13.0219, 77.5671),
    _y("IIM Bangalore (Bannerghatta)", "school_college", 12.8956, 77.6022),
    _y("ITPL International Tech Park (Whitefield)", "working_hub", 12.9875, 77.7366, core_km=2.0, zone_km=12.0),
    _y("Manyata Tech Park (Nagavara)", "working_hub", 13.0458, 77.6206, core_km=2.0, zone_km=12.0),
    _y("Electronic City Phase I IT Hub", "working_hub", 12.8452, 77.6602, core_km=2.0, zone_km=12.0),

    # --- HYDERABAD ---
    _g("Apollo Health City (Jubilee Hills)", 17.4156, 78.4126),
    _g("AIG Hospitals (Gachibowli)", 17.4437, 78.3660),
    _g("Yashoda Hospitals (Somajiguda)", 17.4241, 78.4567),
    _g("KIMS Hospitals (Secunderabad)", 17.4366, 78.4852),
    _y("Secunderabad Junction Railway Station", "railway_station", 17.4344, 78.5016),
    _y("Ameerpet Metro Interchange", "metro_station", 17.4357, 78.4446),
    _y("HITEC City Blue Line Metro", "metro_station", 17.4488, 78.3832),
    _y("MGBS Central Bus Terminus", "public_transport", 17.3782, 78.4806),
    _y("IIIT Hyderabad & Univ of Hyderabad", "school_college", 17.4455, 78.3489),
    _y("HITEC City / Mindspace IT Corridor", "working_hub", 17.4435, 78.3772, core_km=2.0, zone_km=12.0),
    _y("Gachibowli Financial District", "working_hub", 17.4193, 78.3387, core_km=2.0, zone_km=12.0),

    # --- CHENNAI ---
    _g("Apollo Hospitals (Greams Road)", 13.0630, 80.2516),
    _g("MIOT International Hospital", 13.0211, 80.1865),
    _g("Fortis Malar Hospital (Adyar)", 13.0104, 80.2584),
    _y("Puratchi Thalaivar Dr. MGR Chennai Central", "railway_station", 13.0827, 80.2755),
    _y("Guindy Metro & Suburban Interchange", "metro_station", 13.0091, 80.2130),
    _y("CMBT Koyambedu Bus Terminus", "public_transport", 13.0695, 80.2054),
    _y("IIT Madras & Anna University", "school_college", 12.9915, 80.2337),
    _y("Tidel Park & OMR IT Corridor", "working_hub", 12.9896, 80.2487, core_km=2.0, zone_km=12.0),

    # --- KOLKATA ---
    _g("Apollo Multispeciality Hospital (Salt Lake)", 22.5746, 88.4017),
    _g("SSKM / IPGMER Hospital", 22.5396, 88.3426),
    _g("Medica Superspecialty (Mukundapur)", 22.4912, 88.4013),
    _y("Howrah Junction Railway Station", "railway_station", 22.5839, 88.3426),
    _y("Sealdah Railway Terminus", "railway_station", 22.5676, 88.3704),
    _y("Salt Lake Sector V Metro", "metro_station", 22.5799, 88.4310),
    _y("Esplanade Transit Hub", "public_transport", 22.5648, 88.3517),
    _y("Jadavpur University", "school_college", 22.4989, 88.3714),
    _y("Salt Lake Sector V & New Town IT Hub", "working_hub", 22.5735, 88.4331, core_km=2.0, zone_km=12.0),

    # --- AHMEDABAD, LUCKNOW, KOCHI, CHANDIGARH, JAIPUR, INDORE ---
    _g("Zydus Hospital (SG Highway Ahmedabad)", 23.0584, 72.5174),
    _g("Civil Hospital & MediCity (Ahmedabad)", 23.0525, 72.6029),
    _y("Ahmedabad Kalupur Railway Station", "railway_station", 23.0269, 72.6009),
    _y("IIM Ahmedabad Campus", "school_college", 23.0305, 72.5335),
    _y("GIFT City IFSC Financial Hub", "working_hub", 23.1636, 72.6836, core_km=2.0, zone_km=12.0),
    _g("Medanta Hospital Lucknow", 26.7867, 81.0033),
    _g("SGPGI & KGMU Medical (Lucknow)", 26.8686, 80.9163),
    _y("Charbagh Railway & Metro Station", "railway_station", 26.8317, 80.9222),
    _y("Gomti Nagar Corporate & IT District", "working_hub", 26.8467, 81.0010, core_km=2.0, zone_km=10.0),
    _g("Aster Medcity & Amrita Hospital (Kochi)", 10.0449, 76.2776),
    _y("Ernakulam South Junction & Kochi Metro", "metro_station", 9.9685, 76.2907),
    _y("Infopark Kochi (Kakkanad)", "working_hub", 10.0099, 76.3616, core_km=2.0, zone_km=12.0),
    _g("PGIMER Chandigarh", 30.7649, 76.7750),
    _y("Chandigarh Junction & ISBT Sector 17", "public_transport", 30.7398, 76.7827),
    _y("Panjab University & PEC", "school_college", 30.7605, 76.7654),
    _y("Rajiv Gandhi Chandigarh IT Park", "working_hub", 30.7284, 76.8439, core_km=2.0, zone_km=10.0),
    _g("SMS Hospital Jaipur", 26.9068, 75.8152),
    _y("Jaipur Junction & Sindhi Camp Metro", "railway_station", 26.9196, 75.7878),
    _g("Bombay Hospital Indore", 22.7582, 75.9016),
    _y("Vijay Nagar & Super Corridor IT Hub (Indore)", "working_hub", 22.7533, 75.8937, core_km=2.0, zone_km=10.0),

    # --- GLOBAL HUBS (London, New York, Austin, Paris) ---
    _g("St Thomas' Hospital (Westminster London)", 51.4989, -0.1180),
    _g("University College Hospital (Bloomsbury London)", 51.5246, -0.1361),
    _y("King's Cross St Pancras Rail & Tube Hub", "railway_station", 51.5308, -0.1238),
    _y("Liverpool Street Elizabeth Line / Tube", "metro_station", 51.5178, -0.0823),
    _y("LSE / UCL Bloomsbury Academic Quarter", "school_college", 51.5144, -0.1165),
    _y("City of London & Canary Wharf Financial CBD", "working_hub", 51.5138, -0.0984, core_km=2.0, zone_km=10.0),
    _g("Bellevue & NYU Langone Medical Center (NYC)", 40.7392, -73.9754),
    _y("Grand Central & Penn Rail Terminals (NYC)", "railway_station", 40.7527, -73.9772),
    _y("Fulton Center Subway Hub (Lower Manhattan)", "metro_station", 40.7104, -74.0086),
    _y("NYU Washington Square Campus", "school_college", 40.7295, -73.9965),
    _y("Lower Manhattan & Midtown CBD", "working_hub", 40.7075, -74.0113, core_km=2.0, zone_km=10.0),
    _g("Dell Seton Medical Center (Austin)", 30.2747, -97.7343),
    _y("Downtown Austin Rail & CapMetro Rapid", "public_transport", 30.2649, -97.7386),
    _y("University of Texas at Austin", "school_college", 30.2849, -97.7341),
    _y("Downtown Austin Tech Corridor", "working_hub", 30.2672, -97.7431, core_km=2.0, zone_km=10.0),
    _g("Hopital Cochin AP-HP (Paris)", 48.8387, 2.3401),
    _y("Gare du Nord & Chatelet-Les Halles RER", "railway_station", 48.8617, 2.3470),
    _y("Sorbonne University (Latin Quarter)", "school_college", 48.8486, 2.3435),
    _y("Paris Bourse / La Defense Business Core", "working_hub", 48.8698, 2.3412, core_km=2.0, zone_km=10.0),
]

# Legacy export names kept compatible for imports
GREEN_MEDICAL_FACILITIES: List[Dict[str, Any]] = [
    a for a in GLOBAL_ZONE_ANCHORS if a["zone_color"] == "green" and haversine_km(a["lat"], a["lon"], 20.2961, 85.8245) <= 35.0
]
YELLOW_INFRA_HUBS: List[Dict[str, Any]] = [
    a for a in GLOBAL_ZONE_ANCHORS if a["zone_color"] == "yellow" and haversine_km(a["lat"], a["lon"], 20.2961, 85.8245) <= 35.0
]

# Bounded in-memory cache for live Overpass zone lookups keyed by (round(lat, 2), round(lon, 2))
_OVERPASS_ZONE_CACHE: Dict[Tuple[float, float], Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = {}


def _offset_coord(lat: float, lon: float, dlat_deg: float, dlon_deg: float) -> Tuple[float, float]:
    return round(lat + dlat_deg, 6), round(lon + dlon_deg, 6)


def _zone_decay_uplift(distance_km: float, max_uplift: float, core_km: float, outer_km: float) -> float:
    """Computes land uplift factor strictly when property falls inside zone (`distance_km <= outer_km`)."""
    if distance_km > outer_km:
        return 0.0
    if distance_km <= core_km:
        return max_uplift
    t = (distance_km - core_km) / max(outer_km - core_km, 0.1)
    return max_uplift * (1.0 - 0.65 * t)


def _query_overpass_live(lat: float, lon: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Optional live OpenStreetMap Overpass query for arbitrary locations outside catalog anchors."""
    cache_key = (round(lat, 2), round(lon, 2))
    if cache_key in _OVERPASS_ZONE_CACHE:
        return _OVERPASS_ZONE_CACHE[cache_key]

    # Keep automated pytest runs offline/fast
    if os.getenv("PYTEST_CURRENT_TEST"):
        return ([], [])

    query = f"""
    [out:json][timeout:2];
    (
      node["amenity"~"hospital|clinic"](around:5500,{lat:.5f},{lon:.5f});
      node["railway"~"station|subway_entrance"](around:5500,{lat:.5f},{lon:.5f});
      node["amenity"~"bus_station|university|college|school"](around:5500,{lat:.5f},{lon:.5f});
      node["office"~"it|company"](around:6000,{lat:.5f},{lon:.5f});
    );
    out center 25;
    """
    try:
        req = urllib.request.Request(
            "https://overpass-api.de/api/interpreter",
            data=("data=" + urllib.parse.quote(query)).encode("utf-8"),
            headers={"User-Agent": "PropAIGeoZoneEngine/2.0"},
        )
        with urllib.request.urlopen(req, timeout=1.8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        greens: List[Dict[str, Any]] = []
        yellows: List[Dict[str, Any]] = []
        seen_names = set()
        for el in payload.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("operator")
            p_lat = el.get("lat")
            p_lon = el.get("lon")
            if not name or p_lat is None or p_lon is None or name in seen_names:
                continue
            seen_names.add(name)
            amenity = tags.get("amenity", "")
            railway = tags.get("railway", "")
            office = tags.get("office", "")
            if amenity in ("hospital", "clinic"):
                greens.append(_g(name, float(p_lat), float(p_lon)))
            elif railway == "station":
                yellows.append(_y(name, "railway_station", float(p_lat), float(p_lon)))
            elif railway == "subway_entrance":
                yellows.append(_y(name, "metro_station", float(p_lat), float(p_lon)))
            elif amenity == "bus_station":
                yellows.append(_y(name, "public_transport", float(p_lat), float(p_lon)))
            elif amenity in ("university", "college", "school"):
                yellows.append(_y(name, "school_college", float(p_lat), float(p_lon)))
            elif office:
                yellows.append(_y(name, "working_hub", float(p_lat), float(p_lon), core_km=2.0, zone_km=10.0))
        result = (greens[:8], yellows[:14])
        _OVERPASS_ZONE_CACHE[cache_key] = result
        return result
    except Exception:
        return ([], [])


class LocationZoneEngine:
    """Backend service computing Green/Yellow priority zones and land-value figures for every location."""

    @staticmethod
    def has_catalog_coverage(latitude: float, longitude: float, radius_km: float = 40.0) -> bool:
        """Returns True if any real geo-anchor exists within radius_km of coordinate."""
        lat = float(latitude)
        lon = float(longitude)
        return any(haversine_km(lat, lon, a["lat"], a["lon"]) <= radius_km for a in GLOBAL_ZONE_ANCHORS)

    @staticmethod
    def evaluate_zones_for_point(
        latitude: float,
        longitude: float,
        distance_hints: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates Green (Medical) & Yellow (Transit / Education / Working Hub) priority zones
        for ANY location globally strictly in the backend.
        """
        lat = float(latitude)
        lon = float(longitude)
        hints = distance_hints or {}

        # Gather all real catalog anchors within 45 km of this location
        nearby_catalog = [
            a for a in GLOBAL_ZONE_ANCHORS
            if haversine_km(lat, lon, a["lat"], a["lon"]) <= 45.0
        ]

        live_greens: List[Dict[str, Any]] = []
        live_yellows: List[Dict[str, Any]] = []
        if not hints and len(nearby_catalog) < 3:
            live_greens, live_yellows = _query_overpass_live(lat, lon)

        green_anchors = [a for a in nearby_catalog if a["zone_color"] == "green"] + live_greens
        yellow_anchors = [a for a in nearby_catalog if a["zone_color"] == "yellow"] + live_yellows

        green_candidates: List[Dict[str, Any]] = []
        yellow_candidates: List[Dict[str, Any]] = []

        if green_anchors or yellow_anchors:
            for item in green_anchors:
                d_km = haversine_km(lat, lon, item["lat"], item["lon"])
                green_candidates.append(
                    {
                        "name": item["name"],
                        "category": item["category"],
                        "zone_color": "green",
                        "hex_color": "#22c55e",
                        "latitude": item["lat"],
                        "longitude": item["lon"],
                        "distance_km": d_km,
                        "core_radius_m": int(item["core_km"] * 1000),
                        "zone_radius_m": int(item["zone_km"] * 1000),
                        "inside_zone": d_km <= item["zone_km"],
                    }
                )
            for item in yellow_anchors:
                d_km = haversine_km(lat, lon, item["lat"], item["lon"])
                yellow_candidates.append(
                    {
                        "name": item["name"],
                        "category": item["category"],
                        "zone_color": "yellow",
                        "hex_color": "#eab308",
                        "latitude": item["lat"],
                        "longitude": item["lon"],
                        "distance_km": d_km,
                        "core_radius_m": int(item["core_km"] * 1000),
                        "zone_radius_m": int(item["zone_km"] * 1000),
                        "inside_zone": d_km <= item["zone_km"],
                    }
                )

        # Ensure every location gets a full multi-modal zone structure (if missing green or yellow in remote towns,
        # backfill that specific missing layer from backend distance hints cleanly)
        if not green_candidates or not yellow_candidates:
            d_hosp = float(hints.get("distance_hospital_km", 8.0))
            d_rail = float(hints.get("distance_rail_km", 10.0))
            d_metro = float(hints.get("distance_metro_km", 12.0))
            d_bus = float(hints.get("distance_bus_stand_km", 7.0))
            d_school = float(hints.get("distance_school_km", 6.0))
            d_work = float(hints.get("distance_it_hub_km", hints.get("distance_cbd_km", 14.0)))
            deg_per_km = 1.0 / 111.0
            synth_defs = [
                ("green", "#22c55e", "Regional Hospital & Medical Care Zone", "hospital_medical", d_hosp, 0.7, 0.7, 1.5, 5.0),
                ("yellow", "#eab308", "Nearest Railway Station Zone", "railway_station", d_rail, -0.8, 0.6, 1.5, 5.0),
                ("yellow", "#eab308", "Metro / Rapid Transit Node", "metro_station", d_metro, 0.5, -0.8, 1.5, 5.0),
                ("yellow", "#eab308", "Public Bus & Transit Stand", "public_transport", d_bus, -0.6, -0.7, 1.5, 5.0),
                ("yellow", "#eab308", "Schools & Colleges Zone", "school_college", d_school, 0.9, 0.2, 1.5, 5.0),
                ("yellow", "#eab308", "Commercial & Working Hub", "working_hub", d_work, -0.4, 0.9, 2.0, 12.0),
            ]
            for color, hex_c, name, cat, d_target, ux, uy, core_km, z_km in synth_defs:
                if color == "green" and green_candidates:
                    continue
                if color == "yellow" and yellow_candidates:
                    continue
                norm = math.hypot(ux, uy) or 1.0
                p_lat, p_lon = _offset_coord(lat, lon, (ux / norm) * d_target * deg_per_km, (uy / norm) * d_target * deg_per_km)
                actual_d = round(d_target, 2)
                entry = {
                    "name": name,
                    "category": cat,
                    "zone_color": color,
                    "hex_color": hex_c,
                    "latitude": p_lat,
                    "longitude": p_lon,
                    "distance_km": actual_d,
                    "core_radius_m": int(core_km * 1000),
                    "zone_radius_m": int(z_km * 1000),
                    "inside_zone": actual_d <= z_km,
                }
                if color == "green":
                    green_candidates.append(entry)
                else:
                    yellow_candidates.append(entry)

        # Respect explicit distance overrides for sensitivity testing & out-of-zone simulations
        if "distance_hospital_km" in hints and green_candidates:
            d_override = float(hints["distance_hospital_km"])
            nearest_g = min(green_candidates, key=lambda x: x["distance_km"])
            nearest_g["distance_km"] = round(d_override, 2)
            nearest_g["inside_zone"] = d_override <= (nearest_g["zone_radius_m"] / 1000.0)
            if not nearest_g["inside_zone"]:
                for g in green_candidates:
                    g["inside_zone"] = False
                    g["distance_km"] = max(g["distance_km"], d_override)

        yellow_override_map = {
            "railway_station": "distance_rail_km",
            "metro_station": "distance_metro_km",
            "public_transport": "distance_bus_stand_km",
            "school_college": "distance_school_km",
            "working_hub": "distance_it_hub_km",
        }
        for cat_key, hint_key in yellow_override_map.items():
            if hint_key in hints:
                d_ov = float(hints[hint_key])
                matching = [y for y in yellow_candidates if y["category"] == cat_key]
                if matching:
                    nearest_y = min(matching, key=lambda x: x["distance_km"])
                    nearest_y["distance_km"] = round(d_ov, 2)
                    nearest_y["inside_zone"] = d_ov <= (nearest_y["zone_radius_m"] / 1000.0)
                    if not nearest_y["inside_zone"]:
                        for y in matching:
                            y["inside_zone"] = False
                            y["distance_km"] = max(y["distance_km"], d_ov)

        green_hits = [g for g in green_candidates if g["inside_zone"]]
        yellow_hits = [y for y in yellow_candidates if y["inside_zone"]]

        in_green = len(green_hits) > 0
        in_yellow = len(yellow_hits) > 0
        in_any = in_green or in_yellow

        green_uplift = 0.0
        if green_hits:
            best_g = min(green_hits, key=lambda x: x["distance_km"])
            base_g = _zone_decay_uplift(
                best_g["distance_km"],
                0.065,
                best_g["core_radius_m"] / 1000.0,
                best_g["zone_radius_m"] / 1000.0,
            )
            multi_hospital_bonus = min(0.015, max(0, len(green_hits) - 1) * 0.005)
            green_uplift = round(base_g + multi_hospital_bonus, 4)

        yellow_uplift = 0.0
        if yellow_hits:
            best_by_cat: Dict[str, Dict[str, Any]] = {}
            for y in yellow_hits:
                cat = y["category"]
                if cat not in best_by_cat or y["distance_km"] < best_by_cat[cat]["distance_km"]:
                    best_by_cat[cat] = y
            cat_weights = {
                "railway_station": 0.032,
                "metro_station": 0.035,
                "public_transport": 0.025,
                "school_college": 0.030,
                "working_hub": 0.035,
            }
            raw_y = sum(
                _zone_decay_uplift(
                    item["distance_km"],
                    cat_weights.get(cat, 0.025),
                    item["core_radius_m"] / 1000.0,
                    item["zone_radius_m"] / 1000.0,
                )
                for cat, item in best_by_cat.items()
            )
            yellow_uplift = round(min(0.115, raw_y), 4)

        total_zone_uplift = round(min(0.18, green_uplift + yellow_uplift), 4) if in_any else 0.0

        if in_green and in_yellow:
            zone_status = "GREEN_AND_YELLOW_PRIORITY_ZONES"
            zone_summary = "Property lies inside BOTH Green (Medical) and Yellow (Transit/Education/Working Hub) zones."
        elif in_green:
            zone_status = "GREEN_MEDICAL_ZONE"
            zone_summary = "Property lies inside Green Zone (Hospital / Medical Facilities)."
        elif in_yellow:
            zone_status = "YELLOW_TRANSIT_EDU_WORK_ZONE"
            zone_summary = "Property lies inside Yellow Zone (Rail/Metro/Public Transport/Schools/Colleges/Working Hubs)."
        else:
            zone_status = "OUTSIDE_PRIORITY_ZONES"
            zone_summary = "Property is outside Green & Yellow priority zones; no zone land-rate premium applied."

        nearest_green = min(green_candidates, key=lambda x: x["distance_km"]) if green_candidates else None
        nearest_yellow = min(yellow_candidates, key=lambda x: x["distance_km"]) if yellow_candidates else None

        return {
            "in_any_zone": in_any,
            "in_green_zone": in_green,
            "in_yellow_zone": in_yellow,
            "zone_classification": zone_status,
            "zone_summary": zone_summary,
            "green_zone_land_uplift_pct": round(green_uplift * 100.0, 2),
            "yellow_zone_land_uplift_pct": round(yellow_uplift * 100.0, 2),
            "total_zone_land_uplift_pct": round(total_zone_uplift * 100.0, 2),
            "land_rate_multiplier": round(1.0 + total_zone_uplift, 4),
            "active_green_facilities_count": len(green_hits),
            "active_yellow_hubs_count": len(yellow_hits),
            "nearest_green_facility": nearest_green,
            "nearest_yellow_hub": nearest_yellow,
            "green_zones": sorted(green_candidates, key=lambda x: x["distance_km"]),
            "yellow_zones": sorted(yellow_candidates, key=lambda x: x["distance_km"]),
            "zone_discovery_mode": "catalog_geo_anchors" if nearby_catalog else ("osm_overpass_live" if (live_greens or live_yellows) else "regional_distance_model"),
        }

    @staticmethod
    def to_public_payload(zone_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strips internal Yellow Zone geometry, flags, counts, and labels so Yellow Zone
        remains strictly backend-only for pricing & valuation while Green (Medical)
        zones remain cleanly inspectable.
        """
        if not zone_analysis:
            return {}
        in_green = bool(zone_analysis.get("in_green_zone"))
        in_any = bool(zone_analysis.get("in_any_zone"))
        if in_green:
            public_class = "GREEN_MEDICAL_ZONE"
            public_summary = "Property lies inside Green Zone (Hospital / Medical Facilities)."
        elif in_any:
            public_class = "URBAN_ACCESSIBILITY_CORRIDOR"
            public_summary = "Standard urban infrastructure corridor pricing applied."
        else:
            public_class = "OUTSIDE_PRIORITY_ZONES"
            public_summary = "Property is outside medical green zones; no zone premium applied."

        return {
            "in_any_zone": in_any,
            "in_green_zone": in_green,
            "zone_classification": public_class,
            "zone_summary": public_summary,
            "green_zone_land_uplift_pct": zone_analysis.get("green_zone_land_uplift_pct", 0.0),
            "total_zone_land_uplift_pct": zone_analysis.get("total_zone_land_uplift_pct", 0.0),
            "land_rate_multiplier": zone_analysis.get("land_rate_multiplier", 1.0),
            "active_green_facilities_count": zone_analysis.get("active_green_facilities_count", 0),
            "nearest_green_facility": zone_analysis.get("nearest_green_facility"),
            "green_zones": zone_analysis.get("green_zones", []),
            "zone_discovery_mode": zone_analysis.get("zone_discovery_mode", "catalog_geo_anchors"),
        }
