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
    headers = {"User-Agent": settings.http_user_agent}

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await client.get(settings.nominatim_url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("display_name")
    except Exception as exc:
        logger.warning(
            "Nominatim reverse geocode failed near lat=%.2f lon=%.2f: %s",
            lat, lon, exc,
            exc_info=True,
        )
        return None
