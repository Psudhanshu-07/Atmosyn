"""GET /alerts, GET /alerts/{id}, POST /alerts/{id}/acknowledge (Safety §14-15)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import Alert, Region
from app.core.schemas import AckRequest, AckResponse, AlertOut, AlertsResponse
from app.services.alert_service import expire_stale_alerts

router = APIRouter()


def _to_out(a: Alert, region_name: str) -> AlertOut:
    return AlertOut(
        alert_id=a.alert_id,
        region_id=str(a.region_id),
        region_name=region_name,
        alert_type=a.alert_type,
        variable=a.variable,
        lead_day=a.lead_day,
        bust_probability=a.bust_probability,
        confidence=a.confidence,
        risk_level=a.risk_level,
        status=a.status,
        message=a.message,
        model_version=a.model_version,
        generated_at=a.generated_at,
        expires_at=a.expires_at,
        acknowledged_by=a.acknowledged_by,
        acknowledged_at=a.acknowledged_at,
    )


@router.get("/alerts", response_model=AlertsResponse)
def list_alerts(
    region_id: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    status: Optional[str] = Query("ACTIVE"),
    db: Session = Depends(get_db),
):
    # Auto-expire alerts whose valid time has passed (SAF-AC-07)
    expire_stale_alerts(db)

    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status.upper())
    if risk_level:
        q = q.filter(Alert.risk_level == risk_level.upper())
    if region_id:
        region = db.query(Region).filter(Region.region_id == region_id.upper()).first()
        if region is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "REGION_NOT_FOUND", "message": f"Region {region_id} was not found"},
            )
        q = q.filter(Alert.region_id == region.id)

    alerts = q.order_by(Alert.bust_probability.desc()).all()
    names = {r.id: r.region_name for r in db.query(Region).all()}

    return AlertsResponse(
        count=len(alerts),
        alerts=[
            _to_out(
                a,
                names.get(a.region_id, ""),
            )
            for a in alerts
        ],
    )


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    a = db.query(Alert).filter(Alert.alert_id == alert_id.upper()).first()
    if a is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ALERT_NOT_FOUND", "message": f"Alert {alert_id} was not found"},
        )
    region = db.query(Region).filter(Region.id == a.region_id).first()
    out = _to_out(a, region.region_name if region else "")
    return out.model_dump() | {
        "prediction_id": a.prediction_id,
        "disclaimer": "This is an AI-derived forecast reliability indicator and is not an official weather warning.",
    }


@router.post("/alerts/{alert_id}/acknowledge", response_model=AckResponse)
def acknowledge_alert(
    alert_id: str,
    req: AckRequest,
    db: Session = Depends(get_db),
):
    a = db.query(Alert).filter(Alert.alert_id == alert_id.upper()).first()
    if a is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ALERT_NOT_FOUND", "message": f"Alert {alert_id} was not found"},
        )
    if a.status not in ("ACTIVE", "ACKNOWLEDGED"):
        raise HTTPException(
            status_code=409,
            detail={"code": "INVALID_STATUS", "message": f"Alert status is {a.status}; cannot acknowledge"},
        )
    a.status = "ACKNOWLEDGED"
    a.acknowledged_by = req.acknowledged_by
    a.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return AckResponse(
        alert_id=a.alert_id,
        status=a.status,
        acknowledged_at=a.acknowledged_at,
        acknowledged_by=a.acknowledged_by,
    )
