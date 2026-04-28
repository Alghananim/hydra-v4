@echo off
REM HYDRA 4.7 War Room — total-failure investigation pipeline.
REM Reads cycles.jsonl from a finished or in-progress backtest and
REM produces every artefact listed in the brief, ending in
REM HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md
REM at the repo root.

setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%
set RUN_DIR=%CD%\replay_runs\v47_2y
set OUT=%CD%\replay_runs\v47_warroom

if not exist "%RUN_DIR%\cycles.jsonl" (
  echo ERROR: %RUN_DIR%\cycles.jsonl not found.
  echo Run Run_V47_Backtest.bat first to produce a cycles.jsonl.
  pause
  exit /b 1
)

if not exist "%OUT%" mkdir "%OUT%"

echo ============================================================
echo HYDRA 4.7 War Room
echo Cycles input: %RUN_DIR%\cycles.jsonl
echo Output dir:   %OUT%
echo ============================================================
echo.

python -m replay.war_room.run_war_room ^
    --cycles "%RUN_DIR%\cycles.jsonl" ^
    --data-cache "%CD%\data_cache" ^
    --out-dir "%OUT%" ^
    --repo-root "%CD%"

if errorlevel 1 (
  echo.
  echo War Room run hit an error.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo WAR ROOM COMPLETE.
echo Report: HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md
echo Artefacts: %OUT%
echo ============================================================
pause
