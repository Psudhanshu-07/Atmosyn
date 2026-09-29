"""GET /health — API, database and ML service status (FR-41)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.schemas import HealthResponse
from app.services.ml_service import get_active_model_version

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    db_status = "connected"
    ml_status = "available"
    active_model = None
    try:
        db.execute(text("SELECT 1"))
        mv = get_active_model_version(db)
        active_model = mv.model_version if mv else None
        if mv is None:
            ml_status = "heuristic_fallback"
    except Exception:
        db_status = "unavailable"
        ml_status = "unavailable"

    status = (
        "healthy"
        if db_status == "connected" and ml_status != "unavailable"
        else "degraded"
    )
    return HealthResponse(
        status=status,
        service="atomsyn-api",
        version=settings.app_version,
        database=db_status,
        ml_service=ml_status,
        active_model=active_model,
        timestamp=datetime.now(timezone.utc),
    )
