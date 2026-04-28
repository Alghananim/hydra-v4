@echo off
REM HYDRA V4.7 — Resumable 2-year backtest on real data.
REM Runs the frozen orchestrator with the V4.7 consensus fix.
REM Resumable: run again to continue from the last checkpoint.

setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%
set OUT=%CD%\replay_runs\v47_2y
if not exist "%OUT%" mkdir "%OUT%"

echo ============================================================
echo HYDRA V4.7 — 2-year backtest (resumable)
echo Output:  %OUT%
echo ============================================================
echo.

REM Run forever in 60-second chunks until DONE marker appears.
:loop
if exist "%OUT%\DONE" goto done
python "%CD%\replay\run_v47_backtest.py" --output-dir "%OUT%" --time-budget-s 55 --checkpoint-every 1000
if errorlevel 1 (
  echo.
  echo Run hit an error. Check "%OUT%\CRASH" if present, fix, then re-launch.
  pause
  exit /b 1
)
goto loop

:done
echo.
echo ============================================================
echo BACKTEST COMPLETE.
echo Summary:  %OUT%\summary.json
echo Cycles:   %OUT%\cycles.jsonl
echo Enters:   %OUT%\enter_candidates.jsonl
echo ============================================================
pause
