"""GRIB2 -> project variables -> region series, with raw/processed separation.

Reads each validated GRIB2 file of a cycle one at a time (never holding a whole
cycle in memory), samples the project's 36 Indian regions by nearest grid cell,
and writes:

  * ``data/processed/gfs/<cycle>/grid.nc``   compact lat/lon NetCDF of the
    requested sub-region, all forecast hours, project variable names
  * ``data/processed/gfs/<cycle>/regions.json``  per-region 3-hourly values
  * ``data/processed/gfs/<cycle>/daily.json``    per-region daily aggregates
    matching the app's ``lead_day`` vocabulary

Raw GRIB2 stays untouched in ``data/raw/gfs``.

GFS values are a *numerical model forecast*, never an observation.
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.core.constants import VARIABLE_UNITS
from app.services.gfs.config import GFSConfig, get_gfs_config
from app.services.gfs.models import GFSCycle, GFSRunStatus, read_json, utcnow, write_json
from app.services.gfs.parser import (
    GRIBValidationError,
    parse_grib2,
    to_project_variables,
)
from app.services.regions_data import REGIONS

logger = logging.getLogger("gfs.processor")

# Variables exposed to the application, in a stable order.
PROCESSED_VARIABLES = ("rainfall", "temperature", "wind_speed", "humidity", "pressure")

# Variables aggregated as a daily mean rather than a daily sum.
MEAN_VARIABLES = ("temperature", "wind_speed", "humidity", "pressure")


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), digits)


def _nearest(dataset, name: str, lat: float, lon: float):
    """Nearest-cell sample that also collapses the (scalar) time dimension."""
    if name not in dataset:
        return None
    field = dataset[name]
    if "time" in field.dims:
        field = field.isel(time=0)
    if "step" in field.dims:
        field = field.isel(step=0)
    if "valid_time" in field.coords:
        field = field.drop_vars("valid_time", errors="ignore")
    try:
        return field.sel(latitude=lat, longitude=lon, method="nearest")
    except (KeyError, ValueError):
        return None


def process_cycle(
    cycle: GFSCycle,
    config: Optional[GFSConfig] = None,
    hours: Optional[List[int]] = None,
    write_grid: bool = True,
) -> Path:
    """Process every valid GRIB2 file of ``cycle`` into region series."""
    from app.services.gfs.downloader import load_run_metadata  # avoid import cycle

    config = config or get_gfs_config()
    meta = load_run_metadata(config, cycle)
    if meta is None:
        raise GRIBValidationError(f"No download metadata for cycle {cycle.label}")

    records = {
        r.forecast_hour: r
        for r in meta.files
        if r.status in (GFSRunStatus.VALID.value, GFSRunStatus.ACTIVE.value)
    }
    if not records:
        raise GRIBValidationError(f"No valid GRIB2 files for cycle {cycle.label}")

    wanted = sorted(hours if hours is not None else records.keys())
    out_dir = config.processed_cycle_dir(cycle.run_date, cycle.cycle)
    out_dir.mkdir(parents=True, exist_ok=True)

    region_rows: List[dict] = []
    grids: Dict[str, Dict[int, np.ndarray]] = {}
    grid_hours: List[int] = []
    lat_axis: Optional[np.ndarray] = None
    lon_axis: Optional[np.ndarray] = None

    for hour in wanted:
        record = records.get(hour)
        if record is None:
            continue
        path = config.cycle_dir(cycle.run_date, cycle.cycle) / record.file_name
        if not path.exists():
            logger.warning("[GFS] Missing raw file for f%03d, skipping", hour)
            continue

        try:
            dataset = parse_grib2(path, config)
        except GRIBValidationError as exc:
            logger.warning("[GFS] Skipping unreadable f%03d: %s", hour, exc)
            continue

        lat_axis = dataset["latitude"].values if lat_axis is None else lat_axis
        lon_axis = dataset["longitude"].values if lon_axis is None else lon_axis
        normalised = to_project_variables(dataset)

        if write_grid:
            # f000 carries no APCP accumulation, so grids are keyed by lead hour
            # and missing hours are filled with NaN rather than dropped.
            wrote_any = False
            for name in PROCESSED_VARIABLES:
                if name in normalised:
                    grids.setdefault(name, {})[hour] = (
                        normalised[name].values.astype("float32")
                    )
                    wrote_any = True
            if wrote_any:
                grid_hours.append(hour)

        valid_time = cycle.run_time + timedelta(hours=hour)
        for region in REGIONS:
            row = {
                "region_id": region["region_id"],
                "region_name": region["region_name"],
                "state": region["state"],
                "forecast_run": cycle.run_time.isoformat(),
                "forecast_hour": hour,
                "valid_time": valid_time.isoformat(),
                "lead_day": lead_day_for_hour(hour),
                "source": config.source_label,
                "data_type": config.data_type,
            }
            for name in PROCESSED_VARIABLES:
                da = _nearest(normalised, name, region["latitude"], region["longitude"])
                row[name] = _round(da.values.item() if da is not None else None)
            region_rows.append(row)

        logger.info(
            "[GFS] Processed f%03d -> %d regions (valid %s)",
            hour,
            len(REGIONS),
            valid_time.isoformat(),
        )
        dataset.close()

    if not region_rows:
        raise GRIBValidationError(
            f"No processable forecast hours for cycle {cycle.label}"
        )

    region_payload = {
        "model": config.model_name,
        "source": config.source_name,
        "source_label": config.source_label,
        "data_type": config.data_type,
        "disclaimer": (
            "GFS is a numerical weather prediction model output, not an "
            "observation and not an official local forecast."
        ),
        "run_date": cycle.run_date,
        "cycle": f"{cycle.cycle:02d}",
        "run_time": cycle.run_time.isoformat(),
        "processed_at": utcnow().isoformat(),
        "rows": region_rows,
    }
    write_json(out_dir / "regions.json", region_payload)

    daily = daily_aggregates(region_rows, cycle)
    write_json(
        out_dir / "daily.json",
        {
            **{k: v for k, v in region_payload.items() if k != "rows"},
            "rows": daily,
        },
    )

    if write_grid and grids:
        grid_path = out_dir / "grid.nc"
        _write_grid(grid_path, grids, grid_hours, cycle, config, lat_axis, lon_axis)
        logger.info("[GFS] Wrote grid %s (%.1f KiB)", grid_path, grid_path.stat().st_size / 1024)

    logger.info("[GFS] Processing complete for %s", cycle.label)
    return out_dir


def _write_grid(
    path: Path,
    grids: Dict[str, Dict[int, np.ndarray]],
    hours: List[int],
    cycle: GFSCycle,
    config: GFSConfig,
    lat_axis,
    lon_axis,
) -> None:
    """Write the sub-region grid for the whole cycle as one NetCDF file."""
    import xarray as xr

    # NetCDF has no timezone concept: store UTC as naive datetime64.
    times = np.array(
        [(cycle.run_time + timedelta(hours=h)).replace(tzinfo=None) for h in hours],
        dtype="datetime64[ns]",
    )
    datasets = {}
    for name, by_hour in grids.items():
        if not by_hour:
            continue
        shape = next(iter(by_hour.values())).shape
        stack = [
            by_hour.get(hour, np.full(shape, np.nan, dtype="float32"))
            for hour in hours
        ]
        datasets[name] = xr.DataArray(
            np.stack(stack).astype("float32"),
            dims=("time", "latitude", "longitude"),
            coords={
                "time": times,
                "latitude": lat_axis,
                "longitude": lon_axis,
            },
            attrs={"units": VARIABLE_UNITS.get(name, "unknown"), "long_name": name},
            name=name,
        )
    ds = xr.Dataset(datasets)
    ds.attrs.update(
        {
            "model": config.model_name,
            "source": config.source_name,
            "source_label": config.source_label,
            "data_type": config.data_type,
            "history": f"GFS {cycle.key} processed by app.services.gfs.processor",
            "note": "NWP model output — not an observation",
        }
    )
    ds.to_netcdf(path)
    ds.close()


def lead_day_for_hour(hour: int) -> int:
    """Day 1 = forecast hours 1..24, day 2 = 25..48, and so on.

    f000 is the analysis and belongs to the accumulation base of day 1 rather
    than to a day of its own.
    """
    return max(1, (hour - 1) // 24 + 1)


def daily_aggregates(rows: List[dict], cycle: GFSCycle) -> List[dict]:
    """Aggregate 3-hourly values to the application's ``lead_day`` scale.

    Day *d* covers forecast hours ``24*(d-1)+1 .. 24*d``. Rainfall is a
    *difference* of the GFS accumulated total across that window, because GFS
    ``tp`` accumulates from the run start; the other variables are daily means.
    """
    by_region: Dict[str, List[dict]] = {}
    for row in rows:
        by_region.setdefault(row["region_id"], []).append(row)

    out: List[dict] = []
    for region_id, region_rows in by_region.items():
        region_rows.sort(key=lambda r: r["forecast_hour"])
        by_hour = {r["forecast_hour"]: r for r in region_rows}
        lead_day = 1
        while True:
            low, high = 24 * (lead_day - 1) + 1, 24 * lead_day
            window = [r for r in region_rows if low <= r["forecast_hour"] <= high]
            if not window:
                break
            base = by_hour.get(low - 1)  # accumulation base (f000, f024, ...)

            record = {
                "region_id": region_id,
                "region_name": window[0]["region_name"],
                "state": window[0]["state"],
                "forecast_run": window[0]["forecast_run"],
                "lead_day": lead_day,
                "valid_time": window[-1]["valid_time"],
                "source": window[0]["source"],
                "data_type": window[0]["data_type"],
            }
            for name in PROCESSED_VARIABLES:
                values = [r[name] for r in window if r.get(name) is not None]
                if name == "rainfall":
                    last = values[-1] if values else None
                    base_value = base.get(name) if base else None
                    if last is None:
                        record[name] = None
                    elif base_value is not None and last > base_value:
                        record[name] = _round(last - base_value, 1)
                    else:
                        record[name] = _round(last, 1)
                    continue
                record[name] = (
                    _round(sum(values) / len(values)) if values else None
                )
            out.append(record)
            lead_day += 1
    return out


# ---------------------------------------------------------------------------
# Read-side helpers used by the API
# ---------------------------------------------------------------------------
def load_processed(cycle: GFSCycle, config: Optional[GFSConfig] = None) -> Optional[dict]:
    config = config or get_gfs_config()
    return read_json(config.processed_cycle_dir(cycle.run_date, cycle.cycle) / "daily.json")


def load_region_hours(cycle: GFSCycle, config: Optional[GFSConfig] = None) -> Optional[dict]:
    config = config or get_gfs_config()
    return read_json(config.processed_cycle_dir(cycle.run_date, cycle.cycle) / "regions.json")


def sync_gfs_to_db(
    db,
    cycle: Optional[GFSCycle] = None,
    config: Optional[GFSConfig] = None,
) -> dict:
    """Synchronize processed GFS daily forecasts into the application database.

    Populates ForecastRun and Forecast records so downstream services (reliability,
    predictions, verification, alerts) can consume live GFS data.
    """
    from app.core.models import Forecast, ForecastRun, Region
    from app.services.gfs.downloader import get_active_cycle
    from app.services.gfs.models import parse_iso

    config = config or get_gfs_config()
    target_cycle = cycle or get_active_cycle(config)
    if target_cycle is None:
        return {"status": "no_cycle", "synced_forecasts": 0}

    daily = load_processed(target_cycle, config)
    if not daily or "rows" not in daily:
        return {"status": "no_data", "synced_forecasts": 0}

    run_time = parse_iso(daily.get("run_time")) or target_cycle.run_time

    # Find or create ForecastRun
    run = db.query(ForecastRun).filter(ForecastRun.run_time == run_time).first()
    if not run:
        run = ForecastRun(
            run_time=run_time,
            source=config.source_name,
            model=config.model_version,
            ingested_at=utcnow(),
        )
        db.add(run)
        db.flush()

    # Map regions
    region_map = {r.region_id: r.id for r in db.query(Region).all()}

    synced_count = 0
    for row in daily["rows"]:
        reg_id = region_map.get(row.get("region_id"))
        if not reg_id:
            continue
        valid_time = parse_iso(row.get("valid_time"))
        if not valid_time:
            continue
        lead_day = row.get("lead_day", 1)

        for var_name in PROCESSED_VARIABLES:
            val = row.get(var_name)
            if val is None:
                continue

            existing = (
                db.query(Forecast)
                .filter(
                    Forecast.run_id == run.id,
                    Forecast.region_id == reg_id,
                    Forecast.variable == var_name,
                    Forecast.valid_time == valid_time,
                )
                .first()
            )
            unit = VARIABLE_UNITS.get(var_name, "units")
            if existing:
                existing.value = float(val)
                existing.lead_day = lead_day
                existing.unit = unit
            else:
                db.add(
                    Forecast(
                        run_id=run.id,
                        region_id=reg_id,
                        variable=var_name,
                        forecast_run=run_time,
                        valid_time=valid_time,
                        lead_day=lead_day,
                        value=float(val),
                        unit=unit,
                    )
                )
                synced_count += 1

    db.commit()
    logger.info(
        "[GFS] Synced %d forecast points to DB for run %s",
        synced_count,
        run_time.isoformat(),
    )
    return {
        "status": "success",
        "run_id": run.id,
        "run_time": run_time.isoformat(),
        "synced_forecasts": synced_count,
        "cycle": target_cycle.key,
    }



def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Process downloaded GFS GRIB2 files")
    parser.add_argument("--run-date", default=None, help="YYYYMMDD of the cycle")
    parser.add_argument("--cycle", type=int, default=None, help="Cycle hour (0/6/12/18)")
    args = parser.parse_args(argv)

    config = get_gfs_config()
    from app.services.gfs.downloader import get_active_cycle, list_known_runs

    if args.run_date and args.cycle is not None:
        cycle = GFSCycle(args.run_date, args.cycle)
    else:
        cycle = get_active_cycle(config)
    if cycle is None:
        runs = list_known_runs(config)
        if not runs:
            print("[GFS] No downloaded GFS cycle to process. Run the downloader first.")
            return 1
        cycle = runs[0].cycle_obj

    out_dir = process_cycle(cycle, config)
    daily = read_json(out_dir / "daily.json") or {}
    rows = daily.get("rows", [])
    print(f"[GFS] Processed {cycle.label} -> {out_dir}")
    print(f"[GFS] {len(rows)} region-day records, {len(REGIONS)} regions")
    for row in rows[:5]:
        print(
            f"    {row['region_id']:<7} day {row['lead_day']}  "
            f"T={row['temperature']}C  RH={row['humidity']}%  "
            f"wind={row['wind_speed']}m/s  rain={row['rainfall']}mm  "
            f"P={row['pressure']}hPa"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    sys.exit(main())
