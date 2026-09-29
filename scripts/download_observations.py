"""Download REAL observations for the configured regions (master prompts Prompt 2).

Source: Open-Meteo Archive API (ERA5 reanalysis, free, no API key) —
https://archive-api.open-meteo.com/v1/archive

Fetches daily observations per region:
    rainfall            -> precipitation_sum            (mm/day)
    temperature         -> temperature_2m_max (tmax)    (degC)
    wind_speed          -> wind_speed_10m_max           (m/s)
    humidity            -> relative_humidity_2m_mean    (%)
    pressure            -> surface_pressure_mean        (hPa)

Output (CSV, append + resumable by region):
    data/processed/obs_daily.csv  columns:
        region_id, variable, valid_time, value, unit, source

Usage:
    python scripts/download_observations.py --start 2023-01-01 --end 2023-12-31
    python scripts/download_observations.py --regions 5 --start 2023-01-01 --end 2023-06-30
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    PROCESSED_DIR,
    append_rows_csv,
    csv_regions_done,
    http_get_json,
    iso_date,
    load_regions,
    setup_logging,
    utc_now_iso,
)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# variable -> (open-meteo daily field, unit, aggregation already daily)
VARIABLE_MAP = {
    "rainfall": ("precipitation_sum", "mm"),
    "temperature": ("temperature_2m_max", "degC"),
    "wind_speed": ("wind_speed_10m_max", "m/s"),
    "humidity": ("relative_humidity_2m_mean", "percent"),
    "pressure": ("surface_pressure_mean", "hPa"),
}

OUTPUT_FIELDS = ["region_id", "variable", "valid_time", "value", "unit", "source"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="end date YYYY-MM-DD (inclusive)")
    parser.add_argument("--regions", type=int, default=None, help="limit to first N regions")
    parser.add_argument(
        "--region-ids", default=None, help="comma-separated region_id list (e.g. MH_MUM,DL_DEL)"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-download even cached regions"
    )
    args = parser.parse_args()

    logger = setup_logging("download_observations")
    start, end = iso_date(args.start), iso_date(args.end)
    if end > start and (end - start).days > 3 * 365:
        logger.warning("range over 3 years — consider splitting into yearly chunks")

    regions = load_regions(args.regions)
    if args.region_ids:
        wanted = {r.strip().upper() for r in args.region_ids.split(",")}
        regions = [r for r in regions if r["region_id"] in wanted]
    if not regions:
        logger.error("no regions selected")
        return 2

    out_path = PROCESSED_DIR / "obs_daily.csv"
    done = set() if args.force else csv_regions_done(out_path)
    logger.info(f"{len(regions)} regions, cache hit for {len(done & {r['region_id'] for r in regions})}")

    failures: list[str] = []
    total_rows = 0
    for region in regions:
        rid = region["region_id"]
        if rid in done:
            continue
        params = {
            "latitude": region["latitude"],
            "longitude": region["longitude"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(field for field, _ in VARIABLE_MAP.values()),
            "timezone": "UTC",
        }
        try:
            payload = http_get_json(ARCHIVE_URL, params, logger)
        except Exception as exc:
            failures.append(rid)
            logger.error(f"[{rid}] download FAILED: {exc!r} — manual fallback: retry later "
                         f"or use IMD gridded data via imdlib / CHIRPS CSV")
            continue

        daily = payload.get("daily", {})
        times = daily.get("time", [])
        if not times:
            failures.append(rid)
            logger.error(f"[{rid}] empty daily payload: {str(payload)[:300]}")
            continue

        rows: list[dict] = []
        for variable, (field, unit) in VARIABLE_MAP.items():
            values = daily.get(field)
            if values is None:
                failures.append(rid)
                logger.error(f"[{rid}] field {field} missing from response — API schema changed?")
                continue
            for i, day in enumerate(times):
                value = values[i] if i < len(values) else None
                if value is None:
                    continue  # missing observation stays missing (never fabricated)
                rows.append(
                    {
                        "region_id": rid,
                        "variable": variable,
                        "valid_time": f"{day}T00:00:00Z",
                        "value": round(float(value), 2),
                        "unit": unit,
                        "source": "ERA5",
                    }
                )
        total_rows += append_rows_csv(out_path, OUTPUT_FIELDS, rows)
        n_days = len(times)
        logger.info(f"[{rid}] {len(rows)} rows ({n_days} days x variables) -> {out_path.name}")

    logger.info(f"done: {total_rows} new rows; failures: {failures if failures else 'none'}")
    if failures:
        logger.error(f"regions with errors (NOT filled with fake data): {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
