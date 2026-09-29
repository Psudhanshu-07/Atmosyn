"""Deterministic synthetic weather generator for the prototype.

Realistic monsoon-season climatology for India is encoded per city (rainfall
maxima, temperature range), then forecasts and observations are generated
around it with a deterministic RNG. Bigger busts at longer lead days and in
orographically complex / coastal-convergence regions, matching the documented
behaviour of medium-range NWP error growth.

All values respect physical ranges from constants.py so the validation layer
accepts every record (Testing TV-03).
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Tuple

from app.core.constants import VARIABLE_RANGES, VARIABLE_UNITS
from app.services.regions_data import RegionRow

FORECAST_SOURCE = "NWP"
OBS_SOURCE = "NCEI"


def stable_seed(*parts) -> int:
    """Process-independent deterministic seed (unlike builtin hash())."""
    key = "|".join(str(p) for p in parts)
    return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % (2**31)


def _clamp(value: float, variable: str) -> float:
    lo, hi = VARIABLE_RANGES[variable]
    return max(lo, min(hi, value))


def _round(value: float, variable: str) -> float:
    if variable == "rainfall":
        return round(value, 1)
    return round(value, 2)


# Rough September climatology used by the generator (rainfall in mm/day).
_CLIM: Dict[str, Tuple[float, float]] = {
    # (typical rainfall mm/day, typical max temperature degC)
    "MH_MUM": (28.0, 30.0), "MH_PUN": (12.0, 29.0), "MH_NAG": (10.0, 31.0),
    "DL_DEL": (8.0, 33.0), "UP_LKO": (14.0, 33.0), "UP_VNS": (13.0, 33.0),
    "BR_PAT": (16.0, 32.0), "JH_RNC": (18.0, 30.0), "WB_KOL": (20.0, 31.5),
    "WB_SIL": (30.0, 29.0), "OD_BBI": (22.0, 31.0), "AP_VJA": (12.0, 33.0),
    "AP_TIR": (10.0, 33.0), "TS_HYD": (11.0, 30.5), "KA_BLR": (9.0, 28.5),
    "KA_MNG": (24.0, 29.0), "TN_MAA": (8.0, 33.5), "TN_CBE": (6.0, 31.0),
    "KL_TRV": (12.0, 29.5), "KL_KOC": (16.0, 29.0), "GJ_AHM": (7.0, 34.0),
    "GJ_SRT": (11.0, 32.0), "RJ_JAI": (6.0, 34.0), "RJ_JDR": (4.0, 35.0),
    "MP_BHO": (13.0, 30.0), "MP_JBP": (14.0, 30.0), "CHD_CHD": (9.0, 32.0),
    "PB_AMD": (8.0, 33.0), "HR_HIS": (7.0, 34.5), "UK_DDH": (15.0, 29.0),
    "HP_SHM": (14.0, 22.0), "JK_SRN": (5.0, 27.0), "AS_GHY": (22.0, 31.0),
    "TR_AGR": (20.0, 31.5), "GA_ITN": (26.0, 29.0), "GO_PAN": (20.0, 29.5),
}


def region_climatology(region: RegionRow) -> Tuple[float, float]:
    return _CLIM.get(
        region["region_id"],
        (10.0, 30.0),
    )


def rainfall_bust_threshold(region: RegionRow) -> float:
    """Climatology-scaled rainfall bust threshold (FR-04 data-driven).

    A 'significant' error is relative to local climatology: 20 mm is a bust
    in arid Jodhpur, while coastal Mumbai needs ~55 mm. Clamped to a
    documented [20, 60] mm band so thresholds stay operationally sane.
    """
    base_rain, _ = region_climatology(region)
    return round(max(20.0, min(60.0, 2.2 * base_rain)), 1)


def generate_observation_series(
    region: RegionRow,
    start: date,
    days: int,
    seed: int,
) -> List[dict]:
    """Daily observations for one region: rainfall, temperature, wind, etc."""
    rng = random.Random(seed)
    base_rain, base_temp = region_climatology(region)
    lat_factor = 1.0 + (region["latitude"] - 20.0) / 40.0
    rows: List[dict] = []

    for d in range(days):
        day = start + timedelta(days=d)
        ts = datetime(day.year, day.month, day.day, 3, 0, tzinfo=timezone.utc)
        month = day.month
        phase = math.sin((day.timetuple().tm_yday / 365.0) * 2 * math.pi)
        # September-dominant monsoon: boost rainfall Jun-Sep.
        monsoon_boost = 1.0 + 0.9 * phase if month in (6, 7, 8, 9) else 0.35

        wet_day = rng.random() < min(0.85, 0.25 + 0.5 * monsoon_boost)
        rain = 0.0
        if wet_day:
            intensity = rng.random() ** 1.6
            rain = base_rain * monsoon_boost * (0.3 + 2.2 * intensity)
            if region["coastal"] and rng.random() < 0.10:
                rain *= 3.0  # extreme-rainfall episodes (bust-prone)

        temp = (
            base_temp
            - 2.5 * monsoon_boost
            + 4.0 * rng.random()
            - 2.0
            - 0.5 * (rain / 30.0)
        )
        humidity = min(98.0, 55.0 + 35.0 * monsoon_boost + rng.random() * 10 - 5)
        pressure = (
            1008.0
            - 6.0 * monsoon_boost
            + rng.random() * 6
            - 3
            - 2.0 * (rain / 50.0)
        )
        wind = 2.5 + 6.0 * monsoon_boost * rng.random() + (2.5 if region["coastal"] else 0.0)

        rows.append(
            {
                "valid_time": ts,
                "rainfall": _round(_clamp(rain, "rainfall"), "rainfall"),
                "temperature": _round(_clamp(temp, "temperature"), "temperature"),
                "humidity": _round(_clamp(humidity, "humidity"), "humidity"),
                "pressure": _round(_clamp(pressure, "pressure"), "pressure"),
                "wind_speed": _round(_clamp(wind, "wind_speed"), "wind_speed"),
            }
        )
    return rows


def generate_forecast_for_lead(
    observed: float,
    variable: str,
    lead_day: int,
    climatology: Tuple[float, float],
    seed: int,
) -> float:
    """A forecast for one valid time, with realistic error growth by lead day.

    Rainfall uses a timing/intensity error model like real NWP: the forecast
    can miss a wet day entirely (timing error), rain spuriously on a dry day,
    or get the intensity wrong. Miss/spurious probability and relative
    intensity error both grow with lead day. Continuous variables use
    Gaussian errors whose spread grows with lead day.
    """
    rng = random.Random(seed)
    lead_factor = 1.0 + 0.30 * (lead_day - 1)

    if variable == "rainfall":
        miss_prob = min(0.50, 0.09 * lead_factor)
        spur_prob = min(0.45, 0.07 * lead_factor)
        rel_sigma = 0.30 + 0.08 * (lead_day - 1)
        if observed <= 0.1:
            if rng.random() < spur_prob:
                # Spurious rain on a dry day (timing miss): magnitude grows
                # with lead day and can reach bust-scale amounts.
                spur_scale = 0.3 + 0.3 * lead_day
                value = climatology[0] * spur_scale * (0.3 + 1.2 * rng.random())
            else:
                value = max(0.0, rng.gauss(0.3, 0.8))
        else:
            if rng.random() < miss_prob:
                # Wet day completely missed (forecast dry)
                value = max(0.0, rng.gauss(0.8, 1.6))
            else:
                value = max(0.0, observed * (1.0 + rng.gauss(0.0, rel_sigma)))
    elif variable == "temperature":
        sigma = 0.7 + 0.25 * (lead_day - 1)
        value = observed + rng.gauss(0.0, sigma)
    elif variable == "wind_speed":
        sigma = 0.9 + 0.35 * (lead_day - 1)
        value = observed + rng.gauss(0.0, sigma)
    elif variable == "pressure":
        sigma = 1.0 + 0.4 * (lead_day - 1)
        value = observed + rng.gauss(0.0, sigma)
    else:  # humidity
        sigma = 4.0 + 1.5 * (lead_day - 1)
        value = observed + rng.gauss(0.0, sigma)

    return _round(_clamp(value, variable), variable)


def generate_run_change_and_spread(
    variable: str,
    forecast_value: float,
    lead_day: int,
    climatology: Tuple[float, float],
    seed: int,
) -> Tuple[float, float]:
    """Forecast run-to-run relative change and ensemble spread (FR-17/18)."""
    rng = random.Random(seed)
    base_rain, _ = climatology
    lead_factor = 1.0 + 0.25 * (lead_day - 1)

    if variable == "rainfall":
        scale = base_rain * 0.25 * lead_factor + 1.5
        run_change = min(1.2, abs(rng.gauss(0.0, scale)) / max(forecast_value, 5.0))
        spread = max(0.5, abs(rng.gauss(0.0, scale * 0.8)))
    else:
        spread = max(0.3, abs(rng.gauss(0.0, 1.5 * lead_factor)))
        run_change = min(1.0, spread / 30.0 + abs(rng.gauss(0.0, 0.05)))

    return round(run_change, 4), round(spread, 2)


def atmospheric_context(obs_row: dict, seed: int) -> Dict[str, float]:
    """Atmospheric predictors available at forecast time (no future leakage)."""
    rng = random.Random(seed)
    return {
        "temperature": obs_row["temperature"],
        "humidity": obs_row["humidity"],
        "pressure": obs_row["pressure"],
        "wind_speed": obs_row["wind_speed"],
        "phase_noise": rng.random(),
    }
