"""Geographic calculation utilities — pure math, no I/O."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two lat/lon points using Haversine formula."""
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bbox_from_point(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """Return (min_lat, min_lon, max_lat, max_lon) bounding box around a point."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def solar_zenith_angle(lat: float, lon: float, dt: Optional[datetime] = None) -> float:
    """Calculate approximate solar zenith angle in degrees."""
    if dt is None:
        dt = datetime.now(timezone.utc)

    doy = dt.timetuple().tm_yday
    B = math.radians((360.0 / 365.0) * (doy - 81))
    decl = math.radians(23.45) * math.sin(B)

    hour_utc = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    solar_noon_offset = lon / 15.0
    hour_angle = math.radians(15.0 * (hour_utc + solar_noon_offset - 12.0))

    lat_rad = math.radians(lat)
    cos_zenith = (math.sin(lat_rad) * math.sin(decl) +
                  math.cos(lat_rad) * math.cos(decl) * math.cos(hour_angle))
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    return math.degrees(math.acos(cos_zenith))


def is_daytime(lat: float, lon: float, dt: Optional[datetime] = None) -> bool:
    """Return True if sun is above horizon at given location and time."""
    return solar_zenith_angle(lat, lon, dt) < 90.0


def is_southern_hemisphere(lat: float) -> bool:
    """Return True if latitude is in southern hemisphere."""
    return lat < 0.0


def get_fire_season_factor(lat: float, month: int) -> float:
    """Return seasonal fire likelihood multiplier (0.5-1.5)."""
    if is_southern_hemisphere(lat):
        peak_months = {12, 1, 2, 3}
        shoulder_months = {4, 11}
    else:
        peak_months = {6, 7, 8, 9, 10}
        shoulder_months = {5, 11}

    if month in peak_months:
        return 1.3
    elif month in shoulder_months:
        return 1.0
    else:
        return 0.7


def meters_to_degrees_lat(meters: float) -> float:
    """Convert meters to approximate degrees latitude."""
    return meters / 111_320.0


def meters_to_degrees_lon(meters: float, lat: float) -> float:
    """Convert meters to approximate degrees longitude at given latitude."""
    return meters / (111_320.0 * math.cos(math.radians(lat)))
