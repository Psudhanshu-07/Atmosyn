"""Shared helpers for the real-data download pipeline.

Global rules from forecast_reliability_master_prompts.txt:

    - every script is runnable from the command line and logs to /logs
    - cache downloads (never re-download existing files)
    - throttle HTTP requests with retries and exponential backoff
    - NEVER fabricate data: on failure, report the exact error and exit
      non-zero, leaving the partial cache in place.

Synthetic data is NOT generated here — these scripts fetch only real
public no-key data (Open-Meteo ERA5 archive / Previous Runs APIs).
"""
from __future__ import annotations

import csv
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))

DATA_DIR = _ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"
LOGS_DIR = _ROOT / "logs"
REPORTS_DIR = _ROOT / "reports"

# India bounding box (master prompts Prompt 1)
INDIA_BBOX = {"lat_min": 6.0, "lat_max": 38.0, "lon_min": 68.0, "lon_max": 98.0}

# Open-Meteo free tier is non-commercial with daily request limits:
# throttle every request, and retry with exponential backoff on failure.
REQUEST_DELAY_SECONDS = 1.5
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 3.0
HTTP_TIMEOUT_SECONDS = 90

USER_AGENT = "forecast-reliability-layer/1.0 (hackathon; free non-commercial use)"


def setup_logging(name: str) -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        fh = logging.FileHandler(LOGS_DIR / f"{name}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
    return logger


def load_regions(limit: int | None = None) -> List[Dict]:
    """Region catalogue from the backend (single source of truth)."""
    from app.services.regions_data import REGIONS

    regions = list(REGIONS)
    for r in regions:
        assert (
            INDIA_BBOX["lat_min"] <= r["latitude"] <= INDIA_BBOX["lat_max"]
            and INDIA_BBOX["lon_min"] <= r["longitude"] <= INDIA_BBOX["lon_max"]
        ), f"region {r['region_id']} outside India bounding box"
    if limit is not None:
        regions = regions[:limit]
    return regions


def http_get_json(url: str, params: Dict, logger: logging.Logger) -> Dict:
    """Throttled GET with retries + exponential backoff. Raises on final failure."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY_SECONDS)
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            logger.error(f"network error (attempt {attempt}/{MAX_RETRIES}) for {url}: {exc!r}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
            continue

        if resp.status_code == 200:
            return resp.json()
        logger.error(
            f"HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES}) for {url}: "
            f"{resp.text[:300]}"
        )
        if attempt == MAX_RETRIES:
            resp.raise_for_status()
        time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    raise RuntimeError(f"unreachable: retries exhausted for {url}")  # pragma: no cover


def append_rows_csv(path: Path, fieldnames: List[str], rows: List[Dict]) -> int:
    """Append rows to a CSV, creating it with a header if absent."""
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def csv_regions_done(path: Path) -> set:
    """Region IDs already present in a cached output CSV (resumable downloads)."""
    done: set = set()
    if not path.exists():
        return done
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rid = row.get("region_id")
            if rid:
                done.add(rid)
    return done


def iso_date(s: str) -> date:
    return date.fromisoformat(s)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
