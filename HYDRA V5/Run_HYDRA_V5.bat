@echo off
REM ============================================================
REM HYDRA V5 — main launcher.
REM
REM This script is intentionally conservative. It defaults to DRY-RUN.
REM Live trading is only ever active when both:
REM   - HYDRA_LIVE_ARMED=1 is set in this shell, AND
REM   - HYDRA V5\approval_YYYYMMDD.token exists with non-empty content
REM   - All 16 safety guards in live\safety_guards.py pass per-cycle.
REM
REM Behaviour:
REM   1. Health check: Python present, repo intact, secrets NOT in repo.
REM   2. Run gatemind unit tests (sanity).
REM   3. Show menu:
REM        [1] Backtest (resumable, 2-year, no live).
REM        [2] War Room (analyse the last backtest).
REM        [3] Dry-run (live data, execution blocked).
REM        [4] Controlled-live micro (requires arming + token).
REM        [Q] Quit.
REM ============================================================

setlocal enabledelayedexpansion
set HYDRA=C:\Users\Mansur\Desktop\HYDRA V4
set V5=%~dp0
cd /d "%HYDRA%"
set PYTHONPATH=%HYDRA%

title HYDRA V5

echo.
echo ============================================================
echo  HYDRA V5 — main launcher
echo  Repo:  %HYDRA%
echo  V5:    %V5%
echo  Live:  %HYDRA_LIVE_ARMED%  (1 = armed, anything else = dry)
echo ============================================================
echo.

REM --- Health checks --------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: python not on PATH. Install Python 3.10+ and retry.
  pause
  exit /b 1
)

if not exist gatemind\v4\GateMindV4.py (
  echo ERROR: HYDRA V4 source tree not found at %HYDRA%.
  pause
  exit /b 1
)

REM Refuse to run if anything looking like an OANDA secret is in the
REM tracked tree. The .gitignore should prevent this but defence in depth.
findstr /m /s /i "oanda_api_token" "%HYDRA%\*.py" >nul 2>nul
if not errorlevel 1 (
  echo ERROR: An oanda_api_token literal appears in tracked source.
  echo This launcher refuses to start with a possible secret leak.
  pause
  exit /b 1
)

REM --- Sanity tests ---------------------------------------------------------
echo Running gatemind sanity tests...
python -m pytest gatemind\v4\tests --tb=line -q --no-header
if errorlevel 1 (
  echo.
  echo Sanity tests failed. Refusing to launch.
  pause
  exit /b 1
)
echo Sanity OK.
echo.

:menu
echo Choose an action:
echo   [1] Backtest 2-year (resumable, no live).
echo   [2] War Room (analyse last backtest output).
echo   [3] Dry-run live (no orders, blocked by design).
echo   [4] Controlled-live micro (requires arming + approval token).
echo   [Q] Quit.
set CHOICE=
set /p CHOICE=Selection:

if /I "%CHOICE%"=="1" goto backtest
if /I "%CHOICE%"=="2" goto warroom
if /I "%CHOICE%"=="3" goto dryrun
if /I "%CHOICE%"=="4" goto live
if /I "%CHOICE%"=="Q" goto end
echo Invalid choice.
goto menu

:backtest
set OUT=%HYDRA%\replay_runs\v47_2y
if not exist "%OUT%" mkdir "%OUT%"
:bt_loop
if exist "%OUT%\DONE" goto bt_done
python "%HYDRA%\replay\run_v47_backtest.py" --output-dir "%OUT%" --time-budget-s 300 --checkpoint-every 1000
if errorlevel 1 (
  echo Backtest hit an error. See "%OUT%\CRASH" if present.
  pause
  goto menu
)
goto bt_loop
:bt_done
echo Backtest complete: %OUT%\DONE
pause
goto menu

:warroom
set RUN_DIR=%HYDRA%\replay_runs\v47_2y
set WR_OUT=%HYDRA%\replay_runs\v47_warroom
if not exist "%RUN_DIR%\cycles.jsonl" (
  echo No cycles.jsonl. Run option [1] first.
  pause
  goto menu
)
if not exist "%WR_OUT%" mkdir "%WR_OUT%"
python -m replay.war_room.run_war_room --cycles "%RUN_DIR%\cycles.jsonl" --data-cache "%HYDRA%\data_cache" --out-dir "%WR_OUT%" --repo-root "%HYDRA%"
echo War Room complete: see HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md
pause
goto menu

:dryrun
set DR_OUT=%HYDRA%\replay_runs\dry_run
echo Starting dry-run. Press Ctrl+C to stop.
python "%HYDRA%\live\dry_run.py" --output-dir "%DR_OUT%" --duration-minutes 60
pause
goto menu

:live
set CL_OUT=%HYDRA%\replay_runs\controlled_live
if not "%HYDRA_LIVE_ARMED%"=="1" (
  echo HYDRA_LIVE_ARMED is not 1. Set it explicitly in your shell:
  echo     set HYDRA_LIVE_ARMED=1
  echo Then re-run this launcher.
  pause
  goto menu
)
echo Controlled-live: requires approval_YYYYMMDD.token in %CL_OUT%.
python "%HYDRA%\live\controlled_live.py" --output-dir "%CL_OUT%" --duration-minutes 60 --risk-pct 0.10 --max-trades-today 4 --max-daily-loss-pct 1.0
pause
goto menu

:end
echo Bye.
endlocal
