"""Geographic helpers for tourist proximity scoring."""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Tourist hotspot coordinates (lat, lng)
# ---------------------------------------------------------------------------
TOURIST_HOTSPOT_COORDS: dict[str, tuple[float, float]] = {
    # Tokyo
    "shibuya_crossing": (35.6595, 139.7004),
    "shinjuku_station": (35.6896, 139.7006),
    "asakusa_sensoji": (35.7148, 139.7967),
    "akihabara": (35.7023, 139.7745),
    "ginza": (35.6717, 139.7649),
    "harajuku_takeshita": (35.6702, 139.7026),
    "roppongi": (35.6633, 139.7317),
    "ueno_park": (35.7146, 139.7732),
    "ikebukuro": (35.7295, 139.7149),
    "tokyo_station": (35.6812, 139.7671),
    "meiji_jingu": (35.6764, 139.6993),
    "tsukiji_toyosu": (35.6454, 139.7842),
    # Kyoto
    "gion": (35.0036, 135.7781),
    "arashiyama": (35.0094, 135.6681),
    "kawaramachi": (35.0050, 135.7684),
    "fushimi_inari": (34.9671, 135.7727),
    "kinkakuji": (35.0394, 135.7292),
    # Osaka
    "dotonbori": (34.6686, 135.5010),
    "namba": (34.6658, 135.5010),
    "shinsaibashi": (34.6719, 135.5028),
    # Other major areas
    "kanazawa_castle": (36.5906, 136.6626),
    "hakone_yumoto": (35.2327, 139.1070),
    "kamakura": (35.3192, 139.5466),
    "nikko": (36.7199, 139.5980),
    "hiroshima_peace_park": (34.3853, 132.4553),
    "nara_deer_park": (34.6851, 135.8432),
    "fukuoka_canal_city": (33.5903, 130.4017),
    "sapporo_odori": (43.0607, 141.3490),
}

# Major city centre coordinates for broader city-level scoring
MAJOR_CITY_COORDS: dict[str, tuple[float, float]] = {
    "tokyo": (35.6812, 139.7671),
    "kyoto": (35.0116, 135.7681),
    "osaka": (34.6719, 135.5028),
    "fukuoka": (33.5903, 130.4017),
    "sapporo": (43.0607, 141.3490),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two points in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_hotspot_distance(
    lat: float,
    lng: float,
) -> tuple[float, str]:
    """Return (distance_km, hotspot_name) for the nearest tourist hotspot."""
    best_km = float("inf")
    best_name = ""
    for name, (hlat, hlng) in TOURIST_HOTSPOT_COORDS.items():
        d = haversine_km(lat, lng, hlat, hlng)
        if d < best_km:
            best_km = d
            best_name = name
    return best_km, best_name


def nearest_city_distance(
    lat: float,
    lng: float,
) -> tuple[float, str]:
    """Return (distance_km, city_name) for the nearest major city centre."""
    best_km = float("inf")
    best_name = ""
    for name, (clat, clng) in MAJOR_CITY_COORDS.items():
        d = haversine_km(lat, lng, clat, clng)
        if d < best_km:
            best_km = d
            best_name = name
    return best_km, best_name
