"""Tests for ground schemas."""
import pytest
from pydantic import ValidationError

from app.api.schemas import (
    EnhanceRequest,
    GroundEnhancedResult,
    SatelliteResultInput,
    Verdict,
)


def test_satellite_result_input_accepts_valid_data(mock_satellite_result) -> None:
    assert mock_satellite_result.final_confidence == 0.65
    assert mock_satellite_result.verdict == Verdict.UNCERTAIN


def test_enhance_request_requires_at_least_one_result() -> None:
    with pytest.raises(ValidationError):
        EnhanceRequest(results=[])


def test_verdict_enum_values() -> None:
    assert Verdict.TRUE_FIRE.value == "TRUE_FIRE"
    assert Verdict.FALSE_POSITIVE.value == "FALSE_POSITIVE"
    assert Verdict.UNCERTAIN.value == "UNCERTAIN"


def test_ground_enhanced_result_defaults(mock_satellite_result) -> None:
    result = GroundEnhancedResult(
        satellite_result=mock_satellite_result,
        ground_verdict=Verdict.UNCERTAIN,
        ground_confidence=0.65,
    )
    assert result.ground_reasons == []
    assert result.ground_summary == ""
    assert result.processing_time_ms == 0.0
    assert result.geocoding_address is None
    assert result.historical is None
    assert result.industrial_fp is None
