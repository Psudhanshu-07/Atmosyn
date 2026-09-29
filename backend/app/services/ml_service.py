"""ML inference service: model registry, loading, prediction, SHAP.

The active model is resolved from the model registry (DB) — the version whose
status is ACTIVE — and loaded from MODEL_PATH. If no trained model exists the
service degrades safely to a documented transparent heuristic (Safety §18:
fail safe, never fabricate an official-quality forecast).

All scoring paths produce: expected_error, bust_probability, confidence,
risk_level plus per-feature contributions for the explanation API (FR-06/07,
FR-13/21/22).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np

from app.core.constants import FEATURE_COLUMNS
from app.core.database import SessionLocal
from app.core.models import ModelVersion
from app.services.error_engine import confidence_from_probability, risk_level_from_probability


class PredictionResult(dict):
    """dict with attribute access convenience."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:  # pragma: no cover
            raise AttributeError(item) from exc


_MODEL_CACHE: Dict[str, Any] = {"bundle": None, "version": None, "explainer": None}


def get_active_model_version(db) -> Optional[ModelVersion]:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.status == "ACTIVE")
        .order_by(ModelVersion.created_at.desc())
        .first()
    )


def load_bundle(db=None) -> Optional[dict]:
    """Load the active model bundle (cached). Returns None if unavailable."""
    if db is None:
        db = SessionLocal()
        try:
            return load_bundle(db)
        finally:
            db.close()

    mv = get_active_model_version(db)
    if mv is None:
        return None
    if _MODEL_CACHE["version"] == mv.model_version and _MODEL_CACHE["bundle"]:
        return _MODEL_CACHE["bundle"]

    path = mv.model_path or os.path.join(
        _default_model_dir(), f"{mv.model_version}.joblib"
    )
    if not os.path.exists(path):
        return None

    # Integrity verification before load (Security §23)
    checksum = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    if mv.checksum and checksum != mv.checksum:
        raise RuntimeError(
            f"Model checksum mismatch for {mv.model_version}: "
            f"expected {mv.checksum}, got {checksum}"
        )

    bundle = joblib.load(path)
    _MODEL_CACHE["bundle"] = bundle
    _MODEL_CACHE["version"] = mv.model_version
    return bundle


def _default_model_dir() -> str:
    from app.core.config import settings

    return settings.model_path


def _features_array(features: Dict[str, float]) -> np.ndarray:
    return np.array([[float(features.get(c, 0.0)) for c in FEATURE_COLUMNS]])


def _heuristic_predict(features: Dict[str, float]) -> PredictionResult:
    """Transparent fallback when no trained model is available.

    Documented logistic-style combination of the dominant documented drivers:
    lead day, historical error, run change, ensemble spread (PRD FR-13 list).
    """
    lead = features.get("lead_day", 1)
    hist_mae = features.get("historical_mae", 0.0)
    hist_bust = features.get("historical_bust_rate", 0.0)
    run_change = features.get("forecast_run_change", 0.0)
    spread = features.get("ensemble_spread", 0.0)
    forecast_value = features.get("forecast_value", 0.0)
    variable = features.get("variable", "rainfall")

    lead_term = (lead - 1) / 9.0
    if variable == "rainfall":
        err_scale = 10.0 + 0.5 * forecast_value
    else:
        err_scale = 2.0

    hist_term = min(1.0, hist_mae / max(err_scale, 1e-6))
    instability = min(
        1.0, 0.6 * min(1.0, run_change / 0.5) + 0.4 * min(1.0, spread / max(err_scale, 1e-6))
    )
    z = (
        -1.9
        + 2.6 * lead_term
        + 1.4 * hist_term
        + 1.2 * hist_bust
        + 1.1 * instability
    )
    p = 1.0 / (1.0 + math.exp(-z))
    expected_error = err_scale * (0.15 + 0.10 * lead) * (0.5 + p)

    contributions = [
        ("lead_day", lead, 2.6 * lead_term),
        ("historical_mae", hist_mae, 1.4 * hist_term),
        ("historical_bust_rate", hist_bust, 1.2 * hist_bust),
        ("forecast_run_change", run_change, 0.66 * min(1.0, run_change / 0.5)),
        ("ensemble_spread", spread, 0.44 * min(1.0, spread / max(err_scale, 1e-6))),
    ]
    return PredictionResult(
        expected_error=round(expected_error, 2),
        bust_probability=round(p, 4),
        contributions=contributions,
        model_version="heuristic_fallback",
    )


def predict(features: Dict[str, float]) -> PredictionResult:
    """Score one feature vector with the active model (or safe fallback)."""
    bundle = load_bundle()
    if bundle is None:
        return _heuristic_predict(features)

    model = bundle["bust_model"]
    reg = bundle["error_model"]
    calibrator = bundle.get("calibrator")

    x = _features_array(features)
    raw_p = float(model.predict_proba(x)[0, 1])
    if calibrator is not None:
        p = float(np.clip(calibrator.predict([raw_p])[0], 0.0, 1.0))
    else:
        p = raw_p

    expected_error = float(reg.predict(x)[0])
    expected_error = max(0.0, expected_error)

    # SHAP contributions (TreeExplainer, cached; fast for XGBoost). Falls
    # back to zero contributions if SHAP is unavailable in the environment.
    contributions: List[Tuple[str, float, float]] = []
    try:
        import shap

        if _MODEL_CACHE.get("explainer") is None:
            _MODEL_CACHE["explainer"] = shap.TreeExplainer(model)
        explainer = _MODEL_CACHE["explainer"]
        sv = explainer.shap_values(x)
        if isinstance(sv, list):
            vals = sv[1][0] if len(sv) > 1 else sv[0][0]
        elif hasattr(sv, "values"):
            exp_vals = sv.values
            if getattr(exp_vals, "ndim", 0) == 3:
                vals = exp_vals[0, :, 1]
            elif getattr(exp_vals, "ndim", 0) == 2:
                vals = exp_vals[0]
            else:
                vals = exp_vals
        elif isinstance(sv, np.ndarray):
            if sv.ndim == 3:
                vals = sv[0, :, 1]
            elif sv.ndim == 2:
                vals = sv[0]
            else:
                vals = sv
        else:
            vals = sv[0]
        vals = np.asarray(vals).ravel()
        n_feat = min(len(FEATURE_COLUMNS), len(vals))
        contributions = [
            (FEATURE_COLUMNS[i], float(features.get(FEATURE_COLUMNS[i], 0.0)), float(vals[i]))
            for i in range(n_feat)
        ]
    except Exception:  # pragma: no cover - SHAP optional at inference
        contributions = [
            (c, float(features.get(c, 0.0)), 0.0) for c in FEATURE_COLUMNS
        ]

    return PredictionResult(
        expected_error=round(expected_error, 2),
        bust_probability=round(min(1.0, max(0.0, p)), 4),
        contributions= contributions,
        model_version=bundle.get("model_version", "unknown"),
    )


def build_explanation(
    contributions: List[Tuple[str, float, float]],
    bust_probability: float,
    variable: str,
    lead_day: int,
    region_name: str,
) -> Tuple[List[dict], str]:
    """Top factors + human-readable summary from actual model outputs only.

    (Security §35: explanation generated ONLY from structured model outputs;
    the engine never invents meteorological causes.)
    """
    ordered = sorted(contributions, key=lambda c: abs(c[2]), reverse=True)
    positive = [c for c in ordered if c[2] > 0][:4]

    LABELS = {
        "lead_day": "Long forecast lead time",
        "forecast_value": "Current forecast magnitude",
        "historical_mae": "High historical forecast error for this region",
        "historical_rmse": "High historical RMSE for this region",
        "historical_bust_rate": "Frequent historical busts in this region",
        "forecast_run_change": "Large change from the previous forecast run",
        "ensemble_spread": "High ensemble spread (member disagreement)",
        "pressure": "Unusual pressure pattern",
        "temperature": "Unusual temperature pattern",
        "humidity": "High humidity variability",
        "wind_speed": "Strong winds / rapid wind changes",
        "month": "Seasonal factor",
        "season_monsoon": "Monsoon-season variability",
        "season_post_monsoon": "Post-monsoon variability",
        "season_winter": "Winter regime",
        "season_pre_monsoon": "Pre-monsoon regime",
        "region_avg_error": "Region-specific historical instability",
    }

    explanation: List[dict] = []
    for feat, value, shap_val in positive:
        magnitude = abs(shap_val)
        impact = "HIGH" if magnitude >= 0.25 else "MEDIUM" if magnitude >= 0.10 else "LOW"
        explanation.append(
            {
                "feature": feat,
                "label": LABELS.get(feat, feat),
                "value": round(float(value), 3),
                "impact": impact,
                "shap_value": round(magnitude, 4),
                "direction": "increases bust risk",
            }
        )

    if bust_probability >= 0.6:
        summary = (
            f"Confidence is LOW for {region_name} {variable} at Day {lead_day}. "
            + "The model estimates a "
            f"{bust_probability:.0%} probability of a significant forecast error, driven by: "
            + "; ".join(f["label"].lower() for f in explanation[:3])
            + "."
        )
    elif bust_probability >= 0.4:
        summary = (
            f"Confidence is MODERATE for {region_name} {variable} at Day {lead_day} "
            f"(bust probability {bust_probability:.0%}). "
            + "Main considerations: "
            + "; ".join(f["label"].lower() for f in explanation[:2])
            + "."
        )
    else:
        summary = (
            f"Confidence is HIGH for {region_name} {variable} at Day {lead_day} "
            f"(bust probability {bust_probability:.0%}). Historical behaviour and "
            "current forecast stability support the current forecast."
        )

    return explanation, summary


def score_region_day(
    features: Dict[str, float],
    variable: str,
    lead_day: int,
    region_name: str,
) -> PredictionResult:
    """Full reliability score: probability -> calibration-aware confidence."""
    result = predict(features)
    p = result["bust_probability"]
    result["confidence_score"] = round(confidence_from_probability(p), 4)
    result["risk_level"] = risk_level_from_probability(p)
    explanation, summary = build_explanation(
        result["contributions"], p, variable, lead_day, region_name
    )
    result["explanation"] = explanation
    result["summary"] = summary
    return result
