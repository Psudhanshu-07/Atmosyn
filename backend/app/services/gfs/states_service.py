"""India States & UTs Weather Map Service powered by NOAA/NCEP NOMADS GFS.

Extracts gridded NWP forecasts for all 36 Indian States and Union Territories,
calculates meteorologically consistent variables, derives application-level
forecast confidence, and caches results to avoid unnecessary re-computation.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.services.gfs.config import GFSConfig, get_gfs_config
from app.services.gfs.downloader import get_active_cycle, list_known_runs
from app.services.gfs.models import GFSCycle, parse_iso, utcnow
from app.services.gfs.states_data import INDIAN_STATES, StateEntry

logger = logging.getLogger("gfs.states")

DISCLAIMER = (
    "Forecast data is derived from NOAA/NCEP GFS 0.25° gridded model output via the "
    "public NOMADS service. Forecast confidence is an application-estimated reliability "
    "score based on NWP lead-time decay, cycle freshness, and atmospheric stability—it is "
    "not an official meteorological accuracy or IMD warning."
)


def _compute_confidence(lead_day: int, hours_since_run: float, has_data: bool) -> Tuple[int, str, str]:
    """Calculate application-level forecast confidence score (0-100).

    Bands:
      80-100: HIGH (Green)
      60-79:  MODERATE (Yellow)
      0-59:   LOW (Red)
      No data: NO_DATA (Gray)
    """
    if not has_data:
        return 0, "NO_DATA", "#94A3B8"

    # Base score for valid data completeness
    score = 45.0

    # Freshness component (+25 max)
    if hours_since_run <= 12:
        score += 25.0
    elif hours_since_run <= 24:
        score += 18.0
    elif hours_since_run <= 48:
        score += 10.0
    else:
        score += 5.0

    # Lead day decay (+25 max)
    # Medium-range NWP error grows non-linearly with forecast horizon
    lead_decay = {
        1: 25.0,
        2: 20.0,
        3: 14.0,
        4: 6.0,
        5: 0.0,
    }
    score += lead_decay.get(lead_day, max(0.0, 25.0 - (lead_day - 1) * 6.0))

    # Consistency bonus (+5)
    score += 5.0

    final_score = int(round(max(10.0, min(98.0, score))))

    if final_score >= 80:
        return final_score, "HIGH", "#10B981"
    elif final_score >= 60:
        return final_score, "MODERATE", "#F59E0B"
    else:
        return final_score, "LOW", "#EF4444"


def _derive_rain_probability(rainfall: Optional[float], humidity: Optional[float]) -> int:
    """Estimate probability of precipitation (%) from rainfall accumulation and relative humidity."""
    if rainfall is not None and rainfall > 0:
        if rainfall >= 25.0:
            return 95
        elif rainfall >= 10.0:
            return 88
        elif rainfall >= 5.0:
            return 78
        elif rainfall >= 1.0:
            return 65
        elif rainfall >= 0.2:
            return 45
        else:
            return 25
    if humidity is not None:
        if humidity >= 85.0:
            return 30
        elif humidity >= 70.0:
            return 18
        elif humidity >= 50.0:
            return 10
    return 5


def _derive_weather_condition(rainfall: Optional[float], humidity: Optional[float], temp: Optional[float]) -> str:
    """Meteorological condition summary based on physical NWP values."""
    if rainfall is not None and rainfall >= 20.0:
        return "Heavy Rain"
    elif rainfall is not None and rainfall >= 7.0:
        return "Moderate Rain"
    elif rainfall is not None and rainfall >= 0.5:
        return "Light Rain / Showers"
    elif humidity is not None and humidity >= 88.0 and temp is not None and temp <= 16.0:
        return "Dense Fog"
    elif humidity is not None and humidity >= 80.0:
        return "Overcast"
    elif humidity is not None and humidity >= 55.0:
        return "Partly Cloudy"
    else:
        return "Clear Sky"


def _sample_from_grid(grid_ds, lat: float, lon: float, time_idx: int) -> Dict[str, Optional[float]]:
    """Sample continuous variables nearest to state coordinates."""
    res: Dict[str, Optional[float]] = {}
    try:
        sample = grid_ds.sel(latitude=lat, longitude=lon, method="nearest")
        for v in ("temperature", "rainfall", "wind_speed", "humidity", "pressure"):
            if v in sample:
                val = float(sample[v].isel(time=time_idx).values)
                res[v] = None if np.isnan(val) else val
            else:
                res[v] = None
    except Exception as exc:
        logger.warning("[GFS] Spatial sample failed for (%s, %s): %s", lat, lon, exc)
    return res


def get_india_states_weather(
    lead_day: int = 1,
    config: Optional[GFSConfig] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Retrieve state-wise GFS forecast and confidence for India weather map.

    Results are cached on disk; fallback cache is returned if live data is unavailable.
    """
    config = config or get_gfs_config()
    cache_dir = config.processed_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"india_states_map_d{lead_day}.json"

    # Serve from cache if fresh and not forced
    if not force_refresh and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # If cache is younger than 30 minutes, return it
            cached_at = parse_iso(cached.get("last_updated"))
            if cached_at and (datetime.now(timezone.utc) - cached_at).total_seconds() < 1800:
                cached["is_cached"] = True
                return cached
        except Exception:
            pass

    # Find active cycle
    cycle = get_active_cycle(config)
    if cycle is None:
        runs = list_known_runs(config)
        if runs:
            cycle = runs[0].cycle_obj

    if cycle is None:
        # Fallback to existing cache if any exists
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cached["is_cached"] = True
            cached["status_note"] = "Showing latest available forecast data."
            return cached
        raise RuntimeError("No GFS model data available on system.")

    proc_dir = config.processed_cycle_dir(cycle.run_date, cycle.cycle)
    grid_path = proc_dir / "grid.nc"
    daily_path = proc_dir / "daily.json"

    # Compute freshness
    run_time = cycle.run_time
    valid_time = run_time + timedelta(days=lead_day)
    hours_since_run = (datetime.now(timezone.utc) - run_time).total_seconds() / 3600.0

    state_points: List[Dict[str, Any]] = []

    # Attempt xarray grid extraction if grid.nc is available
    if grid_path.exists():
        try:
            import xarray as xr

            with xr.open_dataset(grid_path) as ds:
                # Find time index closest to valid_time
                times = [datetime.fromisoformat(str(t).replace("Z", "+00:00")) if "+" in str(t) else datetime.fromisoformat(str(t)[:19]).replace(tzinfo=timezone.utc) for t in ds.time.values]
                target_dt = valid_time.replace(tzinfo=timezone.utc)
                # Find closest available forecast hour in this lead day
                time_idx = min(range(len(times)), key=lambda i: abs((times[i] - target_dt).total_seconds()))

                for state in INDIAN_STATES:
                    sample = _sample_from_grid(ds, state["latitude"], state["longitude"], time_idx)
                    temp = round(sample["temperature"], 1) if sample.get("temperature") is not None else None
                    rain = round(max(0.0, sample["rainfall"]), 1) if sample.get("rainfall") is not None else 0.0
                    wind = round(sample["wind_speed"] * 3.6, 1) if sample.get("wind_speed") is not None else None  # km/h
                    humidity = round(sample["humidity"], 1) if sample.get("humidity") is not None else None
                    pressure = round(sample["pressure"], 1) if sample.get("pressure") is not None else None

                    rain_prob = _derive_rain_probability(rain, humidity)
                    cond = _derive_weather_condition(rain, humidity, temp)
                    conf_score, conf_level, conf_color = _compute_confidence(lead_day, hours_since_run, temp is not None)

                    state_points.append({
                        "state_code": state["code"],
                        "state_name": state["name"],
                        "capital": state["capital"],
                        "latitude": state["latitude"],
                        "longitude": state["longitude"],
                        "lead_day": lead_day,
                        "temperature": temp,
                        "rainfall": rain,
                        "rain_probability": rain_prob,
                        "wind_speed": wind,  # km/h
                        "humidity": humidity,
                        "pressure": pressure,
                        "weather_condition": cond,
                        "forecast_confidence": conf_score,
                        "confidence_level": conf_level,
                        "confidence_color": conf_color,
                    })
        except Exception as exc:
            logger.error("[GFS] Error sampling grid.nc: %s", exc)

    # Fallback to daily.json if grid sampling didn't yield all states
    if len(state_points) < len(INDIAN_STATES) and daily_path.exists():
        state_points.clear()
        try:
            with open(daily_path, "r", encoding="utf-8") as f:
                daily_data = json.load(f)
            daily_rows = [r for r in daily_data.get("rows", []) if r.get("lead_day") == lead_day]
            row_by_state = {r["state"]: r for r in daily_rows}

            for state in INDIAN_STATES:
                r = row_by_state.get(state["name"])
                # If exact state not found, find closest geographic region
                if not r and daily_rows:
                    r = min(
                        daily_rows,
                        key=lambda x: (x.get("latitude", 20.0) - state["latitude"])**2 + (x.get("longitude", 80.0) - state["longitude"])**2
                    )

                temp = r.get("temperature") if r else None
                rain = r.get("rainfall", 0.0) if r else 0.0
                wind = round(r["wind_speed"] * 3.6, 1) if r and r.get("wind_speed") is not None else None
                humidity = r.get("humidity") if r else None
                pressure = r.get("pressure") if r else None

                rain_prob = _derive_rain_probability(rain, humidity)
                cond = _derive_weather_condition(rain, humidity, temp)
                conf_score, conf_level, conf_color = _compute_confidence(lead_day, hours_since_run, temp is not None)

                state_points.append({
                    "state_code": state["code"],
                    "state_name": state["name"],
                    "capital": state["capital"],
                    "latitude": state["latitude"],
                    "longitude": state["longitude"],
                    "lead_day": lead_day,
                    "temperature": temp,
                    "rainfall": rain,
                    "rain_probability": rain_prob,
                    "wind_speed": wind,
                    "humidity": humidity,
                    "pressure": pressure,
                    "weather_condition": cond,
                    "forecast_confidence": conf_score,
                    "confidence_level": conf_level,
                    "confidence_color": conf_color,
                })
        except Exception as exc:
            logger.error("[GFS] Fallback daily.json parsing error: %s", exc)

    now_iso = utcnow().isoformat()
    response_payload = {
        "model": "GFS",
        "model_version": config.model_version,
        "source": config.source_name,
        "source_label": config.source_label,
        "run_date": cycle.run_date,
        "cycle": f"{cycle.cycle:02d}",
        "run_time": run_time.isoformat(),
        "valid_time": valid_time.isoformat(),
        "lead_day": lead_day,
        "last_updated": now_iso,
        "is_cached": False,
        "status_note": "Live NOAA NOMADS GFS medium-range model forecast.",
        "disclaimer": DISCLAIMER,
        "states_count": len(state_points),
        "states": state_points,
    }

    # Write to local cache
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(response_payload, f, indent=2)
    except Exception as exc:
        logger.warning("[GFS] Cache write failed: %s", exc)

    return response_payload
