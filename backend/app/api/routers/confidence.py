"""GET /confidence, /confidence/10day, /map/confidence (API contract §8-10)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.constants import MAX_LEAD_DAY, MIN_LEAD_DAY
from app.core.database import get_db
from app.core.models import ForecastRun, Prediction, Region
from app.core.schemas import (
    ConfidenceDay,
    ConfidenceOut,
    MapConfidenceResponse,
    MapRegionPoint,
    TenDayResponse,
)
from app.services import reliability_service
from app.services.error_engine import bust_concern_band, confidence_label

router = APIRouter()


def _band_fields(bust_probability: float, confidence_score: float) -> dict:
    """Doc-aligned (Prompt 6) concern band + confidence label fields."""
    return {
        "bust_band": bust_concern_band(bust_probability),
        "confidence_label": confidence_label(confidence_score * 100.0),
    }


def _latest_predictions(db: Session, run_time) -> dict:
    """Latest prediction per (region, variable, lead_day) for the given run."""
    rows = (
        db.query(Prediction)
        .filter(Prediction.forecast_run == run_time)
        .all()
    )
    return {(p.region_id, p.variable, p.lead_day): p for p in rows}


@router.get("/confidence", response_model=ConfidenceOut)
def get_confidence(
    region_id: str = Query(...),
    lead_day: int = Query(1, ge=MIN_LEAD_DAY, le=MAX_LEAD_DAY),
    variable: str = Query("rainfall"),
    db: Session = Depends(get_db),
):
    region = (
        db.query(Region).filter(Region.region_id == region_id.upper()).first()
    )
    if region is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REGION_NOT_FOUND", "message": f"Region {region_id} was not found"},
        )

    run_time = reliability_service.latest_run_time(db)
    if run_time is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_FORECAST_DATA", "message": "No forecast data available"},
        )

    pred = (
        db.query(Prediction)
        .filter(
            Prediction.region_id == region.id,
            Prediction.variable == variable.lower(),
            Prediction.lead_day == lead_day,
            Prediction.forecast_run == run_time,
        )
        .first()
    )
    if pred is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PREDICTION_NOT_FOUND",
                "message": "No AI prediction available for this region/day/variable",
            },
        )

    return ConfidenceOut(
        region_id=region.region_id,
        lead_day=pred.lead_day,
        variable=pred.variable,
        bust_probability=pred.bust_probability,
        confidence_score=pred.confidence_score,
        risk_level=pred.risk_level,
        expected_error=pred.expected_error,
        forecast_value=pred.forecast_value,
        model_version=pred.model_version,
        forecast_run=pred.forecast_run,
        valid_time=pred.valid_time,
        prediction_id=pred.prediction_id,
        **_band_fields(pred.bust_probability, pred.confidence_score),
    )


@router.get("/confidence/10day", response_model=TenDayResponse)
def get_confidence_10day(
    region_id: str = Query(...),
    variable: str = Query("rainfall"),
    db: Session = Depends(get_db),
):
    region = (
        db.query(Region).filter(Region.region_id == region_id.upper()).first()
    )
    if region is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REGION_NOT_FOUND", "message": f"Region {region_id} was not found"},
        )

    run_time = reliability_service.latest_run_time(db)
    if run_time is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_FORECAST_DATA", "message": "No forecast data available"},
        )

    preds = (
        db.query(Prediction)
        .filter(
            Prediction.region_id == region.id,
            Prediction.variable == variable.lower(),
            Prediction.forecast_run == run_time,
            Prediction.lead_day.between(MIN_LEAD_DAY, MAX_LEAD_DAY),
        )
        .order_by(Prediction.lead_day)
        .all()
    )
    if not preds:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PREDICTION_NOT_FOUND",
                "message": "No AI predictions available for this region/variable",
            },
        )

    return TenDayResponse(
        region_id=region.region_id,
        region_name=region.region_name,
        variable=variable.lower(),
        forecast_run=run_time,
        days=[
            ConfidenceDay(
                lead_day=p.lead_day,
                bust_probability=p.bust_probability,
                confidence=p.confidence_score,
                risk_level=p.risk_level,
                expected_error=p.expected_error,
                forecast_value=p.forecast_value,
            )
            for p in preds
        ],
    )


@router.get("/map/confidence", response_model=MapConfidenceResponse)
def get_map_confidence(
    lead_day: int = Query(1, ge=MIN_LEAD_DAY, le=MAX_LEAD_DAY),
    variable: str = Query("rainfall"),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    run_time = reliability_service.latest_run_time(db)
    if run_time is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_FORECAST_DATA", "message": "No forecast data available"},
        )

    q = db.query(Region)
    if state:
        q = q.filter(Region.state.ilike(f"%{state}%"))
    regions = q.order_by(Region.region_id).all()

    preds = _latest_predictions(db, run_time)

    data_status = "CURRENT"
    run_naive = run_time.replace(tzinfo=None) if run_time.tzinfo else run_time
    age_hours = (
        datetime.now(timezone.utc).replace(tzinfo=None) - run_naive
    ).total_seconds() / 3600.0
    if age_hours > 24 * 3:
        data_status = "STALE"

    points: list[MapRegionPoint] = []
    for r in regions:
        p = preds.get((r.id, variable.lower(), lead_day))
        points.append(
            MapRegionPoint(
                region_id=r.region_id,
                region_name=r.region_name,
                state=r.state,
                latitude=r.latitude,
                longitude=r.longitude,
                forecast_value=p.forecast_value if p else None,
                bust_probability=p.bust_probability if p else None,
                confidence=p.confidence_score if p else None,
                risk_level=p.risk_level if p else None,
                expected_error=p.expected_error if p else None,
                status="OK" if p else "NO_PREDICTION",
            )
        )

    return MapConfidenceResponse(
        lead_day=lead_day,
        variable=variable.lower(),
        forecast_run=run_time,
        generated_at=datetime.now(timezone.utc),
        data_status=data_status,
        regions=points,
    )
