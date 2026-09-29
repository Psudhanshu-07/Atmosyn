"""NOAA/NCEP GFS ingestion via the public NOMADS service.

Source: https://nomads.ncep.noaa.gov/  (no API key, public domain)
Product: GFS 0.25° GRIB2 gridded forecast output.

Pipeline:

    NOMADS -> client -> cycle_detector -> downloader -> parser
           -> processor -> storage -> existing FastAPI backend -> frontend

GFS is a *numerical weather prediction model* forecast. It is never labelled
as an observation or as an official local forecast in this application.
"""

from app.services.gfs.config import (
    GFSBounds,
    GFSConfig,
    GFSVariableSpec,
    get_gfs_config,
)
from app.services.gfs.models import (
    GFSCycle,
    GFSFileRecord,
    GFSRunMetadata,
    GFSRunStatus,
    SOURCE_LABEL,
    SOURCE_NAME,
)

__all__ = [
    "GFSBounds",
    "GFSCycle",
    "GFSConfig",
    "GFSFileRecord",
    "GFSRunMetadata",
    "GFSRunStatus",
    "GFSVariableSpec",
    "SOURCE_LABEL",
    "SOURCE_NAME",
    "get_gfs_config",
]
