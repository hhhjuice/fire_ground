"""Generate human-readable Chinese reasons for ground enhancement.

Adds FIRMS historical fire and industrial facility reasons on top of satellite reasons.
"""
from typing import Optional

from app.api.schemas import (
    FirmsMatchLevel,
    FirmsResult,
    IndustrialProximity,
    IndustrialResult,
    SatelliteResultInput,
    Verdict,
)

_FIRMS_REASON: dict[FirmsMatchLevel, str] = {
    FirmsMatchLevel.EXACT_MATCH: "历史数据显示同位置1km内近期有火灾记录",
    FirmsMatchLevel.NEARBY_SAME_SEASON: "历史数据显示5km内同季节有火灾记录",
    FirmsMatchLevel.REGIONAL: "历史数据显示10km内有区域性火灾记录",
    FirmsMatchLevel.NO_SEASON_RECORD: "当前为火灾高发季节，但50km内无历史火点记录",
    FirmsMatchLevel.NO_HISTORY: "搜索范围内无历史火点记录",
    FirmsMatchLevel.CONFIRMED_NONE: "该区域为确认无火灾区域（常年沙漠/水体/冰雪）",
}

_VERDICT_TEXT: dict[Verdict, str] = {
    Verdict.TRUE_FIRE: "判定为真实火点",
    Verdict.FALSE_POSITIVE: "判定为假阳性",
    Verdict.UNCERTAIN: "判定结果待确认",
}

_INDUSTRIAL_REASON: dict[IndustrialProximity, str] = {
    IndustrialProximity.WITHIN_500M: "500m内发现工业设施，疑似工业热源假阳性",
    IndustrialProximity.WITHIN_2KM: "2km内发现工业设施，存在工业热源干扰可能",
    IndustrialProximity.WITHIN_5KM: "5km内发现工业设施，存在轻微工业热源干扰",
    IndustrialProximity.NONE: "周边未发现工业设施",
}


def generate_ground_reasons(
    satellite_result: SatelliteResultInput,
    firms: Optional[FirmsResult] = None,
    industrial: Optional[IndustrialResult] = None,
) -> list[str]:
    """Generate ground enhancement reason list.

    Starts with satellite reasons, then appends ground-only analysis.
    """
    reasons: list[str] = list(satellite_result.reasons)

    if firms is not None:
        reason_text = _FIRMS_REASON.get(firms.match_level, firms.detail)
        reasons.append(f"[地面增强] {reason_text}")

    if industrial is not None:
        if industrial.is_gas_flare:
            reasons.append(f"[地面增强] {industrial.detail}")
        else:
            reason_text = _INDUSTRIAL_REASON.get(industrial.proximity, industrial.detail)
            reasons.append(f"[地面增强] {reason_text}")

    return reasons


def generate_ground_summary(
    ground_verdict: Verdict,
    ground_confidence: float,
    satellite_result: SatelliteResultInput,
    firms: Optional[FirmsResult] = None,
    industrial: Optional[IndustrialResult] = None,
) -> str:
    """Generate a one-paragraph Chinese summary of the ground enhancement."""
    parts: list[str] = []
    parts.append(
        f"地面增强分析{_VERDICT_TEXT.get(ground_verdict, '未知')}，"
        f"最终置信度{ground_confidence:.1f}%"
        f"（星上置信度{satellite_result.final_confidence:.1f}%）。"
    )

    if firms is not None:
        reason_text = _FIRMS_REASON.get(firms.match_level, firms.detail)
        parts.append(f"{reason_text}。")

    if industrial is not None:
        if industrial.is_gas_flare:
            parts.append(f"工业设施检测: {industrial.detail}。")
        elif industrial.proximity != IndustrialProximity.NONE:
            reason_text = _INDUSTRIAL_REASON.get(industrial.proximity, industrial.detail)
            parts.append(f"工业设施检测: {reason_text}。")

    return "".join(parts)
