@echo off
chcp 65001 >nul
title HYDRA V4 - Phase 8 Two-Year Backtest
color 0B

cls
echo.
echo  ============================================================
echo            HYDRA V4 - PHASE 8 TWO-YEAR BACKTEST
echo  ============================================================
echo.
echo  Pick a run depth:
echo.
echo    [1] 7-day smoke test       (~3-5 minutes)  — fast sanity check
echo    [2] 90-day sample          (~25-40 minutes) — meaningful sample
echo    [3] 365-day half-year      (~90-120 minutes)
echo    [4] 730-day FULL 2-year    (~3-4 hours)    — definitive Phase 8
echo.

set /p CHOICE="Choice [1-4]: "

if "%CHOICE%"=="1" set "REPLAY_DAYS=7"
if "%CHOICE%"=="2" set "REPLAY_DAYS=90"
if "%CHOICE%"=="3" set "REPLAY_DAYS=365"
if "%CHOICE%"=="4" set "REPLAY_DAYS=730"

if "%REPLAY_DAYS%"=="" (
    echo  Invalid choice. Defaulting to 90 days.
    set "REPLAY_DAYS=90"
)

echo.
echo  ============================================================
echo  Replay window: %REPLAY_DAYS% days
echo  Pairs: EUR_USD + USD_JPY
echo  Granularity: M15
echo  News: ReplayNewsMindV4 (calendar-only, no HTTP, no lookahead)
echo  Live trading: BLOCKED by LIVE_ORDER_GUARD (6 layers)
echo  ============================================================
echo.
echo  Output:
echo    Full log:        %USERPROFILE%\Desktop\PHASE8_BACKTEST_LOG.txt
echo    Replay reports:  %USERPROFILE%\Desktop\HYDRA V4\replay_results\
echo.
echo  Press any key to start.
pause >nul

set "ROOT=%USERPROFILE%\Desktop\HYDRA V4"
set "LOG=%USERPROFILE%\Desktop\PHASE8_BACKTEST_LOG.txt"

cd /d "%ROOT%"

REM Clear old replay_results
if exist "replay_results" rmdir /s /q "replay_results" 2>nul

echo HYDRA V4 - PHASE 8 BACKTEST > "%LOG%"
echo Started: %DATE% %TIME% >> "%LOG%"
echo REPLAY_DAYS=%REPLAY_DAYS% >> "%LOG%"
echo. >> "%LOG%"

REM Tee output to both stdout and log
echo Y | python setup_and_run.py 2>&1
set "RC=%errorlevel%"

echo. >> "%LOG%"
echo Finished: %DATE% %TIME% >> "%LOG%"
echo Exit code: %RC% >> "%LOG%"

REM Capture the full HYDRA_REPLAY.log into the Phase 8 log too
if exist "%USERPROFILE%\Desktop\HYDRA_REPLAY.log" (
    echo. >> "%LOG%"
    echo === HYDRA_REPLAY.log appended === >> "%LOG%"
    type "%USERPROFILE%\Desktop\HYDRA_REPLAY.log" >> "%LOG%"
)

echo.
echo  ============================================================
if "%RC%"=="0" (
    echo  Backtest completed.
    if exist "replay_results\REAL_DATA_REPLAY_REPORT.md" (
        echo  Reports written to:
        echo    %ROOT%\replay_results\
        echo.
        echo  Tell Claude "Phase 8 done" to read and aggregate.
    ) else (
        echo  Backtest exited 0 but no report file found.
        echo  Check %LOG% for details.
    )
) else (
    echo  Backtest exited with code %RC%.
    echo  Check %LOG% for details.
)
echo  ============================================================
echo.
echo  Press any key to close.
pause >nul
exit /b %RC%
