"""Pydantic schemas for the ground fire enhancement system.

SatelliteResultInput mirrors the satellite system's output so the ground
system can accept it directly without transformation.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    """Fire point validation verdict."""
    TRUE_FIRE = "TRUE_FIRE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    UNCERTAIN = "UNCERTAIN"


# ---------------------------------------------------------------------------
# Satellite sub-result mirrors (received as input)
# ---------------------------------------------------------------------------

class FirePointInput(BaseModel):
    """Original fire point from satellite sensor."""
    latitude: float = Field(..., ge=-90, le=90, description="纬度")
    longitude: float = Field(..., ge=-180, le=180, description="经度")
    confidence: Optional[float] = Field(None, ge=0, le=100, description="卫星原始置信度 (0-100)")
    acquisition_time: Optional[datetime] = Field(None, description="观测时间 (UTC)")


class LandCoverResult(BaseModel):
    """Land cover analysis result (from satellite)."""
    class_code: int = Field(..., description="ESA WorldCover 地物编码")
    class_name: str = Field(..., description="地物类型名称")
    likelihood_ratio: float = Field(..., description="地物火灾似然比")
    description: str = Field("", description="地物类型描述")


class FalsePositiveFlag(BaseModel):
    """A single false positive detection flag."""
    detector: str = Field(..., description="检测器名称")
    triggered: bool = Field(..., description="是否触发")
    penalty: float = Field(0.0, ge=0, description="置信度惩罚值")
    detail: str = Field("", description="检测细节")


class SatelliteFalsePositiveResult(BaseModel):
    """Satellite false positive detection results (received as input)."""
    flags: list[FalsePositiveFlag] = Field(default_factory=list, description="各检测器结果")
    total_penalty: float = Field(0.0, ge=0, description="总惩罚值")
    is_likely_false_positive: bool = Field(False, description="是否可能为假阳性")


class EnvironmentalResult(BaseModel):
    """Environmental factor analysis result (from satellite)."""
    is_daytime: bool = Field(..., description="是否为白天")
    solar_zenith_angle: float = Field(..., description="太阳天顶角 (度)")
    fire_season_factor: float = Field(..., description="火灾季节因子")
    env_score: float = Field(0.0, description="环境综合评分")
    detail: str = Field("", description="环境因素详情")


class CoordinateCorrection(BaseModel):
    """Coordinate correction result (from satellite)."""
    original_lat: float = Field(..., description="原始纬度")
    original_lon: float = Field(..., description="原始经度")
    corrected_lat: float = Field(..., description="修正纬度")
    corrected_lon: float = Field(..., description="修正经度")
    offset_m: float = Field(0.0, ge=0, description="修正偏移量 (m)")
    correction_applied: bool = Field(False, description="是否进行了修正")
    reason: str = Field("", description="修正原因")


class SatelliteConfidenceBreakdown(BaseModel):
    """Satellite confidence breakdown (received as input)."""
    initial_confidence: float = Field(50.0, description="初始置信度 (0-100)")
    landcover_contribution: float = Field(0.0, description="地物类型贡献 (logit 空间)")
    environmental_contribution: float = Field(0.0, description="环境因素贡献 (logit 空间)")
    false_positive_penalty: float = Field(0.0, description="假阳性惩罚 (logit 空间)")
    final_confidence: float = Field(0.0, ge=0, le=100, description="最终置信度 (0-100)")


# ---------------------------------------------------------------------------
# Input to ground system — mirrors satellite output
# ---------------------------------------------------------------------------

class SatelliteResultInput(BaseModel):
    """Input to ground enhancement system — the satellite's full output."""
    input_point: FirePointInput = Field(..., description="输入火点")

    verdict: Verdict = Field(..., description="星上判定结果")
    final_confidence: float = Field(..., ge=0, le=100, description="星上最终置信度 (0-100)")
    reasons: list[str] = Field(default_factory=list, description="星上判断原因列表")
    summary: str = Field("", description="星上综合判断摘要")

    coordinate_correction: Optional[CoordinateCorrection] = Field(None, description="坐标修正结果")
    landcover: Optional[LandCoverResult] = Field(None, description="地物分析结果")
    false_positive: Optional[SatelliteFalsePositiveResult] = Field(None, description="假阳性检测结果")
    environmental: Optional[EnvironmentalResult] = Field(None, description="环境因素分析")
    confidence_breakdown: Optional[SatelliteConfidenceBreakdown] = Field(None, description="置信度分解")

    fire_area_m2: Optional[float] = Field(None, ge=0, description="火点估算面积 (m²)，来自星上系统")
    processing_time_ms: float = Field(0.0, ge=0, description="星上处理耗时 (毫秒)")


class EnhanceRequest(BaseModel):
    """Request to enhance one or more satellite validation results."""
    results: list[SatelliteResultInput] = Field(..., min_length=1, description="星上验证结果列表")


# ---------------------------------------------------------------------------
# Ground sub-results (added by ground system)
# ---------------------------------------------------------------------------

class FirmsMatchLevel(str, Enum):
    """FIRMS historical fire data spatial/temporal match level."""
    EXACT_MATCH = "EXACT_MATCH"               # 同位置（1km²），同季节（±1月），3年内
    NEARBY_SAME_SEASON = "NEARBY_SAME_SEASON"  # 5km内，同季节，5年内
    REGIONAL = "REGIONAL"                      # 10km内，任意时间
    NO_SEASON_RECORD = "NO_SEASON_RECORD"      # 火灾高发季节，50km内无记录
    NO_HISTORY = "NO_HISTORY"                  # 50km内无任何历史火点
    CONFIRMED_NONE = "CONFIRMED_NONE"          # 确认无火灾区域


class FirmsResult(BaseModel):
    """FIRMS historical fire data match result."""
    match_level: FirmsMatchLevel = Field(..., description="FIRMS 时空匹配等级")
    nearest_fire_km: Optional[float] = Field(None, ge=0, description="最近历史火点距离 (km)")
    nearest_fire_date: Optional[datetime] = Field(None, description="最近历史火点日期")
    detail: str = Field("", description="详情说明")


class IndustrialProximity(str, Enum):
    """Nearest industrial heat-source proximity class."""
    WITHIN_500M = "WITHIN_500M"
    WITHIN_2KM = "WITHIN_2KM"
    WITHIN_5KM = "WITHIN_5KM"
    NONE = "NONE"                              # 10km内无工业设施


class IndustrialResult(BaseModel):
    """Industrial facility proximity detection result."""
    proximity: IndustrialProximity = Field(..., description="最近工业设施距离等级")
    nearest_facility_m: Optional[float] = Field(None, ge=0, description="最近工业设施距离 (m)")
    facility_type: Optional[str] = Field(None, description="设施类型（电厂/钢铁厂/化工厂等）")
    is_gas_flare: bool = Field(False, description="是否为油气火炬（真实燃烧源，不施加惩罚）")
    detail: str = Field("", description="详情说明")


class GroundConfidenceBreakdown(BaseModel):
    """Ground confidence breakdown — shows what ground system added."""
    satellite_confidence: float = Field(..., ge=0, le=100, description="星上置信度 (0-100)")
    firms_contribution: float = Field(0.0, description="FIRMS 历史数据贡献 (logit 空间)")
    industrial_contribution: float = Field(0.0, description="工业设施修正 (logit 空间)")
    final_confidence: float = Field(0.0, ge=0, le=100, description="地面最终置信度 (0-100)")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

class HeatSourceCandidateSchema(BaseModel):
    """Single heat source category with its probability score."""

    type: str = Field(..., description="热源类型标识")
    label_zh: str = Field(..., description="热源类型中文名称")
    probability: float = Field(..., ge=0, le=1, description="概率 (0-1)")
    raw_score: float = Field(..., description="原始评分（softmax 前）")


class HeatSourceClassificationSchema(BaseModel):
    """Heat source type classification result."""

    ranked_sources: list[HeatSourceCandidateSchema] = Field(
        ..., description="热源类型概率排名（降序）"
    )
    top_type: str = Field(..., description="最可能的热源类型标识")
    top_label_zh: str = Field(..., description="最可能的热源类型中文名称")
    top_probability: float = Field(..., ge=0, le=1, description="最高类型概率")


class GroundEnhancedResult(BaseModel):
    """Complete ground-enhanced result for a single fire point."""
    # Pass through satellite results
    satellite_result: SatelliteResultInput = Field(..., description="星上验证结果")

    # Ground verdict (may differ from satellite)
    ground_verdict: Verdict = Field(..., description="地面判定结果")
    ground_confidence: float = Field(..., ge=0, le=100, description="地面最终置信度 (0-100)")
    ground_reasons: list[str] = Field(default_factory=list, description="地面增强原因列表")
    ground_summary: str = Field("", description="地面增强摘要")

    # Ground-only analysis results
    firms: Optional[FirmsResult] = Field(None, description="FIRMS 历史数据分析")
    industrial: Optional[IndustrialResult] = Field(None, description="工业设施检测")
    ground_confidence_breakdown: Optional[GroundConfidenceBreakdown] = Field(None, description="地面置信度分解")

    # Geocoding (ground-only, needs Nominatim)
    geocoding_address: Optional[str] = Field(None, description="反向地理编码地址")

    # Heat source classification and area estimate
    heat_source_classification: Optional[HeatSourceClassificationSchema] = Field(
        None, description="热源类型概率分类及面积估算"
    )

    processing_time_ms: float = Field(0.0, ge=0, description="地面处理耗时 (毫秒)")


class EnhanceResponse(BaseModel):
    """Response for ground enhancement request."""
    results: list[GroundEnhancedResult] = Field(..., description="增强结果列表")
    total_points: int = Field(..., ge=0, description="总火点数")
    true_fire_count: int = Field(0, ge=0, description="真火点数")
    false_positive_count: int = Field(0, ge=0, description="假阳性数")
    uncertain_count: int = Field(0, ge=0, description="待确认数")
    total_processing_time_ms: float = Field(0.0, ge=0, description="总处理耗时 (毫秒)")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field("ok", description="服务状态")
    version: str = Field("1.0.0", description="版本号")
    services: dict[str, bool] = Field(default_factory=dict, description="各服务可用性")
