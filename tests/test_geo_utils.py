"""Tests for ground geo utilities."""
from datetime import datetime, timezone

import pytest

from app.utils.geo import (
    bbox_from_point,
    get_fire_season_factor,
    haversine,
    is_daytime,
    solar_zenith_angle,
)


def test_haversine_same_point_is_zero() -> None:
    assert haversine(40.7128, -74.0060, 40.7128, -74.0060) == pytest.approx(0.0, abs=1e-6)


def test_haversine_nyc_to_la_known_distance() -> None:
    distance_m = haversine(40.7128, -74.0060, 34.0522, -118.2437)
    assert distance_m / 1000 == pytest.approx(3944, rel=0.02)


def test_bbox_from_point_symmetry_and_size() -> None:
    lat, lon, radius_m = 10.0, 20.0, 1000.0
    min_lat, min_lon, max_lat, max_lon = bbox_from_point(lat, lon, radius_m)

    assert (lat - min_lat) == pytest.approx(max_lat - lat, rel=1e-9)
    assert (lon - min_lon) == pytest.approx(max_lon - lon, rel=1e-9)

    north_distance = haversine(lat, lon, max_lat, lon)
    east_distance = haversine(lat, lon, lat, max_lon)
    assert north_distance == pytest.approx(radius_m, rel=0.03)
    assert east_distance == pytest.approx(radius_m, rel=0.03)


def test_solar_zenith_angle_equator_equinox_noon_and_midnight() -> None:
    noon = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)
    midnight = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)

    noon_zenith = solar_zenith_angle(0.0, 0.0, noon)
    midnight_zenith = solar_zenith_angle(0.0, 0.0, midnight)

    assert 0.0 <= noon_zenith <= 15.0
    assert midnight_zenith > 90.0


def test_is_daytime_noon_true_midnight_false() -> None:
    noon = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)
    midnight = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)

    assert is_daytime(0.0, 0.0, noon) is True
    assert is_daytime(0.0, 0.0, midnight) is False


def test_get_fire_season_factor_hemisphere_seasonality() -> None:
    north_summer = get_fire_season_factor(45.0, 7)
    north_winter = get_fire_season_factor(45.0, 1)
    south_summer = get_fire_season_factor(-30.0, 1)
    south_winter = get_fire_season_factor(-30.0, 7)

    assert north_summer > north_winter
    assert south_summer > south_winter
