"""Integration-style tests for ground API routes."""

from fastapi.testclient import TestClient

from app.api import routes
from app.api.schemas import EnhanceResponse, GroundEnhancedResult, Verdict
from app.main import app


def test_health_endpoint_database_degraded(monkeypatch) -> None:
    async def degraded_db() -> bool:
        return False

    monkeypatch.setattr(routes, "check_db_health", degraded_db)

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["services"]["database"] is False


def test_enhance_endpoint_returns_200_when_db_save_fails(monkeypatch, mock_satellite_result) -> None:
    async def fake_enhance_batch(results, firms_map_key=None):
        return EnhanceResponse(
            results=[
                GroundEnhancedResult(
                    satellite_result=mock_satellite_result,
                    ground_verdict=Verdict.UNCERTAIN,
                    ground_confidence=65.0,
                    ground_summary="地面增强摘要",
                )
            ],
            total_points=1,
            uncertain_count=1,
        )

    async def failing_save(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(routes, "enhance_batch", fake_enhance_batch)
    monkeypatch.setattr(routes, "save_enhancement_result", failing_save)

    response = TestClient(app).post(
        "/api/enhance",
        json={"results": [mock_satellite_result.model_dump(mode="json")], "firms_map_key": "SECRET"},
    )

    assert response.status_code == 200
    assert response.json()["total_points"] == 1
    assert "SECRET" not in response.text


def test_cors_preflight_is_restricted_to_configured_headers() -> None:
    response = TestClient(app).options(
        "/api/enhance",
        headers={
            "Origin": "http://localhost:8001",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-credentials") is None
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed_headers
    assert "authorization" not in allowed_headers
