"""Periodic GFS update loop.

    every GFS_UPDATE_INTERVAL_MINUTES
            ↓
    detect the latest published cycle
            ↓
    same as stored?  →  wait
            ↓ no
    download → validate → process → store → mark active

Runs as a plain daemon thread (no Celery/Redis dependency, matching the
prototype's "no external broker" posture) and is also safe to trigger once
from the API.

Run directly:

    python -m app.services.gfs.scheduler
    python -m app.services.gfs.scheduler --once
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from typing import Callable, List, Optional

from app.services.gfs.config import GFSConfig, get_gfs_config

logger = logging.getLogger("gfs.scheduler")


class GFSScheduler:
    """Runs :func:`app.services.gfs.downloader.run_update` on a fixed interval."""

    def __init__(
        self,
        config: Optional[GFSConfig] = None,
        interval_minutes: Optional[int] = None,
        on_update: Optional[Callable[[object, str], None]] = None,
    ) -> None:
        self.config = config or get_gfs_config()
        self.interval_minutes = interval_minutes or self.config.update_interval_minutes
        self.on_update = on_update
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_outcome: Optional[str] = None
        self.last_run_at: Optional[str] = None
        self.run_count = 0

    # -- single tick -------------------------------------------------------
    def run_once(self, hours: Optional[List[int]] = None, process: bool = True):
        from app.services.gfs.downloader import run_update

        logger.info("[GFS] Update check starting")
        meta, outcome = run_update(config=self.config, hours=hours, process=process)
        self.last_outcome = outcome
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        self.run_count += 1
        logger.info("[GFS] Update check finished: %s", outcome)
        if self.on_update is not None:
            try:
                self.on_update(meta, outcome)
            except Exception:  # pragma: no cover - callback must not kill the loop
                logger.exception("[GFS] on_update callback failed")
        return meta, outcome

    # -- loop --------------------------------------------------------------
    def _loop(self) -> None:
        from app.services.gfs.downloader import apply_retention

        interval = max(1, self.interval_minutes) * 60
        while not self._stop.is_set():
            try:
                self.run_once()
                apply_retention(self.config)
            except Exception:  # a cycle being unavailable must not kill the loop
                logger.exception("[GFS] Scheduler tick failed; will retry next interval")
            logger.info(
                "[GFS] Next check in %d minute(s)", max(1, self.interval_minutes)
            )
            self._stop.wait(interval)
        logger.info("[GFS] Scheduler stopped")

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.warning("[GFS] Scheduler already running")
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="gfs-scheduler", daemon=True
        )
        self._thread.start()
        logger.info(
            "[GFS] Automatic updates started (every %d minute(s))",
            self.interval_minutes,
        )

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


_scheduler: Optional[GFSScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> GFSScheduler:
    """Process-wide scheduler singleton (started by the API lifespan hook)."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = GFSScheduler()
        return _scheduler


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Continuously refresh GFS data from NOAA NOMADS"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run a single update check and exit"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Minutes between checks (default: GFS_UPDATE_INTERVAL_MINUTES)",
    )
    parser.add_argument(
        "--hours", type=int, nargs="+", default=None, help="Restrict forecast hours"
    )
    args = parser.parse_args(argv)

    scheduler = GFSScheduler(interval_minutes=args.interval)

    if args.once:
        meta, outcome = scheduler.run_once(hours=args.hours)
        print(f"[GFS] Outcome: {outcome}")
        if meta is not None:
            print(f"[GFS] Cycle : {meta.run_date} {meta.cycle} UTC ({meta.status})")
        return 0 if outcome in ("new_cycle", "up_to_date") else 1

    def _handle_signal(signum, frame):  # pragma: no cover - signal path
        logger.info("[GFS] Signal %s received; shutting down", signum)
        scheduler.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):  # pragma: no cover - non-main thread
            pass

    scheduler.start()
    print(
        f"[GFS] Watching for new GFS cycles every {scheduler.interval_minutes} minute(s). "
        "Press Ctrl+C to stop."
    )
    try:
        while scheduler.is_running():
            scheduler._thread.join(timeout=1.0)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        pass
    finally:
        scheduler.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    sys.exit(main())
