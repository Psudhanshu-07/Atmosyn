# ATOMSYN — Forecast Reliability Platform

AI-powered analysis of medium-range weather forecast reliability (Day 1–10).

ATOMSYN analyzes numerical weather prediction (NWP) outputs, historical
forecast-vs-observation errors and meteorological information to estimate
**where, when and why a forecast is more likely to be significantly wrong**.
It is an analytical reliability layer: it does **not** replace forecasts and
does **not** issue official weather warnings — always defer to national
meteorological agencies.

Core flow: NWP forecast → historical forecast-vs-observation errors → ML bust
detection → calibrated bust probability → reliability score → explainable
drivers → interactive map, analytics, alerts, REST API.

## Features

- **Reliability map** — 36 Indian regions and all 36 States/UTs, Day 1–10,
  five weather variables (rainfall, temperature, wind, humidity, pressure).
- **Bust detection** — calibrated probability of a larger-than-usual forecast
  error, from an XGBoost classifier with isotonic probability calibration.
- **Expected error** — regressor estimating the magnitude of the error.
- **Explainability** — per-prediction feature attribution ("why is this
  forecast less reliable?").
- **Analytics** — historical error trends, bust patterns, confidence
  validation.
- **Alerts** — deduplicated high-risk indicators with expiry (reliability
  information, not warnings).
- **Data quality** — automated completeness, timeliness, uniqueness and
  validity checks with quarantine (never silently corrected).
- **REST API** — full programmatic access at `/api/v1/*`, interactive docs at
  `/docs`.

## Architecture

```
  NWP forecasts (GFS 0.25° via NOAA NOMADS; Open-Meteo for history)
        │                                observations (ERA5 archive / ISD)
        ▼                                        ▼
  backend/app/services/gfs   ────►   Forecast ↔ Observation pairing
        │                                        ▼
        │                        HistoricalError (error + bust label)
        │                                        ▼
        │              ml/training: XGBoost classifier + regressor,
        │              isotonic calibration, chronological split
        ▼                                        ▼
  reliability_service ──► Prediction (bust probability, confidence, SHAP)
        │                                        ▼
        └──► Alert (dedup/expiry)        FastAPI /api/v1/* ──► React UI
                                                 (Leaflet map, Chart.js, zustand)
```

## Installation

Backend (Python 3.11+):

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (bash: source .venv/Scripts/activate)
pip install -r backend/requirements.txt

cd backend
python seed_database.py           # builds the demo dataset + trains the model if absent
python -m uvicorn app.main:app --port 8000
```

API docs: http://127.0.0.1:8000/docs

Frontend (Node 18+):

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

UI: http://localhost:5173

Docker: `docker compose up --build` (backend + frontend containers).

## Data sources

| Source | Role | Notes |
|---|---|---|
| NOAA/NCEP GFS 0.25° (NOMADS) | operational forecasts Day 1–10 | public domain; cached + throttled in `backend/app/services/gfs/` |
| Open-Meteo Previous Runs API | historical forecast-vs-actual pairs | free non-commercial tier; throttled + resumable |
| Open-Meteo Archive API (ERA5) | daily observations (rain, tmax, wind, humidity, pressure) | free; reanalysis, not station truth |
| NOAA GEFS/GFS on AWS (`s3://noaa-gefs-pds`, anon) | Day 8–10 / reforecast | GRIB2; optional |
| IMD gridded via `imdlib` / CHIRPS | better rainfall ground truth | optional manual step |

Downloads cache to `data/processed/*.csv`, log to `logs/`, throttle requests,
retry with exponential backoff, and **never fabricate missing data** — a
failed download is reported and left missing.

## Model methodology

- **Bust definition (documented, deterministic)** — rainfall: bust when
  `abs_error > max(25 mm, 1.0×|obs| + 25 mm)` or the IMD rainfall class
  differs by ≥ 2 (<2.5, 2.5–15.5, 15.6–64.4, 64.5–115.5, 115.6–204.4,
  >204.4 mm/day). Temperature/wind/humidity/pressure: bust when
  `abs_error > max(25 units-equivalent, |obs| + threshold)` with thresholds
  5 °C, 10 m/s, 30 %, 10 hPa. The engine lives in
  `app/services/error_engine.py`; thresholds are configurable in
  `app/core/constants.py`.
- **Model** — XGBoost bust classifier + expected-error regressor, isotonic
  probability calibration on the validation slice, logistic-regression
  baseline.
- **Validation** — chronological split only (train 70 % / validation 15 % /
  test 15 % by valid time); no random splits, no future leakage; historical
  error features use only valid times strictly before the scored run.
  A ROC-AUC > 0.97 raises a leakage warning in the exported metrics.

## Output semantics

- Bust probability concern bands: **< 30 % low, 30–60 % moderate, > 60 % high**.
- Reliability score 0–100 → labels: **High ≥ 70, Medium 40–69, Low < 40**.
- Every alert carries: *"AI reliability alert — not an official weather warning."*

## Database

SQLite (`backend/forecast_bust.db`) via SQLAlchemy ORM — tables for regions,
forecast runs, forecasts, observations, historical errors, predictions,
model versions, alerts and data-quality reports. Tables are created on
startup; the seeder (`backend/seed_database.py`) builds the demo dataset and
trains/registers the active model. Swap `DATABASE_URL` (see
`.env.example`) for PostgreSQL in production.

## REST API (prefix `/api/v1`)

`/health` · `/regions` · `/forecast` · `/confidence` (+`/10day`, `/map/confidence`)
· `/predict/bust` · `/explanation/{id}` · `/analytics` · `/alerts` · `/models`
· `/dashboard/kpis` · `/data-quality` · `/quality` · `/data-sources`
· `/system-verification` · `/gfs/*` — full schemas at `/docs`.

## Development

```
backend/    FastAPI app (app/api, app/services, app/core), seeder, tests
frontend/   React + Vite + Tailwind + Leaflet + Chart.js + zustand
ml/         training pipeline and exported model bundles
scripts/    real-data download / dataset build / report export scripts
data/       raw + processed data caches
reports/    exported metrics and validation artifacts
```

## Testing

```bash
cd backend && python -m pytest tests/ -q
cd frontend && npm test && npm run lint && npm run build
```

## Reports

`scripts/export_reports.py` writes: `reports/model_metrics.json` (MAE, RMSE,
Precision, Recall, F1, ROC-AUC, PR-AUC, Brier), `reports/patterns.json`
(human-readable error patterns), `reports/shap_summary.png`, and
`reports/confidence_validation.json` — the test-period proof that *Low*
reliability rows show larger mean errors and higher bust rates than *High*.

## Limitations (honest)

- Demo bundle data is synthetic (deterministic seeder); real-data scripts are
  provided above and marked in every response's `source` field.
- ERA5 is reanalysis, not station ground truth; IMD station/gridded data is
  the better reference and can be ingested via `imdlib`.
- Open-Meteo free tier: non-commercial use, daily request limits.
- Historical archive currently 14 months × 36 city regions; Day 8–10 skill
  is limited by training data depth.
- Reliability indicators are AI estimates, **not** official warnings — always
  defer to national meteorological agencies.
