"""Ground confidence enhancement engine.

Formula:
    logit(P_ground) = logit(P_satellite) + β_hist × hist_score - industrial_penalty

P_satellite is the satellite's final_confidence — NOT recalculated.
Only adds historical and industrial on top.
"""
import logging
import math
from typing import Optional

from app.api.schemas import (
    GroundConfidenceBreakdown,
    HistoricalFireResult,
    IndustrialFalsePositiveResult,
    Verdict,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def _logit(p: float) -> float:
    """Compute logit (log-odds) of probability p. Clamps to avoid infinity."""
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    """Compute sigmoid function. Clamps input to avoid overflow."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def compute_ground_confidence(
    satellite_confidence: float,
    historical: Optional[HistoricalFireResult] = None,
    industrial_fp: Optional[IndustrialFalsePositiveResult] = None,
) -> tuple[float, GroundConfidenceBreakdown]:
    """Compute ground-enhanced confidence.

    Args:
        satellite_confidence: The satellite system's final confidence (P₀ for ground).
        historical: Historical fire result from FIRMS (provides score in [-1, 1]).
        industrial_fp: Industrial false positive result from OSM.

    Returns:
        Tuple of (ground_confidence, breakdown).
    """
    settings = get_settings()

    logit_score = _logit(satellite_confidence)

    # Historical contribution
    historical_contribution = 0.0
    if historical is not None:
        historical_contribution = settings.beta_hist * historical.score
    logit_score += historical_contribution

    # Industrial penalty
    industrial_penalty = 0.0
    if industrial_fp is not None:
        industrial_penalty = industrial_fp.flag.penalty
    logit_score -= industrial_penalty

    ground_confidence = _sigmoid(logit_score)
    ground_confidence = round(ground_confidence, 4)

    breakdown = GroundConfidenceBreakdown(
        satellite_confidence=satellite_confidence,
        historical_contribution=round(historical_contribution, 4),
        industrial_penalty=round(industrial_penalty, 4),
        final_confidence=ground_confidence,
    )

    return ground_confidence, breakdown


def determine_verdict(confidence: float) -> Verdict:
    """Determine fire point verdict based on ground confidence.

    Uses the same thresholds as satellite for consistency.
    """
    # Ground uses fixed thresholds matching satellite defaults
    if confidence >= 0.75:
        return Verdict.TRUE_FIRE
    elif confidence < 0.35:
        return Verdict.FALSE_POSITIVE
    else:
        return Verdict.UNCERTAIN
