"""Application settings loaded from environment variables (.env supported)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Project root = three levels above this file (backend/app/core/config.py)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load .env first, then .env.local (project-local overrides) — both gitignored.
# Neither overrides variables already present in the process environment:
# explicit environment always wins (12-factor), which keeps test databases
# and deployment overrides authoritative over checked-in defaults.
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(_PROJECT_ROOT / ".env.local")


def _default_database_url() -> str:
    # Absolute path so the server works from any working directory.
    db_path = _PROJECT_ROOT / "backend" / "forecast_bust.db"
    return f"sqlite:///{db_path.as_posix()}"


class Settings:
    """Central runtime configuration (Security.txt section 27)."""

    environment: str = os.getenv("ENVIRONMENT", "development")

    database_url: str = os.getenv("DATABASE_URL", _default_database_url())

    model_path: str = os.getenv("MODEL_PATH", "./ml/models")
    nwp_data_path: str = os.getenv("NWP_DATA_PATH", "./data/raw")
    observation_data_path: str = os.getenv(
        "OBSERVATION_DATA_PATH", "./data/raw"
    )

    # A forecast run older than this many hours is flagged stale (Safety §8)
    forecast_freshness_hours: float = float(
        os.getenv("FORECAST_FRESHNESS_HOURS", "30")
    )

    # Risk band thresholds on bust probability
    risk_very_high: float = float(os.getenv("RISK_VERY_HIGH", "0.8"))
    risk_high: float = float(os.getenv("RISK_HIGH", "0.6"))
    risk_moderate: float = float(os.getenv("RISK_MODERATE", "0.4"))
    risk_low: float = float(os.getenv("RISK_LOW", "0.2"))

    # Alerts are generated when bust probability >= threshold (Safety §6)
    alert_probability_threshold: float = float(
        os.getenv("ALERT_PROBABILITY_THRESHOLD", "0.6")
    )

    # ------------------------------------------------------------------
    # NOAA/NCEP GFS via NOMADS (no API key, public domain)
    # Consumed by app.services.gfs — kept here so there is a single
    # configuration mechanism for the whole project.
    # ------------------------------------------------------------------
    gfs_base_url: str = os.getenv(
        "GFS_BASE_URL",
        "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl",
    )
    gfs_datasource: str = os.getenv("GFS_DATASET", "gfs")       # file prefix
    gfs_file_pattern: str = os.getenv(
        "GFS_FILE_PATTERN", "{ds}.t{cycle:02d}z.pgrb2.0p25.f{fhour:03d}"
    )

    # Geographic sub-region (India-focused defaults)
    gfs_left_lon: float = float(os.getenv("GFS_LEFT_LON", "68"))
    gfs_right_lon: float = float(os.getenv("GFS_RIGHT_LON", "98"))
    gfs_bottom_lat: float = float(os.getenv("GFS_BOTTOM_LAT", "6"))
    gfs_top_lat: float = float(os.getenv("GFS_TOP_LAT", "38"))

    # Forecast hours to retrieve
    gfs_forecast_start: int = int(os.getenv("GFS_FORECAST_START", "0"))
    gfs_forecast_end: int = int(os.getenv("GFS_FORECAST_END", "120"))
    gfs_forecast_interval: int = int(os.getenv("GFS_FORECAST_INTERVAL", "3"))

    # Extra f-hours on top of the configured grid (NOMADS publishes 3-hourly
    # fields but analysis/accumulation resets are at 6/12/24h). Empty by default.
    gfs_extra_forecast_hours: str = os.getenv("GFS_EXTRA_FORECAST_HOURS", "")

    # Variables to request. Comma separated NOMADS short names.
    gfs_variables: str = os.getenv("GFS_VARIABLES", "TMP,APCP,UGRD,VGRD,RH")
    gfs_include_pressure: bool = os.getenv("GFS_INCLUDE_PRESSURE", "1") not in (
        "0",
        "false",
        "False",
    )

    # Update loop
    gfs_update_interval_minutes: int = int(
        os.getenv("GFS_UPDATE_INTERVAL_MINUTES", "30")
    )
    # Start the GFS background updater inside the FastAPI lifespan hook.
    # Off by default so tests/CI never touch the network on startup.
    gfs_auto_update: bool = os.getenv("GFS_AUTO_UPDATE", "0") not in (
        "0",
        "false",
        "False",
    )
    # Grace period added to the nominal cycle time before probing NOMADS,
    # covering NOAA analysis/publication delay.
    gfs_cycle_delay_hours: float = float(os.getenv("GFS_CYCLE_DELAY_HOURS", "3"))

    # HTTP client behaviour
    gfs_http_timeout: float = float(os.getenv("GFS_HTTP_TIMEOUT", "120"))
    gfs_max_retries: int = int(os.getenv("GFS_MAX_RETRIES", "3"))
    gfs_backoff_base: float = float(os.getenv("GFS_BACKOFF_BASE", "2.0"))
    gfs_request_delay: float = float(os.getenv("GFS_REQUEST_DELAY", "1.0"))

    # Storage
    gfs_raw_dir: str = os.getenv("GFS_RAW_DIR", "./data/raw/gfs")
    gfs_processed_dir: str = os.getenv("GFS_PROCESSED_DIR", "./data/processed/gfs")
    gfs_retention_days: int = int(os.getenv("GFS_RETENTION_DAYS", "3"))

    # CORS allowlist — never "*" in production (Security §14)
    cors_origins: list = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:3000,"
            "https://atmosyn-eosin.vercel.app",
        ).split(",")
        if o.strip()
    ]

    api_prefix: str = "/api/v1"
    app_version: str = "1.0.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
