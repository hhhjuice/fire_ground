"""Shared test fixtures for ground fire enhancement tests."""
import os

import pytest

from app.api.schemas import (
    FirmsMatchLevel,
    FirmsResult,
    IndustrialProximity,
    IndustrialResult,
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
            "confidence": 80,
        },
        verdict=Verdict.UNCERTAIN,
        final_confidence=65.0,
        reasons=["地物类型为草地，属于高火灾风险区域", "未检测到假阳性特征"],
        summary="星上分析判定结果待确认，最终置信度65.0%。",
    )


@pytest.fixture
def positive_firms_result() -> FirmsResult:
    return FirmsResult(
        match_level=FirmsMatchLevel.NEARBY_SAME_SEASON,
        nearest_fire_km=3.2,
        nearest_fire_date=None,
        detail="5km内发现历史火点，距离3.20km",
    )


@pytest.fixture
def no_history_firms_result() -> FirmsResult:
    return FirmsResult(
        match_level=FirmsMatchLevel.NO_HISTORY,
        nearest_fire_km=None,
        nearest_fire_date=None,
        detail="搜索范围内无历史火点记录",
    )


@pytest.fixture
def industrial_result() -> IndustrialResult:
    return IndustrialResult(
        proximity=IndustrialProximity.WITHIN_500M,
        nearest_facility_m=320.0,
        facility_type="plant",
        is_gas_flare=False,
        detail="周边发现2个工业设施: 某某电厂, 某某工厂，最近设施距离320m（WITHIN_500M）",
    )


@pytest.fixture
def no_industrial_result() -> IndustrialResult:
    return IndustrialResult(
        proximity=IndustrialProximity.NONE,
        nearest_facility_m=None,
        facility_type=None,
        is_gas_flare=False,
        detail="5km内未发现工业设施",
    )
