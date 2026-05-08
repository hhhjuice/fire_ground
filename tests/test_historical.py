"""Tests for FIRMS historical query control flow."""

import pytest
import httpx

from app.api.schemas import FirmsMatchLevel, FirmsQueryStatus
from app.services import historical


@pytest.mark.asyncio
async def test_get_historical_fires_without_key_is_disabled(monkeypatch) -> None:
    async def fail_query(*args, **kwargs):
        raise AssertionError("FIRMS should not be queried without a key")

    monkeypatch.setattr(historical, "query_firms", fail_query)

    result = await historical.get_historical_fires(28.5, 116.3, firms_map_key=None)

    assert result.status == FirmsQueryStatus.DISABLED
    assert result.match_level == FirmsMatchLevel.NO_HISTORY
    assert "跳过" in result.detail


@pytest.mark.asyncio
async def test_get_historical_fires_failure_is_not_no_history(monkeypatch) -> None:
    async def failed_query(*args, **kwargs):
        return [], len(historical.FIRMS_SOURCES)

    monkeypatch.setattr(historical, "query_firms", failed_query)

    result = await historical.get_historical_fires(28.5, 116.3, firms_map_key="key")

    assert result.status == FirmsQueryStatus.FAILED
    assert result.match_level == FirmsMatchLevel.NO_HISTORY
    assert "未将无历史记录作为负证据" in result.detail


@pytest.mark.parametrize(
    ("distance_m", "expected"),
    [
        (1000.0, FirmsMatchLevel.EXACT_MATCH),
        (5000.0, FirmsMatchLevel.NEARBY),
        (10000.0, FirmsMatchLevel.REGIONAL),
    ],
)
def test_classify_match_level_includes_distance_boundaries(monkeypatch, distance_m, expected) -> None:
    monkeypatch.setattr(historical, "haversine", lambda *args: distance_m)

    result = historical._classify_match_level(
        [{"latitude": "28.5", "longitude": "116.3", "acq_date": "2026-02-15"}],
        28.5,
        116.3,
    )

    assert result.match_level == expected


@pytest.mark.asyncio
async def test_query_source_does_not_log_firms_key(caplog) -> None:
    secret = "SECRET_MAP_KEY"

    class FailingClient:
        async def get(self, url, headers):
            request = httpx.Request("GET", url)
            raise httpx.RequestError(f"failed {url}", request=request)

    caplog.set_level("WARNING")

    result = await historical._query_source(
        FailingClient(),
        secret,
        "https://firms.example/api/area/csv",
        "test-agent",
        "VIIRS_SNPP_NRT",
        "1,2,3,4",
        5,
    )

    assert result is None
    assert secret not in caplog.text
    assert "firms.example" not in caplog.text
