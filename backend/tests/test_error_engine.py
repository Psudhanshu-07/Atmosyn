"""TV-05/TV-06/TV-12: error calculation, bust labels, confidence & risk."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest

from app.services.error_engine import (
    absolute_error,
    adaptive_threshold,
    bias,
    bust_label,
    confidence_from_probability,
    forecast_run_change,
    historical_bust_rate,
    mae,
    percent_error,
    risk_level_from_probability,
    rmse,
    season_of,
    signed_error,
)


class TestErrorMetrics:
    def test_absolute_error_prd_example(self):
        # PRD FR-03: forecast 100 mm, observed 40 mm -> 60 mm
        assert absolute_error(100.0, 40.0) == pytest.approx(60.0)

    def test_absolute_error_symmetric(self):
        assert absolute_error(30.0, 80.0) == pytest.approx(
            absolute_error(80.0, 30.0)
        )

    def test_signed_error_direction(self):
        assert signed_error(100.0, 40.0) == pytest.approx(60.0)   # over-forecast
        assert signed_error(40.0, 100.0) == pytest.approx(-60.0)  # under-forecast

    def test_percent_error(self):
        assert percent_error(110.0, 100.0) == pytest.approx(0.10)
        assert percent_error(50.0, 0.0) is None  # undefined for zero obs

    def test_mae_rmse_bias(self):
        errs = [10.0, -20.0, 30.0]
        assert mae(errs) == pytest.approx(20.0)
        assert rmse(errs) == pytest.approx(((100 + 400 + 900) / 3) ** 0.5)
        assert bias(errs) == pytest.approx(20.0 / 3.0)

    def test_empty_series_returns_zero(self):
        assert mae([]) == 0.0
        assert rmse([]) == 0.0
        assert bias([]) == 0.0


class TestBustLabelling:
    def test_prd_architecture_example(self):
        # Arctitcture.txt §4: error 85, threshold 50 -> bust
        assert bust_label(85.0, 50.0) is True

    def test_boundary_is_not_bust(self):
        # strictly greater: error == threshold -> no bust
        assert bust_label(50.0, 50.0) is False
        assert bust_label(50.01, 50.0) is True

    def test_deterministic(self):
        # TV-06: identical input -> identical label
        assert bust_label(51.0, 50.0) == bust_label(51.0, 50.0)

    def test_variable_default_thresholds(self):
        assert bust_label(51.0, None, variable="rainfall") is True
        assert bust_label(49.0, None, variable="rainfall") is False
        assert bust_label(6.0, None, variable="temperature") is True

    def test_adaptive_threshold_quantile(self):
        errs = list(range(1, 101))  # 1..100
        assert adaptive_threshold(errs, 0.75) == pytest.approx(75.25)

    def test_bust_rate(self):
        assert historical_bust_rate([True, False, True, True]) == pytest.approx(0.75)
        assert historical_bust_rate([]) == 0.0


class TestConfidenceAndRisk:
    def test_confidence_formula(self):
        # FR-08: Confidence = 1 - bust probability
        assert confidence_from_probability(0.35) == pytest.approx(0.65)
        assert confidence_from_probability(0.0) == pytest.approx(1.0)
        assert confidence_from_probability(1.0) == pytest.approx(0.0)

    def test_confidence_monotonic(self):
        # TV-12: higher bust probability -> lower confidence
        assert confidence_from_probability(0.9) < confidence_from_probability(0.1)

    def test_confidence_clamped(self):
        assert 0.0 <= confidence_from_probability(1.5) <= 1.0

    def test_risk_bands(self):
        # Safety §4 prototype thresholds
        assert risk_level_from_probability(0.10) == "VERY_LOW"
        assert risk_level_from_probability(0.30) == "LOW"
        assert risk_level_from_probability(0.50) == "MODERATE"
        assert risk_level_from_probability(0.78) == "HIGH"
        assert risk_level_from_probability(0.90) == "VERY_HIGH"
        assert risk_level_from_probability(1.0) == "VERY_HIGH"


class TestFeatureHelpers:
    def test_seasons(self):
        assert season_of(7) == "monsoon"
        assert season_of(10) == "post_monsoon"
        assert season_of(1) == "winter"
        assert season_of(4) == "pre_monsoon"

    def test_forecast_run_change(self):
        assert forecast_run_change(84.0, 61.0) == pytest.approx(0.377, abs=1e-3)
        assert forecast_run_change(None, 61.0) == 0.0
        assert forecast_run_change(84.0, 0.0) == 0.0
