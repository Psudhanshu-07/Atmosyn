"""SQLAlchemy ORM models — prototype schema (Technological stack §22-25).

Kept intentionally normalized around the core relationship:
Forecast -> Observation -> Error -> Bust label -> Prediction -> Alert.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Region(Base):
    """Geographic region: a city/district point representative of an area."""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    region_name: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(120), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    elevation: Mapped[float] = mapped_column(Float, default=0.0)
    coastal: Mapped[bool] = mapped_column(Boolean, default=False)

    forecasts: Mapped[list["Forecast"]] = relationship(back_populates="region")


class ForecastRun(Base):
    """One NWP model run (initialization time)."""

    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(60), default="NWP")
    model: Mapped[str] = mapped_column(String(60), default="GFS-0.25deg")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Forecast(Base):
    """A single forecast value: run + region + valid time + variable + lead day."""

    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "region_id", "valid_time", "variable", name="uq_forecast"
        ),
        Index("ix_forecasts_lookup", "run_id", "region_id", "variable", "lead_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    variable: Mapped[str] = mapped_column(String(32), index=True)
    forecast_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lead_day: Mapped[int] = mapped_column(Integer, index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))

    region: Mapped["Region"] = relationship(back_populates="forecasts")
    run: Mapped["ForecastRun"] = relationship()


class Observation(Base):
    """What actually happened at a region + valid time + variable."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("region_id", "valid_time", "variable", name="uq_observation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    variable: Mapped[str] = mapped_column(String(32), index=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(60), default="NCEI")


class HistoricalError(Base):
    """Paired forecast vs observation with computed error + bust label.

    This is the ML training ground truth: Forecast -> Observation -> Error.
    """

    __tablename__ = "historical_errors"
    __table_args__ = (
        UniqueConstraint(
            "region_id", "variable", "valid_time", "lead_day",
            name="uq_error_per_target",
        ),
        Index("ix_hist_lookup", "region_id", "variable", "lead_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable: seeder may link errors to forecasts after a second pass.
    forecast_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("forecasts.id"), nullable=True
    )
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    variable: Mapped[str] = mapped_column(String(32))
    forecast_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lead_day: Mapped[int] = mapped_column(Integer)

    forecast_value: Mapped[float] = mapped_column(Float)
    observed_value: Mapped[float] = mapped_column(Float)
    absolute_error: Mapped[float] = mapped_column(Float)
    signed_error: Mapped[float] = mapped_column(Float)  # bias component
    percent_error: Mapped[float] = mapped_column(Float, nullable=True)

    bust: Mapped[bool] = mapped_column(Boolean, index=True)
    bust_threshold: Mapped[float] = mapped_column(Float)

    # Engineered features captured at training/inference time (anti-leakage:
    # only information available at forecast_run time is stored here)
    historical_mae: Mapped[float] = mapped_column(Float, default=0.0)
    historical_rmse: Mapped[float] = mapped_column(Float, default=0.0)
    historical_bust_rate: Mapped[float] = mapped_column(Float, default=0.0)
    forecast_run_change: Mapped[float] = mapped_column(Float, default=0.0)
    ensemble_spread: Mapped[float] = mapped_column(Float, default=0.0)
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    humidity: Mapped[float] = mapped_column(Float, default=0.0)
    pressure: Mapped[float] = mapped_column(Float, default=0.0)
    wind_speed: Mapped[float] = mapped_column(Float, default=0.0)
    month: Mapped[int] = mapped_column(Integer, default=1)
    season: Mapped[str] = mapped_column(String(20), default="winter")
    region_avg_error: Mapped[float] = mapped_column(Float, default=0.0)


class Prediction(Base):
    """ML output for the current forecast run (bust probability + confidence)."""

    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint(
            "prediction_key", name="uq_prediction_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    # Deduplication key: region|variable|lead_day|forecast_run (Safety §9)
    prediction_key: Mapped[str] = mapped_column(String(160))

    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    variable: Mapped[str] = mapped_column(String(32), index=True)
    lead_day: Mapped[int] = mapped_column(Integer, index=True)
    forecast_run: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Nullable for ad-hoc API predictions with no fixed valid time.
    valid_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    forecast_value: Mapped[float] = mapped_column(Float)
    expected_error: Mapped[float] = mapped_column(Float)
    bust_probability: Mapped[float] = mapped_column(Float)
    confidence_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(16), index=True)

    model_version: Mapped[str] = mapped_column(String(60))
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    features_json: Mapped[str] = mapped_column(String(4000), default="{}")


class Alert(Base):
    """AI reliability alert — never an official weather warning (Safety §3)."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("alert_key", name="uq_alert_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    alert_key: Mapped[str] = mapped_column(String(200))

    prediction_id: Mapped[str] = mapped_column(String(24))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    variable: Mapped[str] = mapped_column(String(32))
    lead_day: Mapped[int] = mapped_column(Integer)
    forecast_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    alert_type: Mapped[str] = mapped_column(String(32), default="FORECAST_BUST")
    bust_probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(16), index=True)

    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    acknowledged_by: Mapped[str] = mapped_column(String(80), nullable=True)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    message: Mapped[str] = mapped_column(String(500), default="")
    model_version: Mapped[str] = mapped_column(String(60), default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelVersion(Base):
    """Registered ML model versions with metrics (Security §21-22)."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    algorithm: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    trained_from: Mapped[date] = mapped_column(Date, nullable=True)
    trained_to: Mapped[date] = mapped_column(Date, nullable=True)
    features: Mapped[str] = mapped_column(String(2000), default="")

    roc_auc: Mapped[float] = mapped_column(Float, nullable=True)
    brier_score: Mapped[float] = mapped_column(Float, nullable=True)
    precision_: Mapped[float] = mapped_column(Float, nullable=True)
    recall_: Mapped[float] = mapped_column(Float, nullable=True)
    f1: Mapped[float] = mapped_column(Float, nullable=True)
    mae: Mapped[float] = mapped_column(Float, nullable=True)
    rmse: Mapped[float] = mapped_column(Float, nullable=True)

    checksum: Mapped[str] = mapped_column(String(80), default="")
    model_path: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
