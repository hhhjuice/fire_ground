"""Tests for ground reason generator."""
from app.api.schemas import Verdict
from app.utils.reason_generator import generate_ground_reasons, generate_ground_summary


def test_ground_reasons_include_satellite_reasons(mock_satellite_result) -> None:
    """Ground reasons should start with satellite reasons."""
    reasons = generate_ground_reasons(satellite_result=mock_satellite_result)
    assert "地物类型为草地" in reasons[0]
    assert "未检测到假阳性特征" in reasons[1]


def test_ground_reasons_include_historical(mock_satellite_result, positive_historical_result) -> None:
    """Should add historical fire analysis reason."""
    reasons = generate_ground_reasons(
        satellite_result=mock_satellite_result,
        historical=positive_historical_result,
    )
    joined = " ".join(reasons)
    assert "[地面增强]" in joined
    assert "历史" in joined


def test_ground_reasons_include_industrial(mock_satellite_result, industrial_fp_result) -> None:
    """Should add industrial detection reason."""
    reasons = generate_ground_reasons(
        satellite_result=mock_satellite_result,
        industrial_fp=industrial_fp_result,
    )
    joined = " ".join(reasons)
    assert "[地面增强]" in joined
    assert "工业设施" in joined


def test_ground_summary_contains_verdict_and_confidence(mock_satellite_result) -> None:
    summary = generate_ground_summary(
        ground_verdict=Verdict.TRUE_FIRE,
        ground_confidence=0.82,
        satellite_result=mock_satellite_result,
    )
    assert "地面增强" in summary
    assert "82.0%" in summary
    assert "65.0%" in summary  # satellite confidence reference
