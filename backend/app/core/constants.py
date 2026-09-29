"""Shared meteorological and reliability constants for the prototype.

All bust thresholds, risk bands and units follow the project specification
documents (PRD.txt / Safety.txt). Values are configurable at runtime via
settings, but these defaults encode the documented prototype behaviour.
"""
from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# Variables, units and physical ranges (Weather Data & Grounding spec, §6)
# ---------------------------------------------------------------------------
VARIABLE_UNITS: Dict[str, str] = {
    "rainfall": "mm",
    "temperature": "degC",
    "wind_speed": "m/s",
    "pressure": "hPa",
    "humidity": "percent",
}

# (min, max) physically plausible values; used for validation + synthetic data
VARIABLE_RANGES: Dict[str, tuple] = {
    "rainfall": (0.0, 500.0),
    "temperature": (-10.0, 55.0),
    "wind_speed": (0.0, 60.0),
    "pressure": (950.0, 1050.0),
    "humidity": (0.0, 100.0),
}

# Default bust thresholds: |forecast - observed| beyond this = bust.
# Per-variable, aligned with "Forecast: 100 mm vs Observed: 40 mm" examples.
DEFAULT_BUST_THRESHOLDS: Dict[str, float] = {
    "rainfall": 50.0,     # PRD example: threshold 50 mm -> bust
    "temperature": 5.0,
    "wind_speed": 10.0,
    "pressure": 10.0,
    "humidity": 30.0,
}

MIN_LEAD_DAY = 1
MAX_LEAD_DAY = 10

# ---------------------------------------------------------------------------
# Risk engine (Arctitcture.txt §14 / Safety.txt §4)
# ---------------------------------------------------------------------------
RISK_BANDS: List[dict] = [
    {"max": 0.20, "level": "VERY_LOW"},
    {"max": 0.40, "level": "LOW"},
    {"max": 0.60, "level": "MODERATE"},
    {"max": 0.80, "level": "HIGH"},
    {"max": 1.01, "level": "VERY_HIGH"},
]

RISK_LEVELS = [b["level"] for b in RISK_BANDS]

# Maps risk level -> UI colour token (shared with frontend legend semantics)
RISK_COLORS: Dict[str, str] = {
    "VERY_LOW": "#16a34a",
    "LOW": "#84cc16",
    "MODERATE": "#f59e0b",
    "HIGH": "#f97316",
    "VERY_HIGH": "#dc2626",
    "UNAVAILABLE": "#6b7280",
}

# ---------------------------------------------------------------------------
# ML feature set (AILLM Specification, "Suggested ML Features")
# ---------------------------------------------------------------------------
FEATURE_COLUMNS: List[str] = [
    "lead_day",
    "forecast_value",
    "historical_mae",
    "historical_rmse",
    "historical_bust_rate",
    "forecast_run_change",
    "ensemble_spread",
    "pressure",
    "temperature",
    "humidity",
    "wind_speed",
    "month",
    "season_monsoon",
    "season_post_monsoon",
    "season_winter",
    "season_pre_monsoon",
    "region_avg_error",
]

# Quantile of historical errors used as data-driven bust threshold fallback
ADAPTIVE_BUST_QUANTILE = 0.75

# ---------------------------------------------------------------------------
# Doc-aligned bands + labels (forecast_reliability_master_prompts.txt,
# Prompt 6): confidence labels on the 0-100 score and bust-probability
# concern bands shown in the UI legend.
# ---------------------------------------------------------------------------
CONFIDENCE_LABEL_THRESHOLDS: Dict[str, float] = {
    "HIGH": 70.0,    # score >= 70
    "MEDIUM": 40.0,  # 40 <= score < 70
    # LOW otherwise
}

# (upper-exclusive bound, label) for bust probability concern bands
BUST_PROBABILITY_BANDS: List[dict] = [
    {"max": 0.30, "label": "LOW"},       # low concern
    {"max": 0.60, "label": "MODERATE"},  # moderate concern
    {"max": 1.01, "label": "HIGH"},      # high concern
]

# IMD daily rainfall classification (mm/day), used for class-shift busts:
# bust when the observed and forecast classes differ by >= 2.
#   0: <2.5 | 1: 2.5-15.5 | 2: 15.6-64.4 | 3: 64.5-115.5
#   4: 115.6-204.4 | 5: >204.4
IMD_RAINFALL_CLASSES: List[tuple] = [
    (0.0, 2.5),
    (2.5, 15.6),
    (15.6, 64.5),
    (64.5, 115.6),
    (115.6, 204.5),
    (204.5, float("inf")),
]

# Rainfall bust definition (Prompt 3): abs_error > max(25mm, 1.0*|obs|+thr)
# with the 25 mm floor and the additive threshold configurable.
RAINFALL_BUST_FLOOR_MM = 25.0
RAINFALL_BUST_THRESHOLD_MM = 25.0

# India bounding box (Prompt 1) used by range validation
INDIA_BBOX = {"lat_min": 6.0, "lat_max": 38.0, "lon_min": 68.0, "lon_max": 98.0}
