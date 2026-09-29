@echo off
REM Full pipeline (master prompts Prompt 11 / Part D) for Windows:
REM download -> quality -> build_dataset -> train (if needed) -> reports -> API.
REM All steps use REAL public data only; no synthetic data is generated here.
REM Start small first (Part F advice):
REM   scripts\run_all.bat --smoke
REM   scripts\run_all.bat --regions 5 --start 2023-01-01 --end 2023-06-30
setlocal
cd /d "%~dp0.."

if "%PYTHON%"=="" set PYTHON=python

set SMOKE=0
set REGIONS_ARG=
set START=2023-01-01
set END=2023-12-31

:parse
if "%1"=="" goto run
if /I "%1"=="--smoke" ( set SMOKE=1 & shift & goto parse )
if /I "%1"=="--regions" ( set REGIONS_ARG=--regions %2 & shift & shift & goto parse )
if /I "%1"=="--start" ( set START=%2 & shift & shift & goto parse )
if /I "%1"=="--end" ( set END=%2 & shift & shift & goto parse )
echo unknown option: %1
exit /b 2

:run
if "%SMOKE%"=="1" (
  set REGIONS_ARG=--regions 5
  set START=2023-01-01
  set END=2023-03-31
)

echo == 1/6 downloading real observations (Open-Meteo ERA5 archive) ==
%PYTHON% scripts\download_observations.py --start %START% --end %END% %REGIONS_ARG%

echo == 2/6 downloading real forecast history (Open-Meteo Previous Runs) ==
%PYTHON% scripts\download_forecasts_history.py --start %START% --end %END% %REGIONS_ARG%

echo == 3/6 building training dataset ==
%PYTHON% scripts\build_dataset.py

echo == 4/6 training models (DB-backed, chronological split) ==
%PYTHON% -m ml.training.train_model

echo == 5/6 exporting reports (metrics / patterns / SHAP) ==
%PYTHON% scripts\export_reports.py

echo == 6/6 starting API ==
echo    uvicorn app.main:app --port 8000  (docs at /docs)
cd backend
%PYTHON% -m uvicorn app.main:app --port 8000
