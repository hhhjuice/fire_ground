"""Generate human-readable Chinese reasons for ground enhancement.

Adds historical fire and industrial facility reasons on top of satellite reasons.
"""
from typing import Optional

from app.api.schemas import (
    HistoricalFireResult,
    IndustrialFalsePositiveResult,
    SatelliteResultInput,
    Verdict,
)


def generate_ground_reasons(
    satellite_result: SatelliteResultInput,
    historical: Optional[HistoricalFireResult] = None,
    industrial_fp: Optional[IndustrialFalsePositiveResult] = None,
) -> list[str]:
    """Generate ground enhancement reason list.

    Starts with satellite reasons, then appends ground-only analysis.
    """
    reasons: list[str] = list(satellite_result.reasons)

    # Historical fire reason (ground-only)
    if historical is not None:
        if historical.nearby_fire_count > 0:
            reasons.append(
                f"[地面增强] 历史数据显示该区域近期有{historical.nearby_fire_count}次火灾记录，"
                f"最近距离{historical.nearest_distance_m:.0f}m"
            )
        else:
            reasons.append("[地面增强] 该区域近期无历史火灾记录")

    # Industrial false positive reason (ground-only)
    if industrial_fp is not None:
        reasons.append(f"[地面增强] {industrial_fp.flag.detail}")

    return reasons


def generate_ground_summary(
    ground_verdict: Verdict,
    ground_confidence: float,
    satellite_result: SatelliteResultInput,
    historical: Optional[HistoricalFireResult] = None,
    industrial_fp: Optional[IndustrialFalsePositiveResult] = None,
) -> str:
    """Generate a one-paragraph Chinese summary of the ground enhancement."""
    verdict_text = {
        Verdict.TRUE_FIRE: "判定为真实火点",
        Verdict.FALSE_POSITIVE: "判定为假阳性",
        Verdict.UNCERTAIN: "判定结果待确认",
    }

    parts: list[str] = []
    parts.append(
        f"地面增强分析{verdict_text.get(ground_verdict, '未知')}，"
        f"最终置信度{ground_confidence:.1%}"
        f"（星上置信度{satellite_result.final_confidence:.1%}）。"
    )

    if historical is not None:
        if historical.nearby_fire_count > 0:
            parts.append(f"历史数据显示该区域有火灾先例（{historical.nearby_fire_count}次记录）。")
        else:
            parts.append("该区域近期无历史火灾记录。")

    if industrial_fp is not None and industrial_fp.flag.triggered:
        parts.append(f"工业设施检测: {industrial_fp.flag.detail}。")

    return "".join(parts)
