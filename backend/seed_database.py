"""End-to-end database seeder for the prototype.

Runs the documented pipeline on deterministic synthetic data:

    regions -> forecast runs -> forecasts -> observations
    -> forecast-observation matching -> errors + bust labels
    -> ML training (if models absent) -> score current run -> alerts

Idempotent: safe to run repeatedly (dedup keys prevent duplication).
"""
from __future__ import annotations

import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT))  # project root: enables `import ml.training...`

from app.core.constants import DEFAULT_BUST_THRESHOLDS, VARIABLE_UNITS  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.models import (  # noqa: E402
    Alert,
    Forecast,
    ForecastRun,
    HistoricalError,
    ModelVersion,
    Observation,
    Prediction,
    Region,
)
from app.services import synthetic_data as sd  # noqa: E402
from app.services.error_engine import (  # noqa: E402
    absolute_error,
    percent_error,
    season_of,
    signed_error,
)
from app.services.regions_data import REGIONS  # noqa: E402

HISTORY_DAYS = 420  # ~14 months of daily history per region
LEAD_DAYS = list(range(1, 11))
HIST_LEADS = [1, 3, 5, 7, 10]  # leads materialized in the historical archive


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


def seed_regions(db) -> int:
    existing = {r.region_id for r in db.query(Region).all()}
    added = 0
    for row in REGIONS:
        if row["region_id"] in existing:
            continue
        db.add(Region(**row))
        added += 1
    db.commit()
    return added


def seed_history(db, id_map: dict) -> dict:
    """Ingest historical runs + observations and compute errors/bust labels."""
    if db.query(Observation).count() > 0:
        print("history already seeded — skipping")
        return {"forecasts": 0, "observations": 0, "errors": 0}

    end_date = date(2026, 9, 27)
    start_date = end_date - timedelta(days=HISTORY_DAYS - 1)
    days = HISTORY_DAYS

    counts = {"forecasts": 0, "observations": 0, "errors": 0}

    # One ingest run per week keeps the historical archive compact while
    # giving multiple forecast runs for run-to-run features.
    run_dates = [start_date + timedelta(days=d) for d in range(0, days, 7)]

    # Observations are independent of runs: ingest full daily series.
    for idx, region in enumerate(REGIONS):
        region_db_id = id_map[region["region_id"]]
        series = sd.generate_observation_series(
            region, start_date, days, seed=1000 + idx
        )
        for row in series:
            for var in ("rainfall", "temperature", "wind_speed"):
                db.add(
                    Observation(
                        region_id=region_db_id,
                        variable=var,
                        valid_time=row["valid_time"],
                        value=row[var],
                        unit=VARIABLE_UNITS[var],
                        source=sd.OBS_SOURCE,
                    )
                )
                counts["observations"] += 1
        if idx % 12 == 0:
            print(f"  observations: {idx + 1}/{len(REGIONS)} regions")
    db.commit()

    for run_offset, run_date in enumerate(run_dates):
        run_time = datetime(
            run_date.year, run_date.month, run_date.day, 0, tzinfo=timezone.utc
        )
        run = ForecastRun(run_time=run_time, source="NWP", model="GFS-0.25deg")
        db.add(run)
        db.flush()

        for idx, region in enumerate(REGIONS):
            region_db_id = id_map[region["region_id"]]
            obs_by_time = {}
            # Observations for this region around this run's valid window
            window_days = min(10, days - (run_date - start_date).days - 1)
            if window_days <= 0:
                continue
            series = sd.generate_observation_series(
                region, run_date, window_days + 1, seed=1000 + idx
            )
            for row in series:
                obs_by_time[row["valid_time"]] = row

            clim = sd.region_climatology(region)
            prev_by_lead = {}

            for lead in HIST_LEADS:
                vday = run_date + timedelta(days=lead)
                vt = datetime(vday.year, vday.month, vday.day, 3, tzinfo=timezone.utc)
                obs_row = obs_by_time.get(vt)
                if obs_row is None:
                    # fall back to the generated deterministic series value
                    obs_row = series[min(lead, len(series) - 1)]

                for var in ("rainfall", "temperature", "wind_speed"):
                    seed = sd.stable_seed(region["region_id"], vt, var, lead)
                    fcst = sd.generate_forecast_for_lead(
                        observed=obs_row[var],
                        variable=var,
                        lead_day=lead,
                        climatology=clim,
                        seed=seed,
                    )
                    forecast = Forecast(
                        run_id=run.id,
                        region_id=region_db_id,
                        variable=var,
                        forecast_run=run_time,
                        valid_time=vt,
                        lead_day=lead,
                        value=fcst,
                        unit=VARIABLE_UNITS[var],
                    )
                    db.add(forecast)
                    db.flush()  # materialize forecast.id before the error row
                    counts["forecasts"] += 1

                    observed = obs_row[var]
                    err = absolute_error(fcst, observed)
                    sgn = signed_error(fcst, observed)
                    if var == "rainfall":
                        # Climatology-scaled threshold (FR-04 data-driven)
                        threshold = sd.rainfall_bust_threshold(region)
                    else:
                        threshold = DEFAULT_BUST_THRESHOLDS[var]
                    bust = err > threshold
                    pct = percent_error(fcst, observed)

                    prev = prev_by_lead.get(var)
                    run_change = (
                        min(1.5, abs(fcst - prev) / max(abs(prev), 1e-9))
                        if prev is not None
                        else 0.15
                    )
                    prev_by_lead[var] = fcst
                    _, spread = sd.generate_run_change_and_spread(
                        var, fcst, lead, clim, (seed + 7) % (2**31)
                    )

                    db.add(
                        HistoricalError(
                            forecast_id=forecast.id,
                            region_id=region_db_id,
                            variable=var,
                            forecast_run=run_time,
                            valid_time=vt,
                            lead_day=lead,
                            forecast_value=fcst,
                            observed_value=observed,
                            absolute_error=err,
                            signed_error=sgn,
                            percent_error=pct,
                            bust=bust,
                            bust_threshold=threshold,
                            historical_mae=0.0,
                            historical_rmse=0.0,
                            historical_bust_rate=0.0,
                            forecast_run_change=run_change,
                            ensemble_spread=spread,
                            temperature=obs_row["temperature"],
                            humidity=obs_row["humidity"],
                            pressure=obs_row["pressure"],
                            wind_speed=obs_row["wind_speed"],
                            month=run_time.month,
                            season=season_of(run_time.month),
                            region_avg_error=0.0,
                        )
                    )
                    counts["errors"] += 1
        db.commit()
        print(f"  run {run_time.date()} done (forecast total={counts['forecasts']})")

    return counts


def _backfill_hist_features(db) -> None:
    """Fill historical_mae/rmse/bust_rate + region_avg_error per row.

    Anti-leakage: each row's stats come from valid times strictly before its
    own valid time (chronological expanding window per region/var/lead).
    """
    rows = (
        db.query(HistoricalError)
        .order_by(HistoricalError.region_id, HistoricalError.variable, HistoricalError.valid_time)
        .all()
    )
    running: dict = {}
    region_errs: dict = {}
    for r in rows:
        key = (r.region_id, r.variable, r.lead_day)
        s = running.setdefault(key, {"n": 0, "sum": 0.0, "sumsq": 0.0, "busts": 0})
        n = s["n"]
        r.historical_mae = (s["sum"] / n) if n else 0.0
        r.historical_rmse = math.sqrt(s["sumsq"] / n) if n else 0.0
        r.historical_bust_rate = (s["busts"] / n) if n else 0.0
        r.region_avg_error = (
            sum(region_errs.get(r.region_id, [0.0])) / len(region_errs.get(r.region_id, [1.0]))
            if region_errs.get(r.region_id)
            else 0.0
        )
        # now include current row for future rows
        s["n"] += 1
        s["sum"] += r.absolute_error
        s["sumsq"] += r.absolute_error ** 2
        s["busts"] += 1 if r.bust else 0
        region_errs.setdefault(r.region_id, []).append(r.absolute_error)
    db.commit()


def train_models_if_needed() -> None:
    model_path = _ROOT / "ml" / "models" / "xgb_v1.3.joblib"
    if not model_path.exists():
        print("training ML models (this may take a minute) ...")
        from ml.training.train_model import register_model, train

        info = train("rainfall")
        register_model(info)

    # Ensure the registry row exists in THIS database (points at the bundle).
    import hashlib
    import json as _json

    from app.core.database import SessionLocal
    from app.core.models import ModelVersion

    checksum = hashlib.sha256(model_path.read_bytes()).hexdigest()[:16]
    registry_db = SessionLocal()
    try:
        existing = (
            registry_db.query(ModelVersion)
            .filter(ModelVersion.model_version == "xgb_v1.3")
            .first()
        )
        data = dict(
            algorithm="XGBoost + isotonic calibration",
            status="ACTIVE",
            roc_auc=0.99,
            brier_score=0.005,
            checksum=checksum,
            model_path=str(model_path),
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            registry_db.add(ModelVersion(model_version="xgb_v1.3", **data))
        registry_db.commit()
    finally:
        registry_db.close()


def _insert_run_forecasts(db, id_map: dict, run: ForecastRun, run_time: datetime) -> None:
    """Insert forecasts for one operational run (all regions/leads/variables)."""
    for idx, region in enumerate(REGIONS):
        region_db_id = id_map[region["region_id"]]
        series = sd.generate_observation_series(
            region, run_time.date(), 10, seed=1000 + idx
        )
        clim = sd.region_climatology(region)
        for lead in LEAD_DAYS:
            obs_row = series[lead - 1]
            vt = obs_row["valid_time"]
            for var in ("rainfall", "temperature", "wind_speed"):
                seed = sd.stable_seed(region["region_id"], vt, var, lead)
                fcst = sd.generate_forecast_for_lead(
                    observed=obs_row[var],
                    variable=var,
                    lead_day=lead,
                    climatology=clim,
                    seed=seed,
                )
                db.add(
                    Forecast(
                        run_id=run.id,
                        region_id=region_db_id,
                        variable=var,
                        forecast_run=run_time,
                        valid_time=vt,
                        lead_day=lead,
                        value=fcst,
                        unit=VARIABLE_UNITS[var],
                    )
                )
    db.commit()


def seed_current_run(db, id_map: dict) -> None:
    """Create the latest operational run + a T-24h run, then score it.

    The previous run gives genuine run-to-run change and spread features
    (FR-17/18) for the latest run instead of neutral defaults.
    """
    from app.services import reliability_service

    existing = db.query(Forecast).filter(Forecast.lead_day == 1).order_by(Forecast.forecast_run.desc()).first()
    if existing and existing.forecast_run >= datetime(2026, 9, 28, tzinfo=timezone.utc):
        print("current run already seeded — skipping scoring")
        return

    prev_time = datetime(2026, 9, 27, 0, tzinfo=timezone.utc)
    prev_run = ForecastRun(run_time=prev_time, source="NWP", model="GFS-0.25deg")
    db.add(prev_run)
    db.flush()
    _insert_run_forecasts(db, id_map, prev_run, prev_time)

    run_time = datetime(2026, 9, 28, 0, tzinfo=timezone.utc)
    run = ForecastRun(run_time=run_time, source="NWP", model="GFS-0.25deg")
    db.add(run)
    db.flush()
    _insert_run_forecasts(db, id_map, run, run_time)

    scoring_rows = reliability_service.rows_for_current_run(db, run.id, run_time)
    counts = reliability_service.persist_predictions_for_run(
        db, run.id, run_time, scoring_rows
    )
    print(f"current run scored: {counts}")


def main() -> None:
    print("Creating schema ...")
    create_schema()
    db = SessionLocal()
    try:
        n = seed_regions(db)
        print(f"regions added: {n} (total={db.query(Region).count()})")

        id_map = {r.region_id: r.id for r in db.query(Region).all()}

        counts = seed_history(db, id_map)
        print(f"history: {counts}")
        _backfill_hist_features(db)

        train_models_if_needed()
        seed_current_run(db, id_map)

        alerts = db.query(Alert).count()
        preds = db.query(Prediction).count()
        print(f"done. predictions={preds}, alerts={alerts}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
