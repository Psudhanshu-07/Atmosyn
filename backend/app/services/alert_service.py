"""Alert generation, deduplication and expiry (Safety.txt §6, §9, §16)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.models import Alert, Prediction


def alert_key_for(pred: Prediction) -> str:
    """Deduplication key (Safety §9): region+run+valid_time+variable+type."""
    return "|".join(
        [
            f"region:{pred.region_id}",
            f"run:{pred.forecast_run.isoformat()}",
            f"valid:{pred.valid_time.isoformat()}",
            f"var:{pred.variable}",
            "type:FORECAST_BUST",
        ]
    )


def generate_alert_for_prediction(
    db: Session,
    pred: Prediction,
    summary: str,
) -> Optional[Alert]:
    """Create/update an AI reliability alert when probability >= threshold.

    - Deduplicated by alert_key (update existing instead of duplicating).
    - Expired when valid time has passed (SAF-AC-07).
    Returns the alert, or None when below threshold.
    """
    if pred.bust_probability < settings.alert_probability_threshold:
        return None

    key = alert_key_for(pred)
    existing = db.query(Alert).filter(Alert.alert_key == key).first()
    if existing:
        # UPDATE EXISTING ALERT (Safety §9)
        existing.bust_probability = pred.bust_probability
        existing.confidence = pred.confidence_score
        existing.risk_level = pred.risk_level
        existing.message = summary
        existing.model_version = pred.model_version
        existing.prediction_id = pred.prediction_id
        return existing

    alert_id = f"ALT-{pred.id:05d}"
    alert = Alert(
        alert_id=alert_id,
        alert_key=key,
        prediction_id=pred.prediction_id,
        region_id=pred.region_id,
        variable=pred.variable,
        lead_day=pred.lead_day,
        forecast_run=pred.forecast_run,
        valid_time=pred.valid_time,
        alert_type="FORECAST_BUST",
        bust_probability=pred.bust_probability,
        confidence=pred.confidence_score,
        risk_level=pred.risk_level,
        status="ACTIVE",
        message=summary,
        model_version=pred.model_version,
        generated_at=datetime.now(timezone.utc),
        expires_at=pred.valid_time + timedelta(days=1),
    )
    db.add(alert)
    return alert


def expire_stale_alerts(db: Session) -> int:
    """Expire alerts whose valid time has passed (Safety §16)."""
    now = datetime.now(timezone.utc)
    stale = (
        db.query(Alert)
        .filter(Alert.status == "ACTIVE", Alert.valid_time < now)
        .all()
    )
    for a in stale:
        a.status = "EXPIRED"
    if stale:
        db.commit()
    return len(stale)
