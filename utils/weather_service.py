"""
Weather Service for ByaHero
Fetches and caches current weather for Digos City stops using Open-Meteo API.
Includes graceful fallback for SSL/network issues.
"""

import json
import os
import urllib.request
import urllib.parse
import time
from pathlib import Path

# Cache TTL: 10 minutes between API calls per location.
_CACHE_TTL_SECONDS = 600
_DB_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "data"
_CACHE_FILE = _DB_DIR / "weather_cache.json"

# Mock weather data for testing/fallback when API unavailable.
_MOCK_WEATHER = {
    "current": {
        "temperature_2m": 28.5,
        "relative_humidity_2m": 78,
        "apparent_temperature": 32.0,
        "weather_code": 2,
        "precipitation": 0.0,
        "rain": 0.0,
        "wind_speed_10m": 8.5,
        "wind_direction_10m": 210,
    }
}


def _load_cache():
    """Load the local weather cache (empty dict on miss)."""
    try:
        if _CACHE_FILE.exists():
            with _CACHE_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


def _save_cache(cache):
    """Persist the weather cache to disk."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE_FILE.open("w", encoding="utf-8") as fh:
            json.dump(cache, fh)
    except Exception:
        pass


def _cache_key(lat, lng):
    """Return a stable filename-safe cache key for a coordinate pair."""
    return f"{lat:.4f}_{lng:.4f}"


def get_weather(lat, lng, force_refresh=False):
    """
    Fetch current weather for a location from Open-Meteo.
    Returns a dict shaped like ``{"current": {...}}`` on success, or None on failure.
    Results are cached locally for 10 minutes to keep the app snappy.
    Falls back to mock data for local development / SSL issues.
    """
    if lat is None or lng is None:
        return None

    key = _cache_key(lat, lng)
    cache = _load_cache()

    if not force_refresh and key in cache:
        entry = cache[key]
        if time.time() - entry.get("ts", 0) < _CACHE_TTL_SECONDS:
            return entry.get("data")

    try:
        params = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lng,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,precipitation,rain,wind_speed_10m,wind_direction_10m",
            "timezone": "Asia/Manila",
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cache[key] = {"ts": time.time(), "data": data}
            _save_cache(cache)
            return data
    except Exception as e:
        print(f"[weather] fetch failed for ({lat}, {lng}): {e}")
        # Fall back to a cached hit even if stale when the network is down.
        if key in cache:
            return cache[key].get("data")
        # Return mock data for local development.
        return _MOCK_WEATHER


def get_weather_for_location(location):
    """
    Return a compact weather dict for a single location row (id, name, lat, lng).
    Returns None when the location has no coordinates or fetch fails.
    """
    lat = location.get("latitude")
    lng = location.get("longitude")
    if lat is None or lng is None:
        return None
    data = get_weather(float(lat), float(lng))
    if not data or "current" not in data:
        return None
    c = data["current"]
    return {
        "location_id": location.get("location_id"),
        "name": location.get("name"),
        "temperature_c": c.get("temperature_2m"),
        "apparent_temp_c": c.get("apparent_temperature"),
        "humidity_pct": c.get("relative_humidity_2m"),
        "wind_speed_kmh": c.get("wind_speed_10m"),
        "wind_direction_deg": c.get("wind_direction_10m"),
        "precipitation_mm": c.get("precipitation"),
        "rain_mm": c.get("rain"),
        "weather_code": c.get("weather_code"),
        "weather_text": _weather_text(c.get("weather_code")),
    }


def get_weather_for_route(route_locations):
    """Return a list of weather dicts, one per location that has coordinates."""
    results = []
    for loc in (route_locations or []):
        info = get_weather_for_location(loc)
        if info:
            results.append(info)
    return results


WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _weather_text(code):
    """Map WMO weather codes to human-readable labels."""
    if code is None:
        return "Unknown"
    return WEATHER_CODES.get(int(code), f"Weather code {code}")


def get_weather_factor(code, precipitation_mm=0.0, temperature_c=25.0):
    """
    Return a multiplier applied to the baseline travel time, plus a short reason
    that can be surfaced to the user.
    """
    if code is None:
        return 1.0, None
    factor = 1.0
    reasons = []
    code = int(code)
    if code in (61, 80):
        factor = max(factor, 1.15)
        reasons.append("light rain")
    elif code in (63, 81):
        factor = max(factor, 1.25)
        reasons.append("moderate rain")
    elif code in (65, 82, 95, 96, 99):
        factor = max(factor, 1.40)
        reasons.append("heavy rain/thunderstorm")
    elif code in (71, 73, 75, 77, 85, 86):
        factor = max(factor, 1.20)
        reasons.append("snow")
    if precipitation_mm and precipitation_mm > 10:
        factor = max(factor, 1.40)
        reasons.append("heavy precipitation")
    if temperature_c and temperature_c < 15:
        factor = max(factor, 1.10)
        reasons.append("cold conditions")
    return factor, " and ".join(reasons) if reasons else None
