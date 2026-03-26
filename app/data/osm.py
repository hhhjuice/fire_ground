"""OSM Overpass API client for querying industrial POIs."""
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# OSM tags that indicate a gas flare (true combustion source — not a false positive)
_GAS_FLARE_TYPES = frozenset({"flare", "petroleum_well", "gas_well"})


async def query_industrial_pois(lat: float, lon: float, radius_m: float = 5000.0) -> list[dict]:
    """Query Overpass API for industrial facilities near the given coordinates.

    Returns a list of dicts, each with keys:
        name, type, osm_id, lat, lon, is_gas_flare
    Coordinates allow the caller to compute exact distances.
    """
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
      node["man_made"="flare"](around:{radius_m},{lat},{lon});
      way["man_made"="flare"](around:{radius_m},{lat},{lon});
      node["man_made"="petroleum_well"](around:{radius_m},{lat},{lon});
      node["man_made"="gas_well"](around:{radius_m},{lat},{lon});
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
                facility_type = (
                    tags.get("man_made")
                    or tags.get("landuse")
                    or tags.get("power")
                    or tags.get("industrial", "industrial")
                )
                is_gas_flare = facility_type in _GAS_FLARE_TYPES

                # Extract coordinates: nodes have lat/lon directly; ways have center
                if elem.get("type") == "node":
                    poi_lat = elem.get("lat")
                    poi_lon = elem.get("lon")
                else:
                    center = elem.get("center", {})
                    poi_lat = center.get("lat")
                    poi_lon = center.get("lon")

                if poi_lat is None or poi_lon is None:
                    continue

                results.append(
                    {
                        "name": tags.get("name", "unnamed"),
                        "type": facility_type,
                        "osm_id": elem.get("id"),
                        "lat": poi_lat,
                        "lon": poi_lon,
                        "is_gas_flare": is_gas_flare,
                    }
                )
            return results
    except Exception as e:
        logger.warning("Overpass query failed for (%.4f, %.4f): %s", lat, lon, e)
        return []
