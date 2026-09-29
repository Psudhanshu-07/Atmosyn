"""Automatic detection of the latest usable GFS model cycle.

    Current UTC time
          ↓
    Enumerate candidate cycles (00/06/12/18 UTC, newest first)
          ↓
    Skip cycles inside the NOAA publication delay
          ↓
    Ask NOMADS whether the cycle is published
          ↓
    First available cycle wins

Run directly:

    python -m app.services.gfs.cycle_detector
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.services.gfs.client import (
    CycleAvailability,
    GFSError,
    NOMADSClient,
)
from app.services.gfs.config import GFSConfig, get_gfs_config
from app.services.gfs.models import GFSCycle

logger = logging.getLogger("gfs.cycle_detector")

LOOKBACK_DAYS = 3  # how far back to search if recent cycles are unavailable


def candidate_cycles(
    now: Optional[datetime] = None,
    config: Optional[GFSConfig] = None,
) -> List[GFSCycle]:
    """Cycles that could plausibly be published, newest first.

    A cycle is skipped if its nominal run time is newer than
    ``cycle_delay_hours`` — NOMADS needs time to finish and publish the run,
    so the newest few candidates are usually still "future data".
    """
    config = config or get_gfs_config()
    now = now or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)

    latest_nominal = now - timedelta(hours=config.cycle_delay_hours)
    result: List[GFSCycle] = []
    for day_offset in range(LOOKBACK_DAYS + 1):
        day = (now - timedelta(days=day_offset)).date()
        for cycle_hour in sorted(config.cycles, reverse=True):
            run_time = datetime(
                day.year, day.month, day.day, cycle_hour, tzinfo=timezone.utc
            )
            if run_time <= latest_nominal:
                result.append(GFSCycle(day.strftime("%Y%m%d"), cycle_hour))
    return result


def detect_latest_cycle(
    client: Optional[NOMADSClient] = None,
    config: Optional[GFSConfig] = None,
    now: Optional[datetime] = None,
) -> Optional[GFSCycle]:
    """Return the newest cycle NOMADS currently serves, or ``None``."""
    config = config or get_gfs_config()
    client = client or NOMADSClient(config)
    logger.info("[GFS] Checking latest available cycle...")

    for cycle in candidate_cycles(now=now, config=config):
        try:
            availability = client.check_cycle(cycle.run_date, cycle.cycle)
        except GFSError as exc:
            logger.warning(
                "[GFS] Availability probe failed for %s: %s", cycle.label, exc
            )
            continue
        if availability.available:
            logger.info("[GFS] Latest available cycle: %s", cycle.label)
            return cycle

    logger.warning("[GFS] No available GFS cycle found in the lookback window")
    return None


def report(
    client: Optional[NOMADSClient] = None,
    config: Optional[GFSConfig] = None,
    now: Optional[datetime] = None,
) -> List[CycleAvailability]:
    """Availability of each candidate cycle, for CLI/operator inspection."""
    config = config or get_gfs_config()
    client = client or NOMADSClient(config)
    results: List[CycleAvailability] = []
    for cycle in candidate_cycles(now=now, config=config):
        try:
            results.append(client.check_cycle(cycle.run_date, cycle.cycle))
        except GFSError as exc:
            results.append(
                CycleAvailability(
                    cycle_key=cycle.key,
                    available=False,
                    reason=str(exc),
                    checked_at=datetime.now(timezone.utc).isoformat(),
                )
            )
    return results


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Detect the latest GFS cycle on NOMADS")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show availability for every candidate cycle",
    )
    args = parser.parse_args(argv)

    config = get_gfs_config()
    client = NOMADSClient(config)

    if args.all:
        for availability in report(client, config):
            mark = "AVAILABLE" if availability.available else "unavailable"
            print(
                f"  {availability.cycle_key}: {mark} "
                f"(probe f{availability.probe_hour:03d}, {availability.reason})"
            )

    latest = detect_latest_cycle(client, config)
    if latest is None:
        print("[GFS] No usable GFS cycle is currently published on NOMADS.")
        return 1

    print(f"[GFS] Latest available cycle: {latest.label}")
    print(f"        run_date : {latest.run_date}")
    print(f"        cycle    : {latest.cycle:02d} UTC")
    print(f"        run_time : {latest.run_time.isoformat()}")
    print(f"        dir      : {latest.nomads_sort_dir(config.datasource)}")
    print(f"        hours    : {config.forecast_hours[0]:03d}-{config.forecast_hours[-1]:03d} "
          f"every {config.forecast_hours[1] - config.forecast_hours[0] if len(config.forecast_hours) > 1 else 0}h")
    print(f"        variables: {', '.join(s.short_name for s in config.variables)}")
    print(f"        bounds   : {config.bounds.as_dict()}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    sys.exit(main())
