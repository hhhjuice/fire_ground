"""NASA FIRMS historical fire point query service."""
import asyncio
import csv
import logging
import math
from io import StringIO

import httpx

from app.api.schemas import HistoricalFireResult
from app.config import get_settings
from app.utils.geo import bbox_from_point, haversine

logger = logging.getLogger(__name__)

FIRMS_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]
FIRMS_MAX_DAYS = 5
FIRMS_SOURCE_TIMEOUT = 6.0


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
        reader = csv.DictReader(StringIO(text))
        return [r for r in reader if r]
    except Exception as e:
        logger.warning("FIRMS query failed (source=%s days=%d): %s", source, days, e)
        return []


async def query_firms(
    lat: float,
    lon: float,
    radius_km: float = 5.0,
    days_back: int = 30,
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


def _compute_score(
    fires: list[dict],
    lat: float,
    lon: float,
    radius_km: float,
) -> tuple[float, float, int]:
    if not fires:
        return -0.3, 0.0, 0

    distances: list[float] = []
    for fire in fires:
        try:
            f_lat = float(fire.get("latitude", 0))
            f_lon = float(fire.get("longitude", 0))
            dist = haversine(lat, lon, f_lat, f_lon)
            distances.append(dist)
        except (ValueError, TypeError):
            continue

    if not distances:
        return -0.3, 0.0, 0

    radius_m = radius_km * 1000.0
    nearby_distances = [d for d in distances if d <= radius_m]
    if not nearby_distances:
        return -0.3, 0.0, 0

    nearest = min(nearby_distances)
    count = len(nearby_distances)

    dist_factor = max(0.0, 1.0 - (nearest / radius_m))
    count_factor = min(1.0, math.log1p(count) / math.log1p(20))

    score = 0.7 * dist_factor + 0.3 * count_factor
    score = max(-1.0, min(1.0, score))

    return score, nearest, count


async def get_historical_fires(
    lat: float,
    lon: float,
    radius_km: float = 5.0,
    days_back: int = 30,
) -> HistoricalFireResult:
    try:
        fires = await query_firms(lat, lon, radius_km=radius_km, days_back=days_back)
        score, nearest_m, count = _compute_score(fires, lat, lon, radius_km)

        if count > 0:
            detail = (
                f"过去{days_back}天内半径{radius_km}km范围发现{count}个历史火点，"
                f"最近距离{nearest_m:.0f}m"
            )
        else:
            detail = f"过去{days_back}天内半径{radius_km}km范围未发现历史火点"

        return HistoricalFireResult(
            nearby_fire_count=count,
            nearest_distance_m=nearest_m if count > 0 else None,
            days_searched=days_back,
            score=score,
            detail=detail,
        )
    except Exception as e:
        logger.warning("Historical fire service failed: %s", e)
        return HistoricalFireResult(
            nearby_fire_count=0,
            nearest_distance_m=None,
            days_searched=days_back,
            score=0.0,
            detail="历史火点查询失败，返回默认结果",
        )
