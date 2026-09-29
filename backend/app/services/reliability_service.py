"""Reliability engine orchestration: predict -> persist -> alert (Safety §6)."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.models import Alert, Forecast, HistoricalError, Prediction
from app.core.constants import RISK_BANDS
from app.services.alert_service import generate_alert_for_prediction
from app.services.error_engine import season_of
from app.services.ml_service import score_region_day
from app.services.regions_data import REGION_INDEX, RegionRow
from app.services.synthetic_data import region_climatology


def latest_run_id(db: Session) -> Optional[int]:
    row = db.query(Forecast.run_id).order_by(Forecast.forecast_run.desc()).first()
    return row[0] if row else None


def latest_run_time(db: Session) -> Optional[datetime]:
    """Latest usable forecast run for the reliability UI.

    Preference order:
      1. latest run that is SCORED (has predictions) AND covers the full
         Day 1-10 horizon;
      2. latest scored run of any horizon;
      3. latest raw run (nothing scored yet).

    A live GFS ingest (POST /api/v1/gfs/update) can create a newer run that is
    unscored and/or limited to Day 1-5 (NOMADS 120 h filter default); serving
    such a run would blank out Days 6-10 or 404 the confidence endpoints.
    Ad-hoc /predict/bust predictions use wall-clock timestamps that match no
    Forecast run, so the join naturally excludes them.
    """
    from app.core.constants import MAX_LEAD_DAY
    from sqlalchemy import func

    full_scored = (
        db.query(Forecast.forecast_run)
        .join(Prediction, Prediction.forecast_run == Forecast.forecast_run)
        .group_by(Forecast.forecast_run)
        .having(func.max(Forecast.lead_day) >= MAX_LEAD_DAY)
        .order_by(Forecast.forecast_run.desc())
        .first()
    )
    if full_scored and full_scored[0] is not None:
        return full_scored[0]

    scored = (
        db.query(Forecast.forecast_run)
        .join(Prediction, Prediction.forecast_run == Forecast.forecast_run)
        .order_by(Forecast.forecast_run.desc())
        .first()
    )
    if scored and scored[0] is not None:
        return scored[0]

    row = (
        db.query(Forecast.forecast_run)
        .order_by(Forecast.forecast_run.desc())
        .first()
    )
    return row[0] if row else None


def prediction_key(
    region_db_id: int, variable: str, lead_day: int, run: datetime
) -> str:
    return f"{region_db_id}|{variable}|{lead_day}|{run.isoformat()}"


def _static_atmosphere(region: RegionRow, month: int) -> Dict[str, float]:
    """Climatological atmospheric predictors at forecast time (no leakage)."""
    _, temp = region_climatology(region)
    return {
        "temperature": temp,
        "humidity": 78.0 if month in (6, 7, 8, 9) else 55.0,
        "pressure": 1004.0 if month in (6, 7, 8, 9) else 1010.0,
        "wind_speed": 7.5 if month in (6, 7, 8, 9) else 4.5,
    }


def forecast_instability(f: Forecast, db: Session) -> Tuple[float, float]:
    """Run-to-run change + ensemble spread for one forecast row (FR-17/18).

    Compares with the most recent previous run for the same region/variable/
    valid_time; falls back to documented neutral values when unavailable.
    """
    prev = (
        db.query(Forecast)
        .filter(
            Forecast.region_id == f.region_id,
            Forecast.variable == f.variable,
            Forecast.valid_time == f.valid_time,
            Forecast.forecast_run < f.forecast_run,
        )
        .order_by(Forecast.forecast_run.desc())
        .first()
    )
    if prev is None:
        return 0.15, 3.0

    denom = max(abs(prev.value), 1e-6)
    change = min(1.5, abs(f.value - prev.value) / denom)
    spread = abs(f.value - prev.value) * 0.8 + 1.0
    return round(change, 4), round(spread, 2)


def _historical_stats(
    db: Session, run_time: datetime
) -> Tuple[Dict[tuple, Dict[str, float]], Dict[int, float]]:
    """Per-(region, variable, lead_day) error stats from past valid times only."""
    rows = (
        db.query(
            HistoricalError.region_id,
            HistoricalError.variable,
            HistoricalError.lead_day,
            HistoricalError.absolute_error,
            HistoricalError.bust,
        )
        .filter(HistoricalError.valid_time < run_time)
        .all()
    )

    stats: Dict[tuple, Dict[str, float]] = {}
    region_errs: Dict[int, List[float]] = {}

    for rid, var, lead, err, bust in rows:
        s = stats.setdefault(
            (rid, var, lead),
            {"n": 0, "sum": 0.0, "sumsq": 0.0, "busts": 0},
        )
        s["n"] += 1
        s["sum"] += err
        s["sumsq"] += err * err
        s["busts"] += 1 if bust else 0
        region_errs.setdefault(rid, []).append(err)

    derived: Dict[tuple, Dict[str, float]] = {}
    for key, s in stats.items():
        n = max(int(s["n"]), 1)
        derived[key] = {
            "mae": s["sum"] / n,
            "rmse": math.sqrt(s["sumsq"] / n),
            "bust_rate": s["busts"] / n,
            "count": s["n"],
        }

    region_avg = {
        rid: sum(errs) / len(errs) for rid, errs in region_errs.items() if errs
    }
    return derived, region_avg


def rows_for_current_run(db: Session, run_id: int, run_time: datetime) -> List[dict]:
    """Build scoring rows (feature vectors) for the latest forecast run.

    Anti-leakage (Testing §4): uses only the forecast issued at run_time plus
    historical statistics computed from valid times strictly before run_time.
    """
    stats, region_avg = _historical_stats(db, run_time)
    forecasts = db.query(Forecast).filter(Forecast.run_id == run_id).all()

    rows: List[dict] = []
    for f in forecasts:
        region = REGION_INDEX.get(f.region.region_id)
        if region is None:  # pragma: no cover
            continue

        s = stats.get((f.region_id, f.variable, f.lead_day), {})
        run_change, spread = forecast_instability(f, db)
        month = run_time.month
        season = season_of(month)

        features = {
            "lead_day": f.lead_day,
            "forecast_value": f.value,
            "historical_mae": round(s.get("mae", 0.0), 4),
            "historical_rmse": round(s.get("rmse", 0.0), 4),
            "historical_bust_rate": round(s.get("bust_rate", 0.0), 4),
            "forecast_run_change": run_change,
            "ensemble_spread": spread,
            **_static_atmosphere(region, month),
            "month": month,
            "season_monsoon": 1 if season == "monsoon" else 0,
            "season_post_monsoon": 1 if season == "post_monsoon" else 0,
            "season_winter": 1 if season == "winter" else 0,
            "season_pre_monsoon": 1 if season == "pre_monsoon" else 0,
            "region_avg_error": round(region_avg.get(f.region_id, 0.0), 4),
        }
        rows.append(
            {
                "region_db_id": f.region_id,
                "region_id": f.region.region_id,
                "region_name": f.region.region_name,
                "variable": f.variable,
                "lead_day": f.lead_day,
                "forecast_value": f.value,
                "valid_time": f.valid_time,
                "features": features,
            }
        )
    return rows


def persist_predictions_for_run(
    db: Session,
    run_id: int,
    run_time: datetime,
    scoring_rows: List[dict],
) -> Dict[str, int]:
    """Score every (region, variable, lead_day) row; store predictions + alerts."""
    counts = {"created": 0, "updated": 0, "alerts": 0}
    now = datetime.now(timezone.utc)

    for row in scoring_rows:
        key = prediction_key(
            row["region_db_id"], row["variable"], row["lead_day"], run_time
        )
        existing = (
            db.query(Prediction).filter(Prediction.prediction_key == key).first()
        )

        result = score_region_day(
            features=row["features"],
            variable=row["variable"],
            lead_day=row["lead_day"],
            region_name=row["region_name"],
        )

        values = dict(
            forecast_value=row["forecast_value"],
            expected_error=result["expected_error"],
            bust_probability=result["bust_probability"],
            confidence_score=result["confidence_score"],
            risk_level=result["risk_level"],
            model_version=result["model_version"],
            features_json=json.dumps(row["features"], default=str)[:3900],
        )

        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            pred = existing
            counts["updated"] += 1
        else:
            seq = db.query(Prediction).count() + 1
            pred = Prediction(
                prediction_id=f"PRED-{seq:05d}",
                prediction_key=key,
                region_id=row["region_db_id"],
                variable=row["variable"],
                lead_day=row["lead_day"],
                forecast_run=run_time,
                valid_time=row["valid_time"],
                predicted_at=now,
                **values,
            )
            db.add(pred)
            counts["created"] += 1

        db.flush()

        if result["bust_probability"] >= 0.6:
            alert = generate_alert_for_prediction(db, pred, result["summary"])
            if alert is not None:
                counts["alerts"] += 1

    db.commit()
    return counts
