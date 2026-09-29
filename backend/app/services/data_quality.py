"""Data quality checking service (master prompts Prompt 4 — Feature 16).

Rules-based checks over the operational database:

    - missing values in key numeric columns
    - stale data (latest forecast run older than the freshness limit)
    - duplicate keys (region/variable/valid_time/lead_day etc.)
    - out-of-range physical values (doc bounds: rain 0-1000 mm/day,
      temperature -10..55 degC, humidity 0-100 %, pressure 850-1100 hPa,
      wind >= 0 m/s)
    - region coordinates outside the India bounding box

Output: a JSON report (written to ``reports/data_quality.json``) and, for
out-of-range rows, a quarantine file ``data/processed/rejected.parquet``
(CSV fallback when pyarrow is unavailable). Bad rows are REPORTED and
quarantined — never silently corrected or fabricated.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import INDIA_BBOX
from app.core.config import settings
from app.core.models import Forecast, HistoricalError, Observation, Prediction, Region

# Doc-aligned sanity bounds (Prompt 4). Broader than the synthetic-data
# clamp ranges in constants.py: these detect physically impossible values.
QUALITY_BOUNDS: Dict[str, tuple] = {
    "rainfall": (0.0, 1000.0),
    "temperature": (-10.0, 55.0),
    "humidity": (0.0, 100.0),
    "pressure": (850.0, 1100.0),
    "wind_speed": (0.0, 120.0),
}

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = _PROJECT_ROOT / "reports"
PROCESSED_DIR = _PROJECT_ROOT / "data" / "processed"


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _check(name: str, category: str, status: str, affected: int, details: str) -> Dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "status": status,  # PASS | WARN | FAIL
        "affected_rows": affected,
        "details": details,
    }


def _find_out_of_range(db: Session) -> List[Dict[str, Any]]:
    """Collect rows whose stored value violates the physical bounds.

    Pressure: GFS 'PRES' is surface (station) pressure, genuinely below the
    doc's sea-level 850-1100 hPa band at elevated regions (Srinagar ~1.6 km,
    Shimla ~2.2 km). Rule: regions at <= 500 m must respect the doc band;
    elevated regions are checked against a wide station-pressure envelope
    [600, 1080] hPa instead, so real data is not false-flagged while
    impossible values still are.
    """
    bad: List[Dict[str, Any]] = []
    elevations = {
        row_id: (elev or 0.0)
        for row_id, elev in db.query(Region.id, Region.elevation).all()
    }
    STATION_PRESSURE_BOUNDS = (600.0, 1080.0)

    sources = (
        ("observation", Observation),
        ("forecast", Forecast),
    )
    for table_name, model in sources:
        rows = db.query(model.id, model.variable, model.value, model.region_id).all()
        for row_id, variable, value, region_db_id in rows:
            bounds = QUALITY_BOUNDS.get(variable or "")
            if bounds is None or value is None:
                continue
            lo, hi = bounds
            v = float(value)
            reason = f"value {value} outside [{lo}, {hi}]"
            if variable == "pressure" and elevations.get(region_db_id, 0.0) > 500.0:
                lo, hi = STATION_PRESSURE_BOUNDS
                reason = f"value {value} outside station envelope [{lo}, {hi}]"
            if not (lo <= v <= hi):
                bad.append(
                    {
                        "table": table_name,
                        "row_id": row_id,
                        "variable": variable,
                        "value": float(value),
                        "reason": reason,
                    }
                )
    return bad


def _duplicate_counts(db: Session) -> Dict[str, int]:
    """Count duplicate keys per table (same natural key appearing >1x)."""
    dupes: Dict[str, int] = {}

    dup_obs = (
        db.query(
            Observation.region_id, Observation.variable, Observation.valid_time, func.count()
        )
        .group_by(Observation.region_id, Observation.variable, Observation.valid_time)
        .having(func.count() > 1)
        .count()
    )
    dupes["observations"] = dup_obs

    dup_err = (
        db.query(
            HistoricalError.region_id,
            HistoricalError.variable,
            HistoricalError.valid_time,
            HistoricalError.lead_day,
            func.count(),
        )
        .group_by(
            HistoricalError.region_id,
            HistoricalError.variable,
            HistoricalError.valid_time,
            HistoricalError.lead_day,
        )
        .having(func.count() > 1)
        .count()
    )
    dupes["historical_errors"] = dup_err

    dup_fcst = (
        db.query(
            Forecast.run_id, Forecast.region_id, Forecast.variable, Forecast.valid_time, func.count()
        )
        .group_by(Forecast.run_id, Forecast.region_id, Forecast.variable, Forecast.valid_time)
        .having(func.count() > 1)
        .count()
    )
    dupes["forecasts"] = dup_fcst
    return dupes


def _missing_counts(db: Session) -> Dict[str, int]:
    """Count NULLs in key numeric columns."""
    return {
        "forecasts.value": db.query(Forecast).filter(Forecast.value.is_(None)).count(),
        "observations.value": db.query(Observation).filter(Observation.value.is_(None)).count(),
        "historical_errors.absolute_error": db.query(HistoricalError)
        .filter(HistoricalError.absolute_error.is_(None))
        .count(),
        "predictions.bust_probability": db.query(Prediction)
        .filter(Prediction.bust_probability.is_(None))
        .count(),
    }


def _stale_hours(db: Session) -> Optional[float]:
    latest = db.query(func.max(Forecast.forecast_run)).scalar()
    latest = _naive(latest)
    if latest is None:
        return None
    return (_utcnow_naive() - latest).total_seconds() / 3600.0


def _regions_outside_india(db: Session) -> List[Dict[str, Any]]:
    rows = db.query(Region.id, Region.region_id, Region.latitude, Region.longitude).all()
    bad = []
    for row_id, region_id, lat, lon in rows:
        if lat is None or lon is None:
            bad.append({"table": "regions", "row_id": row_id, "region_id": region_id,
                        "reason": "missing lat/lon"})
            continue
        if not (INDIA_BBOX["lat_min"] <= lat <= INDIA_BBOX["lat_max"]) or not (
            INDIA_BBOX["lon_min"] <= lon <= INDIA_BBOX["lon_max"]
        ):
            bad.append(
                {
                    "table": "regions",
                    "row_id": row_id,
                    "region_id": region_id,
                    "reason": f"coordinates ({lat}, {lon}) outside India bounding box",
                }
            )
    return bad


def _write_quarantine(rejected: List[Dict[str, Any]]) -> Optional[str]:
    """Persist rejected rows. Parquet preferred, CSV fallback (no pyarrow)."""
    if not rejected:
        return None
    try:
        import pandas as pd

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        path_parquet = PROCESSED_DIR / "rejected.parquet"
        path_csv = PROCESSED_DIR / "rejected.csv"
        try:
            pd.DataFrame(rejected).to_parquet(path_parquet, index=False)
            return str(path_parquet)
        except (ImportError, ModuleNotFoundError):
            pd.DataFrame(rejected).to_csv(path_csv, index=False)
            return str(path_csv)
    except Exception:
        return None  # report generation must never crash the pipeline


def run_all(db: Session, write_report: bool = True) -> Dict[str, Any]:
    """Run every quality check; return the report dict (and write JSON)."""
    checks: List[Dict[str, Any]] = []

    # 1. Missing values
    missing = _missing_counts(db)
    total_missing = sum(missing.values())
    checks.append(
        _check(
            "missing_values",
            "completeness",
            "PASS" if total_missing == 0 else "FAIL",
            total_missing,
            json.dumps(missing),
        )
    )

    # 2. Staleness
    stale_hours = _stale_hours(db)
    if stale_hours is None:
        checks.append(_check("freshness", "timeliness", "FAIL", 0, "No forecast data at all"))
    else:
        limit = settings.forecast_freshness_hours
        status = "PASS" if stale_hours <= limit else "WARN"
        checks.append(
            _check(
                "freshness",
                "timeliness",
                status,
                0 if stale_hours <= limit else 1,
                f"Latest forecast run is {stale_hours:.1f}h old (limit {limit:.0f}h)",
            )
        )

    # 3. Duplicates
    dupes = _duplicate_counts(db)
    total_dupes = sum(dupes.values())
    checks.append(
        _check(
            "duplicate_keys",
            "uniqueness",
            "PASS" if total_dupes == 0 else "FAIL",
            total_dupes,
            json.dumps(dupes),
        )
    )

    # 4. Out-of-range physical values (+ quarantine)
    rejected = _find_out_of_range(db)
    checks.append(
        _check(
            "out_of_range_values",
            "validity",
            "PASS" if not rejected else "FAIL",
            len(rejected),
            f"{len(rejected)} rows violate physical bounds" if rejected else "All values within bounds",
        )
    )

    # 5. Geography
    geo_bad = _regions_outside_india(db)
    checks.append(
        _check(
            "region_coordinates",
            "validity",
            "PASS" if not geo_bad else "FAIL",
            len(geo_bad),
            f"{len(geo_bad)} regions outside India bounding box" if geo_bad else "All regions inside India bbox",
        )
    )

    fails = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    overall = "FAIL" if fails else ("WARN" if warns else "PASS")

    quarantine_path = _write_quarantine(rejected)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "checks": checks,
        "totals": {
            "checks_run": len(checks),
            "fails": fails,
            "warnings": warns,
            "quarantined_rows": len(rejected),
        },
        "quarantine_file": quarantine_path,
        "note": "Reported rows are quarantined, never silently corrected or replaced with synthetic values.",
    }

    if write_report:
        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            (REPORTS_DIR / "data_quality.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # read-only filesystems must not break the API

    return report
