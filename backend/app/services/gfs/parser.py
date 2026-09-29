"""GRIB2 reading, validation and unit normalisation (xarray + cfgrib + eccodes).

The pipeline stays on GRIB2 — files are downloaded once and re-read on demand;
no unnecessary NetCDF round-trip is performed.

Note on cfgrib: a GFS pgrb2 file usually mixes several ``heightAboveGround``
levels. ``xr.open_dataset(..., engine="cfgrib")`` raises DatasetBuildError in
that case, so :func:`parse_grib2` uses ``cfgrib.open_datasets`` which returns
one dataset per level and merges them under unique CF variable names.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
try:
    import xarray as xr
except ImportError:
    xr = None  # type: ignore

from app.services.gfs.config import (
    CFGRIB_NAMES,
    CFGRIB_TO_GRIB,
    ECCODES_SHORT_NAMES,
    GFSConfig,
    VARIABLE_CATALOG,
    get_gfs_config,
)

logger = logging.getLogger("gfs.parser")

GRIB_MAGIC_OFFSET = 0
MIN_GRIB_BYTES = 512  # smallest meaningful GRIB2 message is far larger


class GRIBValidationError(Exception):
    """Downloaded file is not a usable GRIB2 message."""


@dataclass
class GRIBValidation:
    valid: bool
    size_bytes: int
    reason: str = ""
    variables: List[str] = field(default_factory=list)
    latitude_range: Optional[tuple] = None
    longitude_range: Optional[tuple] = None
    valid_time: Optional[str] = None
    run_time: Optional[str] = None

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.valid


def _grib_magic_ok(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(4) == b"GRIB"


def validate_grib2(path, config: Optional[GFSConfig] = None) -> GRIBValidation:
    """Structural validation: size, GRIB2 magic, eccodes readability, bounds.

    A file that fails any of these checks must never be marked valid.
    """
    config = config or get_gfs_config()
    path = Path(path)
    if not path.exists():
        return GRIBValidation(False, 0, "file does not exist")

    size = path.stat().st_size
    if size < MIN_GRIB_BYTES:
        return GRIBValidation(False, size, f"file too small ({size} bytes)")
    if not _grib_magic_ok(path):
        return GRIBValidation(
            False, size, "missing GRIB2 magic bytes (likely an HTML error page)"
        )

    try:
        dataset = parse_grib2(path, config)
    except Exception as exc:  # cfgrib/eccodes raise a variety of types
        return GRIBValidation(False, size, f"GRIB2 parse failed: {exc}")

    if not list(dataset.data_vars):
        return GRIBValidation(False, size, "GRIB2 file contains no data variables")

    lat_range = (float(dataset.latitude.min()), float(dataset.latitude.max()))
    lon_range = (float(dataset.longitude.min()), float(dataset.longitude.max()))
    bounds = config.bounds
    if not (bounds.bottom_lat - 0.5 <= lat_range[0] and lat_range[1] <= bounds.top_lat + 0.5):
        return GRIBValidation(
            False,
            size,
            f"latitude range {lat_range} outside requested sub-region {bounds.as_dict()}",
            latitude_range=lat_range,
            longitude_range=lon_range,
        )
    if not (bounds.left_lon - 0.5 <= lon_range[0] and lon_range[1] <= bounds.right_lon + 0.5):
        return GRIBValidation(
            False,
            size,
            f"longitude range {lon_range} outside requested sub-region {bounds.as_dict()}",
            latitude_range=lat_range,
            longitude_range=lon_range,
        )

    valid_time = dataset.attrs.get("valid_time")
    return GRIBValidation(
        True,
        size,
        variables=sorted(str(v) for v in dataset.data_vars),
        latitude_range=lat_range,
        longitude_range=lon_range,
        valid_time=str(valid_time) if valid_time is not None else None,
        run_time=str(dataset.attrs.get("time")) if dataset.attrs.get("time") is not None else None,
    )


def _identify_grib_field(name: str, attrs: Dict[str, object]) -> Optional[str]:
    """Map a cfgrib variable onto its GFS short name (TMP, APCP, UGRD, ...).

    cfgrib names the field from the CF convention (``t2m``, ``u10``) while
    ``GRIB_shortName`` holds the ecCodes name (``2t``, ``10u``); both are
    accepted so identification is robust across ecCodes versions.
    """
    ecodes_name = str(attrs.get("GRIB_shortName", "")).lower()
    if ecodes_name in ECCODES_SHORT_NAMES:
        return ECCODES_SHORT_NAMES[ecodes_name]
    if str(name).lower() in CFGRIB_TO_GRIB:
        return CFGRIB_TO_GRIB[str(name).lower()]
    upper = str(name).upper()
    if upper in CFGRIB_NAMES:
        return upper
    if upper in VARIABLE_CATALOG:
        return upper
    return None


def parse_grib2(
    path,
    config: Optional[GFSConfig] = None,
    short_names: Optional[List[str]] = None,
) -> xr.Dataset:
    """Read a GRIB2 file into a single merged :class:`xarray.Dataset`.

    Returns surface/multi-level fields under stable CF names
    (``t2m``, ``tp``, ``u10``, ``v10``, ``r2``, ``sp``).
    """
    import cfgrib  # imported lazily so the module loads without eccodes

    config = config or get_gfs_config()
    path = Path(path)
    wanted = {s.short_name for s in config.variables}
    if short_names is not None:
        wanted = {str(s).upper() for s in short_names}

    try:
        parts = cfgrib.open_datasets(str(path))
    except Exception as exc:
        raise GRIBValidationError(f"cfgrib could not read {path.name}: {exc}") from exc

    merged: Optional[xr.Dataset] = None
    kept: List[str] = []
    for part in parts:
        renames: Dict[str, str] = {}
        for name in list(part.data_vars):
            grib_name = _identify_grib_field(name, part[name].attrs)
            if grib_name is None or grib_name not in wanted:
                continue
            target = CFGRIB_NAMES.get(grib_name, name)
            if target in renames.values():
                continue
            renames[name] = target
        if not renames:
            continue
        subset = part[list(renames)].rename(renames)
        # Drop conflicting scalar coords (e.g. heightAboveGround 2 vs 10) so the
        # merge is well defined; the level is preserved in each var's attrs.
        drop = [
            c
            for c in ("heightAboveGround", "depthBelowLand", "isobaricInhPa", "level")
            if c in subset.coords and subset[c].ndim == 0
        ]
        if drop:
            subset = subset.drop_vars(drop)
        subset = subset.reset_coords(drop=True)
        kept.extend(renames.values())
        merged = subset if merged is None else xr.merge([merged, subset])

    if merged is None or not list(merged.data_vars):
        raise GRIBValidationError(
            f"No requested variables found in {path.name} "
            f"(wanted {sorted(wanted)}); GRIB2 may be truncated"
        )

    merged.attrs["gfs_source"] = config.source_label
    merged.attrs["gfs_file"] = path.name
    merged.attrs["gfs_variables"] = ",".join(sorted(set(kept)))
    merged.attrs["gfs_data_type"] = config.data_type
    return merged


# ---------------------------------------------------------------------------
# Unit normalisation -> project variable names (core/constants.py vocabulary)
# ---------------------------------------------------------------------------
KELVIN_OFFSET = 273.15


def to_project_variables(dataset: xr.Dataset) -> Dict[str, xr.DataArray]:
    """Map GRIB fields onto the project's variable vocabulary.

    GFS encoding: TMP in K, APCP in kg/m2 (== mm), UGRD/VGRD in m/s,
    RH in %, PRES in Pa.
    """
    out: Dict[str, xr.DataArray] = {}

    if "t2m" in dataset:
        out["temperature"] = dataset["t2m"] - KELVIN_OFFSET
    if "r2" in dataset:
        out["humidity"] = dataset["r2"]
    if "tp" in dataset:
        # kg/m2 is numerically identical to mm for liquid water equivalent.
        out["rainfall"] = dataset["tp"]
    if "sp" in dataset:
        out["pressure"] = dataset["sp"] / 100.0
    if "u10" in dataset and "v10" in dataset:
        u, v = dataset["u10"], dataset["v10"]
        out["wind_speed"] = xr.DataArray(
            np.hypot(u.values, v.values),
            dims=("latitude", "longitude"),
            coords={"latitude": u.latitude, "longitude": u.longitude},
            name="wind_speed",
        )
        out["wind_u"] = u
        out["wind_v"] = v
    return out


def read_and_normalise(
    path,
    config: Optional[GFSConfig] = None,
) -> Dict[str, xr.DataArray]:
    """Convenience wrapper: parse then normalise in one call."""
    return to_project_variables(parse_grib2(path, config))


def sample_value(
    dataset: xr.Dataset, name: str, lat: float, lon: float
) -> Optional[float]:
    """Nearest-grid-cell value of ``name`` at a point (region extraction)."""
    if name not in dataset:
        return None
    field = dataset[name]
    if "valid_time" in field.coords:
        field = field.isel(time=0, drop=True) if "time" in field.dims else field
    try:
        da = field.sel(latitude=lat, longitude=lon, method="nearest")
    except (KeyError, ValueError):
        return None
    value = da.values
    if value is None or np.isnan(value):
        return None
    return float(value)
