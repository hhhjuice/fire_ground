"""Tests for ground confidence engine."""
import math

import pytest

from app.api.schemas import (
    FirmsMatchLevel,
    FirmsResult,
    IndustrialProximity,
    IndustrialResult,
    Verdict,
)
from app.core.confidence import compute_ground_confidence, determine_verdict


def test_ground_confidence_no_enhancement_preserves_satellite() -> None:
    """With no FIRMS or industrial data, ground confidence equals satellite."""
    conf, bd = compute_ground_confidence(satellite_confidence=65.0)
    assert conf == pytest.approx(65.0, abs=0.1)
    assert bd.satellite_confidence == 65.0


def test_firms_exact_match_increases_confidence() -> None:
    """Exact FIRMS match should significantly increase confidence."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=65.0)
    firms = FirmsResult(
        match_level=FirmsMatchLevel.EXACT_MATCH,
        nearest_fire_km=0.3,
        nearest_fire_date=None,
        detail="",
    )
    boosted_conf, bd = compute_ground_confidence(
        satellite_confidence=65.0,
        firms=firms,
    )
    assert boosted_conf > base_conf
    assert bd.firms_contribution == pytest.approx(math.log(4.0), abs=1e-4)


def test_firms_no_history_decreases_confidence() -> None:
    """No history should decrease confidence."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=65.0)
    firms = FirmsResult(
        match_level=FirmsMatchLevel.NO_HISTORY,
        nearest_fire_km=None,
        nearest_fire_date=None,
        detail="",
    )
    lowered_conf, _ = compute_ground_confidence(
        satellite_confidence=65.0,
        firms=firms,
    )
    assert lowered_conf < base_conf


def test_industrial_within_500m_decreases_confidence(industrial_result) -> None:
    """Industrial facilities within 500m should decrease confidence."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=65.0)
    penalized_conf, bd = compute_ground_confidence(
        satellite_confidence=65.0,
        industrial=industrial_result,
    )
    assert penalized_conf < base_conf
    assert bd.industrial_contribution < 0


def test_no_industrial_applies_positive_delta(no_industrial_result) -> None:
    """No industrial facilities applies a small positive delta."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=65.0)
    boosted_conf, bd = compute_ground_confidence(
        satellite_confidence=65.0,
        industrial=no_industrial_result,
    )
    assert boosted_conf > base_conf
    assert bd.industrial_contribution > 0


def test_gas_flare_skips_penalty() -> None:
    """Gas flare should not reduce confidence."""
    base_conf, _ = compute_ground_confidence(satellite_confidence=65.0)
    gas_flare = IndustrialResult(
        proximity=IndustrialProximity.WITHIN_500M,
        nearest_facility_m=100.0,
        facility_type="flare",
        is_gas_flare=True,
        detail="",
    )
    same_conf, bd = compute_ground_confidence(
        satellite_confidence=65.0,
        industrial=gas_flare,
    )
    assert same_conf == pytest.approx(base_conf, abs=1e-4)
    assert bd.industrial_contribution == 0.0


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (75.0, Verdict.TRUE_FIRE),
        (90.0, Verdict.TRUE_FIRE),
        (49.9, Verdict.FALSE_POSITIVE),
        (20.0, Verdict.FALSE_POSITIVE),
        (50.0, Verdict.UNCERTAIN),
        (60.0, Verdict.UNCERTAIN),
        (74.9, Verdict.UNCERTAIN),
    ],
)
def test_determine_verdict_thresholds(confidence: float, expected: Verdict) -> None:
    assert determine_verdict(confidence) == expected
