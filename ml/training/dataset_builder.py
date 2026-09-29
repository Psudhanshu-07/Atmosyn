"""Training dataset built DIRECTLY from the seeded database.

Single source of truth: the same HistoricalError rows (forecast-observation
pairs with engineered features) that power the API also train the models.
This guarantees the model is trained on exactly the distribution it serves,
eliminating a whole class of train/serve skew bugs.

Anti-leakage is preserved: the seeder's `_backfill_hist_features` computed
historical_mae/rmse/bust_rate per row from valid times strictly before each
row's own valid time (chronological expanding window), and the scoring-time
reliability engine uses the same rule (valid_time < run_time).

This module keeps the public API (build_training_dataset /
chronological_split) used by train_model.py.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import List, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))

from app.core.constants import FEATURE_COLUMNS  # noqa: E402


def load_error_frame(target_variable: str) -> pd.DataFrame:
    """Load HistoricalError rows for one variable as a DataFrame."""
    from app.core.database import SessionLocal
    from app.core.models import HistoricalError

    db = SessionLocal()
    try:
        rows = (
            db.query(HistoricalError)
            .filter(HistoricalError.variable == target_variable)
            .order_by(HistoricalError.valid_time)
            .all()
        )
        records: List[dict] = []
        for r in rows:
            records.append(
                {
                    "region_id": r.region_id,
                    "valid_time": r.valid_time,
                    "lead_day": r.lead_day,
                    "forecast_value": r.forecast_value,
                    "observed_value": r.observed_value,
                    "absolute_error": r.absolute_error,
                    "signed_error": r.signed_error,
                    "bust": int(r.bust),
                    "historical_mae": r.historical_mae,
                    "historical_rmse": r.historical_rmse,
                    "historical_bust_rate": r.historical_bust_rate,
                    "forecast_run_change": r.forecast_run_change,
                    "ensemble_spread": r.ensemble_spread,
                    "pressure": r.pressure,
                    "temperature": r.temperature,
                    "humidity": r.humidity,
                    "wind_speed": r.wind_speed,
                    "month": r.month,
                    "region_avg_error": r.region_avg_error,
                }
            )
        df = pd.DataFrame(records)
    finally:
        db.close()

    # Season one-hot features from month
    season = df["month"].map(_season_of)
    df["season_monsoon"] = (season == "monsoon").astype(int)
    df["season_post_monsoon"] = (season == "post_monsoon").astype(int)
    df["season_winter"] = (season == "winter").astype(int)
    df["season_pre_monsoon"] = (season == "pre_monsoon").astype(int)

    return df


def _season_of(month: int) -> str:
    if month in (6, 7, 8, 9):
        return "monsoon"
    if month in (10, 11, 12):
        return "post_monsoon"
    if month in (1, 2):
        return "winter"
    return "pre_monsoon"


def build_training_dataset(target_variable: str = "rainfall") -> pd.DataFrame:
    """Public API: full feature dataset for one variable, bust label included."""
    return load_error_frame(target_variable)


def chronological_split(
    df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Temporal split by valid_time (Testing §1: chronological split)."""
    df = df.sort_values("valid_time").reset_index(drop=True)
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return df.iloc[:train_end], df.iloc[train_end:val_end], df.iloc[val_end:]


if __name__ == "__main__":
    ds = build_training_dataset("rainfall")
    print(ds.head())
    print(f"rows={len(ds)}, bust_rate={ds['bust'].mean():.3f}")
