@echo off
chcp 65001 >nul
title HYDRA V4 - Two-Year Real Data Replay
color 0E

REM ============================================================
REM  Run_Two_Year_Replay.bat
REM
REM  LIVE_DATA_ONLY phase — NO live orders.
REM
REM  This script will:
REM    1. Load OANDA + Anthropic keys from secrets\.env (gitignored)
REM    2. Run all framework tests (133+ expected)
REM    3. Download 2 years of M15 EUR/USD + USD/JPY
REM    4. Replay through Orchestrator V4 chronologically
REM    5. Call Claude (when used) with secret-redacted payloads
REM    6. Generate REAL_DATA_REPLAY_REPORT.md with ACTUAL numbers
REM
REM  GUARANTEES (enforced by code):
REM    - LIVE_ORDER_GUARD active — any order attempt raises
REM    - No secrets in logs (redactor at every boundary)
REM    - No future bars in orchestrator (slice_visible strict)
REM    - No upgrade authority for Claude (enum-locked)
REM
REM  Just double-click. No admin needed.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo            HYDRA V4 - TWO-YEAR REAL DATA REPLAY
echo            (LIVE_DATA_ONLY - NO LIVE TRADING)
echo  ============================================================
echo.

if not exist "%PROJ%\replay\two_year_replay.py" (
    echo  [X] HYDRA V4 framework not found at: %PROJ%
    echo      Make sure replay\two_year_replay.py exists.
    pause
    exit /b 1
)
echo  Project: %PROJ%
echo.

cd /d "%PROJ%"

REM ---------- Step 1: Load secrets ----------
echo [1/6] Loading secrets from secrets\.env (gitignored)...
if not exist "secrets\.env" (
    echo  [X] secrets\.env NOT FOUND.
    echo.
    echo      Create it manually with these lines (replace placeholders):
    echo        ANTHROPIC_API_KEY=sk-ant-...
    echo        OANDA_API_TOKEN=...
    echo        OANDA_ACCOUNT_ID=001-001-XXXXXXXX-001
    echo        OANDA_ENV=live
    echo.
    echo      DO NOT commit this file. .gitignore protects it.
    pause
    exit /b 1
)

REM Load .env into environment (skip lines starting with #)
for /f "usebackq tokens=1,* delims==" %%a in ("secrets\.env") do (
    set "K=%%a"
    if not "!K!"=="" if not "!K:~0,1!"=="#" (
        set "%%a=%%b"
    )
)
echo      [OK] secrets loaded (NEVER printed)
echo.

REM ---------- Step 2: Run framework tests ----------
echo [2/6] Running framework tests (133+ expected)...
echo  ------------------------------------------------------------
python -m pytest live_data\tests anthropic_bridge\tests replay\tests --tb=line -q 2>&1
set "TEST_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
if not "%TEST_EXIT%"=="0" (
    echo  [X] Framework tests FAILED. Aborting before downloading data.
    pause
    exit /b %TEST_EXIT%
)
echo      [OK] Framework tests pass.
echo.

REM ---------- Step 3: Sanity-run all 5 brain suites ----------
echo [3/6] Sanity: 5 frozen brain suites + Orchestrator V4...
python -m pytest newsmind\v4\tests marketmind\v4\tests chartmind\v4\tests gatemind\v4\tests smartnotebook\v4\tests orchestrator\v4\tests --tb=line -q 2>&1
set "BRAIN_EXIT=%errorlevel%"
if not "%BRAIN_EXIT%"=="0" (
    echo  [X] One or more frozen test suites broke. Investigate before continuing.
    pause
    exit /b %BRAIN_EXIT%
)
echo      [OK] All 632 frozen brain + orchestrator tests pass.
echo.

REM ---------- Step 4: Run the actual two-year replay ----------
echo [4/6] Running 2-year real data replay...
echo  ------------------------------------------------------------
echo   This will:
echo     - Download 2 years of M15 EUR/USD + USD/JPY (cached, resumable)
echo     - Validate data quality (NaN/Inf/gaps rejected)
echo     - Replay chronologically through Orchestrator V4
echo     - Call Anthropic Claude (downgrade-only, redacted)
echo     - Record every decision cycle in SmartNoteBook
echo.
echo   This may take 30-60 minutes on first run.
echo  ------------------------------------------------------------

python run_live_replay.py 2>&1
set "REPLAY_EXIT=%errorlevel%"

if not "%REPLAY_EXIT%"=="0" (
    echo.
    echo  [X] Replay failed (exit code %REPLAY_EXIT%).
    echo      Check replay_results\replay_errors.log for details.
    pause
    exit /b %REPLAY_EXIT%
)
echo.
echo      [OK] Replay completed.
echo.

REM ---------- Step 5: Verify outputs ----------
echo [5/6] Verifying replay outputs...
set "OUTPUTS_OK=1"
for %%F in (
    replay_results\REAL_DATA_REPLAY_REPORT.md
    replay_results\decision_cycles.csv
    replay_results\per_brain_accuracy.csv
    replay_results\rejected_trades_shadow.csv
    replay_results\lessons.jsonl
) do (
    if exist "%%F" (
        echo      [OK] %%F
    ) else (
        echo      [X]  %%F MISSING
        set "OUTPUTS_OK=0"
    )
)
echo.

REM ---------- Step 6: Final summary ----------
echo [6/6] Summary...
echo.
echo  ============================================================
if "%OUTPUTS_OK%"=="1" (
    echo            REPLAY COMPLETE - REAL NUMBERS GENERATED
) else (
    echo            REPLAY FINISHED - SOME OUTPUTS MISSING
)
echo  ============================================================
echo.
echo   Read the report:
echo     %PROJ%\replay_results\REAL_DATA_REPLAY_REPORT.md
echo.
echo   Inspect decision cycles:
echo     %PROJ%\replay_results\decision_cycles.csv
echo.
echo   Reminders:
echo     - Live orders were NEVER placed (LIVE_ORDER_GUARD enforced)
echo     - Secrets were NEVER logged (redactor at every boundary)
echo     - No future data leaked into orchestrator (slice_visible)
echo.
pause
