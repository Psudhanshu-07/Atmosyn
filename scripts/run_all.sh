#!/usr/bin/env bash
# Full pipeline (master prompts Prompt 11 / Part D): download -> quality ->
# build_dataset -> train (if needed) -> reports -> API.
#
# All steps use REAL public data only; no synthetic data is generated here.
# Start small first (Part F advice):
#   ./scripts/run_all.sh --smoke
#   ./scripts/run_all.sh --regions 5 --start 2023-01-01 --end 2023-06-30
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"

SMOKE=0
REGIONS_ARG=""
START="2023-01-01"
END="2023-12-31"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke)   SMOKE=1; shift ;;
    --regions) REGIONS_ARG="--regions $2"; shift 2 ;;
    --start)   START="$2"; shift 2 ;;
    --end)     END="$2"; shift 2 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done
if [[ "$SMOKE" == "1" ]]; then
  REGIONS_ARG="--regions 5"
  START="2023-01-01"
  END="2023-03-31"
fi

echo "== 1/6 downloading real observations (Open-Meteo ERA5 archive) =="
$PY scripts/download_observations.py --start "$START" --end "$END" $REGIONS_ARG

echo "== 2/6 downloading real forecast history (Open-Meteo Previous Runs) =="
$PY scripts/download_forecasts_history.py --start "$START" --end "$END" $REGIONS_ARG

echo "== 3/6 building training dataset =="
$PY scripts/build_dataset.py

echo "== 4/6 training models (DB-backed, chronological split) =="
$PY -m ml.training.train_model

echo "== 5/6 exporting reports (metrics / patterns / SHAP) =="
$PY scripts/export_reports.py

echo "== 6/6 starting API =="
echo "   uvicorn app.main:app --port 8000  (docs at /docs)"
cd backend && exec $PY -m uvicorn app.main:app --port 8000
