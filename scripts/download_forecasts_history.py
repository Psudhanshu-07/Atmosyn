"""Download REAL historical forecasts and pair them with observations
(master prompts Prompt 2 / Prompt 3 core loop).

Sources (free, no API key):
  forecasts: Open-Meteo Previous Runs API
      https://previous-runs-api.open-meteo.com/v1/forecast
      Returns what the model predicted previous_day1..previous_dayN earlier
      for the same valid time — exactly the forecast-vs-actual pairs needed
      for bust statistics. One request per model per region; daily values
      aggregated per the doc: rain summed, tmax max, wind/humidity/pressure
      averaged.
  observations: data/processed/obs_daily.csv produced by
      scripts/download_observations.py (ERA5 archive). If a pair is missing
      an observation it is left unpaired — never fabricated.

Outputs (CSV, append + resumable by region):
    data/processed/forecast_daily.csv  columns:
        region_id, variable, init_date, valid_date, lead_day, fcst_value, source
    data/processed/pairs_daily.csv     columns:
        region_id, variable, valid_date, lead_day, fcst_value, obs_value,
        abs_error, bust, threshold, source

Bust definition (Prompt 3, documented in README):
    rainfall : abs_error > max(25 mm, 1.0*|obs| + 25) OR IMD class shift >= 2
    others   : abs_error > max(25 mm, 1.0*|obs| + threshold_mm) with
               threshold_mm per variable (temperature 5, wind 10, humidity 30,
               pressure 10).

Usage:
    python scripts/download_forecasts_history.py --start 2023-01-01 --end 2023-12-31
    python scripts/download_forecasts_history.py --regions 5 --start 2023-01-01 --end 2023-06-30 --leads 1,3,5
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    PROCESSED_DIR,
    append_rows_csv,
    csv_regions_done,
    http_get_json,
    iso_date,
    load_regions,
    setup_logging,
)

PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

VARIABLES: Dict[str, dict] = {
    "rainfall": {
        "hourly": "precipitation",
        "agg": "sum",
        "previous_field": "precipitation_previous_day{lead}",
        "unit": "mm",
        "threshold_mm": 25.0,
    },
    "temperature": {
        "hourly": "temperature_2m",
        "agg": "max",
        "previous_field": "temperature_2m_previous_day{lead}",
        "unit": "degC",
        "threshold_mm": 5.0,
    },
    "wind_speed": {
        "hourly": "wind_speed_10m",
        "agg": "mean",
        "previous_field": "wind_speed_10m_previous_day{lead}",
        "unit": "m/s",
        "threshold_mm": 10.0,
    },
    "humidity": {
        "hourly": "relative_humidity_2m",
        "agg": "mean",
        "previous_field": "relative_humidity_2m_previous_day{lead}",
        "unit": "percent",
        "threshold_mm": 30.0,
    },
    "pressure": {
        "hourly": "surface_pressure",
        "agg": "mean",
        "previous_field": "surface_pressure_previous_day{lead}",
        "unit": "hPa",
        "threshold_mm": 10.0,
    },
}

FCST_FIELDS = ["region_id", "variable", "init_date", "valid_date", "lead_day", "fcst_value", "source"]
PAIRS_FIELDS = [
    "region_id", "variable", "valid_date", "lead_day",
    "fcst_value", "obs_value", "abs_error", "bust", "threshold", "source",
]

# IMD rainfall classes for the class-shift rule (mirrors error_engine)
_IMD_CLASSES = [(0.0, 2.5), (2.5, 15.6), (15.6, 64.5), (64.5, 115.6), (115.6, 204.5), (204.5, float("inf"))]


def _rain_class(value: float) -> int:
    for idx, (lo, hi) in enumerate(_IMD_CLASSES):
        if lo <= value < hi:
            return idx
    return len(_IMD_CLASSES) - 1


def bust_label(variable: str, forecast: float, observed: float) -> Tuple[bool, float]:
    """Same definition as app.services.error_engine (doc Prompt 3)."""
    from app.services.error_engine import rainfall_bust_label

    threshold = max(25.0, abs(observed) + VARIABLES[variable]["threshold_mm"])
    if variable == "rainfall":
        return rainfall_bust_label(forecast, observed), threshold
    return abs(forecast - observed) > threshold, threshold


def _daily_from_hourly(hourly: Dict, field: str, agg: str) -> Dict[str, float]:
    """Aggregate an hourly block to {YYYY-MM-DD: value} per the doc rule."""
    times: List[str] = hourly.get("time", [])
    values = hourly.get(field) or []
    by_day: Dict[str, List[float]] = {}
    for t, v in zip(times, values):
        if v is None:
            continue
        by_day.setdefault(t[:10], []).append(float(v))
    out: Dict[str, float] = {}
    for day, vals in by_day.items():
        if agg == "sum":
            out[day] = round(sum(vals), 2)
        elif agg == "max":
            out[day] = round(max(vals), 2)
        else:
            out[day] = round(sum(vals) / len(vals), 2)
    return out


def _find_previous_day_field(payload: Dict, model: str, field: str) -> Optional[list]:
    """Schema-tolerant lookup: models may prefix fields (`gfs_seamless_...`)."""
    prefixed = payload.get("hourly", {}).get(f"{model}_{field}")
    if prefixed is not None:
        return prefixed
    return payload.get("hourly", {}).get(field) or payload.get("daily", {}).get(field)


def _load_obs_from_csv(path: Path) -> Dict[Tuple[str, str], Tuple[float, str]]:
    """region/variable/date -> (value, source) from the ERA5 obs CSV."""
    obs: Dict[Tuple[str, str], Tuple[float, str]] = {}
    if not path.exists():
        return obs
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["region_id"], row["variable"], row["valid_date"])
            obs[key] = (float(row["value"]), row.get("source", "ERA5"))
    return obs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="first valid date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="last valid date YYYY-MM-DD")
    parser.add_argument("--regions", type=int, default=None, help="limit to first N regions")
    parser.add_argument("--region-ids", default=None, help="comma-separated region_id list")
    parser.add_argument("--leads", default="1,3,5,7,10", help="lead days to extract")
    parser.add_argument("--models", default="gfs_seamless,ecmwf_ifs025",
                        help="comma-separated previous-runs models (one request each)")
    parser.add_argument("--force", action="store_true", help="ignore cache")
    args = parser.parse_args()

    logger = setup_logging("download_forecasts_history")
    start, end = iso_date(args.start), iso_date(args.end)
    leads = sorted({int(x) for x in args.leads.split(",") if x.strip()})
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    variables = list(VARIABLES.keys())

    regions = load_regions(args.regions)
    if args.region_ids:
        wanted = {r.strip().upper() for r in args.region_ids.split(",")}
        regions = [r for r in regions if r["region_id"] in wanted]
    if not regions:
        logger.error("no regions selected")
        return 2

    fcst_path = PROCESSED_DIR / "forecast_daily.csv"
    pairs_path = PROCESSED_DIR / "pairs_daily.csv"
    obs_path = PROCESSED_DIR / "obs_daily.csv"
    done = set() if args.force else csv_regions_done(fcst_path)
    logger.info(f"{len(regions)} regions x leads={leads} x models={models}; cached={len(done)}")

    obs_lookup = _load_obs_from_csv(obs_path)
    if not obs_lookup:
        logger.warning(
            "data/processed/obs_daily.csv missing or empty — run "
            "scripts/download_observations.py first; pairs will only be "
            "produced where observations exist (none will be fabricated)."
        )

    failures: List[str] = []
    fcst_rows: List[dict] = []
    pairs_rows: List[dict] = []

    for region in regions:
        rid = region["region_id"]
        if rid in done:
            continue

        region_fcst = 0
        for model in models:
            params = {
                "latitude": region["latitude"],
                "longitude": region["longitude"],
                "hourly": ",".join(v["hourly"] for v in VARIABLES.values())
                + ","
                + ",".join(v["previous_field"].format(lead=lead) for v in VARIABLES.values() for lead in leads),
                "models": model,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "timezone": "UTC",
            }
            try:
                payload = http_get_json(PREV_RUNS_URL, params, logger)
            except Exception as exc:
                failures.append(rid)
                logger.error(
                    f"[{rid}] download FAILED for model {model}: {exc!r} — manual "
                    f"fallback: reduce date range/leads, or ingest NOAA GEFS from "
                    f"s3://noaa-gefs-pds (s3fs anon=True)"
                )
                continue

            hourly = payload.get("hourly", {})
            times: List[str] = hourly.get("time", [])
            if not times:
                failures.append(rid)
                logger.error(f"[{rid}] empty hourly block for model {model}: {str(payload)[:300]}")
                continue

            for variable in variables:
                spec = VARIABLES[variable]
                for lead in leads:
                    field = spec["previous_field"].format(lead=lead)
                    raw = _find_previous_day_field(payload, model, field)
                    if not raw:
                        if lead == leads[0] and variable == variables[0]:
                            logger.warning(
                                f"[{rid}] no previous_day fields found for model {model} "
                                f"(may not support this lead range)"
                            )
                        continue

                    by_day: Dict[str, List[float]] = {}
                    for t, v in zip(times, raw):
                        if v is None:
                            continue
                        by_day.setdefault(t[:10], []).append(float(v))

                    for day, vals in sorted(by_day.items()):
                        if spec["agg"] == "sum":
                            fcst_value = round(sum(vals), 2)
                        elif spec["agg"] == "max":
                            fcst_value = round(max(vals), 2)
                        else:
                            fcst_value = round(sum(vals) / len(vals), 2)

                        init_date = (
                            datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=lead)
                        ).isoformat()
                        source = f"OPEN_METEO_PREV_RUNS:{model}"
                        fcst_rows.append(
                            {
                                "region_id": rid,
                                "variable": variable,
                                "init_date": init_date,
                                "valid_date": day,
                                "lead_day": lead,
                                "fcst_value": fcst_value,
                                "source": source,
                            }
                        )
                        region_fcst += 1

                        obs_hit = obs_lookup.get((rid, variable, day))
                        if obs_hit is None:
                            continue  # unpaired forecast kept; observation NOT fabricated
                        obs, obs_source = obs_hit
                        err = abs(fcst_value - obs)
                        bust, threshold = bust_label(variable, fcst_value, obs)
                        pairs_rows.append(
                            {
                                "region_id": rid,
                                "variable": variable,
                                "valid_date": day,
                                "lead_day": lead,
                                "fcst_value": fcst_value,
                                "obs_value": obs,
                                "abs_error": round(err, 2),
                                "bust": int(bust),
                                "threshold": round(threshold, 2),
                                "source": f"{source}|OBS:{obs_source}",
                            }
                        )
        logger.info(f"[{rid}] {region_fcst} forecast rows, {len(pairs_rows)} cumulative pairs")

    n1 = append_rows_csv(fcst_path, FCST_FIELDS, fcst_rows)
    n2 = append_rows_csv(pairs_path, PAIRS_FIELDS, pairs_rows)
    logger.info(f"done: +{n1} forecast rows -> {fcst_path.name}; +{n2} pair rows -> {pairs_path.name}")

    if failures:
        logger.error(f"regions with errors (NOT filled with fake data): {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
