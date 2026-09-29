"""Tests for master-prompt alignment additions (Prompts 3, 4, 6, 8).

Synthetic values here are UNIT TEST FIXTURES ONLY (allowed by the global
rule); the application pipeline itself never generates data.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))

from app.services.error_engine import (  # noqa: E402
    bust_concern_band,
    confidence_label,
    rainfall_bust_label,
)


class TestRainfallBustDefinition:
    def test_magnitude_rule_fires(self):
        # abs_error 60 > max(25, |40|+25=65)? No -> magnitude rule NOT fired.
        # 100 vs 40: error 60, threshold 65 -> not a magnitude bust...
        # but IMD class shift: 100 = class 2 (15.6-64.4), 40 = class 2 -> no.
        assert rainfall_bust_label(100.0, 40.0) is False

    def test_large_error_is_bust(self):
        # 200 vs 40: error 160 > 65 and classes 4 vs 2 (shift 2) -> bust.
        assert rainfall_bust_label(200.0, 40.0) is True

    def test_floor_25mm(self):
        # 30 vs 0.5: error 29.5 > max(25, 0.5+25=25.5) -> bust.
        assert rainfall_bust_label(30.0, 0.5) is True

    def test_small_error_not_bust(self):
        assert rainfall_bust_label(12.0, 10.0) is False

    def test_class_shift_two_is_bust(self):
        # 20 mm forecast vs 0.5 mm observed: error 19.5 < max(25, 25.5) so the
        # magnitude rule does NOT fire, but IMD classes 2 vs 0 -> shift 2 -> bust.
        assert rainfall_bust_label(20.0, 0.5) is True

    def test_same_class_not_bust_by_shift(self):
        # 60 vs 30: same class (2), error 30 < max(25, 55) -> no bust.
        assert rainfall_bust_label(60.0, 30.0) is False


class TestBandsAndLabels:
    def test_concern_bands(self):
        assert bust_concern_band(0.29) == "LOW"
        assert bust_concern_band(0.30) == "MODERATE"
        assert bust_concern_band(0.60) == "MODERATE"
        assert bust_concern_band(0.61) == "HIGH"
        assert bust_concern_band(0.95) == "HIGH"

    def test_confidence_labels(self):
        assert confidence_label(70.0) == "HIGH"
        assert confidence_label(69.9) == "MEDIUM"
        assert confidence_label(40.0) == "MEDIUM"
        assert confidence_label(39.9) == "LOW"
        assert confidence_label(0.0) == "LOW"


class TestQualityEndpoint:
    def test_quality_report(self, seeded_db, client):
        resp = client.get("/api/v1/quality")
        assert resp.status_code == 200
        body = resp.json()
        assert body["overall_status"] in ("PASS", "WARN", "FAIL")
        assert body["totals"]["checks_run"] >= 5
        names = {c["name"] for c in body["checks"]}
        assert {
            "missing_values",
            "freshness",
            "duplicate_keys",
            "out_of_range_values",
            "region_coordinates",
        } <= names

    def test_quality_report_written_to_disk(self, seeded_db, client):
        client.get("/api/v1/quality")
        report = _ROOT / "reports" / "data_quality.json"
        assert report.exists()
        text = report.read_text(encoding="utf-8")
        assert "overall_status" in text


class TestLatestRunSelection:
    """Regression: a newer partial live-GFS run must not hide Day 6-10.

    A live NOMADS ingest creates a newer run scored only for Day 1-5 (120 h
    filter). latest_run_time must keep serving the latest FULL-horizon scored
    run so the UI keeps its complete Day 1-10 trend.
    """

    def test_prefers_full_horizon_scored_run(self, seeded_db, client):
        from datetime import timedelta

        from app.core.database import SessionLocal
        from app.core.models import Forecast, ForecastRun, Prediction, Region
        from app.services import reliability_service

        db = SessionLocal()
        try:
            full_run = reliability_service.latest_run_time(db)
            assert full_run is not None

            newer = full_run + timedelta(hours=12)
            run = ForecastRun(run_time=newer, source="NOAA/NCEP NOMADS", model="GFS-0.25deg")
            db.add(run)
            db.flush()
            rid = db.query(Region).first().id
            for lead in (1, 2):
                db.add(
                    Forecast(
                        run_id=run.id, region_id=rid, variable="rainfall",
                        forecast_run=newer, valid_time=newer + timedelta(days=lead),
                        lead_day=lead, value=5.0, unit="mm",
                    )
                )
                db.add(
                    Prediction(
                        prediction_id=f"PRED-TST{lead}",
                        prediction_key=f"t|{lead}|{newer.isoformat()}",
                        region_id=rid, variable="rainfall", lead_day=lead,
                        forecast_run=newer, valid_time=None, forecast_value=5.0,
                        expected_error=1.0, bust_probability=0.1,
                        confidence_score=0.9, risk_level="LOW", model_version="test",
                    )
                )
            db.commit()

            assert reliability_service.latest_run_time(db) == full_run
        finally:
            db.close()
