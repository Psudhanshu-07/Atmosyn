"""Build the training dataset from downloaded REAL forecast-observation pairs
(master prompts Prompt 3).

Input : data/processed/pairs_daily.csv   (from scripts/download_forecasts_history.py)
        data/processed/forecast_daily.csv (for run-to-run change features)
Output: data/processed/train.csv with feature columns + chronological split

Features (Prompt 3 subset available from the CSV pipeline):
    abs_error, relative_error
    lead_day, month, season, day_of_year
    run_to_run_change = |fcst(init) - fcst(init-1)| for the same valid date
    climatology anomaly vs region-month mean (computed on TRAIN years only)
    rolling 30-day mean abs error of the same region/variable/lead,
        shifted so no future leakage
Bust label: applied at download time with the documented definition
(rainfall: max(25, |obs|+25) or IMD class shift >= 2; others: magnitude rule).

Split by time ONLY: train ~70% / validation 15% / test 15% by valid_date.

Usage:
    python scripts/build_dataset.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import PROCESSED_DIR, REPORTS_DIR, setup_logging  # noqa: E402

TRAIN_FIELDS = [
    "region_id", "variable", "valid_date", "lead_day",
    "fcst_value", "obs_value", "abs_error", "relative_error",
    "month", "season", "day_of_year",
    "run_to_run_change", "climatology_anomaly", "rolling_mae_30d",
    "bust", "split",
]


def _season_of(month: int) -> str:
    if month in (6, 7, 8, 9):
        return "monsoon"
    if month in (10, 11, 12):
        return "post_monsoon"
    if month in (1, 2):
        return "winter"
    return "pre_monsoon"


def _quantile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    pos = q * (len(sorted_vals) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _load_pairs(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(
                {
                    "region_id": row["region_id"],
                    "variable": row["variable"],
                    "valid_date": row["valid_date"],
                    "lead_day": int(row["lead_day"]),
                    "fcst_value": float(row["fcst_value"]),
                    "obs_value": float(row["obs_value"]),
                    "abs_error": float(row["abs_error"]),
                    "bust": int(row["bust"]),
                }
            )
    return rows


def _load_forecasts(path: Path) -> Dict[Tuple[str, str, str, int], float]:
    """(region, variable, valid_date, lead) -> {init_date: fcst} maps."""
    fcst: Dict[Tuple[str, str, str, int], Dict[str, float]] = defaultdict(dict)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fcst[(row["region_id"], row["variable"], row["valid_date"], int(row["lead_day"]))][
                row["init_date"]
            ] = float(row["fcst_value"])
    out: Dict[Tuple[str, str, str, int], float] = {}
    for key, by_init in fcst.items():
        inits = sorted(by_init.keys())
        if len(inits) >= 2:
            # change between the two most recent runs for the same valid date
            out[key] = abs(by_init[inits[-1]] - by_init[inits[-2]])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default=str(PROCESSED_DIR / "pairs_daily.csv"))
    parser.add_argument("--out", default=str(PROCESSED_DIR / "train.csv"))
    args = parser.parse_args()

    logger = setup_logging("build_dataset")
    pairs_path = Path(args.pairs)
    rows = _load_pairs(pairs_path)
    if not rows:
        logger.error(
            f"no pairs found at {pairs_path}. Run scripts/download_observations.py "
            f"and scripts/download_forecasts_history.py first. NO synthetic data "
            f"will be generated (global rule)."
        )
        return 2

    fcst_path = PROCESSED_DIR / "forecast_daily.csv"
    run_change = _load_forecasts(fcst_path)

    # ---- Feature computation ----
    # 1. run-to-run change per (region, variable, valid_date, lead)
    # 2. climatology from TRAIN years only (region, variable, month) mean fcst
    # 3. rolling 30-day mean abs error per (region, variable, lead), shifted
    rows.sort(key=lambda r: r["valid_date"])
    for r in rows:
        r["month"] = int(r["valid_date"][5:7])
        r["season"] = _season_of(r["month"])
        r["day_of_year"] = date.fromisoformat(r["valid_date"]).timetuple().tm_yday
        key = (r["region_id"], r["variable"], r["valid_date"], r["lead_day"])
        r["run_to_run_change"] = run_change.get(key)

    # climatology: region/variable/month mean forecast, from earliest 70% dates
    n_train = int(len(rows) * 0.7)
    train_dates = {rows[i]["valid_date"] for i in range(n_train)}
    clim_sum: Dict[Tuple[str, str, int], List[float]] = defaultdict(list)
    for r in rows:
        if r["valid_date"] in train_dates:
            clim_sum[(r["region_id"], r["variable"], r["month"])].append(r["fcst_value"])
    clim_mean = {k: (sum(v) / len(v)) for k, v in clim_sum.items()}

    # rolling 30-day mean abs error per (region, variable, lead), shifted by 1
    by_key: Dict[Tuple, List[dict]] = defaultdict(list)
    for r in rows:
        by_key[(r["region_id"], r["variable"], r["lead_day"])].append(r)
    for key, group in by_key.items():
        group.sort(key=lambda r: r["valid_date"])
        window: List[float] = []
        for i, r in enumerate(group):
            r["rolling_mae_30d"] = round(sum(window) / len(window), 3) if window else None
            window.append(r["abs_error"])
            if len(window) > 30:
                window.pop(0)

    # relative error (undefined when obs ~ 0 -> None, never fabricated)
    for r in rows:
        if abs(r["obs_value"]) < 1e-9:
            r["relative_error"] = None
        else:
            r["relative_error"] = round(
                (r["fcst_value"] - r["obs_value"]) / r["obs_value"], 3
            )
        r["climatology_anomaly"] = (
            round(r["fcst_value"] - clim_mean[(r["region_id"], r["variable"], r["month"])], 3)
            if (r["region_id"], r["variable"], r["month"]) in clim_mean
            else None
        )

    # ---- Chronological split (train 70 / val 15 / test 15 by valid_date) ----
    dates = sorted({r["valid_date"] for r in rows})
    train_end = dates[int(len(dates) * 0.7)]
    val_end = dates[int(len(dates) * 0.85)]

    for r in rows:
        if r["valid_date"] < train_end:
            r["split"] = "train"
        elif r["valid_date"] < val_end:
            r["split"] = "validation"
        else:
            r["split"] = "test"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seen_fields = []
    for f in TRAIN_FIELDS:
        if f not in seen_fields:
            seen_fields.append(f)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=seen_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # ---- Coverage + class balance report (Prompt 3 requirement) ----
    by_split: Dict[str, dict] = {}
    for split in ("train", "validation", "test"):
        subset = [r for r in rows if r["split"] == split]
        busts = sum(r["bust"] for r in subset)
        by_split[split] = {
            "rows": len(subset),
            "bust_rate": round(busts / len(subset), 4) if subset else None,
        }
    report = {
        "generated_at": datetime.now().isoformat(),
        "input_pairs": len(rows),
        "output_rows": len(rows),
        "regions": len({r["region_id"] for r in rows}),
        "variables": sorted({r["variable"] for r in rows}),
        "leads": sorted({r["lead_day"] for r in rows}),
        "date_min": dates[0],
        "date_max": dates[-1],
        "class_balance_by_split": by_split,
        "feature_columns": [f for f in TRAIN_FIELDS if f not in ("region_id", "variable", "valid_date", "bust", "split")],
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "dataset_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info(f"train.csv written: {len(rows)} rows, splits={by_split}")
    logger.info(f"report: {REPORTS_DIR / 'dataset_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
