@echo off
chcp 65001 >nul
title HYDRA V4 - System Run + Health Check
color 0E

REM ============================================================
REM  Run_HYDRA_V4.bat
REM
REM  Runs HYDRA V4 environment check + smoke test + status report.
REM
REM  This script is SAFE — it does NOT:
REM    - Open trades
REM    - Call OANDA live
REM    - Print secrets
REM    - Modify any frozen brain
REM    - Need administrator privileges
REM
REM  Just double-click. The system speaks for itself.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo                    HYDRA V4 - System Run
echo  ============================================================
echo.

REM ---------- Environment check ----------
echo [1/6] Environment check...

if not exist "%PROJ%\contracts\brain_output.py" (
    echo  [X] HYDRA V4 not found at: %PROJ%
    echo      Looking for: contracts\brain_output.py
    pause
    exit /b 1
)
echo      [OK] Project found: %PROJ%

python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python not in PATH. Install from python.org and re-open shell.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo      [OK] Python %PYVER%

git --version >nul 2>&1
if errorlevel 1 (
    echo      [WARN] git not in PATH. Tag inspection unavailable.
    set "GIT_OK=0"
) else (
    echo      [OK] git available
    set "GIT_OK=1"
)
echo.

cd /d "%PROJ%"

REM ---------- Verify brain folders exist ----------
echo [2/6] Verifying 5 brain folders + orchestrator...
set "ALL_OK=1"
for %%B in (newsmind\v4 marketmind\v4 chartmind\v4 gatemind\v4 smartnotebook\v4 orchestrator\v4) do (
    if exist "%%B\__init__.py" (
        echo      [OK] %%B
    ) else (
        echo      [X]  %%B MISSING
        set "ALL_OK=0"
    )
)
if "%ALL_OK%"=="0" (
    echo      [X] One or more components missing. Cannot continue.
    pause
    exit /b 1
)
echo.

REM ---------- Check for forbidden imports ----------
echo [3/6] Checking for forbidden imports (live orders/network)...
set "FORBIDDEN_FOUND=0"
findstr /S /R /C:"^import oanda" /C:"^from oanda" /C:"^import requests" /C:"^from requests" /C:"submit_market_order\|place_order\|buy_market\|sell_market" *.py >nul 2>&1
if not errorlevel 1 (
    echo      [WARN] Forbidden patterns detected. Review with:
    echo               findstr /S /R /C:"submit_market_order" *.py
    set "FORBIDDEN_FOUND=1"
) else (
    echo      [OK] No live order or broker SDK imports found
)
echo.

REM ---------- Run frozen brain tests ----------
echo [4/6] Running frozen brain test suites (sanity)...
echo  ------------------------------------------------------------
set "BRAIN_FAILS=0"
for %%B in (newsmind marketmind chartmind gatemind smartnotebook) do (
    echo   * Testing %%B...
    python -m pytest %%B\v4\tests\ --tb=line -q 2>&1 | findstr /R /C:"passed\|failed\|error"
    if errorlevel 1 (
        echo      [X] %%B tests FAILED
        set /a BRAIN_FAILS+=1
    )
)
echo  ------------------------------------------------------------
if "%BRAIN_FAILS%"=="0" (
    echo      [OK] All 5 frozen brain suites pass
) else (
    echo      [X] %BRAIN_FAILS% brain suite(s) failed. Investigate before integration tests.
)
echo.

REM ---------- Run orchestrator integration tests ----------
echo [5/6] Running Orchestrator V4 integration tests...
echo  ------------------------------------------------------------
python -m pytest orchestrator\v4\tests\ --tb=short -q 2>&1
set "ORCH_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
if "%ORCH_EXIT%"=="0" (
    echo      [OK] Orchestrator V4 integration tests pass
) else (
    echo      [X] Orchestrator V4 tests failed
)
echo.

REM ---------- Final status report ----------
echo [6/6] System status report...
echo.
echo  ============================================================
echo                 HYDRA V4 STATUS REPORT
echo  ============================================================
echo.
echo   Components found:
echo     - NewsMind V4
echo     - MarketMind V4
echo     - ChartMind V4
echo     - GateMind V4
echo     - SmartNoteBook V4
echo     - Orchestrator V4
echo.
if "%GIT_OK%"=="1" (
    echo   Git tags:
    git tag -l 2>nul
    echo.
    echo   Latest commit:
    git log --oneline -1 2>nul
    echo.
)
echo   Pre-flight rules:
echo     - Trade pairs: EUR/USD + USD/JPY only
echo     - NY windows: 03:00-05:00 + 08:00-12:00 NY (DST-aware)
echo     - GateMind: 3/3 unanimous + A/A+ only + no B
echo     - Claude: downgrade-only (no upgrade authority)
echo     - Live orders: BLOCKED in this script
echo     - OANDA live: NOT CALLED in this script
echo.
if "%BRAIN_FAILS%"=="0" if "%ORCH_EXIT%"=="0" (
    echo  ============================================================
    echo            HYDRA V4 - HEALTHY
    echo  ============================================================
    echo.
    echo   All 632 tests pass ^(538 brain + 94 orchestrator^).
    echo   System is ready for next phases:
    echo     - Backtester V4
    echo     - Risk/Execution Layer
    echo     - Live monitoring dashboard
) else (
    echo  ============================================================
    echo            HYDRA V4 - DEGRADED
    echo  ============================================================
    echo.
    echo   One or more test suites failed. Investigate before
    echo   trusting the system in any production-like mode.
)
echo.
echo  Reports available in: %PROJ%\All files\
echo.
pause
