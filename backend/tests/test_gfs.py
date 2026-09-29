"""Tests for the NOAA/NCEP GFS ingestion service (app.services.gfs).

Unit tests are hermetic: no network access. The GRIB2 parsing tests reuse the
real files downloaded by the ingestion service when they are present, and are
skipped otherwise (run ``python -m app.services.gfs.downloader`` first to
populate them).
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.gfs import client as client_mod
from app.services.gfs import cycle_detector, downloader, parser, processor
from app.services.gfs.config import (
    GFSBounds,
    GFSVariableSpec,
    VARIABLE_CATALOG,
    get_gfs_config,
)
from app.services.gfs.models import GFSCycle, GFSFileRecord, GFSRunStatus


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------
class TestBuildUrl:
    def test_contains_file_vars_levels_bounds_and_dir(self):
        url = client_mod.build_gfs_url(
            date="20260928",
            cycle=12,
            forecast_hour=6,
            variables=["TMP", "APCP", "UGRD", "VGRD"],
            levels=["2_m_above_ground", "10_m_above_ground", "surface"],
            bounds=GFSBounds(68, 98, 6, 38),
        )
        assert url.startswith("https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?")
        assert "file=gfs.t12z.pgrb2.0p25.f006" in url
        for var in ("TMP", "APCP", "UGRD", "VGRD"):
            assert f"var_{var}=on" in url
        assert "lev_2_m_above_ground=on" in url
        assert "lev_10_m_above_ground=on" in url
        assert "leftlon=68" in url and "rightlon=98" in url
        assert "toplat=38" in url and "bottomlat=6" in url
        assert "dir=%2Fgfs.20260928%2F12%2Fatmos" in url

    def test_subregion_flag_present_with_bounds(self):
        """NOMADS ignores the lat/lon box unless ``subregion`` is sent."""
        url = client_mod.build_gfs_url("20260928", 0, 0, ["TMP"], ["2_m_above_ground"],
                                       GFSBounds(68, 98, 6, 38))
        assert "subregion" in url

    def test_no_subregion_without_bounds(self):
        url = client_mod.build_gfs_url("20260928", 0, 0, ["TMP"], ["2_m_above_ground"])
        assert "subregion" not in url
        assert "leftlon" not in url

    def test_accepts_date_objects(self):
        url = client_mod.build_gfs_url(datetime(2026, 9, 28, tzinfo=timezone.utc), 18, 120,
                                       ["TMP"], ["2_m_above_ground"])
        assert "file=gfs.t18z.pgrb2.0p25.f120" in url
        assert "dir=%2Fgfs.20260928%2F18%2Fatmos" in url

    def test_hour_zero_is_zero_padded(self):
        url = client_mod.build_gfs_url("20260928", 0, 0, ["TMP"], ["2_m_above_ground"])
        assert "f000" in url
        assert "t00z" in url


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class TestConfig:
    def test_defaults_are_india_focused(self):
        cfg = get_gfs_config()
        assert cfg.bounds.as_dict() == {
            "leftlon": 68.0, "rightlon": 98.0, "toplat": 38.0, "bottomlat": 6.0
        }

    def test_forecast_hour_grid(self):
        cfg = get_gfs_config()
        assert cfg.forecast_hours[0] == 0
        assert cfg.forecast_hours[-1] == 120
        assert cfg.forecast_hours[1] - cfg.forecast_hours[0] == 3

    def test_cycles(self):
        assert get_gfs_config().cycles == (0, 6, 12, 18)

    def test_required_variables_present(self):
        shorts = {s.short_name for s in get_gfs_config().variables}
        assert {"TMP", "APCP", "UGRD", "VGRD"} <= shorts
        assert "RH" in shorts

    def test_catalog_is_extensible(self):
        """A new variable only needs a catalog entry to become requestable."""
        assert "HGT" not in VARIABLE_CATALOG
        VARIABLE_CATALOG["HGT"] = GFSVariableSpec(
            "HGT", "isobaricInhPa", 500.0, "500_mb", None, "gpm"
        )
        try:
            assert VARIABLE_CATALOG["HGT"].level_name == "500_mb"
        finally:
            del VARIABLE_CATALOG["HGT"]


# ---------------------------------------------------------------------------
# Cycle candidate generation
# ---------------------------------------------------------------------------
class TestCandidateCycles:
    def test_newest_first(self):
        cycles = cycle_detector.candidate_cycles(
            now=datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)
        )
        assert cycles[0] == GFSCycle("20260928", 12)

    def test_publication_delay_is_respected(self):
        """A cycle inside the delay window must not be proposed."""
        now = datetime(2026, 9, 28, 13, 0, tzinfo=timezone.utc)
        keys = {c.key for c in cycle_detector.candidate_cycles(now=now)}
        assert "20260928_12" not in keys  # only 1 h after nominal time
        assert "20260928_06" in keys

    def test_all_candidates_are_valid_cycles(self):
        for cycle in cycle_detector.candidate_cycles(
            now=datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)
        ):
            assert cycle.cycle in (0, 6, 12, 18)

    def test_nomads_dir_format(self):
        assert GFSCycle("20260928", 12).nomads_dir == "/gfs.20260928/12/atmos"

    def test_run_time_roundtrip(self):
        cycle = GFSCycle("20260928", 18)
        assert cycle.run_time == datetime(2026, 9, 28, 18, tzinfo=timezone.utc)
        assert GFSCycle.from_run_time(cycle.run_time) == cycle


# ---------------------------------------------------------------------------
# Dedupe / metadata
# ---------------------------------------------------------------------------
class TestDedupe:
    def test_valid_record_with_matching_file_is_current(self, tmp_path):
        path = tmp_path / "f006.grib2"
        path.write_bytes(b"GRIB" + b"\x00" * 2048)
        record = GFSFileRecord(
            cycle="12",
            run_date="20260928",
            forecast_hour=6,
            status=GFSRunStatus.VALID.value,
            size_bytes=path.stat().st_size,
        )
        from app.services.gfs.models import sha256_of

        record.checksum = sha256_of(path)
        assert downloader.is_file_current(record, path) is True

    def test_missing_file_is_not_current(self, tmp_path):
        record = GFSFileRecord(
            cycle="12", run_date="20260928", forecast_hour=6,
            status=GFSRunStatus.VALID.value, size_bytes=100,
        )
        assert downloader.is_file_current(record, tmp_path / "nope.grib2") is False

    def test_invalid_record_is_never_current(self, tmp_path):
        path = tmp_path / "f006.grib2"
        path.write_bytes(b"GRIB" + b"\x00" * 100)
        record = GFSFileRecord(
            cycle="12", run_date="20260928", forecast_hour=6,
            status=GFSRunStatus.INVALID.value, size_bytes=path.stat().st_size,
        )
        assert downloader.is_file_current(record, path) is False

    def test_size_mismatch_is_not_current(self, tmp_path):
        path = tmp_path / "f006.grib2"
        path.write_bytes(b"GRIB" + b"\x00" * 100)
        record = GFSFileRecord(
            cycle="12", run_date="20260928", forecast_hour=6,
            status=GFSRunStatus.VALID.value, size_bytes=999,
        )
        assert downloader.is_file_current(record, path) is False


# ---------------------------------------------------------------------------
# Validation (corrupt / incomplete data must never be marked valid)
# ---------------------------------------------------------------------------
class TestValidation:
    def test_missing_file(self, tmp_path):
        result = parser.validate_grib2(tmp_path / "absent.grib2")
        assert not result.valid
        assert "does not exist" in result.reason

    def test_too_small(self, tmp_path):
        path = tmp_path / "tiny.grib2"
        path.write_bytes(b"GRIB")
        result = parser.validate_grib2(path)
        assert not result.valid
        assert "too small" in result.reason

    def test_html_error_page_is_rejected(self, tmp_path):
        path = tmp_path / "error.grib2"
        path.write_bytes(b"<html>Request for Future Data</html>" * 100)
        result = parser.validate_grib2(path)
        assert not result.valid
        assert "GRIB2 magic" in result.reason

    def test_truncated_grib_is_rejected(self, tmp_path):
        path = tmp_path / "truncated.grib2"
        path.write_bytes(b"GRIB" + b"\x00" * 4096)
        result = parser.validate_grib2(path)
        assert not result.valid
        assert "parse failed" in result.reason or "no data variables" in result.reason

    def test_quarantine_moves_file_out_of_the_way(self, tmp_path):
        cfg = dataclasses.replace(
            get_gfs_config(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "processed"
        )
        cfg.ensure_dirs()
        bad = cfg.cycle_dir("20260928", 12) / "bad.grib2"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"not grib")
        moved = downloader.quarantine(cfg, bad, "test reason")
        assert moved is not None and moved.exists()
        assert not bad.exists()
        assert json.loads((moved.with_suffix(moved.suffix + ".reason.json")).read_text())[
            "reason"
        ] == "test reason"


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------
class TestUnitNormalisation:
    def test_kelvin_to_celsius(self):
        import numpy as np
        import xarray as xr

        ds = xr.Dataset(
            {"t2m": (("latitude", "longitude"), np.array([[273.15, 283.15]]))},
            coords={"latitude": [0.0], "longitude": [0.0, 0.25]},
        )
        out = parser.to_project_variables(ds)["temperature"]
        assert out.values[0][0] == pytest.approx(0.0)
        assert out.values[0][1] == pytest.approx(10.0)

    def test_wind_speed_from_components(self):
        import numpy as np
        import xarray as xr

        ds = xr.Dataset(
            {
                "u10": (("latitude", "longitude"), np.array([[3.0]])),
                "v10": (("latitude", "longitude"), np.array([[4.0]])),
            },
            coords={"latitude": [0.0], "longitude": [0.0]},
        )
        out = parser.to_project_variables(ds)
        assert out["wind_speed"].values[0][0] == pytest.approx(5.0)

    def test_pascal_to_hpa(self):
        import numpy as np
        import xarray as xr

        ds = xr.Dataset(
            {"sp": (("latitude", "longitude"), np.array([[100800.0]]))},
            coords={"latitude": [0.0], "longitude": [0.0]},
        )
        assert parser.to_project_variables(ds)["pressure"].values[0][0] == pytest.approx(
            1008.0
        )


# ---------------------------------------------------------------------------
# Daily aggregation
# ---------------------------------------------------------------------------
def _row(region_id, hour, lead_day=None, rainfall=None, temperature=25.0):
    return {
        "region_id": region_id,
        "region_name": "X",
        "state": "Y",
        "forecast_run": "2026-09-28T12:00:00+00:00",
        "forecast_hour": hour,
        "valid_time": "2026-09-28T12:00:00+00:00",
        "lead_day": processor.lead_day_for_hour(hour) if lead_day is None else lead_day,
        "source": "NOAA/NCEP GFS",
        "data_type": "NWP_MODEL_FORECAST",
        "rainfall": rainfall,
        "temperature": temperature,
        "wind_speed": 3.0,
        "humidity": 60.0,
        "pressure": 1000.0,
    }


class TestDailyAggregation:
    def test_lead_day_window_boundaries(self):
        assert processor.lead_day_for_hour(0) == 1
        assert processor.lead_day_for_hour(3) == 1
        assert processor.lead_day_for_hour(24) == 1
        assert processor.lead_day_for_hour(27) == 2
        assert processor.lead_day_for_hour(120) == 5

    def test_rainfall_is_differenced_accumulation(self):
        """GFS ``tp`` accumulates from run start: a day total is a difference."""
        rows = [
            _row("A", 0, rainfall=None),
            _row("A", 3, rainfall=1.0),
            _row("A", 12, rainfall=4.0),
            _row("A", 21, rainfall=7.0),
            _row("A", 24, rainfall=7.0),
        ]
        out = processor.daily_aggregates(rows, GFSCycle("20260928", 12))
        assert len(out) == 1
        # Day 1 covers f003..f021; tp(21) - tp(0). tp(0) is absent in real GFS,
        # so the run-total is used directly.
        assert out[0]["rainfall"] == pytest.approx(7.0)

    def test_rainfall_difference_uses_previous_day_total(self):
        rows = [
            _row("A", 0, rainfall=1.0),
            _row("A", 24, rainfall=6.0),   # run total at end of day 1
            _row("A", 27, rainfall=6.5),
            _row("A", 45, rainfall=9.0),   # run total at end of day 2
        ]
        out = processor.daily_aggregates(rows, GFSCycle("20260928", 12))
        assert len(out) == 2
        assert out[0]["rainfall"] == pytest.approx(5.0)   # 6.0 - 1.0
        assert out[1]["rainfall"] == pytest.approx(3.0)   # 9.0 - 6.0

    def test_rainfall_never_negative(self):
        rows = [
            _row("A", 0, rainfall=5.0),
            _row("A", 24, rainfall=1.0),
        ]
        out = processor.daily_aggregates(rows, GFSCycle("20260928", 12))
        assert out[0]["rainfall"] == 1.0

    def test_temperature_is_a_daily_mean(self):
        rows = [
            _row("A", 3, temperature=20.0),
            _row("A", 12, temperature=30.0),
            _row("A", 21, temperature=25.0),
        ]
        out = processor.daily_aggregates(rows, GFSCycle("20260928", 12))
        assert out[0]["temperature"] == pytest.approx(25.0)

    def test_missing_values_are_tolerated(self):
        rows = [
            _row("A", 3, temperature=None),
            _row("A", 12, temperature=30.0),
            _row("A", 21, temperature=30.0),
        ]
        out = processor.daily_aggregates(rows, GFSCycle("20260928", 12))
        assert out[0]["temperature"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
class TestRetention:
    def test_old_cycle_is_removed_active_one_kept(self, tmp_path):
        cfg = dataclasses.replace(
            get_gfs_config(), raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed", retention_days=1,
        )
        cfg.ensure_dirs()

        old = GFSCycle("20200101", 0)
        keep = GFSCycle("20200102", 0)
        for cycle in (old, keep):
            meta = downloader.new_run_metadata(cfg, cycle)
            meta.status = GFSRunStatus.VALID.value
            downloader.save_run_metadata(cfg, meta)
            cfg.cycle_dir(cycle.run_date, cycle.cycle).mkdir(parents=True)

        downloader.set_active_cycle(keep, cfg)
        downloader.apply_retention(cfg)

        assert not (tmp_path / "raw" / "index" / "20200101_00.json").exists()
        assert (tmp_path / "raw" / "index" / "20200102_00.json").exists()

    def test_retention_disabled(self, tmp_path):
        cfg = dataclasses.replace(
            get_gfs_config(), raw_dir=tmp_path / "raw", retention_days=0
        )
        cfg.ensure_dirs()
        cycle = GFSCycle("20200101", 0)
        downloader.save_run_metadata(cfg, downloader.new_run_metadata(cfg, cycle))
        assert downloader.apply_retention(cfg) == []


# ---------------------------------------------------------------------------
# Active-cycle pointer
# ---------------------------------------------------------------------------
class TestActiveCycle:
    def test_set_and_read(self, tmp_path):
        cfg = dataclasses.replace(
            get_gfs_config(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "processed"
        )
        cfg.ensure_dirs()

        first, second = GFSCycle("20260928", 6), GFSCycle("20260928", 12)
        for cycle in (first, second):
            downloader.save_run_metadata(cfg, downloader.new_run_metadata(cfg, cycle))
            downloader.set_active_cycle(cycle, cfg)

        assert downloader.get_active_cycle(cfg) == second
        pointer = json.loads(cfg.active_pointer.read_text())
        assert pointer["source_label"] == "NOAA/NCEP GFS"
        assert pointer["data_type"] == "NWP_MODEL_FORECAST"
        # previous run is demoted, not deleted
        assert downloader.load_run_metadata(cfg, first).is_active is False

    def test_no_active_cycle_is_none(self, tmp_path):
        cfg = dataclasses.replace(get_gfs_config(), raw_dir=tmp_path / "raw")
        cfg.ensure_dirs()
        assert downloader.get_active_cycle(cfg) is None


# ---------------------------------------------------------------------------
# API (no network: exercises only the stored-data endpoints)
# ---------------------------------------------------------------------------
class TestGFSApi:
    def test_status_endpoint_declares_provenance(self, client):
        response = client.get("/api/v1/gfs/status")
        assert response.status_code == 200
        body = response.json()
        assert body["api_key_required"] is False
        assert body["source_url"] == "https://nomads.ncep.noaa.gov/"
        assert body["data_type"] == "NWP_MODEL_FORECAST"
        assert "not an observation" in body["disclaimer"]

    def test_runs_endpoint(self, client):
        response = client.get("/api/v1/gfs/runs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_forecast_requires_stored_data(self, client):
        """Without a stored cycle the API must 503, never fabricate values."""
        cfg = get_gfs_config()
        if downloader.get_active_cycle(cfg) is not None:
            pytest.skip("a real GFS cycle is stored in this environment")
        response = client.get("/api/v1/gfs/forecast")
        assert response.status_code == 503

    def test_sync_to_db_endpoint(self, client):
        cfg = get_gfs_config()
        if downloader.get_active_cycle(cfg) is None:
            pytest.skip("no active GFS cycle stored")
        response = client.post("/api/v1/gfs/sync-to-db")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["synced_forecasts"] >= 0

    def test_india_map_endpoint(self, client):
        cfg = get_gfs_config()
        if downloader.get_active_cycle(cfg) is None:
            pytest.skip("no active GFS cycle stored")
        response = client.get("/api/v1/gfs/india-map?lead_day=1")
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "GFS"
        assert data["states_count"] == 36
        assert len(data["states"]) == 36
        first = data["states"][0]
        assert "state_name" in first
        assert "temperature" in first
        assert "forecast_confidence" in first
        assert first["confidence_level"] in ("HIGH", "MODERATE", "LOW", "NO_DATA")




# ---------------------------------------------------------------------------
# Real downloaded data (integration; skipped when nothing has been fetched)
# ---------------------------------------------------------------------------
def _first_raw_file() -> Path | None:
    cfg = get_gfs_config()
    if not cfg.raw_dir.exists():
        return None
    files = sorted(cfg.raw_dir.rglob("*.grib2"))
    return files[0] if files else None


@pytest.mark.skipif(_first_raw_file() is None, reason="no downloaded GRIB2 available")
class TestRealGrib:
    def test_real_file_is_valid_and_subset(self):
        path = _first_raw_file()
        result = parser.validate_grib2(path)
        assert result.valid, result.reason
        assert result.latitude_range[0] >= get_gfs_config().bounds.bottom_lat
        assert result.longitude_range[0] >= get_gfs_config().bounds.left_lon

    def test_real_file_yields_expected_variables(self):
        names = parser.parse_grib2(_first_raw_file()).data_vars
        assert {"t2m", "u10", "v10"} <= set(names)
