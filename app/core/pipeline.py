"""Async pipeline orchestrator for ground fire enhancement.

Receives satellite validation results and enhances them with:
- Historical fire data (NASA FIRMS)
- Industrial false positive detection (OSM Overpass)
- Reverse geocoding (Nominatim)

Does NOT repeat any satellite work — only adds network-dependent analysis.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.api.schemas import (
    EnhanceResponse,
    GroundEnhancedResult,
    HeatSourceCandidateSchema,
    HeatSourceClassificationSchema,
    SatelliteResultInput,
    Verdict,
)
from app.core.confidence import compute_ground_confidence, determine_verdict
from app.services.false_positive import detect_industrial_heat
from app.services.geocoding import reverse_geocode
from app.services.heat_source_classifier import classify_heat_sources
from app.services.historical import get_historical_fires
from app.utils.reason_generator import generate_ground_reasons, generate_ground_summary

logger = logging.getLogger(__name__)


async def enhance_single_point(sat_result: SatelliteResultInput) -> GroundEnhancedResult:
    """Enhance a single satellite validation result with ground analysis.

    Execution:
    1. Extract coordinates (prefer corrected if available)
    2. Run historical + industrial + geocoding in parallel
    3. Compute ground confidence on top of satellite confidence
    4. Generate ground reasons and summary
    """
    start_time = time.monotonic()

    if (
        sat_result.coordinate_correction is not None
        and sat_result.coordinate_correction.correction_applied
    ):
        lat = sat_result.coordinate_correction.corrected_lat
        lon = sat_result.coordinate_correction.corrected_lon
    else:
        lat = sat_result.input_point.latitude
        lon = sat_result.input_point.longitude

    # --- Parallel phase: all ground-only services ---
    firms_result, industrial_result, geocoding_result = await asyncio.gather(
        get_historical_fires(lat, lon),
        detect_industrial_heat(lat, lon),
        reverse_geocode(lat, lon),
        return_exceptions=True,
    )

    if isinstance(firms_result, BaseException):
        logger.warning("Historical fire service failed: %s", firms_result)
        firms_result = None
    if isinstance(industrial_result, BaseException):
        logger.warning("Industrial FP detection failed: %s", industrial_result)
        industrial_result = None
    if isinstance(geocoding_result, BaseException):
        logger.warning("Geocoding service failed: %s", geocoding_result)
        geocoding_result = None

    # --- Fusion: compute ground confidence ---
    ground_confidence, confidence_breakdown = compute_ground_confidence(
        satellite_confidence=sat_result.final_confidence,
        firms=firms_result,
        industrial=industrial_result,
    )

    ground_verdict = determine_verdict(ground_confidence)

    # --- Reason and summary generation ---
    ground_reasons = generate_ground_reasons(
        satellite_result=sat_result,
        firms=firms_result,
        industrial=industrial_result,
    )

    ground_summary = generate_ground_summary(
        ground_verdict=ground_verdict,
        ground_confidence=ground_confidence,
        satellite_result=sat_result,
        firms=firms_result,
        industrial=industrial_result,
    )

    # --- Heat source classification and area estimation ---
    classification_result = classify_heat_sources(
        sat_result=sat_result,
        firms=firms_result,
        industrial=industrial_result,
    )
    heat_source_classification = HeatSourceClassificationSchema(
        ranked_sources=[
            HeatSourceCandidateSchema(
                type=c.type.value,
                label_zh=c.label_zh,
                probability=c.probability,
                raw_score=c.raw_score,
            )
            for c in classification_result.ranked_sources
        ],
        top_type=classification_result.top_type.value,
        top_label_zh=classification_result.top_label_zh,
        top_probability=classification_result.top_probability,
        estimated_area_km2=classification_result.estimated_area_km2,
        area_basis=classification_result.area_basis,
    )

    elapsed_ms = (time.monotonic() - start_time) * 1000

    return GroundEnhancedResult(
        satellite_result=sat_result,
        ground_verdict=ground_verdict,
        ground_confidence=ground_confidence,
        ground_reasons=ground_reasons,
        ground_summary=ground_summary,
        firms=firms_result,
        industrial=industrial_result,
        ground_confidence_breakdown=confidence_breakdown,
        geocoding_address=geocoding_result,
        heat_source_classification=heat_source_classification,
        processing_time_ms=round(elapsed_ms, 1),
    )


async def enhance_batch(results: list[SatelliteResultInput]) -> EnhanceResponse:
    """Enhance a batch of satellite results.

    Processes all points concurrently using asyncio.gather.
    """
    start_time = time.monotonic()

    tasks = [enhance_single_point(sat_result) for sat_result in results]
    enhanced = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results: list[GroundEnhancedResult] = []
    for i, result in enumerate(enhanced):
        if isinstance(result, BaseException):
            logger.error("Point %d enhancement failed: %s", i, result)
            sat = results[i]
            valid_results.append(
                GroundEnhancedResult(
                    satellite_result=sat,
                    ground_verdict=sat.verdict,
                    ground_confidence=sat.final_confidence,
                    ground_reasons=list(sat.reasons) + ["[地面增强] 增强过程发生错误，保留星上判定"],
                    ground_summary=f"地面增强失败，保留星上判定结果（置信度{sat.final_confidence:.1f}）。",
                    firms=None,
                    industrial=None,
                    ground_confidence_breakdown=None,
                    geocoding_address=None,
                    processing_time_ms=0.0,
                )
            )
        else:
            valid_results.append(result)

    elapsed_ms = (time.monotonic() - start_time) * 1000

    true_fire = false_positive = uncertain = 0
    for r in valid_results:
        if r.ground_verdict == Verdict.TRUE_FIRE:
            true_fire += 1
        elif r.ground_verdict == Verdict.FALSE_POSITIVE:
            false_positive += 1
        else:
            uncertain += 1

    return EnhanceResponse(
        results=valid_results,
        total_points=len(valid_results),
        true_fire_count=true_fire,
        false_positive_count=false_positive,
        uncertain_count=uncertain,
        total_processing_time_ms=round(elapsed_ms, 1),
    )
