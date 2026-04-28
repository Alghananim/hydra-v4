@echo off
chcp 65001 >nul
title HYDRA V4 - Freeze ChartMind V4
color 0A

REM ============================================================
REM  Freeze_ChartMind_V4.bat
REM
REM  ١) ينتقل لمجلد HYDRA V4
REM  ٢) يشغّل tests/chartmind (يجب يكون 120+ pass)
REM  ٣) يشغّل sanity على tests/newsmind و tests/marketmind
REM  ٤) git add + commit + tag chartmind-v4.0-frozen
REM  ٥) يطبع commit hash + status + النتائج
REM
REM  دبل-كليك. لا أوامر يدوية.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo               HYDRA V4 - Freeze ChartMind V4
echo  ============================================================
echo.

if not exist "%PROJ%\chartmind\v4\ChartMindV4.py" (
    echo  [X] ChartMind V4 not found at: %PROJ%\chartmind\v4\
    pause
    exit /b 1
)
echo  Project: %PROJ%
echo.

cd /d "%PROJ%"

REM ---------- Step 1: confirm we're in a repo ----------
if not exist ".git" (
    echo [X] HYDRA V4 is not a git repo. Run Freeze_NewsMind_V4.bat first.
    pause
    exit /b 1
)
echo [1/6] Git repo confirmed.
echo.

REM ---------- Step 2: ChartMind tests ----------
echo [2/6] Running ChartMind V4 tests (~120 expected)...
echo  ------------------------------------------------------------
python -m pytest chartmind\v4\tests\ -v --tb=short 2>&1
set "CM_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
echo.

if not "%CM_EXIT%"=="0" (
    echo  [X] ChartMind tests FAILED ^(exit code %CM_EXIT%^)
    echo      Do NOT freeze. Capture output above and report.
    pause
    exit /b %CM_EXIT%
)
echo  [OK] ChartMind tests pass.
echo.

REM ---------- Step 3: sanity NewsMind ----------
echo [3/6] Sanity: NewsMind V4 tests still green...
python -m pytest newsmind\v4\tests\ --tb=line -q 2>&1
set "NM_EXIT=%errorlevel%"
if not "%NM_EXIT%"=="0" (
    echo  [X] NewsMind V4 tests broke ^(exit code %NM_EXIT%^)
    echo      ChartMind changes leaked into NewsMind frozen state. Abort.
    pause
    exit /b %NM_EXIT%
)
echo  [OK] NewsMind V4 still green.
echo.

REM ---------- Step 4: sanity MarketMind ----------
echo [4/6] Sanity: MarketMind V4 tests still green...
python -m pytest marketmind\v4\tests\ --tb=line -q 2>&1
set "MM_EXIT=%errorlevel%"
if not "%MM_EXIT%"=="0" (
    echo  [X] MarketMind V4 tests broke ^(exit code %MM_EXIT%^)
    echo      ChartMind changes leaked into MarketMind frozen state. Abort.
    pause
    exit /b %MM_EXIT%
)
echo  [OK] MarketMind V4 still green.
echo.

REM ---------- Step 5: git add + commit ----------
echo [5/6] Committing ChartMind V4...
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "freeze: ChartMind V4.0 - 120 tests, Multi-Reviewer + Red Team approved" -m "What this commit adds:" -m "- chartmind/v4/* (orchestrator + 8 rule modules + price_data + market_structure + breakout + retest + pullback + candle + MTF + liquidity_sweep + references + permission_engine + news_market_integration + chart_thresholds)" -m "- 120 tests across 16 files" -m "- Reuses marketmind.v4.indicators (shared ATR/ADX/EMA/percentile)" -m "- ChartAssessment contract extends BrainOutput" -m "- entry_zone is BAND (never single price)" -m "- A+ via additive 8-evidence ladder (NOT 12-AND chain)" -m "" -m "Multi-Reviewer + Red Team breaks fixed:" -m "  C1 magic 0.2 in ChartMindV4.py:242 (HIGH): now uses ENTRY_BAND_BREAKOUT_ATR" -m "  C2 tautological no-lookahead suite (HIGH): rewritten with bar-poisoning + meta-test" -m "  C3 A+ unreachable e2e (HIGH): tuned bullish_strong fixture, A+ proven via 7/8 evidence" -m "  C4 magic numbers in liquidity_sweep/candle/references (MEDIUM): 5 new named constants" -m "  C5 cap.value string compare (LOW): now enum comparison" -m "  C6 weak direction-conflict test (LOW): strengthened to exact grade B + risk_flag check" -m "" -m "FROZEN: do not modify ChartMind V4 unless GateMind V4 integration reveals a real bug." -m "Test command: python -m pytest chartmind/v4/tests/ -v" -m "Expected: 120 passed" >nul 2>&1
    if errorlevel 1 (
        echo  [X] commit failed
        pause
        exit /b 1
    )
    echo  [OK] commit created.
) else (
    echo  [SKIP] no changes to commit.
)
echo.

REM ---------- Step 6: tag + summary ----------
echo [6/6] Creating tag chartmind-v4.0-frozen...
git tag -f chartmind-v4.0-frozen -m "ChartMind V4 frozen: 120 tests, Multi-Reviewer + Red Team approved, NewsMind/MarketMind integration clean" >nul 2>&1
echo  [OK]
echo.

REM ---------- Final summary ----------
echo  ============================================================
echo                          SUMMARY
echo  ============================================================
echo.
echo  >>>>> Latest commits:
git log --oneline -4
echo.
echo  >>>>> Tags in repo:
git tag -l
echo.
echo  >>>>> Working tree status:
git status --short
echo.
echo  ============================================================
echo            ChartMind V4 - OFFICIALLY FROZEN
echo  ============================================================
echo.
echo   HYDRA V4 progress:
echo     - NewsMind V4   : FROZEN (49 tests)
echo     - MarketMind V4 : FROZEN (116+ tests)
echo     - ChartMind V4  : FROZEN (120 tests)  ^<-- just now
echo     - GateMind V4   : pending
echo     - SmartNoteBook V4 : pending
echo.
echo   Total V4 tests so far: 285+
echo.
echo   Next: GateMind V4 with same protocol:
echo     V3 Audit -^> Build -^> Multi-Review -^> Red Team -^> Freeze
echo.
pause
