"""GET /forecast — NWP forecast values for the latest run (API contract §7)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.constants import VARIABLE_UNITS
from app.core.database import get_db
from app.core.models import Forecast, HistoricalError, Region
from app.core.schemas import VerificationPair, VerificationSeriesResponse
from app.services import reliability_service

router = APIRouter()


def _get_region(db: Session, region_id: str) -> Region:
    r = db.query(Region).filter(Region.region_id == region_id.upper()).first()
    if r is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REGION_NOT_FOUND", "message": f"Region {region_id} was not found"},
        )
    return r


@router.get("/forecast")
def get_forecast(
    region_id: str = Query(...),
    lead_day: Optional[int] = Query(None, ge=1, le=10),
    variable: Optional[str] = Query(None),
    forecast_run: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    region = _get_region(db, region_id)

    run_time = reliability_service.latest_run_time(db)
    if run_time is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_FORECAST_DATA", "message": "No forecast data available"},
        )

    q = db.query(Forecast).filter(
        Forecast.region_id == region.id,
        Forecast.forecast_run == run_time,
    )
    if variable:
        q = q.filter(Forecast.variable == variable.lower())
    if lead_day is not None:
        q = q.filter(Forecast.lead_day == lead_day)

    rows = q.order_by(Forecast.lead_day, Forecast.variable).all()
    return {
        "region_id": region.region_id,
        "forecast_run": run_time,
        "count": len(rows),
        "forecasts": [
            {
                "region_id": region.region_id,
                "forecast_run": f.forecast_run,
                "valid_time": f.valid_time,
                "lead_day": f.lead_day,
                "variable": f.variable,
                "value": f.value,
                "unit": f.unit,
                "source": "NWP",
            }
            for f in rows
        ],
    }


@router.get("/forecast/verification", response_model=VerificationSeriesResponse)
def get_forecast_verification(
    region_id: str = Query(...),
    variable: str = Query("rainfall"),
    lead_day: Optional[int] = Query(None, ge=1, le=10),
    limit: int = Query(30, ge=5, le=100),
    db: Session = Depends(get_db),
):
    """Historical Forecast vs Observed verification series (Master Prompt §27)."""
    region = _get_region(db, region_id)
    unit = VARIABLE_UNITS.get(variable.lower(), "units")

    q = (
        db.query(HistoricalError)
        .filter(
            HistoricalError.region_id == region.id,
            HistoricalError.variable == variable.lower(),
        )
    )
    if lead_day is not None:
        q = q.filter(HistoricalError.lead_day == lead_day)

    rows = (
        q.order_by(HistoricalError.valid_time.desc())
        .limit(limit)
        .all()
    )

    pairs = [
        VerificationPair(
            valid_time=r.valid_time,
            forecast_run=r.forecast_run,
            lead_day=r.lead_day,
            forecast_value=r.forecast_value,
            observed_value=r.observed_value,
            absolute_error=r.absolute_error,
            signed_error=r.signed_error,
            bust=r.bust,
            bust_threshold=r.bust_threshold,
            unit=unit,
        )
        for r in reversed(rows)
    ]

    return VerificationSeriesResponse(
        region_id=region.region_id,
        region_name=region.region_name,
        variable=variable.lower(),
        count=len(pairs),
        pairs=pairs,
    )


@router.get("/forecast/india-map")
def get_forecast_india_map(
    lead_day: int = Query(1, ge=1, le=5, description="Forecast lead day (1 to 5)"),
    force: bool = Query(False, description="Bypass disk cache and recalculate"),
):
    """Alias for India States & UTs Weather Map data."""
    from app.services.gfs.states_service import get_india_states_weather

    return get_india_states_weather(lead_day=lead_day, force_refresh=force)


