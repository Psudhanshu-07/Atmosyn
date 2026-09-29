"""HTTP client for the NOAA/NCEP NOMADS GRIB filter.

Public service, no API key: https://nomads.ncep.noaa.gov/

Responsibilities:
  * build NOMADS request URLs dynamically (never hard-coded dates/cycles),
  * probe whether a cycle is published yet (cheap, one small request),
  * download GRIB2 with timeout / retry / exponential backoff,
  * write to a ``.part`` file and move atomically so a partial download is
    never mistaken for a complete one.

NOAA etiquette (spec §15): a small delay is applied between successive
requests, retries are bounded, and 403/404 ("not yet available") is never
retried.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, Sequence
from urllib.parse import urlencode

import requests

from app.services.gfs.config import GFSBounds, GFSConfig, GFSVariableSpec, get_gfs_config

logger = logging.getLogger("gfs.client")

NOMADS_USER_AGENT = "forecast-bust-gfs/1.0 (public NOMADS client)"

# NOMADS answers 403 "Request for Future Data" for cycles it has not
# published yet, and 404 for files outside the rolling buffer.
STATUS_NOT_AVAILABLE = (403, 404)


class GFSError(Exception):
    """Base error for the GFS ingestion layer."""


class GFSNotAvailableError(GFSError):
    """The cycle/file is not published on NOMADS yet (403/404)."""


class GFSTransientError(GFSError):
    """NOMADS was unreachable, timed out or returned a server error."""


@dataclass
class DownloadResult:
    path: str
    size_bytes: int
    status_code: int
    attempts: int
    url: str


@dataclass
class CycleAvailability:
    cycle_key: str
    available: bool
    status_code: Optional[int] = None
    reason: str = ""
    probe_hour: int = 0
    checked_at: Optional[str] = None

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.available


def build_gfs_url(
    date,
    cycle,
    forecast_hour,
    variables: Sequence[str],
    levels: Optional[Iterable[str]] = None,
    bounds: Optional[GFSBounds] = None,
    datasource: str = "gfs",
    file_pattern: str = "{ds}.t{cycle:02d}z.pgrb2.0p25.f{fhour:03d}",
) -> str:
    """Build a NOMADS GRIB filter URL.

    ``date`` may be ``YYYYMMDD`` or a ``datetime``/``date``. ``levels`` are
    NOMADS ``lev_`` keys such as ``"2_m_above_ground"``. When ``bounds`` is
    supplied the ``subregion`` flag is added — NOMADS ignores
    leftlon/rightlon/toplat/bottomlat without it and would silently return the
    full global grid.
    """
    if isinstance(date, (datetime,)):
        date_str = date.strftime("%Y%m%d")
    elif hasattr(date, "strftime"):
        date_str = date.strftime("%Y%m%d")
    else:
        date_str = str(date).replace("-", "")

    file_name = file_pattern.format(
        ds=datasource, cycle=int(cycle), fhour=int(forecast_hour)
    )

    params: Dict[str, str] = {"file": file_name}
    for var in variables:
        params[f"var_{var}"] = "on"
    for lev in levels or ():
        params[f"lev_{lev}"] = "on"

    if bounds is not None:
        params["subregion"] = ""
        params.update(bounds.as_params())

    params["dir"] = f"/{datasource}.{date_str}/{int(cycle):02d}/atmos"

    return f"https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?{urlencode(params)}"


def _level_keys(variables: Sequence[GFSVariableSpec]) -> list[str]:
    seen, out = set(), []
    for spec in variables:
        if spec.level_name not in seen:
            seen.add(spec.level_name)
            out.append(spec.level_name)
    return out


class NOMADSClient:
    """Thin, polite wrapper around the NOMADS GRIB filter."""

    def __init__(
        self,
        config: Optional[GFSConfig] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.config = config or get_gfs_config()
        self.base_url = self.config.base_url
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": NOMADS_USER_AGENT})
        self._last_request_at: Optional[float] = None
        self._availability_cache: Dict[str, CycleAvailability] = {}

    # -- etiquette ---------------------------------------------------------
    def _throttle(self) -> None:
        delay = self.config.request_delay
        if delay <= 0 or self._last_request_at is None:
            return
        wait = delay - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    # -- URL building ------------------------------------------------------
    def url_for_hour(self, date, cycle: int, forecast_hour: int) -> str:
        return build_gfs_url(
            date=date,
            cycle=cycle,
            forecast_hour=forecast_hour,
            variables=[s.short_name for s in self.config.variables],
            levels=_level_keys(self.config.variables),
            bounds=self.config.bounds,
            datasource=self.config.datasource,
            file_pattern=self.config.file_pattern,
        )

    def _probe_url(self, date, cycle: int, forecast_hour: int) -> str:
        """Minimal request (1 variable, tiny box) used only to test existence."""
        tiny = GFSBounds(
            left_lon=min(self.config.bounds.left_lon, 20.0),
            right_lon=min(self.config.bounds.left_lon + 1.0, 179.0),
            bottom_lat=min(self.config.bounds.bottom_lat, 20.0),
            top_lat=min(self.config.bounds.bottom_lat + 1.0, 89.0),
        )
        return build_gfs_url(
            date=date,
            cycle=cycle,
            forecast_hour=forecast_hour,
            variables=["TMP"],
            levels=["2_m_above_ground"],
            bounds=tiny,
            datasource=self.config.datasource,
            file_pattern=self.config.file_pattern,
        )

    # -- availability ------------------------------------------------------
    def check_cycle(
        self,
        date,
        cycle: int,
        probe_hour: Optional[int] = None,
        use_cache: bool = True,
    ) -> CycleAvailability:
        """Is this cycle published on NOMADS yet?

        Probes the analysis hour (f000) by default because GFS pgrb2 files are
        posted in reverse lead-time order, so f000 is the last one available and
        therefore the conservative "cycle is usable" signal.
        """
        date_str = str(date).replace("-", "")
        key = f"{date_str}_{int(cycle):02d}"
        if use_cache and key in self._availability_cache:
            return self._availability_cache[key]

        hour = self.config.forecast_hours[0] if probe_hour is None else probe_hour
        url = self._probe_url(date_str, cycle, hour)
        logger.info("[GFS] Checking availability of cycle %s (probe f%03d)", key, hour)

        try:
            result = self._request_with_retry(url, expect_grib=False)
        except GFSNotAvailableError:
            result = None

        available = result is not None and result.status_code == 200 and result.size_bytes > 0
        avail = CycleAvailability(
            cycle_key=key,
            available=available,
            status_code=result.status_code if result else 403,
            reason="" if available else "not yet published on NOMADS",
            probe_hour=hour,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(
            "[GFS] Cycle %s %s (HTTP %s)",
            key,
            "available" if available else "not available",
            avail.status_code,
        )
        self._availability_cache[key] = avail
        return avail

    # -- download ----------------------------------------------------------
    def download(
        self,
        date,
        cycle: int,
        forecast_hour: int,
        dest_path,
    ) -> DownloadResult:
        """Download one GRIB2 file to ``dest_path`` (atomic replace)."""
        url = self.url_for_hour(date, cycle, forecast_hour)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        result = self._request_with_retry(url, expect_grib=True, dest_path=dest_path)
        logger.info(
            "[GFS] Downloaded f%03d of %s_%02d -> %s (%.1f KiB, %d attempt(s))",
            forecast_hour,
            date,
            cycle,
            dest_path.name,
            result.size_bytes / 1024,
            result.attempts,
        )
        return result

    # -- internals ---------------------------------------------------------
    def _request_with_retry(
        self,
        url: str,
        expect_grib: bool,
        dest_path=None,
        attempts_override: Optional[int] = None,
    ) -> DownloadResult:
        max_attempts = attempts_override or max(1, self.config.max_retries)
        last_error: Optional[Exception] = None
        last_status: Optional[int] = None

        for attempt in range(1, max_attempts + 1):
            self._throttle()
            started = time.monotonic()
            try:
                with self.session.get(
                    url, stream=True, timeout=self.config.http_timeout
                ) as response:
                    self._last_request_at = time.monotonic()
                    last_status = response.status_code

                    if response.status_code in STATUS_NOT_AVAILABLE:
                        # Not a transient fault: NOMADS has not published it.
                        raise GFSNotAvailableError(
                            f"NOMADS returned HTTP {response.status_code} "
                            f"(data not yet available) for {url}"
                        )
                    if response.status_code >= 400:
                        raise GFSTransientError(
                            f"NOMADS returned HTTP {response.status_code} for {url}"
                        )

                    payload = response.content if dest_path is None else None
                    written = self._stream_to_disk(response, dest_path) if dest_path else 0
                    size = written or len(payload or b"")

                    if expect_grib and size <= 0:
                        raise GFSTransientError(f"Empty response body from {url}")

                    return DownloadResult(
                        path=str(dest_path) if dest_path else "",
                        size_bytes=size,
                        status_code=response.status_code,
                        attempts=attempt,
                        url=url,
                    )
            except GFSNotAvailableError:
                raise
            except (requests.Timeout, requests.ConnectionError, GFSTransientError) as exc:
                last_error = exc
                logger.warning(
                    "[GFS] Request failed (attempt %d/%d) after %.1fs: %s",
                    attempt,
                    max_attempts,
                    time.monotonic() - started,
                    exc,
                )
                if dest_path is not None and dest_path.exists():
                    dest_path.unlink(missing_ok=True)
                if attempt < max_attempts:
                    backoff = self.config.backoff_base ** attempt
                    logger.info("[GFS] Retrying in %.1fs", backoff)
                    time.sleep(backoff)

        raise GFSTransientError(
            f"NOMADS request failed after {max_attempts} attempt(s) "
            f"(last status {last_status}): {last_error}"
        )

    @staticmethod
    def _stream_to_disk(response: requests.Response, dest_path) -> int:
        """Stream to ``<dest>.part`` then atomically move into place."""
        part_path = dest_path.with_suffix(dest_path.suffix + ".part")
        written = 0
        try:
            with part_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1 << 18):
                    if chunk:
                        fh.write(chunk)
                        written += len(chunk)
        except Exception:
            part_path.unlink(missing_ok=True)
            raise
        if written == 0:
            part_path.unlink(missing_ok=True)
            raise GFSTransientError(f"Zero-byte body written for {dest_path}")
        part_path.replace(dest_path)
        return written
