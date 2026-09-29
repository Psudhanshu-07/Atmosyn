"""GFS download orchestration: dedupe, validate, quarantine, activate.

    Detect cycle -> download each required f-hour -> validate GRIB2
                 -> record metadata -> mark run active

Duplicate downloads are prevented by a JSON sidecar index
(``data/raw/gfs/index/<run_date>_<cycle>.json``) plus an on-disk existence and
size check, so a crash or restart cannot cause a re-download of files that are
already present and valid.

Run directly:

    python -m app.services.gfs.downloader
    python -m app.services.gfs.downloader --hours 0 6 12 --no-process
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from app.services.gfs.client import (
    NOMADSClient,
    GFSNotAvailableError,
    GFSTransientError,
)
from app.services.gfs.config import GFSConfig, get_gfs_config
from app.services.gfs.cycle_detector import detect_latest_cycle
from app.services.gfs.models import (
    GFSCycle,
    GFSFileRecord,
    GFSRunMetadata,
    GFSRunStatus,
    read_json,
    sha256_of,
    utcnow,
    write_json,
)
from app.services.gfs.parser import GRIBValidationError, validate_grib2

logger = logging.getLogger("gfs.downloader")

HOUR_FILE_TEMPLATE = "gfs_{run_date}_{cycle:02d}z_f{fhour:03d}.grib2"


# ---------------------------------------------------------------------------
# Metadata index
# ---------------------------------------------------------------------------
def index_path(config: GFSConfig, cycle: GFSCycle) -> Path:
    return config.index_dir / f"{cycle.key}.json"


def load_run_metadata(
    config: GFSConfig, cycle: GFSCycle
) -> Optional[GFSRunMetadata]:
    data = read_json(index_path(config, cycle))
    if data is None:
        return None
    return GFSRunMetadata.from_dict(data)


def save_run_metadata(config: GFSConfig, meta: GFSRunMetadata) -> None:
    write_json(index_path(config, meta.cycle_obj), meta.to_dict())


def get_active_cycle(config: Optional[GFSConfig] = None) -> Optional[GFSCycle]:
    """The cycle currently marked active on disk (the one the API serves)."""
    config = config or get_gfs_config()
    data = read_json(config.active_pointer)
    if not data:
        return None
    try:
        return GFSCycle(str(data["run_date"]), int(data["cycle"]))
    except (KeyError, TypeError, ValueError):
        return None


def set_active_cycle(cycle: GFSCycle, config: Optional[GFSConfig] = None) -> None:
    config = config or get_gfs_config()
    config.ensure_dirs()
    # Demote any previously active run.
    current = get_active_cycle(config)
    if current is not None and current.key != cycle.key:
        previous = load_run_metadata(config, current)
        if previous is not None:
            previous.is_active = False
            previous.status = GFSRunStatus.VALID.value
            save_run_metadata(config, previous)

    meta = load_run_metadata(config, cycle)
    if meta is not None:
        meta.is_active = True
        meta.status = GFSRunStatus.ACTIVE.value
        meta.activated_at = utcnow().isoformat()
        save_run_metadata(config, meta)

    write_json(
        config.active_pointer,
        {
            "model": config.model_name,
            "source": config.source_name,
            "source_label": config.source_label,
            "data_type": config.data_type,
            "run_date": cycle.run_date,
            "cycle": f"{cycle.cycle:02d}",
            "cycle_time": cycle.run_time.isoformat(),
            "activated_at": utcnow().isoformat(),
        },
    )
    logger.info("[GFS] Cycle activated: %s", cycle.label)


def list_known_runs(config: Optional[GFSConfig] = None) -> List[GFSRunMetadata]:
    config = config or get_gfs_config()
    if not config.index_dir.exists():
        return []
    runs = []
    for path in sorted(config.index_dir.glob("*.json")):
        if path.name == "active_cycle.json":
            continue
        data = read_json(path)
        if data:
            runs.append(GFSRunMetadata.from_dict(data))
    return sorted(runs, key=lambda m: m.cycle_obj.run_time, reverse=True)


# ---------------------------------------------------------------------------
# Per-file download + validation
# ---------------------------------------------------------------------------
def _record_for(meta: GFSRunMetadata, forecast_hour: int) -> GFSFileRecord:
    for record in meta.files:
        if record.forecast_hour == forecast_hour:
            return record
    record = GFSFileRecord(
        cycle=f"{meta.cycle_obj.cycle:02d}",
        run_date=meta.run_date,
        forecast_hour=forecast_hour,
    )
    meta.files.append(record)
    meta.files.sort(key=lambda r: r.forecast_hour)
    return record


def is_file_current(record: GFSFileRecord, path: Path) -> bool:
    """Dedupe check: a record is current only if the file is still on disk,
    unchanged in size and previously validated."""
    if record.status not in (
        GFSRunStatus.VALID.value,
        GFSRunStatus.ACTIVE.value,
    ):
        return False
    if not path.exists():
        return False
    if path.stat().st_size != record.size_bytes:
        return False
    return record.checksum == sha256_of(path)


def download_hour(
    client: NOMADSClient,
    config: GFSConfig,
    cycle: GFSCycle,
    forecast_hour: int,
    meta: GFSRunMetadata,
    force: bool = False,
) -> GFSFileRecord:
    """Download and validate one forecast hour (idempotent)."""
    dest = config.cycle_dir(cycle.run_date, cycle.cycle) / HOUR_FILE_TEMPLATE.format(
        run_date=cycle.run_date, cycle=cycle.cycle, fhour=forecast_hour
    )
    record = _record_for(meta, forecast_hour)
    record.file_name = dest.name

    if not force and is_file_current(record, dest):
        logger.info("[GFS] f%03d already downloaded and valid, skipping", forecast_hour)
        return record

    record.status = GFSRunStatus.DOWNLOADING.value
    record.url = client.url_for_hour(cycle.run_date, cycle.cycle, forecast_hour)
    save_run_metadata(config, meta)
    logger.info(
        "[GFS] Downloading f%03d for %s (run %s, cycle %02d UTC)",
        forecast_hour,
        config.source_label,
        cycle.run_date,
        cycle.cycle,
    )

    try:
        result = client.download(cycle.run_date, cycle.cycle, forecast_hour, dest)
    except GFSNotAvailableError as exc:
        record.status = GFSRunStatus.INVALID.value
        record.error = str(exc)
        record.retry_count = 0
        meta.last_error = f"f{forecast_hour:03d}: {exc}"
        logger.warning(
            "[GFS] f%03d not available yet (run %s cycle %02d): %s",
            forecast_hour,
            cycle.run_date,
            cycle.cycle,
            exc,
        )
        return record
    except GFSTransientError as exc:
        record.status = GFSRunStatus.INVALID.value
        record.error = str(exc)
        record.retry_count = config.max_retries
        meta.last_error = f"f{forecast_hour:03d}: {exc}"
        logger.error(
            "[GFS] f%03d download failed after retries (run %s cycle %02d, url=%s): %s",
            forecast_hour,
            cycle.run_date,
            cycle.cycle,
            record.url,
            exc,
        )
        return record

    record.retry_count = result.attempts
    record.size_bytes = result.size_bytes
    record.downloaded_at = utcnow().isoformat()
    record.run_time = cycle.run_time.isoformat()
    record.valid_time = (
        cycle.run_time + timedelta(hours=forecast_hour)
    ).isoformat()

    logger.info("[GFS] Validating GRIB2 f%03d", forecast_hour)
    validation = validate_grib2(dest, config)
    if not validation.valid:
        record.status = GFSRunStatus.INVALID.value
        record.error = validation.reason
        quarantine(config, dest, validation.reason)
        meta.last_error = f"f{forecast_hour:03d}: {validation.reason}"
        logger.error(
            "[GFS] f%03d failed validation (run %s cycle %02d): %s -> quarantined",
            forecast_hour,
            cycle.run_date,
            cycle.cycle,
            validation.reason,
        )
        return record

    record.checksum = sha256_of(dest)
    record.status = GFSRunStatus.VALID.value
    record.error = None
    logger.info(
        "[GFS] f%03d valid (%.1f KiB, vars=%s, lat=%s, lon=%s)",
        forecast_hour,
        result.size_bytes / 1024,
        ",".join(validation.variables),
        validation.latitude_range,
        validation.longitude_range,
    )
    return record


def quarantine(config: GFSConfig, path: Path, reason: str) -> Optional[Path]:
    """Move a corrupt/incomplete file out of the active directory."""
    if not path.exists():
        return None
    config.quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = config.quarantine_dir / f"{path.name}.{int(datetime.now(timezone.utc).timestamp())}"
    shutil.move(str(path), str(target))
    write_json(
        target.with_suffix(target.suffix + ".reason.json"),
        {"reason": reason, "quarantined_at": utcnow().isoformat()},
    )
    return target


# ---------------------------------------------------------------------------
# Run-level orchestration
# ---------------------------------------------------------------------------
def new_run_metadata(config: GFSConfig, cycle: GFSCycle) -> GFSRunMetadata:
    return GFSRunMetadata(
        model=config.model_name,
        source=config.source_name,
        run_date=cycle.run_date,
        cycle=f"{cycle.cycle:02d}",
        run_time=cycle.run_time.isoformat(),
        discovered_at=utcnow().isoformat(),
        bounds=config.bounds.as_dict(),
        variables=[s.short_name for s in config.variables],
        forecast_hours=list(config.forecast_hours),
        data_type=config.data_type,
        source_label=config.source_label,
    )


def download_cycle(
    cycle: GFSCycle,
    client: Optional[NOMADSClient] = None,
    config: Optional[GFSConfig] = None,
    hours: Optional[List[int]] = None,
    force: bool = False,
    process: bool = True,
    activate: bool = True,
) -> GFSRunMetadata:
    """Download every required forecast hour of one cycle, then process it."""
    config = config or get_gfs_config()
    config.ensure_dirs()
    client = client or NOMADSClient(config)
    hours = list(hours if hours is not None else config.forecast_hours)

    meta = load_run_metadata(config, cycle) or new_run_metadata(config, cycle)
    meta.status = GFSRunStatus.DOWNLOADING.value
    meta.forecast_hours = hours
    save_run_metadata(config, meta)

    for hour in hours:
        download_hour(client, config, cycle, hour, meta, force=force)
        save_run_metadata(config, meta)

    valid = [r for r in meta.files if r.status == GFSRunStatus.VALID.value]
    invalid = [r for r in meta.files if r.status == GFSRunStatus.INVALID.value]
    if not valid:
        meta.status = GFSRunStatus.INVALID.value
    elif invalid:
        meta.status = GFSRunStatus.PARTIAL.value
        meta.notes.append(
            f"{len(invalid)} of {len(hours)} forecast hours unavailable or invalid"
        )
    else:
        meta.status = GFSRunStatus.VALID.value
    save_run_metadata(config, meta)

    if process and valid:
        from app.services.gfs.processor import process_cycle  # local import: heavy

        try:
            process_cycle(cycle, config=config)
        except GRIBValidationError as exc:
            logger.error("[GFS] Processing failed for %s: %s", cycle.label, exc)
            meta.last_error = f"processing: {exc}"
            save_run_metadata(config, meta)
        else:
            meta.processed_at = utcnow().isoformat()
            save_run_metadata(config, meta)
            logger.info("[GFS] Processing complete for %s", cycle.label)

    if activate and valid:
        set_active_cycle(cycle, config)
        meta = load_run_metadata(config, cycle) or meta
    save_run_metadata(config, meta)
    return meta


def run_update(
    client: Optional[NOMADSClient] = None,
    config: Optional[GFSConfig] = None,
    hours: Optional[List[int]] = None,
    force: bool = False,
    process: bool = True,
) -> Tuple[Optional[GFSRunMetadata], str]:
    """One scheduler tick: detect the newest cycle, download only if new.

    Returns ``(metadata, outcome)`` where outcome is one of
    ``new_cycle`` / ``up_to_date`` / ``no_cycle`` / ``failed``.
    """
    config = config or get_gfs_config()
    config.ensure_dirs()
    client = client or NOMADSClient(config)

    cycle = detect_latest_cycle(client, config)
    if cycle is None:
        logger.warning("[GFS] No available cycle; keeping currently stored data")
        return None, "no_cycle"

    current = get_active_cycle(config)
    if current is not None:
        logger.info(
            "[GFS] Current stored cycle: %s", current.label
        )
    if current is not None and current.key == cycle.key and not force:
        logger.info(
            "[GFS] No new cycle (stored %s == latest %s); nothing to download",
            current.key,
            cycle.key,
        )
        return load_run_metadata(config, cycle), "up_to_date"

    logger.info("[GFS] New cycle detected: %s", cycle.label)
    meta = download_cycle(
        cycle, client=client, config=config, hours=hours, force=force, process=process
    )
    if meta.status == GFSRunStatus.INVALID.value:
        logger.error(
            "[GFS] Cycle %s could not be downloaded (%s); keeping previous run",
            cycle.label,
            meta.last_error,
        )
        return meta, "failed"
    return meta, "new_cycle"


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
def apply_retention(config: Optional[GFSConfig] = None) -> List[str]:
    """Delete raw and processed data older than ``retention_days``.

    The active run and anything newer than the retention window is kept.
    """
    config = config or get_gfs_config()
    if config.retention_days <= 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.retention_days)
    active = get_active_cycle(config)
    removed: List[str] = []

    for run in list_known_runs(config):
        cycle = run.cycle_obj
        if active is not None and cycle.key == active.key:
            continue
        if cycle.run_time >= cutoff:
            continue
        for directory in (
            config.cycle_dir(cycle.run_date, cycle.cycle),
            config.processed_cycle_dir(cycle.run_date, cycle.cycle),
        ):
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
                removed.append(str(directory))
        path = index_path(config, cycle)
        if path.exists():
            path.unlink()
            removed.append(str(path))
        logger.info("[GFS] Retention: removed old cycle %s", cycle.label)

    if removed:
        logger.info("[GFS] Retention: %d path(s) removed (cutoff %s)", len(removed), cutoff)
    return removed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Download GFS data from NOAA NOMADS")
    parser.add_argument(
        "--hours",
        type=int,
        nargs="+",
        default=None,
        help="Forecast hours to fetch (default: GFS_FORECAST_START..END)",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    parser.add_argument(
        "--no-process", action="store_true", help="Skip GRIB2 -> region extraction"
    )
    parser.add_argument(
        "--no-activate", action="store_true", help="Do not mark the cycle active"
    )
    parser.add_argument(
        "--retention-only", action="store_true", help="Only apply retention and exit"
    )
    args = parser.parse_args(argv)

    config = get_gfs_config()
    config.ensure_dirs()

    if args.retention_only:
        removed = apply_retention(config)
        print(f"[GFS] Retention removed {len(removed)} path(s)")
        return 0

    meta, outcome = run_update(
        config=config, hours=args.hours, force=args.force, process=not args.no_process
    )
    print(f"[GFS] Update outcome: {outcome}")
    if meta is None:
        print("[GFS] No cycle available; previously stored data is unchanged.")
        return 1

    print(f"[GFS] Run      : {meta.run_date} {meta.cycle} UTC")
    print(f"[GFS] Source   : {meta.source_label} ({meta.source})")
    print(f"[GFS] Status   : {meta.status}")
    print(f"[GFS] Active   : {meta.is_active}")
    valid = [r for r in meta.files if r.status == GFSRunStatus.VALID.value]
    print(f"[GFS] Files    : {len(valid)}/{len(meta.files)} valid")
    for record in sorted(meta.files, key=lambda r: r.forecast_hour):
        print(
            f"    f{record.forecast_hour:03d}  {record.status:<9} "
            f"{record.size_bytes / 1024:>9.1f} KiB  {record.error or ''}"
        )
    apply_retention(config)
    return 0 if valid else 1


if __name__ == "__main__":  # pragma: no cover - CLI
    sys.exit(main())
