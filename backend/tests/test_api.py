"""TV-02: API contract tests against the seeded test database."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest


@pytest.fixture(scope="module")
def seeded(client):
    import importlib

    import seed_database

    importlib.reload(seed_database)
    seed_database.create_schema()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        seed_database.seed_regions(db)
        id_map = {r.region_id: r.id for r in db.query(Region).all()}
        seed_database.seed_history(db, id_map)
        seed_database._backfill_hist_features(db)
        seed_database.train_models_if_needed()
        seed_database.seed_current_run(db, id_map)
    finally:
        db.close()
    return True


from app.core.models import Region  # noqa: E402


class TestHealth:
    def test_health(self, client):
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] in ("healthy", "degraded")
        assert body["database"] == "connected"
        assert body["service"] == "atomsyn-api"


class TestRegions:
    def test_list_regions(self, client, seeded):
        res = client.get("/api/v1/regions")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] >= 36
        assert any(r["region_id"] == "MH_MUM" for r in body["regions"])

    def test_region_filter_by_state(self, client, seeded):
        res = client.get("/api/v1/regions?state=Maharashtra")
        assert res.status_code == 200
        assert all("Maharashtra" in r["state"] for r in res.json()["regions"])

    def test_region_detail(self, client, seeded):
        res = client.get("/api/v1/regions/MH_MUM")
        assert res.status_code == 200
        assert res.json()["region_name"] == "Mumbai"

    def test_region_not_found(self, client, seeded):
        res = client.get("/api/v1/regions/XX_XXX")
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "REGION_NOT_FOUND"


class TestForecast:
    def test_forecast_for_region(self, client, seeded):
        res = client.get("/api/v1/forecast?region_id=MH_MUM&lead_day=5&variable=rainfall")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] >= 1
        f = body["forecasts"][0]
        assert f["variable"] == "rainfall"
        assert f["lead_day"] == 5
        assert f["unit"] == "mm"

    def test_forecast_invalid_region(self, client, seeded):
        res = client.get("/api/v1/forecast?region_id=NOPE")
        assert res.status_code == 404


class TestConfidence:
    def test_confidence_single(self, client, seeded):
        res = client.get("/api/v1/confidence?region_id=MH_MUM&lead_day=5&variable=rainfall")
        assert res.status_code == 200
        body = res.json()
        assert 0.0 <= body["bust_probability"] <= 1.0
        assert body["confidence_score"] == pytest.approx(
            1 - body["bust_probability"], abs=1e-6
        )
        assert body["risk_level"] in (
            "VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH",
        )

    def test_confidence_10day(self, client, seeded):
        res = client.get("/api/v1/confidence/10day?region_id=MH_MUM&variable=rainfall")
        assert res.status_code == 200
        days = res.json()["days"]
        assert [d["lead_day"] for d in days] == list(range(1, 11))
        # confidence trend generally decreases with lead day
        conf = [d["confidence"] for d in days]
        assert conf[0] > conf[-1]

    def test_confidence_invalid_lead_day(self, client, seeded):
        res = client.get("/api/v1/confidence?region_id=MH_MUM&lead_day=11")
        assert res.status_code == 422

    def test_map_confidence(self, client, seeded):
        res = client.get("/api/v1/map/confidence?lead_day=5&variable=rainfall")
        assert res.status_code == 200
        body = res.json()
        assert body["lead_day"] == 5
        assert len(body["regions"]) >= 36
        point = body["regions"][0]
        for key in ("region_id", "latitude", "longitude", "risk_level"):
            assert key in point


class TestPredictAndExplain:
    def test_predict_bust(self, client, seeded):
        payload = {
            "region_id": "MH_MUM",
            "lead_day": 5,
            "variable": "rainfall",
            "forecast_value": 84.2,
            "historical_mae": 31.6,
            "historical_rmse": 42.1,
            "historical_bust_rate": 0.34,
            "run_to_run_change": 0.38,
            "ensemble_spread": 18.4,
        }
        res = client.post("/api/v1/predict/bust", json=payload)
        assert res.status_code == 200
        body = res.json()
        assert body["prediction_id"].startswith("PRED-")
        assert 0.0 <= body["bust_probability"] <= 1.0
        assert body["expected_error"] >= 0

        # prediction retrievable
        res2 = client.get(f"/api/v1/predictions/{body['prediction_id']}")
        assert res2.status_code == 200

        # explanation retrievable and structured
        res3 = client.get(f"/api/v1/explanation/{body['prediction_id']}")
        assert res3.status_code == 200
        exp = res3.json()
        assert isinstance(exp["summary"], str) and len(exp["summary"]) > 10
        for factor in exp["explanation"]:
            assert factor["impact"] in ("HIGH", "MEDIUM", "LOW")

    def test_predict_invalid_lead_day(self, client, seeded):
        res = client.post(
            "/api/v1/predict/bust",
            json={"region_id": "MH_MUM", "lead_day": 0, "variable": "rainfall",
                  "forecast_value": 10.0},
        )
        assert res.status_code == 422

    def test_predict_unknown_region(self, client, seeded):
        res = client.post(
            "/api/v1/predict/bust",
            json={"region_id": "XX_XX", "lead_day": 3, "variable": "rainfall",
                  "forecast_value": 10.0},
        )
        assert res.status_code == 404


class TestAnalytics:
    def test_error_stats(self, client, seeded):
        res = client.get(
            "/api/v1/analytics/error?region_id=MH_MUM&variable=rainfall&lead_day=5"
        )
        assert res.status_code == 200
        stats = res.json()["statistics"]
        assert stats["sample_count"] > 0
        assert stats["mae"] >= 0
        assert stats["rmse"] >= stats["mae"] * 0.9
        assert 0.0 <= stats["bust_rate"] <= 1.0

    def test_trends(self, client, seeded):
        res = client.get("/api/v1/analytics/trends?region_id=MH_MUM&variable=rainfall")
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) >= 1


class TestAlerts:
    def test_alerts_list(self, client, seeded):
        res = client.get("/api/v1/alerts")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] >= 1
        alert = body["alerts"][0]
        # SAF-AC-02/03: alerts carry region, variable, lead time, probability
        for key in ("region_id", "variable", "lead_day", "bust_probability", "confidence"):
            assert key in alert

    def test_alert_detail_disclaimer(self, client, seeded):
        res = client.get("/api/v1/alerts")
        alert_id = res.json()["alerts"][0]["alert_id"]
        res2 = client.get(f"/api/v1/alerts/{alert_id}")
        assert res2.status_code == 200
        assert "not an official weather warning" in res2.json()["disclaimer"]

    def test_acknowledge(self, client, seeded):
        res = client.get("/api/v1/alerts")
        alert_id = res.json()["alerts"][0]["alert_id"]
        res2 = client.post(f"/api/v1/alerts/{alert_id}/acknowledge",
                           json={"acknowledged_by": "tester"})
        assert res2.status_code == 200
        assert res2.json()["status"] == "ACKNOWLEDGED"


class TestModelsAndQuality:
    def test_models(self, client, seeded):
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        models = res.json()["models"]
        assert len(models) >= 1
        active = [m for m in models if m["status"] == "ACTIVE"]
        assert active and active[0]["roc_auc"] > 0.5

    def test_data_quality(self, client, seeded):
        res = client.get("/api/v1/data-quality")
        assert res.status_code == 200
        body = res.json()
        assert body["overall_status"] in ("GOOD", "DEGRADED", "CRITICAL")

    def test_dashboard_kpis(self, client, seeded):
        res = client.get("/api/v1/dashboard/kpis?lead_day=5&variable=rainfall")
        assert res.status_code == 200
        body = res.json()
        assert body["regions_monitored"] >= 36
        assert 0.0 <= body["avg_confidence"] <= 1.0


class TestVerificationAndDataSources:
    def test_data_sources(self, client):
        res = client.get("/api/v1/data-sources")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] == 4
        ids = [s["id"] for s in body["sources"]]
        assert "noaa-nomads-gfs" in ids
        assert "noaa-ncei-isd" in ids
        assert "ecmwf-copernicus-era5" in ids
        assert "isro-mosdac-insat" in ids
        for s in body["sources"]:
            assert s["url"].startswith("http")
            assert len(s["variables"]) > 0

    def test_system_verification(self, client, seeded):
        res = client.get("/api/v1/system-verification")
        assert res.status_code == 200
        body = res.json()
        assert body["overall_status"] in ("PASS", "DEGRADED", "FAIL")
        comps = [item["component"] for item in body["items"]]
        assert "Database Connection" in comps
        assert "Forecast Data" in comps
        assert "Observation Data" in comps
        assert "Historical Error Archive" in comps
        assert "ML Model Loaded" in comps
        assert "Anti-Leakage Guard" in comps

    def test_forecast_verification_endpoint(self, client, seeded):
        res = client.get("/api/v1/forecast/verification?region_id=MH_MUM&variable=rainfall&limit=10")
        assert res.status_code == 200
        body = res.json()
        assert body["region_id"] == "MH_MUM"
        assert body["variable"] == "rainfall"
        assert body["count"] > 0
        pair = body["pairs"][0]
        assert "forecast_value" in pair
        assert "observed_value" in pair
        assert "absolute_error" in pair
        assert pair["absolute_error"] == pytest.approx(abs(pair["forecast_value"] - pair["observed_value"]), abs=1e-4)

