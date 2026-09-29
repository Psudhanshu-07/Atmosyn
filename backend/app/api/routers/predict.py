"""POST /predict/bust, GET /predictions/{id}, GET /explanation/{id}."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import Prediction, Region
from app.core.schemas import (
    ExplanationResponse,
    PredictBustRequest,
    PredictionOut,
)
from app.services.ml_service import load_bundle, score_region_day
from app.services.error_engine import bust_concern_band, confidence_label

router = APIRouter()


@router.post("/predict/bust", response_model=PredictionOut)
def predict_bust(req: PredictBustRequest, db: Session = Depends(get_db)):
    region = (
        db.query(Region).filter(Region.region_id == req.region_id.upper()).first()
    )
    if region is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REGION_NOT_FOUND", "message": f"Region {req.region_id} was not found"},
        )

    import math
    from app.core.models import HistoricalError
    from app.services.regions_data import REGION_INDEX
    from app.services.reliability_service import _static_atmosphere

    m = datetime.now(timezone.utc).month
    region_meta = REGION_INDEX.get(region.region_id)
    atmo = _static_atmosphere(region_meta, m) if region_meta else {
        "temperature": 30.0, "humidity": 75.0, "pressure": 1006.0, "wind_speed": 6.0
    }

    # Query historical error statistics from database for this region & variable
    past_rows = (
        db.query(HistoricalError.absolute_error, HistoricalError.bust)
        .filter(
            HistoricalError.region_id == region.id,
            HistoricalError.variable == req.variable.lower(),
        )
        .all()
    )
    if past_rows:
        n_p = len(past_rows)
        hist_mae = sum(r[0] for r in past_rows) / n_p
        hist_rmse = math.sqrt(sum(r[0] ** 2 for r in past_rows) / n_p)
        hist_bust_rate = sum(1 for r in past_rows if r[1]) / n_p
    else:
        # Climatology-based fallback if no historical cases exist
        base_rain = 15.0
        hist_mae = base_rain * 0.8
        hist_rmse = base_rain * 1.2
        hist_bust_rate = 0.20

    features = {
        "lead_day": req.lead_day,
        "forecast_value": req.forecast_value,
        "historical_mae": req.historical_mae if req.historical_mae is not None else round(hist_mae, 4),
        "historical_rmse": req.historical_rmse if req.historical_rmse is not None else round(hist_rmse, 4),
        "historical_bust_rate": req.historical_bust_rate if req.historical_bust_rate is not None else round(hist_bust_rate, 4),
        "forecast_run_change": req.run_to_run_change if req.run_to_run_change is not None else 0.15,
        "ensemble_spread": req.ensemble_spread if req.ensemble_spread is not None else round(max(2.0, hist_mae * 0.3), 2),
        "temperature": req.temperature if req.temperature is not None else atmo["temperature"],
        "humidity": req.humidity if req.humidity is not None else atmo["humidity"],
        "pressure": req.pressure if req.pressure is not None else atmo["pressure"],
        "wind_speed": req.wind_speed if req.wind_speed is not None else atmo["wind_speed"],
        "month": m,
        "season_monsoon": 0, "season_post_monsoon": 0,
        "season_winter": 0, "season_pre_monsoon": 0,
        "region_avg_error": round(hist_mae, 4),
    }
    season = "monsoon" if m in (6, 7, 8, 9) else "post_monsoon" if m in (10, 11, 12) else "winter" if m in (1, 2) else "pre_monsoon"
    features[f"season_{season}"] = 1

    result = score_region_day(
        features=features,
        variable=req.variable,
        lead_day=req.lead_day,
        region_name=region.region_name,
    )

    seq = db.query(Prediction).count() + 1
    pred = Prediction(
        prediction_id=f"PRED-{seq:05d}",
        prediction_key=f"adhoc|{req.region_id}|{req.variable}|{req.lead_day}|{datetime.now(timezone.utc).isoformat()}",
        region_id=region.id,
        variable=req.variable,
        lead_day=req.lead_day,
        forecast_run=datetime.now(timezone.utc),
        valid_time=None,
        forecast_value=req.forecast_value,
        expected_error=result["expected_error"],
        bust_probability=result["bust_probability"],
        confidence_score=result["confidence_score"],
        risk_level=result["risk_level"],
        model_version=result["model_version"],
        features_json=json.dumps({k: v for k, v in features.items()})[:3900],
    )
    db.add(pred)
    db.commit()

    return PredictionOut(
        prediction_id=pred.prediction_id,
        region_id=region.region_id,
        variable=pred.variable,
        lead_day=pred.lead_day,
        forecast_run=pred.forecast_run,
        valid_time=pred.valid_time,
        forecast_value=pred.forecast_value,
        expected_error=pred.expected_error,
        bust_probability=pred.bust_probability,
        confidence_score=pred.confidence_score,
        risk_level=pred.risk_level,
        bust_band=bust_concern_band(pred.bust_probability),
        confidence_label=confidence_label(pred.confidence_score * 100.0),
        model_version=pred.model_version,
        predicted_at=pred.predicted_at,
    )


@router.get("/predictions/{prediction_id}", response_model=PredictionOut)
def get_prediction(prediction_id: str, db: Session = Depends(get_db)):
    pred = (
        db.query(Prediction).filter(Prediction.prediction_id == prediction_id.upper()).first()
    )
    if pred is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PREDICTION_NOT_FOUND", "message": f"Prediction {prediction_id} was not found"},
        )
    region = db.query(Region).filter(Region.id == pred.region_id).first()
    return PredictionOut(
        prediction_id=pred.prediction_id,
        region_id=region.region_id if region else str(pred.region_id),
        variable=pred.variable,
        lead_day=pred.lead_day,
        forecast_run=pred.forecast_run,
        valid_time=pred.valid_time,
        forecast_value=pred.forecast_value,
        expected_error=pred.expected_error,
        bust_probability=pred.bust_probability,
        confidence_score=pred.confidence_score,
        risk_level=pred.risk_level,
        bust_band=bust_concern_band(pred.bust_probability),
        confidence_label=confidence_label(pred.confidence_score * 100.0),
        model_version=pred.model_version,
        predicted_at=pred.predicted_at,
    )


@router.get("/explanation/{prediction_id}", response_model=ExplanationResponse)
def get_explanation(prediction_id: str, db: Session = Depends(get_db)):
    pred = (
        db.query(Prediction).filter(Prediction.prediction_id == prediction_id.upper()).first()
    )
    if pred is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PREDICTION_NOT_FOUND", "message": f"Prediction {prediction_id} was not found"},
        )

    region = db.query(Region).filter(Region.id == pred.region_id).first()
    features = json.loads(pred.features_json or "{}")
    bundle = load_bundle()
    if bundle is not None:
        from app.services.ml_service import predict as ml_predict

        result = ml_predict(features)
        contributions = result["contributions"]
    else:
        # Recompute contributions via the same path used at persistence time
        result = score_region_day(
            features=features,
            variable=pred.variable,
            lead_day=pred.lead_day,
            region_name=region.region_name,
        )
        contributions = result["contributions"]

    explanation, summary = build_explanation_for(
        contributions, pred.bust_probability, pred.variable, pred.lead_day, region.region_name
    )
    return ExplanationResponse(
        prediction_id=pred.prediction_id,
        region_id=region.region_id,
        variable=pred.variable,
        lead_day=pred.lead_day,
        bust_probability=pred.bust_probability,
        risk_level=pred.risk_level,
        summary=summary,
        explanation=explanation,
        model_version=pred.model_version,
    )


def build_explanation_for(contributions, p, variable, lead_day, region_name):
    from app.services.ml_service import build_explanation

    return build_explanation(contributions, p, variable, lead_day, region_name)
