"""Tests for ground confidence engine."""
import pytest

from app.api.schemas import (
    HistoricalFireResult,
    Verdict,
)
from app.core.confidence import compute_ground_confidence, determine_verdict


def test_ground_confidence_no_enhancement_preserves_satellite() -> None:
    """With no historical or industrial data, ground confidence equals satellite."""
    conf, bd = compute_ground_confidence(satellite_confidence=0.65)
    assert conf == pytest.approx(0.65, abs=1e-4)
    assert bd.satellite_confidence == 0.65


def test_positive_historical_increases_confidence() -> None:
    """Positive historical score should increase ground confidence."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=0.5)
    hist = HistoricalFireResult(
        nearby_fire_count=3,
        nearest_distance_m=200.0,
        days_searched=30,
        score=0.8,
        detail="",
    )
    boosted_conf, bd = compute_ground_confidence(
        satellite_confidence=0.5,
        historical=hist,
    )
    assert boosted_conf > base_conf
    assert bd.historical_contribution > 0


def test_negative_historical_decreases_confidence() -> None:
    """Negative historical score (no fires) should decrease confidence."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=0.5)
    hist = HistoricalFireResult(
        nearby_fire_count=0,
        nearest_distance_m=None,
        days_searched=30,
        score=-0.3,
        detail="",
    )
    lowered_conf, _ = compute_ground_confidence(
        satellite_confidence=0.5,
        historical=hist,
    )
    assert lowered_conf < base_conf


def test_industrial_penalty_decreases_confidence(industrial_fp_result) -> None:
    """Industrial facilities should decrease confidence."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=0.65)
    penalized_conf, bd = compute_ground_confidence(
        satellite_confidence=0.65,
        industrial_fp=industrial_fp_result,
    )
    assert penalized_conf < base_conf
    assert bd.industrial_penalty > 0


def test_no_industrial_no_penalty(no_industrial_fp_result) -> None:
    """No industrial facilities means no penalty."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=0.65)
    same_conf, bd = compute_ground_confidence(
        satellite_confidence=0.65,
        industrial_fp=no_industrial_fp_result,
    )
    assert same_conf == pytest.approx(base_conf, abs=1e-4)
    assert bd.industrial_penalty == 0.0


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.75, Verdict.TRUE_FIRE),
        (0.90, Verdict.TRUE_FIRE),
        (0.3499, Verdict.FALSE_POSITIVE),
        (0.20, Verdict.FALSE_POSITIVE),
        (0.35, Verdict.UNCERTAIN),
        (0.50, Verdict.UNCERTAIN),
        (0.74, Verdict.UNCERTAIN),
    ],
)
def test_determine_verdict_thresholds(confidence: float, expected: Verdict) -> None:
    assert determine_verdict(confidence) == expected
