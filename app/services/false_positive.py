"""False positive detection — industrial detector only (ground-only, needs OSM)."""
import logging

from app.api.schemas import FalsePositiveFlag, IndustrialFalsePositiveResult
from app.config import get_settings
from app.data.osm import query_industrial_pois

logger = logging.getLogger(__name__)


async def detect_industrial_heat(lat: float, lon: float) -> IndustrialFalsePositiveResult:
    """Detect industrial heat sources near the fire point via OSM Overpass."""
    settings = get_settings()
    pois = await query_industrial_pois(lat, lon, radius_m=1000.0)
    triggered = len(pois) > 0

    if triggered:
        names = [poi["name"] for poi in pois[:3]]
        detail = f"周边发现{len(pois)}个工业设施: {', '.join(names)}"
    else:
        detail = "周边未发现工业设施"

    flag = FalsePositiveFlag(
        detector="industrial_heat",
        triggered=triggered,
        penalty=settings.fp_penalty_industrial if triggered else 0.0,
        detail=detail,
    )

    return IndustrialFalsePositiveResult(flag=flag)
