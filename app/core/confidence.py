"""Ground confidence enhancement engine.

Formula:
    logit(P_final) = logit(Pₛ/100) + ln(LR_firms) + Δ_industrial

Pₛ is the satellite's final_confidence (0-100) — NOT recalculated.
LR_firms is looked up from config by FirmsMatchLevel enum.
Δ_industrial is looked up from config by IndustrialProximity enum.
Gas flares skip the industrial delta (is_gas_flare=True).
"""
import logging
import math
from typing import Optional

from app.api.schemas import (
    FirmsMatchLevel,
    FirmsResult,
    GroundConfidenceBreakdown,
    IndustrialProximity,
    IndustrialResult,
    Verdict,
)
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _logit(p: float) -> float:
    """Compute logit (log-odds) of probability p. Clamps to avoid infinity."""
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    """Compute sigmoid function. Clamps input to avoid overflow."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def _firms_lr(match_level: FirmsMatchLevel, settings: Settings) -> float:
    """Return likelihood ratio for the given FIRMS match level."""
    return {
        FirmsMatchLevel.EXACT_MATCH: settings.firms_lr_exact_match,
        FirmsMatchLevel.NEARBY: settings.firms_lr_nearby,
        FirmsMatchLevel.REGIONAL: settings.firms_lr_regional,
        FirmsMatchLevel.NO_HISTORY: settings.firms_lr_no_history,
    }[match_level]


def _industrial_delta(proximity: IndustrialProximity, settings: Settings) -> float:
    """Return logit-space delta for the given industrial proximity level."""
    return {
        IndustrialProximity.WITHIN_500M: settings.industrial_delta_within_500m,
        IndustrialProximity.WITHIN_2KM: settings.industrial_delta_within_2km,
        IndustrialProximity.WITHIN_5KM: settings.industrial_delta_within_5km,
        IndustrialProximity.NONE: settings.industrial_delta_none,
    }[proximity]


def compute_ground_confidence(
    satellite_confidence: float,
    firms: Optional[FirmsResult] = None,
    industrial: Optional[IndustrialResult] = None,
) -> tuple[float, GroundConfidenceBreakdown]:
    """Compute ground-enhanced confidence.

    Args:
        satellite_confidence: The satellite system's final confidence (0-100).
        firms: FIRMS historical fire match result.
        industrial: Industrial facility proximity result.

    Returns:
        Tuple of (ground_confidence 0-100, breakdown).
    """
    settings = get_settings()

    logit_score = _logit(satellite_confidence / 100.0)

    # FIRMS contribution: ln(LR_firms)
    firms_contribution = 0.0
    if firms is not None:
        lr = _firms_lr(firms.match_level, settings)
        firms_contribution = math.log(lr)
    logit_score += firms_contribution

    # Industrial contribution: Δ_industrial (skip for gas flares)
    industrial_contribution = 0.0
    if industrial is not None and not industrial.is_gas_flare:
        industrial_contribution = _industrial_delta(industrial.proximity, settings)
    logit_score += industrial_contribution

    ground_confidence = round(_sigmoid(logit_score) * 100.0, 2)

    breakdown = GroundConfidenceBreakdown(
        satellite_confidence=satellite_confidence,
        firms_contribution=round(firms_contribution, 4),
        industrial_contribution=round(industrial_contribution, 4),
        final_confidence=ground_confidence,
    )

    return ground_confidence, breakdown


def determine_verdict(confidence: float) -> Verdict:
    """Determine fire point verdict based on ground confidence (0-100 scale).

    Final thresholds (stricter than satellite-only 70/50):
        ≥ 75 → TRUE_FIRE
        < 50 → FALSE_POSITIVE
        [50, 75) → UNCERTAIN
    """
    if confidence >= 75.0:
        return Verdict.TRUE_FIRE
    elif confidence < 50.0:
        return Verdict.FALSE_POSITIVE
    else:
        return Verdict.UNCERTAIN
