"""FastAPI route definitions for ground fire enhancement API."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import (
    EnhanceRequest,
    EnhanceResponse,
    GroundEnhancedResult,
    HealthResponse,
)
from app.core.pipeline import enhance_batch
from app.data.cache import (
    get_nearby_enhancements,
    get_recent_enhancements,
    save_enhancement_result,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/enhance", response_model=EnhanceResponse, summary="地面增强验证")
async def enhance_fire_points(request: EnhanceRequest) -> EnhanceResponse:
    """接收星上验证结果列表并返回地面增强结果。"""
    try:
        response = await enhance_batch(request.results)
    except Exception as exc:
        logger.exception("Enhancement pipeline error")
        raise HTTPException(status_code=500, detail=f"地面增强流程异常: {exc}") from exc

    # Save results to database
    async def _save_result(result: GroundEnhancedResult) -> None:
        try:
            await save_enhancement_result(
                latitude=result.satellite_result.input_point.latitude,
                longitude=result.satellite_result.input_point.longitude,
                satellite_verdict=result.satellite_result.verdict.value,
                satellite_confidence=result.satellite_result.final_confidence,
                ground_verdict=result.ground_verdict.value,
                ground_confidence=result.ground_confidence,
                summary=result.ground_summary,
                result_json=result.model_dump_json(),
            )
        except Exception as exc:
            logger.warning("Failed to save enhancement result to DB: %s", exc)

    save_tasks = [asyncio.create_task(_save_result(r)) for r in response.results]
    if save_tasks:
        await asyncio.gather(*save_tasks, return_exceptions=True)

    return response


@router.get("/api/health", response_model=HealthResponse, summary="健康检查")
async def health_check() -> HealthResponse:
    """返回地面增强服务状态。"""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        services={"pipeline": True, "database": True},
    )


@router.get("/api/history", summary="历史记录")
async def get_history(
    limit: int = Query(50, ge=1, le=500, description="返回记录数量"),
) -> list[dict]:
    """获取最近的增强结果。"""
    try:
        return await get_recent_enhancements(limit)
    except Exception as exc:
        logger.exception("History query error")
        raise HTTPException(status_code=500, detail=f"查询失败: {exc}") from exc


@router.get("/api/history/nearby", summary="附近历史记录")
async def get_nearby_history(
    lat: float = Query(..., ge=-90, le=90, description="纬度"),
    lon: float = Query(..., ge=-180, le=180, description="经度"),
    radius_deg: float = Query(0.05, gt=0, le=1.0, description="搜索半径(度)"),
) -> list[dict]:
    """获取指定坐标附近的历史增强结果。"""
    try:
        return await get_nearby_enhancements(lat, lon, radius_deg)
    except Exception as exc:
        logger.exception("Nearby query error")
        raise HTTPException(status_code=500, detail=f"查询失败: {exc}") from exc
