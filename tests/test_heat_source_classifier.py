"""Tests for heat source classification and area estimation."""

from __future__ import annotations

from typing import Optional

import pytest

from app.api.schemas import (
    EnvironmentalResult,
    FalsePositiveFlag,
    FirePointInput,
    HistoricalFireResult,
    IndustrialFalsePositiveResult,
    LandCoverResult,
    SatelliteFalsePositiveResult,
    SatelliteResultInput,
    Verdict,
)
from app.services.heat_source_classifier import (
    HeatSourceType,
    classify_heat_sources,
    _estimate_area,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal SatelliteResultInput objects
# ---------------------------------------------------------------------------

def _make_sat(
    landcover_code: int = -1,
    frp: Optional[float] = None,
    brightness: Optional[float] = None,
    satellite: str = "TERRA",
    is_daytime: bool = True,
    solar_zenith: float = 45.0,
    fire_season: float = 1.0,
    fp_flags: Optional[dict[str, bool]] = None,
) -> SatelliteResultInput:
    flags = []
    for name, triggered in (fp_flags or {}).items():
        flags.append(FalsePositiveFlag(detector=name, triggered=triggered, penalty=0.0))

    landcover = None
    if landcover_code >= 0:
        landcover = LandCoverResult(
            class_code=landcover_code,
            class_name="test",
            likelihood_ratio=1.0,
        )

    return SatelliteResultInput(
        input_point=FirePointInput(
            latitude=30.0,
            longitude=110.0,
            satellite=satellite,
            brightness=brightness,
            frp=frp,
        ),
        verdict=Verdict.UNCERTAIN,
        final_confidence=0.5,
        landcover=landcover,
        false_positive=SatelliteFalsePositiveResult(flags=flags) if flags else None,
        environmental=EnvironmentalResult(
            is_daytime=is_daytime,
            solar_zenith_angle=solar_zenith,
            fire_season_factor=fire_season,
            env_score=0.0,
        ),
    )


def _make_historical(score: float = 0.0, count: int = 0) -> HistoricalFireResult:
    return HistoricalFireResult(
        nearby_fire_count=count,
        nearest_distance_m=None if count == 0 else 1000.0,
        days_searched=5,
        score=score,
        detail="",
    )


def _make_industrial(triggered: bool = False) -> IndustrialFalsePositiveResult:
    return IndustrialFalsePositiveResult(
        flag=FalsePositiveFlag(
            detector="industrial",
            triggered=triggered,
            penalty=0.8 if triggered else 0.0,
        )
    )


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestVegetationFire:
    def test_forest_high_frp_fire_season_ranks_first(self):
        sat = _make_sat(landcover_code=10, frp=60.0, fire_season=1.5, is_daytime=True)
        hist = _make_historical(score=0.5, count=8)
        result = classify_heat_sources(sat, hist, _make_industrial(False))

        assert result.top_type == HeatSourceType.VEGETATION_FIRE
        assert result.top_probability > 0.5

    def test_shrubland_ranks_vegetation(self):
        sat = _make_sat(landcover_code=20, frp=25.0, fire_season=1.2)
        result = classify_heat_sources(sat, _make_historical(score=0.4, count=3), None)

        assert result.top_type == HeatSourceType.VEGETATION_FIRE

    def test_industrial_suppresses_vegetation(self):
        sat = _make_sat(landcover_code=10, frp=60.0, fire_season=1.5)
        result = classify_heat_sources(sat, _make_historical(), _make_industrial(True))

        assert result.top_type != HeatSourceType.VEGETATION_FIRE


class TestAgriculturalBurning:
    def test_cropland_moderate_frp_ranks_first(self):
        sat = _make_sat(landcover_code=40, frp=20.0, fire_season=1.2)
        result = classify_heat_sources(sat, _make_historical(score=0.2, count=2), None)

        assert result.top_type == HeatSourceType.AGRICULTURAL_BURNING

    def test_non_cropland_scores_lower(self):
        sat = _make_sat(landcover_code=40, frp=20.0)
        result_crop = classify_heat_sources(sat, None, None)

        sat_forest = _make_sat(landcover_code=10, frp=20.0)
        result_forest = classify_heat_sources(sat_forest, None, None)

        crop_score = next(
            c.raw_score for c in result_crop.ranked_sources
            if c.type == HeatSourceType.AGRICULTURAL_BURNING
        )
        forest_score = next(
            c.raw_score for c in result_forest.ranked_sources
            if c.type == HeatSourceType.AGRICULTURAL_BURNING
        )
        assert crop_score > forest_score


class TestIndustrialHeat:
    def test_industrial_triggered_ranks_first(self):
        sat = _make_sat(landcover_code=50, frp=120.0, fire_season=0.5)
        result = classify_heat_sources(sat, _make_historical(), _make_industrial(True))

        assert result.top_type == HeatSourceType.INDUSTRIAL_HEAT

    def test_urban_heat_flag_boosts_industrial(self):
        sat_with = _make_sat(fp_flags={"urban_heat": True, "industrial": True})
        sat_without = _make_sat(fp_flags={"industrial": True})

        r_with = classify_heat_sources(sat_with, None, _make_industrial(True))
        r_without = classify_heat_sources(sat_without, None, _make_industrial(True))

        score_with = next(
            c.raw_score for c in r_with.ranked_sources
            if c.type == HeatSourceType.INDUSTRIAL_HEAT
        )
        score_without = next(
            c.raw_score for c in r_without.ranked_sources
            if c.type == HeatSourceType.INDUSTRIAL_HEAT
        )
        assert score_with > score_without


class TestSunGlint:
    def test_sun_glint_triggered_daytime_ranks_first(self):
        sat = _make_sat(
            fp_flags={"sun_glint": True},
            is_daytime=True,
            solar_zenith=25.0,
            fire_season=0.8,
        )
        result = classify_heat_sources(sat, _make_historical(score=-0.5), None)

        assert result.top_type == HeatSourceType.SUN_GLINT
        assert result.top_probability > 0.5

    def test_nighttime_suppresses_sun_glint(self):
        sat = _make_sat(fp_flags={"sun_glint": True}, is_daytime=False)
        result = classify_heat_sources(sat, None, None)

        assert result.top_type != HeatSourceType.SUN_GLINT


class TestWaterReflection:
    def test_water_body_landcover_ranks_first(self):
        sat = _make_sat(landcover_code=80, fp_flags={"water_body": True})
        result = classify_heat_sources(sat, _make_historical(score=-0.3), None)

        assert result.top_type == HeatSourceType.WATER_REFLECTION


class TestCoastalReflection:
    def test_coastal_triggered_ranks_first(self):
        sat = _make_sat(landcover_code=90, fp_flags={"coastal_reflection": True})
        result = classify_heat_sources(sat, _make_historical(score=-0.2), None)

        assert result.top_type == HeatSourceType.COASTAL_REFLECTION


class TestWetlandFire:
    def test_wetland_without_coastal_flag_ranks_first(self):
        sat = _make_sat(
            landcover_code=95,
            frp=15.0,
            fire_season=1.3,
            fp_flags={"coastal_reflection": False},
        )
        result = classify_heat_sources(sat, _make_historical(score=0.4, count=4), None)

        assert result.top_type == HeatSourceType.WETLAND_FIRE


# ---------------------------------------------------------------------------
# Probability distribution tests
# ---------------------------------------------------------------------------

class TestProbabilityDistribution:
    def test_probabilities_sum_to_one(self):
        sat = _make_sat(landcover_code=10, frp=30.0)
        result = classify_heat_sources(sat, _make_historical(), None)

        total = sum(c.probability for c in result.ranked_sources)
        assert abs(total - 1.0) < 1e-6

    def test_all_eight_categories_present(self):
        sat = _make_sat()
        result = classify_heat_sources(sat, None, None)

        types_returned = {c.type for c in result.ranked_sources}
        assert types_returned == set(HeatSourceType)

    def test_sorted_descending(self):
        sat = _make_sat(landcover_code=10, frp=40.0, fire_season=1.4)
        result = classify_heat_sources(sat, _make_historical(score=0.5, count=5), None)

        probs = [c.probability for c in result.ranked_sources]
        assert probs == sorted(probs, reverse=True)


# ---------------------------------------------------------------------------
# Area estimation tests
# ---------------------------------------------------------------------------

class TestAreaEstimation:
    def test_viirs_single_pixel_area(self):
        area, basis = _estimate_area("SUOMI NPP", HeatSourceType.INDUSTRIAL_HEAT, None, 0)
        assert area == pytest.approx(0.141, abs=1e-4)
        assert "VIIRS" in basis

    def test_modis_single_pixel_area(self):
        area, basis = _estimate_area("TERRA", HeatSourceType.INDUSTRIAL_HEAT, None, 0)
        assert area == pytest.approx(1.0, abs=1e-4)
        assert "MODIS" in basis

    def test_default_50m_pixel(self):
        area, basis = _estimate_area("UNKNOWN_SAT", HeatSourceType.INDUSTRIAL_HEAT, None, 0)
        assert area == pytest.approx(0.0025, abs=1e-6)
        assert "50m" in basis

    def test_fire_type_scales_with_frp(self):
        area_low, _ = _estimate_area("TERRA", HeatSourceType.VEGETATION_FIRE, 10.0, 0)
        area_high, _ = _estimate_area("TERRA", HeatSourceType.VEGETATION_FIRE, 100.0, 0)
        assert area_high > area_low

    def test_fire_type_scales_with_history(self):
        area_few, _ = _estimate_area("TERRA", HeatSourceType.VEGETATION_FIRE, 25.0, 2)
        area_many, _ = _estimate_area("TERRA", HeatSourceType.VEGETATION_FIRE, 25.0, 20)
        assert area_many > area_few

    def test_fire_area_capped_at_500(self):
        # Extreme values should not exceed 500 km²
        area, _ = _estimate_area("TERRA", HeatSourceType.VEGETATION_FIRE, 9999.0, 9999)
        assert area <= 500.0

    def test_non_fire_type_uses_single_pixel(self):
        area_viirs, _ = _estimate_area("SUOMI NPP", HeatSourceType.SUN_GLINT, 50.0, 10)
        assert area_viirs == pytest.approx(0.141, abs=1e-4)

    def test_area_in_classification_result(self):
        sat = _make_sat(landcover_code=10, frp=50.0, fire_season=1.4, satellite="AQUA")
        result = classify_heat_sources(sat, _make_historical(count=5), None)

        assert result.estimated_area_km2 > 0
        assert result.area_basis != ""
