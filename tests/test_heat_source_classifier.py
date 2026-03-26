"""Tests for heat source classification and area estimation."""

from __future__ import annotations

from typing import Optional

from app.api.schemas import (
    EnvironmentalResult,
    FalsePositiveFlag,
    FirmsMatchLevel,
    FirmsResult,
    FirePointInput,
    IndustrialProximity,
    IndustrialResult,
    LandCoverResult,
    SatelliteFalsePositiveResult,
    SatelliteResultInput,
    Verdict,
)
from app.services.heat_source_classifier import (
    HeatSourceType,
    classify_heat_sources,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal SatelliteResultInput objects
# ---------------------------------------------------------------------------

def _make_sat(
    landcover_code: int = -1,
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
        ),
        verdict=Verdict.UNCERTAIN,
        final_confidence=50.0,
        landcover=landcover,
        false_positive=SatelliteFalsePositiveResult(flags=flags) if flags else None,
        environmental=EnvironmentalResult(
            is_daytime=is_daytime,
            solar_zenith_angle=solar_zenith,
            fire_season_factor=fire_season,
            env_score=0.0,
        ),
    )


def _make_firms(match_level: FirmsMatchLevel = FirmsMatchLevel.NO_HISTORY) -> FirmsResult:
    return FirmsResult(
        match_level=match_level,
        nearest_fire_km=None,
        nearest_fire_date=None,
        detail="",
    )


def _make_industrial(triggered: bool = False) -> IndustrialResult:
    proximity = IndustrialProximity.WITHIN_500M if triggered else IndustrialProximity.NONE
    return IndustrialResult(
        proximity=proximity,
        nearest_facility_m=300.0 if triggered else None,
        facility_type="plant" if triggered else None,
        is_gas_flare=False,
        detail="",
    )


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestVegetationFire:
    def test_forest_fire_season_ranks_first(self):
        sat = _make_sat(landcover_code=10, fire_season=1.5, is_daytime=True)
        firms = _make_firms(FirmsMatchLevel.NEARBY_SAME_SEASON)
        result = classify_heat_sources(sat, firms, _make_industrial(False))

        assert result.top_type == HeatSourceType.VEGETATION_FIRE
        assert result.top_probability > 0.5

    def test_shrubland_ranks_vegetation(self):
        sat = _make_sat(landcover_code=20, fire_season=1.2)
        result = classify_heat_sources(sat, _make_firms(FirmsMatchLevel.NEARBY_SAME_SEASON), None)

        assert result.top_type == HeatSourceType.VEGETATION_FIRE

    def test_industrial_suppresses_vegetation(self):
        sat = _make_sat(landcover_code=10, fire_season=1.5)
        result = classify_heat_sources(sat, _make_firms(), _make_industrial(True))

        assert result.top_type != HeatSourceType.VEGETATION_FIRE


class TestAgriculturalBurning:
    def test_cropland_ranks_first(self):
        sat = _make_sat(landcover_code=40, fire_season=1.2)
        result = classify_heat_sources(sat, _make_firms(FirmsMatchLevel.REGIONAL), None)

        assert result.top_type == HeatSourceType.AGRICULTURAL_BURNING

    def test_non_cropland_scores_lower(self):
        sat = _make_sat(landcover_code=40)
        result_crop = classify_heat_sources(sat, None, None)

        sat_forest = _make_sat(landcover_code=10)
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
        sat = _make_sat(landcover_code=50, fire_season=0.5)
        result = classify_heat_sources(sat, _make_firms(), _make_industrial(True))

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
        result = classify_heat_sources(sat, _make_firms(FirmsMatchLevel.NO_HISTORY), None)

        assert result.top_type == HeatSourceType.SUN_GLINT
        assert result.top_probability > 0.5

    def test_nighttime_suppresses_sun_glint(self):
        sat = _make_sat(fp_flags={"sun_glint": True}, is_daytime=False)
        result = classify_heat_sources(sat, None, None)

        assert result.top_type != HeatSourceType.SUN_GLINT


class TestWaterReflection:
    def test_water_body_landcover_ranks_first(self):
        sat = _make_sat(landcover_code=80, fp_flags={"water_body": True})
        result = classify_heat_sources(sat, _make_firms(FirmsMatchLevel.NO_HISTORY), None)

        assert result.top_type == HeatSourceType.WATER_REFLECTION


class TestCoastalReflection:
    def test_coastal_triggered_ranks_first(self):
        sat = _make_sat(landcover_code=90, fp_flags={"coastal_reflection": True})
        result = classify_heat_sources(sat, _make_firms(FirmsMatchLevel.NO_HISTORY), None)

        assert result.top_type == HeatSourceType.COASTAL_REFLECTION


class TestWetlandFire:
    def test_wetland_without_coastal_flag_ranks_first(self):
        sat = _make_sat(
            landcover_code=95,
            fire_season=1.3,
            fp_flags={"coastal_reflection": False},
        )
        result = classify_heat_sources(sat, _make_firms(FirmsMatchLevel.NEARBY_SAME_SEASON), None)

        assert result.top_type == HeatSourceType.WETLAND_FIRE


# ---------------------------------------------------------------------------
# Probability distribution tests
# ---------------------------------------------------------------------------

class TestProbabilityDistribution:
    def test_probabilities_sum_to_one(self):
        sat = _make_sat(landcover_code=10)
        result = classify_heat_sources(sat, _make_firms(), None)

        total = sum(c.probability for c in result.ranked_sources)
        assert abs(total - 1.0) < 1e-6

    def test_all_eight_categories_present(self):
        sat = _make_sat()
        result = classify_heat_sources(sat, None, None)

        types_returned = {c.type for c in result.ranked_sources}
        assert types_returned == set(HeatSourceType)

    def test_sorted_descending(self):
        sat = _make_sat(landcover_code=10, fire_season=1.4)
        result = classify_heat_sources(sat, _make_firms(FirmsMatchLevel.NEARBY_SAME_SEASON), None)

        probs = [c.probability for c in result.ranked_sources]
        assert probs == sorted(probs, reverse=True)


