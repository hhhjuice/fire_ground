"""Nominatim reverse geocoding service."""
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Reverse geocode coordinates to Chinese address string via Nominatim."""
    settings = get_settings()
    params = {
        "format": "json",
        "lat": lat,
        "lon": lon,
        "accept-language": "zh",
        "zoom": 14,
    }
    headers = {"User-Agent": "FireGroundEnhanceSystem/1.0"}

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await client.get(settings.nominatim_url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("display_name")
    except Exception as exc:
        logger.warning(
            "Nominatim reverse geocode failed for (%.4f, %.4f): %s",
            lat, lon, exc,
        )
        return None
