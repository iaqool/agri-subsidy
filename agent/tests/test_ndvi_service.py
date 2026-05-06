"""Tests for the NDVI simulator."""

import asyncio
from datetime import datetime

import pytest

from ndvi_service import (
    _alert_label,
    _band_base_ndvi,
    _seasonal_adjustment,
    fetch_historical_ndvi,
)


@pytest.mark.parametrize(
    "lat, expected_min",
    [
        (0.0, 0.6),  # equator — tropics
        (15.0, 0.6),  # tropics
        (45.0, 0.45),  # temperate
        (60.0, 0.35),  # boreal
        (80.0, 0.05),  # polar
    ],
)
def test_band_base_ndvi_decreases_away_from_equator(lat, expected_min):
    assert _band_base_ndvi(lat) >= expected_min


def test_seasonal_adjustment_peak_in_summer_north():
    summer = _seasonal_adjustment(50.0, 7)
    winter = _seasonal_adjustment(50.0, 1)
    assert summer > winter


def test_seasonal_adjustment_southern_hemisphere_inverted():
    summer_north = _seasonal_adjustment(50.0, 7)
    summer_south = _seasonal_adjustment(-50.0, 7)
    # July: positive in NH, negative in SH (it's their winter)
    assert summer_north > 0
    assert summer_south < 0


def test_alert_label_severe_drought():
    assert _alert_label(0.15, 0.5) == "severe_drought"


def test_alert_label_anomalous_drop():
    assert _alert_label(0.5, 0.85) == "anomalous_drop"


def test_alert_label_normal():
    assert _alert_label(0.6, 0.65) == "normal"


def test_fetch_historical_ndvi_is_deterministic():
    async def run():
        a = await fetch_historical_ndvi(45.0, 65.0, sleep_s=0)
        b = await fetch_historical_ndvi(45.0, 65.0, sleep_s=0)
        return a, b

    a, b = asyncio.run(run())
    assert a == b


def test_fetch_historical_ndvi_seasonal_difference():
    async def run():
        summer = await fetch_historical_ndvi(
            55.0, 70.0, now=datetime(2026, 7, 15), sleep_s=0
        )
        winter = await fetch_historical_ndvi(
            55.0, 70.0, now=datetime(2026, 1, 15), sleep_s=0
        )
        return summer, winter

    summer, winter = asyncio.run(run())
    assert summer["current_ndvi"] >= winter["current_ndvi"]


def test_fetch_historical_ndvi_validates_ranges():
    async def run_bad_lat():
        await fetch_historical_ndvi(95.0, 0.0, sleep_s=0)

    async def run_bad_lon():
        await fetch_historical_ndvi(0.0, 200.0, sleep_s=0)

    with pytest.raises(ValueError):
        asyncio.run(run_bad_lat())
    with pytest.raises(ValueError):
        asyncio.run(run_bad_lon())


def test_fetch_historical_ndvi_returns_expected_keys():
    async def run():
        return await fetch_historical_ndvi(40.0, 60.0, sleep_s=0)

    result = asyncio.run(run())
    assert {"current_ndvi", "historical_avg", "alert", "source"} <= set(result)
    assert 0 <= result["current_ndvi"] <= 1
    assert 0 <= result["historical_avg"] <= 1
    assert result["source"] == "simulated"
