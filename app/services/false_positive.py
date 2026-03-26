"""False positive detection — industrial detector only (ground-only, needs OSM)."""
import logging
from typing import Optional

from app.api.schemas import IndustrialProximity, IndustrialResult
from app.data.osm import query_industrial_pois
from app.utils.geo import haversine

logger = logging.getLogger(__name__)

# Proximity thresholds (metres)
_WITHIN_500M = 500.0
_WITHIN_2KM = 2000.0
_WITHIN_5KM = 5000.0


def _proximity_from_distance(dist_m: float) -> IndustrialProximity:
    if dist_m < _WITHIN_500M:
        return IndustrialProximity.WITHIN_500M
    elif dist_m < _WITHIN_2KM:
        return IndustrialProximity.WITHIN_2KM
    else:
        return IndustrialProximity.WITHIN_5KM


async def detect_industrial_heat(lat: float, lon: float) -> IndustrialResult:
    """Detect industrial heat sources near the fire point via OSM Overpass.

    Queries within 5 km and maps the nearest facility to an IndustrialProximity level.
    Gas flares (is_gas_flare=True) are reported but exempt from confidence penalty.
    """
    pois = await query_industrial_pois(lat, lon, radius_m=_WITHIN_5KM)

    if not pois:
        return IndustrialResult(
            proximity=IndustrialProximity.NONE,
            nearest_facility_m=None,
            facility_type=None,
            is_gas_flare=False,
            detail="5km内未发现工业设施",
        )

    # Find nearest POI with valid coordinates
    nearest_poi: Optional[dict] = None
    nearest_dist_m: float = float("inf")

    for poi in pois:
        poi_lat = poi.get("lat")
        poi_lon = poi.get("lon")
        if poi_lat is None or poi_lon is None:
            continue
        dist_m = haversine(lat, lon, poi_lat, poi_lon)
        if dist_m < nearest_dist_m:
            nearest_dist_m = dist_m
            nearest_poi = poi

    if nearest_poi is None or nearest_dist_m >= _WITHIN_5KM:
        return IndustrialResult(
            proximity=IndustrialProximity.NONE,
            nearest_facility_m=None,
            facility_type=None,
            is_gas_flare=False,
            detail="5km内未发现有效工业设施",
        )

    proximity = _proximity_from_distance(nearest_dist_m)
    is_gas_flare = nearest_poi.get("is_gas_flare", False)
    facility_type = nearest_poi.get("type")
    names = [p["name"] for p in pois[:3]]

    if is_gas_flare:
        detail = (
            f"发现油气火炬设施（{nearest_poi.get('name', 'unnamed')}），"
            f"距离{nearest_dist_m:.0f}m，属于真实燃烧源，不施加假阳性惩罚"
        )
    else:
        detail = (
            f"周边发现{len(pois)}个工业设施: {', '.join(names)}，"
            f"最近设施距离{nearest_dist_m:.0f}m（{proximity.value}）"
        )

    return IndustrialResult(
        proximity=proximity,
        nearest_facility_m=round(nearest_dist_m, 1),
        facility_type=facility_type,
        is_gas_flare=is_gas_flare,
        detail=detail,
    )
