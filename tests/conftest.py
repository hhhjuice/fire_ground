"""Shared test fixtures for ground fire enhancement tests."""
import os

import pytest

from app.api.schemas import (
    FalsePositiveFlag,
    HistoricalFireResult,
    IndustrialFalsePositiveResult,
    SatelliteResultInput,
    Verdict,
)

# Ensure test env doesn't hit real APIs
os.environ.setdefault("GROUND_FIRMS_MAP_KEY", "TEST_KEY")
os.environ.setdefault("GROUND_DB_PATH", "/tmp/test_fire_ground.db")


@pytest.fixture
def mock_satellite_result() -> SatelliteResultInput:
    """A typical satellite result for testing."""
    return SatelliteResultInput(
        input_point={
            "latitude": 28.5,
            "longitude": 116.3,
            "satellite": "VIIRS",
            "brightness": 340.0,
            "frp": 15.2,
            "confidence": 80,
        },
        verdict=Verdict.UNCERTAIN,
        final_confidence=0.65,
        reasons=["地物类型为草地，属于高火灾风险区域", "未检测到假阳性特征"],
        summary="星上分析判定结果待确认，最终置信度65.0%。",
    )


@pytest.fixture
def positive_historical_result() -> HistoricalFireResult:
    return HistoricalFireResult(
        nearby_fire_count=5,
        nearest_distance_m=120.0,
        days_searched=30,
        score=0.8,
        detail="过去30天内半径5km范围发现5个历史火点，最近距离120m",
    )


@pytest.fixture
def industrial_fp_result() -> IndustrialFalsePositiveResult:
    return IndustrialFalsePositiveResult(
        flag=FalsePositiveFlag(
            detector="industrial_heat",
            triggered=True,
            penalty=0.8,
            detail="周边发现2个工业设施: 某某电厂, 某某工厂",
        )
    )


@pytest.fixture
def no_industrial_fp_result() -> IndustrialFalsePositiveResult:
    return IndustrialFalsePositiveResult(
        flag=FalsePositiveFlag(
            detector="industrial_heat",
            triggered=False,
            penalty=0.0,
            detail="周边未发现工业设施",
        )
    )
