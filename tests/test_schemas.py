"""Tests for ground schemas."""
import pytest
from pydantic import ValidationError

from app.api.schemas import (
    EnhanceRequest,
    GroundEnhancedResult,
    SatelliteResultInput,
    Verdict,
)
from app.config import get_settings


def test_satellite_result_input_accepts_valid_data(mock_satellite_result) -> None:
    assert mock_satellite_result.final_confidence == 65.0
    assert mock_satellite_result.verdict == Verdict.UNCERTAIN


def test_enhance_request_requires_at_least_one_result() -> None:
    with pytest.raises(ValidationError):
        EnhanceRequest(results=[])


def test_enhance_request_rejects_over_limit(mock_satellite_result) -> None:
    results = [mock_satellite_result] * (get_settings().max_batch_results + 1)

    with pytest.raises(ValidationError):
        EnhanceRequest(results=results)


def test_enhance_request_normalizes_blank_firms_key(mock_satellite_result) -> None:
    request = EnhanceRequest(results=[mock_satellite_result], firms_map_key="   ")

    assert request.firms_map_key is None


def test_verdict_enum_values() -> None:
    assert Verdict.TRUE_FIRE.value == "TRUE_FIRE"
    assert Verdict.FALSE_POSITIVE.value == "FALSE_POSITIVE"
    assert Verdict.UNCERTAIN.value == "UNCERTAIN"


def test_ground_enhanced_result_defaults(mock_satellite_result) -> None:
    result = GroundEnhancedResult(
        satellite_result=mock_satellite_result,
        ground_verdict=Verdict.UNCERTAIN,
        ground_confidence=65.0,
    )
    assert result.ground_reasons == []
    assert result.ground_summary == ""
    assert result.processing_time_ms == 0.0
    assert result.geocoding_address is None
    assert result.firms is None
    assert result.industrial is None
