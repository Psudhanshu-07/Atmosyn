"""GET /dashboard/kpis and GET /data-quality (UIUX §9; API contract §20).

Also GET /quality — doc-aligned (master prompts Prompt 8) rules-based data
quality report persisted to reports/data_quality.json.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.models import Alert, Forecast, HistoricalError, Observation, Prediction, Region
from app.core.schemas import DataQualityResponse, DataQualitySource, DashboardKpis
from app.services import reliability_service
from app.services.data_quality import run_all as run_quality_checks

router = APIRouter()


def _utcnow_naive() -> datetime:
    """SQLite stores/returns naive datetimes; compare in the same convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/dashboard/kpis", response_model=DashboardKpis)
def dashboard_kpis(
    lead_day: int = Query(1, ge=1, le=10),
    variable: str = Query("rainfall"),
    db: Session = Depends(get_db),
):
    run_time = reliability_service.latest_run_time(db)
    if run_time is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_FORECAST_DATA", "message": "No forecast data available"},
        )

    regions = db.query(Region).count()
    preds = (
        db.query(Prediction)
        .filter(
            Prediction.forecast_run == run_time,
            Prediction.variable == variable.lower(),
            Prediction.lead_day == lead_day,
        )
        .all()
    )
    high_risk = sum(1 for p in preds if p.risk_level in ("HIGH", "VERY_HIGH"))
    avg_conf = (
        sum(p.confidence_score for p in preds) / len(preds) if preds else 0.0
    )
    worst_day_pred = (
        db.query(Prediction)
        .filter(
            Prediction.forecast_run == run_time,
            Prediction.variable == variable.lower(),
        )
        .order_by(Prediction.bust_probability.desc())
        .first()
    )
    highest_risk_lead = worst_day_pred.lead_day if worst_day_pred else lead_day

    obs_count = db.query(Observation).count()
    err_count = db.query(HistoricalError).count()
    total_forecasts = db.query(Forecast).count()
    quality = min(1.0, (obs_count + err_count) / (2 * max(total_forecasts, 1))) if total_forecasts else 0.0

    age_hours = (_utcnow_naive() - run_time.replace(tzinfo=None)).total_seconds() / 3600.0
    data_status = "CURRENT" if age_hours <= settings.forecast_freshness_hours else "OUTDATED"

    return DashboardKpis(
        regions_monitored=regions,
        high_risk_regions=high_risk,
        avg_confidence=round(avg_conf, 4),
        highest_risk_lead_day=highest_risk_lead,
        data_quality=round(quality, 4),
        forecast_run=run_time,
        data_status=data_status,
    )


@router.get("/data-quality", response_model=DataQualityResponse)
def data_quality(db: Session = Depends(get_db)):
    run_time = reliability_service.latest_run_time(db)
    obs_count = db.query(Observation).count()
    err_count = db.query(HistoricalError).count()
    forecast_count = db.query(Forecast).count()
    prediction_count = db.query(Prediction).count()

    sources = [
        DataQualitySource(
            source="NWP",
            status="GOOD" if forecast_count else "MISSING",
            last_updated=run_time,
            records=forecast_count,
        ),
        DataQualitySource(
            source="OBSERVATION",
            status="GOOD" if obs_count else "MISSING",
            last_updated=None,
            records=obs_count,
        ),
        DataQualitySource(
            source="HISTORICAL_ERRORS",
            status="GOOD" if err_count else "MISSING",
            last_updated=None,
            records=err_count,
        ),
        DataQualitySource(
            source="PREDICTIONS",
            status="GOOD" if prediction_count else "MISSING",
            last_updated=None,
            records=prediction_count,
        ),
    ]
    warnings: list[str] = []
    if run_time is not None:
        age = (_utcnow_naive() - run_time.replace(tzinfo=None)).total_seconds() / 3600.0
        if age > settings.forecast_freshness_hours:
            warnings.append(
                f"Latest forecast run is {age:.0f}h old (freshness limit "
                f"{settings.forecast_freshness_hours:.0f}h)."
            )
    missing = [s.source for s in sources if s.status == "MISSING"]
    if missing:
        warnings.append("Missing data for: " + ", ".join(missing))

    overall = "GOOD"
    if missing:
        overall = "DEGRADED" if len(missing) < len(sources) else "CRITICAL"
    if warnings and overall == "GOOD":
        overall = "DEGRADED"

    return DataQualityResponse(overall_status=overall, sources=sources, warnings=warnings)


@router.get("/quality")
def quality_report(db: Session = Depends(get_db)):
    """Rules-based data quality report (master prompts Prompt 4 / Prompt 8)."""
    return run_quality_checks(db)
