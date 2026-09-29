"""Error calculation, bust labelling, risk mapping and confidence.

Pure functions only (FR-03, FR-04, FR-08, FR-13; Testing TV-05/TV-06/TV-12).
These encode the documented prototype methodology:

    error           = |forecast - observed|
    signed/bias     = forecast - observed
    bust            = error > threshold  (strictly greater)
    confidence      = 1 - calibrated bust probability
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from app.core.constants import (
    BUST_PROBABILITY_BANDS,
    CONFIDENCE_LABEL_THRESHOLDS,
    DEFAULT_BUST_THRESHOLDS,
    IMD_RAINFALL_CLASSES,
    RAINFALL_BUST_FLOOR_MM,
    RAINFALL_BUST_THRESHOLD_MM,
    RISK_BANDS,
)

EPSILON = 1e-9


# ---------------------------------------------------------------------------
# FR-03 — Forecast error calculation
# ---------------------------------------------------------------------------
def absolute_error(forecast: float, observed: float) -> float:
    return abs(forecast - observed)


def signed_error(forecast: float, observed: float) -> float:
    """Positive = forecast over-predicted (wet/ warm bias)."""
    return forecast - observed


def percent_error(forecast: float, observed: float) -> Optional[float]:
    if abs(observed) < EPSILON:
        return None
    return (forecast - observed) / observed


def mae(errors: Sequence[float]) -> float:
    if not errors:
        return 0.0
    return sum(abs(e) for e in errors) / len(errors)


def rmse(errors: Sequence[float]) -> float:
    if not errors:
        return 0.0
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def bias(errors: Sequence[float]) -> float:
    if not errors:
        return 0.0
    return sum(errors) / len(errors)


# ---------------------------------------------------------------------------
# FR-04 — Bust identification (deterministic, documented threshold)
# ---------------------------------------------------------------------------
def bust_label(
    error: float,
    threshold: float,
    variable: Optional[str] = None,
) -> bool:
    """Deterministic bust labelling (TV-06: same input -> same label).

    `threshold` wins if provided; otherwise the per-variable default is used.
    """
    if threshold is None:
        threshold = DEFAULT_BUST_THRESHOLDS.get(variable or "", 0.0)
    return bool(error > threshold)


def rainfall_bust_label(
    forecast: float,
    observed: float,
    floor_mm: float = RAINFALL_BUST_FLOOR_MM,
    threshold_mm: float = RAINFALL_BUST_THRESHOLD_MM,
) -> bool:
    """Doc-aligned rainfall bust definition (master prompts, Prompt 3).

    bust = abs_error > max(25 mm, 1.0 * |obs| + threshold)
    OR the observed vs forecast IMD rainfall class differs by >= 2.
    """
    error = abs(forecast - observed)
    magnitude_bust = error > max(floor_mm, abs(observed) + threshold_mm)
    return bool(magnitude_bust or _rain_class_shift(forecast, observed) >= 2)


def _rain_class(value: float) -> int:
    for idx, (lo, hi) in enumerate(IMD_RAINFALL_CLASSES):
        if lo <= value < hi:
            return idx
    return len(IMD_RAINFALL_CLASSES) - 1


def _rain_class_shift(forecast: float, observed: float) -> int:
    return abs(_rain_class(forecast) - _rain_class(observed))


def adaptive_threshold(errors: Sequence[float], quantile: float = 0.75) -> float:
    """Data-driven threshold from the historical error distribution.

    Used as an alternative to fixed meteorological thresholds.
    """
    if not errors:
        return 0.0
    ordered = sorted(errors)
    pos = quantile * (len(ordered) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))


def historical_bust_rate(busts: Sequence[bool]) -> float:
    if not busts:
        return 0.0
    return sum(1 for b in busts if b) / len(busts)


# ---------------------------------------------------------------------------
# FR-08 / FR-13 — Confidence + risk
# ---------------------------------------------------------------------------
def confidence_from_probability(bust_probability: float) -> float:
    """Confidence = 1 - bust probability, clamped to [0, 1]."""
    return min(1.0, max(0.0, 1.0 - bust_probability))


def risk_level_from_probability(p: float) -> str:
    """Map calibrated bust probability to a risk band (Safety §4)."""
    for band in RISK_BANDS:
        if p < band["max"]:
            return band["level"]
    return RISK_BANDS[-1]["level"]


def bust_concern_band(p: float) -> str:
    """Doc-aligned concern band for a bust probability (Prompt 6).

    <30%% low, 30-60%% moderate (inclusive), >60%% high.
    """
    if p > BUST_PROBABILITY_BANDS[1]["max"]:
        return "HIGH"
    if p >= BUST_PROBABILITY_BANDS[0]["max"]:
        return "MODERATE"
    return "LOW"


def confidence_label(score_0_100: float) -> str:
    """Doc-aligned confidence label (Prompt 6): High >=70, Medium 40-69, Low <40."""
    if score_0_100 >= CONFIDENCE_LABEL_THRESHOLDS["HIGH"]:
        return "HIGH"
    if score_0_100 >= CONFIDENCE_LABEL_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Feature engineering helpers (FR-05) — pure functions over sequences
# ---------------------------------------------------------------------------
def season_of(month: int) -> str:
    if month in (6, 7, 8, 9):
        return "monsoon"
    if month in (10, 11, 12):
        return "post_monsoon"
    if month in (1, 2):
        return "winter"
    return "pre_monsoon"


def forecast_run_change(current: Optional[float], previous: Optional[float]) -> float:
    """Relative change between successive forecast runs (FR-17).

    Returns 0.0 when either run is missing (safe, documented fallback).
    """
    if current is None or previous is None or abs(previous) < EPSILON:
        return 0.0
    return abs(current - previous) / abs(previous)


def summarize_errors(errors: Sequence[float], busts: Sequence[bool]) -> Dict[str, float]:
    return {
        "mae": round(mae(errors), 4),
        "rmse": round(rmse(errors), 4),
        "bias": round(bias(errors), 4),
        "bust_rate": round(historical_bust_rate(busts), 4),
        "sample_count": len(errors),
    }
