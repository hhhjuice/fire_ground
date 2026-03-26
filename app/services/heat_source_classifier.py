"""Heat source type classification for ground enhancement system.

Combines satellite landcover/false-positive/environmental data with ground
enhancement results (historical fires, industrial facilities) to score each
heat source category and estimate the spatial extent of the anomaly.

No network I/O — pure computation on already-gathered data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.api.schemas import (
    FirmsMatchLevel,
    FirmsResult,
    IndustrialProximity,
    IndustrialResult,
    SatelliteResultInput,
)


class HeatSourceType(str, Enum):
    """Anomalous heat source type categories."""

    VEGETATION_FIRE = "vegetation_fire"
    AGRICULTURAL_BURNING = "agricultural_burning"
    INDUSTRIAL_HEAT = "industrial_heat"
    URBAN_HEAT_ISLAND = "urban_heat_island"
    SUN_GLINT = "sun_glint"
    WATER_REFLECTION = "water_reflection"
    COASTAL_REFLECTION = "coastal_reflection"
    WETLAND_FIRE = "wetland_fire"


_LABEL_ZH: dict[HeatSourceType, str] = {
    HeatSourceType.VEGETATION_FIRE: "植被火灾",
    HeatSourceType.AGRICULTURAL_BURNING: "农业焚烧",
    HeatSourceType.INDUSTRIAL_HEAT: "工业热源",
    HeatSourceType.URBAN_HEAT_ISLAND: "城市热岛",
    HeatSourceType.SUN_GLINT: "太阳耀斑",
    HeatSourceType.WATER_REFLECTION: "水体反射",
    HeatSourceType.COASTAL_REFLECTION: "海岸折射",
    HeatSourceType.WETLAND_FIRE: "湿地火灾",
}

# Categories that represent actual combustion events (vs. artifacts / point heat)
_FIRE_TYPES: frozenset[HeatSourceType] = frozenset({
    HeatSourceType.VEGETATION_FIRE,
    HeatSourceType.AGRICULTURAL_BURNING,
    HeatSourceType.WETLAND_FIRE,
})

# Map FirmsMatchLevel to a proxy score and fire cluster count for scoring/area estimation
_FIRMS_SCORE: dict[FirmsMatchLevel, float] = {
    FirmsMatchLevel.EXACT_MATCH: 1.0,
    FirmsMatchLevel.NEARBY_SAME_SEASON: 0.7,
    FirmsMatchLevel.REGIONAL: 0.3,
    FirmsMatchLevel.NO_SEASON_RECORD: -0.2,
    FirmsMatchLevel.NO_HISTORY: -0.3,
    FirmsMatchLevel.CONFIRMED_NONE: -0.5,
}

_FIRMS_COUNT: dict[FirmsMatchLevel, int] = {
    FirmsMatchLevel.EXACT_MATCH: 10,
    FirmsMatchLevel.NEARBY_SAME_SEASON: 5,
    FirmsMatchLevel.REGIONAL: 2,
    FirmsMatchLevel.NO_SEASON_RECORD: 0,
    FirmsMatchLevel.NO_HISTORY: 0,
    FirmsMatchLevel.CONFIRMED_NONE: 0,
}


@dataclass
class HeatSourceCandidate:
    """Single heat source category with its probability."""

    type: HeatSourceType
    label_zh: str
    probability: float
    raw_score: float


@dataclass
class HeatSourceClassificationResult:
    """Complete classification result including area estimate."""

    ranked_sources: list[HeatSourceCandidate]  # sorted by probability, descending
    top_type: HeatSourceType
    top_label_zh: str
    top_probability: float
    estimated_area_km2: float
    area_basis: str


def classify_heat_sources(
    sat_result: SatelliteResultInput,
    firms: Optional[FirmsResult],
    industrial: Optional[IndustrialResult],
) -> HeatSourceClassificationResult:
    """Classify the anomalous heat source type and estimate its area.

    Each category receives a raw additive score based on landcover, false
    positive flags, environmental conditions, and ground enhancement data.
    Scores are converted to probabilities via softmax (numerically stable).
    """
    # --- Safe extraction of satellite fields ---
    landcover_code: int = sat_result.landcover.class_code if sat_result.landcover else -1

    # Build a detector-name → triggered lookup from satellite false-positive flags
    fp_triggered: dict[str, bool] = {}
    if sat_result.false_positive:
        for flag in sat_result.false_positive.flags:
            fp_triggered[flag.detector] = flag.triggered

    water_body_triggered = fp_triggered.get("water_body", False)
    urban_heat_triggered = fp_triggered.get("urban_heat", False)
    sun_glint_triggered = fp_triggered.get("sun_glint", False)
    coastal_triggered = fp_triggered.get("coastal_reflection", False)

    # Environmental defaults (safe if satellite didn't include the block)
    is_daytime: bool = True
    solar_zenith: float = 45.0
    fire_season: float = 1.0
    if sat_result.environmental:
        is_daytime = sat_result.environmental.is_daytime
        solar_zenith = sat_result.environmental.solar_zenith_angle
        fire_season = sat_result.environmental.fire_season_factor

    # Ground service results mapped to proxy values
    hist_score: float = _FIRMS_SCORE.get(firms.match_level, 0.0) if firms else 0.0
    hist_count: int = _FIRMS_COUNT.get(firms.match_level, 0) if firms else 0
    industrial_triggered: bool = (
        industrial.proximity != IndustrialProximity.NONE if industrial else False
    )

    # --- Score each category (additive rule model) ---
    scores: dict[HeatSourceType, float] = {t: 0.0 for t in HeatSourceType}

    # vegetation_fire ─────────────────────────────────────────────────────────
    s = 0.0
    if landcover_code in {10, 20, 30}:
        s += 2.5
    if fire_season >= 1.3:
        s += 0.8
    elif fire_season >= 1.0:
        s += 0.3
    if hist_score > 0.3:
        s += 0.7
    if is_daytime:
        s += 0.3
    if industrial_triggered:
        s -= 3.0
    if sun_glint_triggered:
        s -= 2.0
    if water_body_triggered:
        s -= 2.0
    if urban_heat_triggered:
        s -= 1.0
    if landcover_code in {50, 80}:
        s -= 1.5
    scores[HeatSourceType.VEGETATION_FIRE] = s

    # agricultural_burning ────────────────────────────────────────────────────
    s = 0.0
    if landcover_code == 40:
        s += 3.0
    else:
        s -= 1.0
    if fire_season >= 1.0:
        s += 0.5
    if hist_score > 0:
        s += 0.3
    if industrial_triggered:
        s -= 1.5
    scores[HeatSourceType.AGRICULTURAL_BURNING] = s

    # industrial_heat ─────────────────────────────────────────────────────────
    s = 0.0
    if industrial_triggered:
        s += 3.5
    if urban_heat_triggered:
        s += 1.0
    if landcover_code == 50:
        s += 0.5
    if fire_season < 0.7:
        s += 0.3
    if landcover_code in {10, 20, 30}:
        s -= 1.0
    scores[HeatSourceType.INDUSTRIAL_HEAT] = s

    # urban_heat_island ───────────────────────────────────────────────────────
    s = 0.0
    if urban_heat_triggered:
        s += 3.5
    if landcover_code == 50:
        s += 0.8
    if industrial_triggered:
        s += 0.3
    scores[HeatSourceType.URBAN_HEAT_ISLAND] = s

    # sun_glint ───────────────────────────────────────────────────────────────
    s = 0.0
    if sun_glint_triggered:
        s += 4.0
    if is_daytime:
        s += 0.3
    else:
        s -= 5.0
    if solar_zenith < 30:
        s += 0.5
    if hist_score < 0:
        s += 0.3
    if hist_score > 0.5:
        s -= 1.0
    scores[HeatSourceType.SUN_GLINT] = s

    # water_reflection ────────────────────────────────────────────────────────
    s = 0.0
    if water_body_triggered:
        s += 4.0
    if landcover_code == 80:
        s += 1.0
    if hist_score < 0:
        s += 0.3
    if hist_score > 0.5:
        s -= 1.0
    scores[HeatSourceType.WATER_REFLECTION] = s

    # coastal_reflection ──────────────────────────────────────────────────────
    s = 0.0
    if coastal_triggered:
        s += 4.0
    if landcover_code in {90, 95}:
        s += 0.8
    if hist_score < 0:
        s += 0.3
    if hist_score > 0.5:
        s -= 1.0
    scores[HeatSourceType.COASTAL_REFLECTION] = s

    # wetland_fire ────────────────────────────────────────────────────────────
    s = 0.0
    if landcover_code in {90, 95}:
        s += 2.5
    if not coastal_triggered:
        s += 0.5
    if fire_season >= 1.0:
        s += 0.5
    if hist_score > 0.3:
        s += 0.5
    scores[HeatSourceType.WETLAND_FIRE] = s

    # --- Numerically stable softmax normalization ---
    score_list = [scores[t] for t in HeatSourceType]
    clipped = [max(v, -20.0) for v in score_list]
    max_s = max(clipped)
    exp_vals = [math.exp(v - max_s) for v in clipped]
    total = sum(exp_vals)

    candidates: list[HeatSourceCandidate] = []
    for htype, exp_val, raw in zip(HeatSourceType, exp_vals, score_list):
        candidates.append(HeatSourceCandidate(
            type=htype,
            label_zh=_LABEL_ZH[htype],
            probability=round(exp_val / total, 4),
            raw_score=round(raw, 4),
        ))

    candidates.sort(key=lambda c: c.probability, reverse=True)
    top = candidates[0]

    # --- Area estimation ---
    area_km2, area_basis = _estimate_area(
        top_type=top.type,
        hist_count=hist_count,
    )

    return HeatSourceClassificationResult(
        ranked_sources=candidates,
        top_type=top.type,
        top_label_zh=top.label_zh,
        top_probability=top.probability,
        estimated_area_km2=area_km2,
        area_basis=area_basis,
    )


def _estimate_area(
    top_type: HeatSourceType,
    hist_count: int,
    pixel_km2: float = 0.141,
    sensor_desc: str = "VIIRS (375m)",
) -> tuple[float, str]:
    """Estimate the spatial area of the heat anomaly (km²).

    Fire-type sources are scaled by historical fire cluster size.
    Point sources and atmospheric artifacts use a single pixel.
    Default pixel size is VIIRS (375m) as the most common modern sensor.
    """
    if top_type in _FIRE_TYPES:
        hist_factor = min(1.0 + hist_count * 0.1, 5.0)
        area = pixel_km2 * hist_factor
        area = min(area, 500.0)
        area_basis = (
            f"基于{sensor_desc}单像元面积，结合{hist_count}个历史火点集群规模估算"
        )
    else:
        area = pixel_km2
        area_basis = f"基于{sensor_desc}单像元面积（点热源）"

    return round(area, 6), area_basis
