"""NASA FIRMS historical fire point query service."""
import asyncio
import csv
import logging
from datetime import datetime
from io import StringIO
from typing import Optional

import httpx

from app.api.schemas import FirmsMatchLevel, FirmsResult
from app.config import get_settings
from app.utils.geo import bbox_from_point, haversine

logger = logging.getLogger(__name__)

FIRMS_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]
FIRMS_MAX_DAYS = 5
FIRMS_SOURCE_TIMEOUT = 6.0

# Distance thresholds (km) for FirmsMatchLevel classification
_EXACT_KM = 1.0
_NEARBY_KM = 5.0
_REGIONAL_KM = 10.0


async def _query_source(
    client: httpx.AsyncClient,
    key: str,
    base_url: str,
    source: str,
    bbox_str: str,
    days: int,
) -> list[dict]:
    url = f"{base_url}/{key}/{source}/{bbox_str}/{days}"
    try:
        resp = await asyncio.wait_for(client.get(url), timeout=FIRMS_SOURCE_TIMEOUT)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text or text.startswith("<!") or text.lower().startswith("invalid"):
            return []
        return list(csv.DictReader(StringIO(text)))
    except Exception as e:
        logger.warning("FIRMS query failed (source=%s days=%d): %s", source, days, e)
        return []


async def query_firms(
    lat: float,
    lon: float,
    radius_km: float = 10.0,
    days_back: int = 5,
) -> list[dict]:
    settings = get_settings()
    radius_m = radius_km * 1000.0
    min_lat, min_lon, max_lat, max_lon = bbox_from_point(lat, lon, radius_m)
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    query_days = min(days_back, FIRMS_MAX_DAYS)

    all_fires: list[dict] = []
    seen: set[tuple] = set()

    async with httpx.AsyncClient(timeout=httpx.Timeout(FIRMS_SOURCE_TIMEOUT + 1)) as client:
        results = await asyncio.gather(
            *[
                _query_source(
                    client, settings.firms_map_key, settings.firms_base_url,
                    src, bbox_str, query_days,
                )
                for src in FIRMS_SOURCES
            ],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, list):
                for rec in result:
                    key_tuple = (
                        rec.get("latitude"), rec.get("longitude"),
                        rec.get("acq_date"), rec.get("acq_time"),
                    )
                    if key_tuple not in seen:
                        seen.add(key_tuple)
                        all_fires.append(rec)

    return all_fires


def _parse_fire_date(fire: dict) -> Optional[datetime]:
    """Parse acq_date from a FIRMS record."""
    acq_date = fire.get("acq_date", "")
    if not acq_date:
        return None
    try:
        return datetime.strptime(acq_date, "%Y-%m-%d")
    except ValueError:
        return None


def _classify_match_level(
    fires: list[dict],
    lat: float,
    lon: float,
) -> FirmsResult:
    """Map FIRMS NRT results to a FirmsMatchLevel enum."""
    if not fires:
        return FirmsResult(
            match_level=FirmsMatchLevel.NO_HISTORY,
            nearest_fire_km=None,
            nearest_fire_date=None,
            detail="搜索范围内无历史火点记录",
        )

    distances: list[tuple[float, Optional[datetime]]] = []
    for fire in fires:
        try:
            f_lat = float(fire.get("latitude", 0))
            f_lon = float(fire.get("longitude", 0))
            dist_km = haversine(lat, lon, f_lat, f_lon) / 1000.0
            fire_date = _parse_fire_date(fire)
            distances.append((dist_km, fire_date))
        except (ValueError, TypeError):
            continue

    if not distances:
        return FirmsResult(
            match_level=FirmsMatchLevel.NO_HISTORY,
            nearest_fire_km=None,
            nearest_fire_date=None,
            detail="搜索范围内无有效历史火点记录",
        )

    nearest_km, nearest_date = min(distances, key=lambda x: x[0])

    if nearest_km < _EXACT_KM:
        match_level = FirmsMatchLevel.EXACT_MATCH
        detail = f"同位置1km内发现历史火点，距离{nearest_km:.2f}km"
    elif nearest_km < _NEARBY_KM:
        match_level = FirmsMatchLevel.NEARBY_SAME_SEASON
        detail = f"5km内发现历史火点，距离{nearest_km:.2f}km"
    elif nearest_km < _REGIONAL_KM:
        match_level = FirmsMatchLevel.REGIONAL
        detail = f"10km内发现历史火点，距离{nearest_km:.2f}km"
    else:
        match_level = FirmsMatchLevel.NO_HISTORY
        detail = f"最近历史火点距离{nearest_km:.2f}km，超出有效范围"

    return FirmsResult(
        match_level=match_level,
        nearest_fire_km=round(nearest_km, 2),
        nearest_fire_date=nearest_date,
        detail=detail,
    )


async def get_historical_fires(
    lat: float,
    lon: float,
    radius_km: float = 10.0,
    days_back: int = 5,
) -> FirmsResult:
    try:
        fires = await query_firms(lat, lon, radius_km=radius_km, days_back=days_back)
        return _classify_match_level(fires, lat, lon)
    except Exception as e:
        logger.warning("Historical fire service failed: %s", e)
        return FirmsResult(
            match_level=FirmsMatchLevel.NO_HISTORY,
            nearest_fire_km=None,
            nearest_fire_date=None,
            detail="历史火点查询失败，返回默认结果",
        )
