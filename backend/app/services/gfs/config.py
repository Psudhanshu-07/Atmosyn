"""Typed GFS configuration derived from the project's single settings object.

There is no second environment mechanism here: every value is read from
``app.core.config.settings`` (which is populated from ``.env`` / environment).
This module only adapts those flat settings into a frozen, validated
dataclass that the ingestion pipeline can use, and resolves relative storage
paths against the project root so CLI and API runs agree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Tuple

from app.core.config import settings

# backend/app/services/gfs/config.py -> project root
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

MODEL_NAME = "GFS"
MODEL_VERSION = "GFS-0.25deg"
SOURCE_NAME = "NOAA/NCEP NOMADS"
SOURCE_LABEL = "NOAA/NCEP GFS"
DATA_TYPE = "NWP_MODEL_FORECAST"  # never an observation (Safety §3)
GFS_CYCLES: Tuple[int, ...] = (0, 6, 12, 18)


def _abs(path: str) -> Path:
    """Resolve a possibly-relative storage path against the project root."""
    p = Path(path)
    return p if p.is_absolute() else (_PROJECT_ROOT / p).resolve()


def _parse_hour_list(spec: str) -> Tuple[int, ...]:
    """Parse a comma/space separated list of forecast hours."""
    out = []
    for chunk in spec.replace(" ", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(chunk))
        except ValueError:
            continue
    return tuple(sorted(set(out)))


@dataclass(frozen=True)
class GFSVariableSpec:
    """A GRIB2 field to request, mapped onto the project's variable names."""

    short_name: str            # NOMADS var_ short name, e.g. "TMP"
    level_type: str            # e.g. "heightAboveGround" / "surface"
    level_value: float | None  # e.g. 2.0 / None
    level_name: str            # NOMADS lev_ key, e.g. "2_m_above_ground"
    target: str | None         # project variable name, None if metadata-only
    units: str


# Default GFS field set. Adding a variable is a matter of appending here (or
# setting GFS_VARIABLES to a subset of these short names).
VARIABLE_CATALOG: dict[str, GFSVariableSpec] = {
    "TMP": GFSVariableSpec("TMP", "heightAboveGround", 2.0, "2_m_above_ground", "temperature", "degC"),
    "APCP": GFSVariableSpec("APCP", "surface", None, "surface", "rainfall", "mm"),
    "UGRD": GFSVariableSpec("UGRD", "heightAboveGround", 10.0, "10_m_above_ground", None, "m/s"),
    "VGRD": GFSVariableSpec("VGRD", "heightAboveGround", 10.0, "10_m_above_ground", None, "m/s"),
    "RH": GFSVariableSpec("RH", "heightAboveGround", 2.0, "2_m_above_ground", "humidity", "percent"),
    "PRES": GFSVariableSpec("PRES", "surface", None, "surface", "pressure", "hPa"),
}

# cfgrib shortName for each GRIB2 field, used when reading the downloaded file.
CFGRIB_NAMES: dict[str, str] = {
    "TMP": "t2m",
    "APCP": "tp",
    "UGRD": "u10",
    "VGRD": "v10",
    "RH": "r2",
    "PRES": "sp",
}

# Reverse index: what eccodes/cfgrib calls the field -> GFS short name.
CFGRIB_TO_GRIB: dict[str, str] = {v: k for k, v in CFGRIB_NAMES.items()}

# ecCodes GRIB2 shortName (as exposed in the GRIB_shortName attribute).
ECCODES_SHORT_NAMES: dict[str, str] = {
    "2t": "TMP",
    "10u": "UGRD",
    "10v": "VGRD",
    "2r": "RH",
    "tp": "APCP",
    "sp": "PRES",
}


@dataclass(frozen=True)
class GFSBounds:
    """Geographic sub-region requested from NOMADS."""

    left_lon: float
    right_lon: float
    bottom_lat: float
    top_lat: float

    def as_params(self) -> dict:
        return {
            "leftlon": _num(self.left_lon),
            "rightlon": _num(self.right_lon),
            "toplat": _num(self.top_lat),
            "bottomlat": _num(self.bottom_lat),
        }

    def contains(self, lat: float, lon: float) -> bool:
        return (
            self.bottom_lat <= lat <= self.top_lat
            and self.left_lon <= lon <= self.right_lon
        )

    def as_dict(self) -> dict:
        return {
            "leftlon": self.left_lon,
            "rightlon": self.right_lon,
            "toplat": self.top_lat,
            "bottomlat": self.bottom_lat,
        }


def _num(value: float) -> str:
    """NOMADS wants short numeric strings (e.g. '68' not '68.0')."""
    return str(int(value)) if float(value).is_integer() else str(value)


@dataclass(frozen=True)
class GFSConfig:
    """Everything the GFS pipeline needs, resolved from project settings."""

    base_url: str
    datasource: str
    file_pattern: str
    bounds: GFSBounds
    forecast_hours: Tuple[int, ...]
    variables: Tuple[GFSVariableSpec, ...]
    cycles: Tuple[int, ...] = GFS_CYCLES
    cycle_delay_hours: float = 3.0
    update_interval_minutes: int = 30
    http_timeout: float = 120.0
    max_retries: int = 3
    backoff_base: float = 2.0
    request_delay: float = 1.0
    raw_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "data" / "raw" / "gfs")
    processed_dir: Path = field(
        default_factory=lambda: _PROJECT_ROOT / "data" / "processed" / "gfs"
    )
    retention_days: int = 3
    source_label: str = SOURCE_LABEL
    source_name: str = SOURCE_NAME
    model_name: str = MODEL_NAME
    model_version: str = MODEL_VERSION
    data_type: str = DATA_TYPE

    # -- paths -------------------------------------------------------------
    @property
    def index_dir(self) -> Path:
        """Sidecar metadata (run + file records) — the dedupe source of truth."""
        return self.raw_dir / "index"

    @property
    def quarantine_dir(self) -> Path:
        return self.raw_dir / "quarantine"

    @property
    def active_pointer(self) -> Path:
        return self.index_dir / "active_cycle.json"

    def cycle_dir(self, run_date: str, cycle: int) -> Path:
        return self.raw_dir / f"{MODEL_NAME.lower()}.{run_date}.{cycle:02d}z"

    def processed_cycle_dir(self, run_date: str, cycle: int) -> Path:
        return self.processed_dir / f"{MODEL_NAME.lower()}.{run_date}.{cycle:02d}z"

    def ensure_dirs(self) -> None:
        for path in (
            self.raw_dir,
            self.index_dir,
            self.quarantine_dir,
            self.processed_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _build() -> GFSConfig:
    requested = [v.strip().upper() for v in settings.gfs_variables.split(",") if v.strip()]
    specs: list[GFSVariableSpec] = []
    for short_name in requested:
        spec = VARIABLE_CATALOG.get(short_name)
        if spec is None:
            raise ValueError(
                f"Unsupported GFS variable {short_name!r}. "
                f"Known: {sorted(VARIABLE_CATALOG)}"
            )
        specs.append(spec)

    if settings.gfs_include_pressure and "PRES" not in requested:
        specs.append(VARIABLE_CATALOG["PRES"])

    hours = list(
        range(
            settings.gfs_forecast_start,
            settings.gfs_forecast_end + 1,
            max(1, settings.gfs_forecast_interval),
        )
    )
    hours.extend(_parse_hour_list(settings.gfs_extra_forecast_hours))
    forecast_hours = tuple(sorted({h for h in hours if h >= 0}))

    if settings.gfs_forecast_interval <= 0:
        raise ValueError("GFS_FORECAST_INTERVAL must be a positive number of hours")

    return GFSConfig(
        base_url=settings.gfs_base_url,
        datasource=settings.gfs_datasource,
        file_pattern=settings.gfs_file_pattern,
        bounds=GFSBounds(
            left_lon=settings.gfs_left_lon,
            right_lon=settings.gfs_right_lon,
            bottom_lat=settings.gfs_bottom_lat,
            top_lat=settings.gfs_top_lat,
        ),
        forecast_hours=forecast_hours,
        variables=tuple(specs),
        cycles=GFS_CYCLES,
        cycle_delay_hours=settings.gfs_cycle_delay_hours,
        update_interval_minutes=settings.gfs_update_interval_minutes,
        http_timeout=settings.gfs_http_timeout,
        max_retries=settings.gfs_max_retries,
        backoff_base=settings.gfs_backoff_base,
        request_delay=settings.gfs_request_delay,
        raw_dir=_abs(settings.gfs_raw_dir),
        processed_dir=_abs(settings.gfs_processed_dir),
        retention_days=settings.gfs_retention_days,
    )


@lru_cache
def get_gfs_config() -> GFSConfig:
    """Cached GFS configuration (single construction, cheap to reuse)."""
    return _build()
