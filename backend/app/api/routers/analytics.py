"""GET /analytics/error and /analytics/trends (API contract §14-15)."""
from __future__ import annotations

import math
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import Forecast, HistoricalError, Region
from app.core.schemas import (
    AnalyticsErrorResponse,
    AnalyticsTrendsResponse,
    ErrorStatistics,
    TrendPoint,
)

router = APIRouter()


@router.get("/analytics/error", response_model=AnalyticsErrorResponse)
def get_error_stats(
    region_id: str = Query(...),
    variable: str = Query("rainfall"),
    lead_day: Optional[int] = Query(None, ge=1, le=10),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    region = db.query(Region).filter(Region.region_id == region_id.upper()).first()
    if region is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REGION_NOT_FOUND", "message": f"Region {region_id} was not found"},
        )

    q = (
        db.query(
            HistoricalError.absolute_error,
            HistoricalError.signed_error,
            HistoricalError.bust,
        )
        .filter(
            HistoricalError.region_id == region.id,
            HistoricalError.variable == variable.lower(),
        )
    )
    if lead_day is not None:
        q = q.filter(HistoricalError.lead_day == lead_day)
    if start_date is not None:
        q = q.filter(HistoricalError.valid_time >= start_date)
    if end_date is not None:
        q = q.filter(HistoricalError.valid_time <= end_date)

    rows = q.all()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail={"code": "NO_DATA", "message": "No historical error data for the requested filters"},
        )

    errs = [r.signed_error for r in rows]
    abs_errs = [r.absolute_error for r in rows]
    n = len(rows)
    mae = sum(abs_errs) / n
    rmse = math.sqrt(sum(e * e for e in errs) / n)
    biasv = sum(errs) / n
    bust_rate = sum(1 for r in rows if r.bust) / n

    return AnalyticsErrorResponse(
        region_id=region.region_id,
        variable=variable.lower(),
        lead_day=lead_day,
        statistics=ErrorStatistics(
            mae=round(mae, 3),
            rmse=round(rmse, 3),
            bias=round(biasv, 3),
            bust_rate=round(bust_rate, 4),
            sample_count=n,
        ),
    )


@router.get("/analytics/trends", response_model=AnalyticsTrendsResponse)
def get_error_trends(
    region_id: Optional[str] = Query(None),
    variable: str = Query("rainfall"),
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """Monthly MAE + bust-rate trend for charts (UIUX §21)."""
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=30 * months)

    q = (
        db.query(
            func.strftime("%Y-%m", HistoricalError.valid_time).label("month"),
            HistoricalError.absolute_error,
            HistoricalError.signed_error,
            HistoricalError.bust,
        )
        .filter(
            HistoricalError.variable == variable.lower(),
            HistoricalError.valid_time >= since,
        )
    )
    if region_id:
        region = db.query(Region).filter(Region.region_id == region_id.upper()).first()
        if region is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "REGION_NOT_FOUND", "message": f"Region {region_id} was not found"},
            )
        q = q.filter(HistoricalError.region_id == region.id)

    rows = q.all()
    by_month = {}
    for month, abs_err, signed_err, bust in rows:
        s = by_month.setdefault(month, {"n": 0, "sum_abs": 0.0, "busts": 0})
        s["n"] += 1
        s["sum_abs"] += abs_err
        s["busts"] += 1 if bust else 0

    data = [
        TrendPoint(
            date=f"{month}-01",
            mae=round(s["sum_abs"] / s["n"], 3),
            bust_rate=round(s["busts"] / s["n"], 4),
        )
        for month, s in sorted(by_month.items())
    ]
    return AnalyticsTrendsResponse(region_id=region_id, variable=variable.lower(), data=data)
