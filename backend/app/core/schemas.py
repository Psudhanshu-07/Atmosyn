"""Pydantic response/request schemas mirroring the API contract document."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Variable = Literal["rainfall", "temperature", "wind_speed", "pressure", "humidity"]
RiskLevel = Literal["VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH"]


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
class ApiError(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class Metadata(BaseModel):
    model_version: Optional[str] = None
    forecast_source: str = "NWP"
    observation_source: str = "NCEI"
    forecast_run: Optional[datetime] = None
    generated_at: Optional[datetime] = None


class RegionOut(BaseModel):
    region_id: str
    region_name: str
    state: str
    latitude: float
    longitude: float
    elevation: float = 0.0
    coastal: bool = False


class RegionsResponse(BaseModel):
    count: int
    regions: List[RegionOut]


class ForecastOut(BaseModel):
    region_id: str
    forecast_run: datetime
    valid_time: datetime
    lead_day: int
    variable: str
    value: float
    unit: str
    source: str = "NWP"


class DataQualitySource(BaseModel):
    source: str
    status: str
    last_updated: Optional[datetime] = None
    records: Optional[int] = None


class DataQualityResponse(BaseModel):
    overall_status: str
    sources: List[DataQualitySource]
    warnings: List[str] = []


class ModelOut(BaseModel):
    model_version: str
    algorithm: str
    status: str
    roc_auc: Optional[float] = None
    brier_score: Optional[float] = None
    precision: Optional[float] = Field(default=None, alias="precision_")
    recall: Optional[float] = Field(default=None, alias="recall_")
    f1: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    trained_from: Optional[date] = None
    trained_to: Optional[date] = None
    checksum: str = ""

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Confidence / prediction
# ---------------------------------------------------------------------------
class ConfidenceOut(BaseModel):
    region_id: str
    lead_day: int
    variable: str
    bust_probability: float = Field(..., ge=0, le=1)
    confidence_score: float = Field(..., ge=0, le=1)
    risk_level: RiskLevel
    bust_band: Optional[str] = None      # LOW / MODERATE / HIGH concern (doc Prompt 6)
    confidence_label: Optional[str] = None  # HIGH >=70 / MEDIUM 40-69 / LOW <40
    expected_error: float
    forecast_value: Optional[float] = None
    model_version: Optional[str] = None
    forecast_run: Optional[datetime] = None
    valid_time: Optional[datetime] = None
    prediction_id: Optional[str] = None


class ConfidenceDay(BaseModel):
    lead_day: int
    bust_probability: float
    confidence: float
    risk_level: RiskLevel
    expected_error: float
    forecast_value: Optional[float] = None


class TenDayResponse(BaseModel):
    region_id: str
    region_name: str
    variable: str
    forecast_run: Optional[datetime] = None
    days: List[ConfidenceDay]


class MapRegionPoint(BaseModel):
    region_id: str
    region_name: str
    state: str
    latitude: float
    longitude: float
    forecast_value: Optional[float] = None
    bust_probability: Optional[float] = None
    confidence: Optional[float] = None
    risk_level: Optional[str] = None
    expected_error: Optional[float] = None
    status: str = "OK"  # OK | NO_PREDICTION | STALE_DATA


class MapConfidenceResponse(BaseModel):
    lead_day: int
    variable: str
    forecast_run: Optional[datetime] = None
    generated_at: Optional[datetime] = None
    data_status: str = "CURRENT"
    regions: List[MapRegionPoint]


class PredictBustRequest(BaseModel):
    region_id: str
    lead_day: int = Field(..., ge=1, le=10)
    variable: Variable
    forecast_value: float
    historical_mae: Optional[float] = None
    historical_rmse: Optional[float] = None
    historical_bust_rate: Optional[float] = None
    run_to_run_change: Optional[float] = None
    ensemble_spread: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None


class PredictionOut(BaseModel):
    prediction_id: str
    region_id: str
    variable: str
    lead_day: int
    forecast_run: Optional[datetime] = None
    valid_time: Optional[datetime] = None
    forecast_value: float
    expected_error: float
    bust_probability: float
    confidence_score: float
    risk_level: RiskLevel
    bust_band: Optional[str] = None      # LOW / MODERATE / HIGH concern (doc Prompt 6)
    confidence_label: Optional[str] = None  # HIGH >=70 / MEDIUM 40-69 / LOW <40
    model_version: str
    predicted_at: Optional[datetime] = None


class FactorOut(BaseModel):
    feature: str
    label: str
    value: float
    impact: str  # HIGH / MEDIUM / LOW
    shap_value: float
    direction: str  # "increases bust risk" / "decreases bust risk"


class ExplanationResponse(BaseModel):
    prediction_id: str
    region_id: str
    variable: str
    lead_day: int
    bust_probability: float
    risk_level: str
    summary: str
    explanation: List[FactorOut]
    model_version: str


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class ErrorStatistics(BaseModel):
    mae: float
    rmse: float
    bias: float
    bust_rate: float
    sample_count: int


class AnalyticsErrorResponse(BaseModel):
    region_id: str
    variable: str
    lead_day: Optional[int] = None
    statistics: ErrorStatistics


class TrendPoint(BaseModel):
    date: date
    mae: float
    bust_rate: float


class AnalyticsTrendsResponse(BaseModel):
    region_id: Optional[str] = None
    variable: Optional[str] = None
    data: List[TrendPoint]


class AlertOut(BaseModel):
    alert_id: str
    region_id: str
    region_name: str = ""
    alert_type: str
    variable: str
    lead_day: int
    bust_probability: float
    confidence: float
    risk_level: RiskLevel
    status: str
    message: str = ""
    model_version: str = ""
    generated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None


class AlertsResponse(BaseModel):
    count: int
    alerts: List[AlertOut]


class AckRequest(BaseModel):
    acknowledged_by: str = "operator"


class AckResponse(BaseModel):
    alert_id: str
    status: str
    acknowledged_at: datetime
    acknowledged_by: str


# ---------------------------------------------------------------------------
# KPI / dashboard
# ---------------------------------------------------------------------------
class DashboardKpis(BaseModel):
    regions_monitored: int
    high_risk_regions: int
    avg_confidence: float
    highest_risk_lead_day: int
    data_quality: float
    forecast_run: Optional[datetime] = None
    data_status: str = "CURRENT"


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
    ml_service: str
    active_model: Optional[str] = None
    timestamp: datetime


# ---------------------------------------------------------------------------
# Data Sources & Provenance (PRD §4, §5, §31)
# ---------------------------------------------------------------------------
class DataSourceOut(BaseModel):
    id: str
    name: str
    provider: str
    dataset: str
    purpose: str
    url: str
    variables: List[str]
    spatial_resolution: str
    temporal_resolution: str
    historical_coverage: str
    update_frequency: str
    license_terms: str
    access_requirements: str
    status: str  # OPERATIONAL_READY / REFERENCE / AVAILABLE
    limitations: str


class DataSourcesResponse(BaseModel):
    count: int
    sources: List[DataSourceOut]


# ---------------------------------------------------------------------------
# System Verification (Master Prompt §48)
# ---------------------------------------------------------------------------
class SystemVerificationItem(BaseModel):
    component: str
    category: str  # Data / ML / API / Database / System
    status: str  # PASS / FAIL / WARNING
    details: str
    checked_at: datetime


class SystemVerificationResponse(BaseModel):
    overall_status: str  # PASS / DEGRADED / FAIL
    checked_at: datetime
    items: List[SystemVerificationItem]


# ---------------------------------------------------------------------------
# Forecast vs Observed Verification Series (Master Prompt §27)
# ---------------------------------------------------------------------------
class VerificationPair(BaseModel):
    valid_time: datetime
    forecast_run: datetime
    lead_day: int
    forecast_value: float
    observed_value: float
    absolute_error: float
    signed_error: float
    bust: bool
    bust_threshold: float
    unit: str


class VerificationSeriesResponse(BaseModel):
    region_id: str
    region_name: str
    variable: str
    count: int
    pairs: List[VerificationPair]


# ---------------------------------------------------------------------------
# NOAA/NCEP GFS via NOMADS (ingestion service, app.services.gfs)
# ---------------------------------------------------------------------------
class GFSFileOut(BaseModel):
    forecast_hour: int
    status: str
    file_name: str = ""
    size_bytes: int = 0
    valid_time: Optional[datetime] = None
    checksum: str = ""
    error: Optional[str] = None
    retry_count: int = 0


class GFSRunOut(BaseModel):
    model: str
    source: str
    source_label: str
    data_type: str = "NWP_MODEL_FORECAST"
    run_date: str
    cycle: str
    run_time: Optional[datetime] = None
    status: str
    is_active: bool = False
    bounds: Dict[str, float] = {}
    variables: List[str] = []
    forecast_hours: List[int] = []
    files_valid: int = 0
    files_total: int = 0
    files: List[GFSFileOut] = []
    discovered_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    notes: List[str] = []


class GFSStatusResponse(BaseModel):
    provider: str
    source_url: str
    api_key_required: bool = False
    data_type: str = "NWP_MODEL_FORECAST"
    disclaimer: str
    scheduler_running: bool = False
    update_interval_minutes: int = 30
    last_check_at: Optional[datetime] = None
    last_check_outcome: Optional[str] = None
    active_run: Optional[GFSRunOut] = None
    stored_runs: int = 0


class GFSLatestCycleResponse(BaseModel):
    run_date: Optional[str] = None
    cycle: Optional[str] = None
    run_time: Optional[datetime] = None
    available: bool
    status_code: Optional[int] = None
    reason: str = ""
    candidates: List[Dict[str, Any]] = []


class GFSUpdateResponse(BaseModel):
    outcome: str  # new_cycle / up_to_date / no_cycle / failed
    message: str
    run: Optional[GFSRunOut] = None


class GFSForecastPoint(BaseModel):
    region_id: str
    region_name: str
    state: str
    lead_day: int
    valid_time: Optional[datetime] = None
    forecast_run: Optional[datetime] = None
    variable: str
    value: Optional[float] = None
    unit: str


class GFSForecastResponse(BaseModel):
    source_label: str
    data_type: str = "NWP_MODEL_FORECAST"
    run_date: str
    cycle: str
    run_time: Optional[datetime] = None
    count: int
    points: List[GFSForecastPoint]
