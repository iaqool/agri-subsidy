"""Unit tests for the composite scoring engine."""

from scoring_engine import (
    calculate_composite_score,
    calculate_ndvi_score,
    calculate_weather_score,
)


def test_weather_score_extreme_heat_low_humidity_no_rain():
    weather = {"temperature": 39, "humidity": 18, "rain_1h": 0}
    assert calculate_weather_score(weather) == 100  # capped


def test_weather_score_normal_conditions_low_stress():
    weather = {"temperature": 22, "humidity": 60, "rain_1h": 5}
    assert calculate_weather_score(weather) == 0


def test_weather_score_with_error_returns_neutral():
    assert calculate_weather_score({"error": "API unavailable"}) == 50


def test_ndvi_score_severe_drought_high_stress():
    ndvi = {"current_ndvi": 0.15, "historical_avg": 0.5}
    assert calculate_ndvi_score(ndvi) == 100  # capped after deviation bump


def test_ndvi_score_healthy_vegetation_low_stress():
    ndvi = {"current_ndvi": 0.8, "historical_avg": 0.75}
    assert calculate_ndvi_score(ndvi) == 15


def test_composite_score_drought_case_approves():
    weather = {"temperature": 39, "humidity": 18, "rain_1h": 0}
    ndvi = {"current_ndvi": 0.18, "historical_avg": 0.55}

    result = calculate_composite_score(weather, ndvi)

    assert result["composite_score"] >= result["threshold"]
    assert result["approved"] is True
    assert result["weather_score"] == 100
    assert result["ndvi_score"] == 100


def test_composite_score_normal_case_rejects():
    weather = {"temperature": 22, "humidity": 60, "rain_1h": 5}
    ndvi = {"current_ndvi": 0.75, "historical_avg": 0.7}

    result = calculate_composite_score(weather, ndvi)

    assert result["composite_score"] < result["threshold"]
    assert result["approved"] is False


def test_composite_score_history_penalty_can_block_approval():
    weather = {"temperature": 33, "humidity": 30, "rain_1h": 0}
    ndvi = {"current_ndvi": 0.4, "historical_avg": 0.55}

    clean_history = calculate_composite_score(weather, ndvi, history_penalty=0)
    bad_history = calculate_composite_score(weather, ndvi, history_penalty=80)

    assert clean_history["composite_score"] > bad_history["composite_score"]


def test_composite_weights_sum_correctly():
    """0.4 weather + 0.4 ndvi + 0.2 history must produce expected composite."""
    weather = {"temperature": 35, "humidity": 25, "rain_1h": 0}
    ndvi = {"current_ndvi": 0.3, "historical_avg": 0.5}

    result = calculate_composite_score(weather, ndvi)

    expected = int(
        result["weather_score"] * 0.4
        + result["ndvi_score"] * 0.4
        + result["history_score"] * 0.2
    )
    assert result["composite_score"] == expected
