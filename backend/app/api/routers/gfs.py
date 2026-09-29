"""GFS endpoints — NOAA/NCEP GFS forecast data retrieved directly from NOMADS.

No third-party weather API and no API key are involved: the ingestion service
in ``app.services.gfs`` talks to https://nomads.ncep.noaa.gov/ and this router
serves what has already been stored.

GFS is a numerical weather prediction model output. Responses always carry
``source_label`` and ``data_type`` so the frontend can never present the data
as an observation or an official local forecast (Safety §3).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.constants import VARIABLE_UNITS
from app.core.models import ForecastRun
from app.core.schemas import (
    GFSFileOut,
    GFSForecastPoint,
    GFSForecastResponse,
    GFSLatestCycleResponse,
    GFSRunOut,
    GFSStatusResponse,
    GFSUpdateResponse,
)
from app.services.gfs.config import get_gfs_config
from app.services.gfs.downloader import (
    get_active_cycle,
    list_known_runs,
    run_update,
)
from app.services.gfs.models import GFSCycle, GFSRunMetadata, parse_iso
from app.services.gfs.processor import load_processed, load_region_hours
from app.services.gfs.scheduler import get_scheduler

router = APIRouter()
logger = logging.getLogger("gfs.api")

DISCLAIMER = (
    "GFS is a numerical weather prediction (NWP) model forecast published by "
    "NOAA/NCEP and retrieved from the public NOMADS service. It is not an "
    "observation and not an official local forecast or warning."
)


def _run_out(meta: GFSRunMetadata) -> GFSRunOut:
    files = [
        GFSFileOut(
            forecast_hour=r.forecast_hour,
            status=r.status,
            file_name=r.file_name,
            size_bytes=r.size_bytes,
            valid_time=parse_iso(r.valid_time),
            checksum=r.checksum,
            error=r.error,
            retry_count=r.retry_count,
        )
        for r in sorted(meta.files, key=lambda f: f.forecast_hour)
    ]
    return GFSRunOut(
        model=meta.model,
        source=meta.source,
        source_label=meta.source_label,
        data_type=meta.data_type,
        run_date=meta.run_date,
        cycle=meta.cycle,
        run_time=parse_iso(meta.run_time),
        status=meta.status,
        is_active=meta.is_active,
        bounds=meta.bounds,
        variables=meta.variables,
        forecast_hours=meta.forecast_hours,
        files_valid=sum(1 for r in files if r.status in ("valid", "active")),
        files_total=len(files),
        files=files,
        discovered_at=parse_iso(meta.discovered_at),
        activated_at=parse_iso(meta.activated_at),
        processed_at=parse_iso(meta.processed_at),
        last_error=meta.last_error,
        notes=meta.notes,
    )


def _require_active() -> GFSCycle:
    config = get_gfs_config()
    cycle = get_active_cycle(config)
    if cycle is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No active GFS cycle stored yet. Run "
                "`python -m app.services.gfs.downloader` or POST /api/v1/gfs/update."
            ),
        )
    return cycle


@router.get("/gfs/status", response_model=GFSStatusResponse)
def gfs_status() -> GFSStatusResponse:
    """Current GFS ingestion state: active cycle, stored runs, scheduler."""
    config = get_gfs_config()
    scheduler = get_scheduler()
    cycle = get_active_cycle(config)

    active_run = None
    if cycle is not None:
        for meta in list_known_runs(config):
            if meta.cycle_obj.key == cycle.key:
                active_run = _run_out(meta)
                break

    return GFSStatusResponse(
        provider=f"{config.source_label} via {config.source_name}",
        source_url="https://nomads.ncep.noaa.gov/",
        api_key_required=False,
        data_type=config.data_type,
        disclaimer=DISCLAIMER,
        scheduler_running=scheduler.is_running(),
        update_interval_minutes=config.update_interval_minutes,
        last_check_at=parse_iso(scheduler.last_run_at),
        last_check_outcome=scheduler.last_outcome,
        active_run=active_run,
        stored_runs=len(list_known_runs(config)),
    )


@router.get("/gfs/runs", response_model=List[GFSRunOut])
def gfs_runs() -> List[GFSRunOut]:
    """All GFS cycles known to this installation, newest first."""
    return [_run_out(meta) for meta in list_known_runs(get_gfs_config())]


@router.get("/gfs/latest-cycle", response_model=GFSLatestCycleResponse)
def gfs_latest_cycle(check: bool = Query(True, description="Query NOMADS")):
    """Latest GFS cycle currently published on NOMADS.

    ``check=false`` returns the cycle that would be selected from the clock
    alone (no network request), which is useful for diagnostics.
    """
    from app.services.gfs.cycle_detector import candidate_cycles, detect_latest_cycle
    from app.services.gfs.client import NOMADSClient

    config = get_gfs_config()
    client = NOMADSClient(config)

    cycle = detect_latest_cycle(client, config) if check else candidate_cycles()[0]
    if cycle is None:
        return GFSLatestCycleResponse(
            available=False,
            reason="No GFS cycle is currently published on NOMADS",
            candidates=[
                {
                    "run_date": c.run_date,
                    "cycle": f"{c.cycle:02d}",
                    "available": False,
                }
                for c in candidate_cycles()
            ],
        )

    stored = get_active_cycle(config)
    return GFSLatestCycleResponse(
        run_date=cycle.run_date,
        cycle=f"{cycle.cycle:02d}",
        run_time=cycle.run_time,
        available=True,
        candidates=[
            {
                "run_date": c.run_date,
                "cycle": f"{c.cycle:02d}",
                "is_stored": stored is not None and stored.key == c.key,
            }
            for c in candidate_cycles()[:8]
        ],
    )


@router.post("/gfs/update", response_model=GFSUpdateResponse)
def gfs_update(
    force: bool = Query(False, description="Re-download the active cycle"),
    sync_db: bool = Query(True, description="Sync downloaded forecasts into application database"),
    db: Session = Depends(get_db),
):
    """Run one update check against NOMADS (detect → download → validate → process)."""
    config = get_gfs_config()
    config.ensure_dirs()
    meta, outcome = run_update(config=config, force=force)
    
    if sync_db and outcome in ("new_cycle", "up_to_date") and meta is not None:
        try:
            from app.services.gfs.processor import sync_gfs_to_db
            sync_gfs_to_db(db, cycle=meta.cycle_obj, config=config)

            # Score the freshly ingested run so confidence/prediction endpoints
            # immediately serve the live GFS run instead of the last seeded one.
            from datetime import datetime

            from app.services import reliability_service

            run_row = (
                db.query(ForecastRun)
                .filter(ForecastRun.run_time == meta.cycle_obj.run_time)
                .first()
            )
            if run_row is not None:
                scoring_rows = reliability_service.rows_for_current_run(
                    db, run_row.id, run_row.run_time
                )
                if scoring_rows:
                    counts = reliability_service.persist_predictions_for_run(
                        db, run_row.id, run_row.run_time, scoring_rows
                    )
                    logger.info("[GFS] scored live run: %s", counts)
        except Exception as exc:
            logger.warning("[GFS] Automatic DB sync after update failed: %s", exc)

    messages = {
        "new_cycle": "New GFS cycle downloaded, validated, processed and activated.",
        "up_to_date": "The stored GFS cycle is already the latest published one.",
        "no_cycle": "No GFS cycle is currently available on NOMADS; stored data kept.",
        "failed": "The latest GFS cycle could not be downloaded; previous run kept.",
    }
    return GFSUpdateResponse(
        outcome=outcome,
        message=messages.get(outcome, outcome),
        run=_run_out(meta) if meta is not None else None,
    )


@router.post("/gfs/sync-to-db")
def gfs_sync_to_db_endpoint(db: Session = Depends(get_db)):
    """Explicitly synchronize the active GFS cycle into the application database."""
    from app.services.gfs.processor import sync_gfs_to_db

    result = sync_gfs_to_db(db)
    if result.get("status") == "no_cycle":
        raise HTTPException(status_code=404, detail="No active GFS cycle found.")
    if result.get("status") == "no_data":
        raise HTTPException(
            status_code=404,
            detail="Active GFS cycle has not been processed into daily forecasts.",
        )
    return result


@router.get("/gfs/india-map")
def gfs_india_map(
    lead_day: int = Query(1, ge=1, le=5, description="Forecast lead day (1 to 5)"),
    force: bool = Query(False, description="Bypass disk cache and recalculate"),
):
    """India States & UTs Weather & Forecast Confidence Map data (36 States/UTs)."""
    from app.services.gfs.states_service import get_india_states_weather

    try:
        return get_india_states_weather(lead_day=lead_day, force_refresh=force)
    except Exception as exc:
        logger.error("[GFS] India map failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Unable to generate India weather map from GFS data: {exc}",
        )


@router.get("/gfs/forecast", response_model=GFSForecastResponse)
def gfs_forecast(
    lead_day: Optional[int] = Query(None, ge=1, le=10),
    region_id: Optional[str] = None,
    variable: Optional[str] = Query(None),
) -> GFSForecastResponse:
    """Daily region values from the active GFS cycle (lead_day 1–10)."""
    config = get_gfs_config()
    cycle = _require_active()
    payload = load_processed(cycle, config)
    if not payload:
        raise HTTPException(
            status_code=503,
            detail=f"GFS cycle {cycle.key} has not been processed yet.",
        )

    points: List[GFSForecastPoint] = []
    for row in payload.get("rows", []):
        if lead_day is not None and row.get("lead_day") != lead_day:
            continue
        if region_id is not None and row.get("region_id") != region_id:
            continue
        base = {
            "region_id": row["region_id"],
            "region_name": row["region_name"],
            "state": row["state"],
            "lead_day": row["lead_day"],
            "valid_time": parse_iso(row.get("valid_time")),
            "forecast_run": parse_iso(row.get("forecast_run")),
        }
        names = [variable] if variable else [
            v for v in VARIABLE_UNITS if v in row
        ]
        for name in names:
            points.append(
                GFSForecastPoint(
                    **base,
                    variable=name,
                    value=row.get(name),
                    unit=VARIABLE_UNITS.get(name, "unknown"),
                )
            )

    return GFSForecastResponse(
        source_label=config.source_label,
        data_type=config.data_type,
        run_date=payload["run_date"],
        cycle=payload["cycle"],
        run_time=parse_iso(payload.get("run_time")),
        count=len(points),
        points=points,
    )


@router.get("/gfs/hourly", response_model=GFSForecastResponse)
def gfs_hourly(
    region_id: Optional[str] = None,
    forecast_hour: Optional[int] = Query(None, ge=0, le=240),
) -> GFSForecastResponse:
    """3-hourly region values from the active GFS cycle."""
    config = get_gfs_config()
    cycle = _require_active()
    payload = load_region_hours(cycle, config)
    if not payload:
        raise HTTPException(
            status_code=503,
            detail=f"GFS cycle {cycle.key} has not been processed yet.",
        )

    points: List[GFSForecastPoint] = []
    for row in payload.get("rows", []):
        if region_id is not None and row.get("region_id") != region_id:
            continue
        if forecast_hour is not None and row.get("forecast_hour") != forecast_hour:
            continue
        for name in VARIABLE_UNITS:
            if name not in row:
                continue
            points.append(
                GFSForecastPoint(
                    region_id=row["region_id"],
                    region_name=row["region_name"],
                    state=row["state"],
                    lead_day=row["lead_day"],
                    valid_time=parse_iso(row.get("valid_time")),
                    forecast_run=parse_iso(row.get("forecast_run")),
                    variable=name,
                    value=row.get(name),
                    unit=VARIABLE_UNITS.get(name, "unknown"),
                )
            )

    return GFSForecastResponse(
        source_label=config.source_label,
        data_type=config.data_type,
        run_date=payload["run_date"],
        cycle=payload["cycle"],
        run_time=parse_iso(payload.get("run_time")),
        count=len(points),
        points=points,
    )
