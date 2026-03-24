"""OSM Overpass API client for querying industrial POIs."""
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def query_industrial_pois(lat: float, lon: float, radius_m: float = 1000.0) -> list[dict]:
    """Query Overpass API for industrial facilities near the given coordinates."""
    settings = get_settings()

    query = f"""
    [out:json][timeout:10];
    (
      node["power"="plant"](around:{radius_m},{lat},{lon});
      way["power"="plant"](around:{radius_m},{lat},{lon});
      node["landuse"="industrial"](around:{radius_m},{lat},{lon});
      way["landuse"="industrial"](around:{radius_m},{lat},{lon});
      node["man_made"="works"](around:{radius_m},{lat},{lon});
      way["man_made"="works"](around:{radius_m},{lat},{lon});
      node["industrial"](around:{radius_m},{lat},{lon});
      way["industrial"](around:{radius_m},{lat},{lon});
    );
    out center body;
    """

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await client.post(settings.overpass_url, data={"data": query})
            resp.raise_for_status()
            data = resp.json()

            results = []
            for elem in data.get("elements", []):
                tags = elem.get("tags", {})
                results.append(
                    {
                        "name": tags.get("name", "unnamed"),
                        "type": (
                            tags.get("landuse")
                            or tags.get("power")
                            or tags.get("man_made")
                            or tags.get("industrial", "industrial")
                        ),
                        "osm_id": elem.get("id"),
                    }
                )
            return results
    except Exception as e:
        logger.warning("Overpass query failed for (%.4f, %.4f): %s", lat, lon, e)
        return []
