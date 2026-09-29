"""Dataclasses describing GFS cycles, requests and on-disk metadata records."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.gfs.config import DATA_TYPE, MODEL_NAME, SOURCE_LABEL, SOURCE_NAME


class GFSRunStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    VALID = "valid"
    PARTIAL = "partial"
    INVALID = "invalid"
    ACTIVE = "active"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.astimezone(timezone.utc).isoformat() if value else None


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, order=True)
class GFSCycle:
    """One GFS model run: date + 6-hourly cycle."""

    run_date: str  # YYYYMMDD
    cycle: int  # 0, 6, 12, 18

    @classmethod
    def from_run_time(cls, run_time: datetime) -> "GFSCycle":
        return cls(run_time.strftime("%Y%m%d"), run_time.hour)

    @property
    def run_time(self) -> datetime:
        return datetime(
            int(self.run_date[0:4]),
            int(self.run_date[4:6]),
            int(self.run_date[6:8]),
            self.cycle,
            tzinfo=timezone.utc,
        )

    @property
    def key(self) -> str:
        return f"{self.run_date}_{self.cycle:02d}"

    @property
    def label(self) -> str:
        return f"{self.run_date} {self.cycle:02d} UTC"

    @property
    def nomads_dir(self) -> str:
        """NOMADS ``dir`` argument, e.g. /gfs.20260928/12/atmos"""
        return (
            f"/{self.datasource_prefix}.{self.run_date}/{self.cycle:02d}/atmos"
        )

    @property
    def datasource_prefix(self) -> str:
        return "gfs"

    def nomads_sort_dir(self, datasource: str) -> str:
        return f"/{datasource}.{self.run_date}/{self.cycle:02d}/atmos"

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.label


@dataclass
class GFSFileRecord:
    """Metadata for one downloaded GRIB2 file (dedupe + validation evidence)."""

    model: str = MODEL_NAME
    source: str = SOURCE_NAME
    cycle: str = ""
    run_date: str = ""
    forecast_hour: int = 0
    file_name: str = ""
    url: str = ""
    checksum: str = ""
    size_bytes: int = 0
    downloaded_at: Optional[str] = None
    valid_time: Optional[str] = None
    run_time: Optional[str] = None
    status: str = GFSRunStatus.PENDING.value
    error: Optional[str] = None
    retry_count: int = 0
    data_type: str = DATA_TYPE
    source_label: str = SOURCE_LABEL

    @property
    def file_key(self) -> str:
        return f"{self.run_date}_{int(self.cycle or 0):02d}_f{self.forecast_hour:03d}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GFSFileRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class GFSRunMetadata:
    """Run-level metadata, one JSON document per cycle under ``index/``."""

    model: str = MODEL_NAME
    source: str = SOURCE_NAME
    source_label: str = SOURCE_LABEL
    data_type: str = DATA_TYPE
    run_date: str = ""
    cycle: str = ""
    run_time: Optional[str] = None
    status: str = GFSRunStatus.PENDING.value
    is_active: bool = False
    discovered_at: Optional[str] = None
    activated_at: Optional[str] = None
    processed_at: Optional[str] = None
    bounds: Dict[str, Any] = field(default_factory=dict)
    variables: List[str] = field(default_factory=list)
    forecast_hours: List[int] = field(default_factory=list)
    files: List[GFSFileRecord] = field(default_factory=list)
    last_error: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.run_date}_{int(self.cycle or 0):02d}"

    @property
    def cycle_obj(self) -> GFSCycle:
        return GFSCycle(self.run_date, int(self.cycle or 0))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["files"] = [f.to_dict() for f in self.files]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GFSRunMetadata":
        payload = dict(data)
        files = [GFSFileRecord.from_dict(f) for f in payload.pop("files", [])]
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        meta = cls(**{k: v for k, v in payload.items() if k in known})
        meta.files = files
        return meta


# ---------------------------------------------------------------------------
# JSON sidecar store (source of truth for dedupe; survives without a DB)
# ---------------------------------------------------------------------------
def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
