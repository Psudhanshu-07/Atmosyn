"""GET /models — registered model versions with metrics (API contract §21)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import ModelVersion
from app.core.schemas import ModelOut

router = APIRouter()


@router.get("/models")
def list_models(db: Session = Depends(get_db)):
    models = (
        db.query(ModelVersion).order_by(ModelVersion.created_at.desc()).all()
    )
    return {
        "models": [
            ModelOut(
                model_version=m.model_version,
                algorithm=m.algorithm,
                status=m.status,
                roc_auc=m.roc_auc,
                brier_score=m.brier_score,
                precision_=m.precision_,
                recall_=m.recall_,
                f1=m.f1,
                mae=m.mae,
                rmse=m.rmse,
                trained_from=m.trained_from,
                trained_to=m.trained_to,
                checksum=m.checksum,
            )
            for m in models
        ]
    }
