@echo off
chcp 65001 >nul
title HYDRA V4 - Freeze MarketMind V4
color 0A

REM ============================================================
REM  Freeze_MarketMind_V4.bat
REM
REM  ١) ينتقل لمجلد HYDRA V4
REM  ٢) يشغّل tests/marketmind (يجب يكون 116+ pass)
REM  ٣) git add + commit + tag marketmind-v4.0-frozen
REM  ٤) يطبع commit hash + status + النتائج
REM
REM  دبل-كليك. لا أوامر يدوية.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo               HYDRA V4 - Freeze MarketMind V4
echo  ============================================================
echo.

if not exist "%PROJ%\marketmind\v4\MarketMindV4.py" (
    echo  [X] MarketMind V4 not found at: %PROJ%\marketmind\v4\
    pause
    exit /b 1
)
echo  Project: %PROJ%
echo.

cd /d "%PROJ%"

REM ---------- Step 1: confirm we're in a repo + on main ----------
if not exist ".git" (
    echo [X] HYDRA V4 is not a git repo. Run Freeze_NewsMind_V4.bat first.
    pause
    exit /b 1
)
echo [1/5] Git repo confirmed.
echo.

REM ---------- Step 2: run MarketMind tests ----------
echo [2/5] Running MarketMind V4 tests (~116 expected)...
echo  ------------------------------------------------------------
python -m pytest marketmind\v4\tests\ -v --tb=short 2>&1
set "TEST_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
echo.

if not "%TEST_EXIT%"=="0" (
    echo  [X] Tests FAILED ^(exit code %TEST_EXIT%^)
    echo      Do NOT freeze. Capture output above and report.
    pause
    exit /b %TEST_EXIT%
)
echo  [OK] All MarketMind tests pass.
echo.

REM ---------- Step 3: also run NewsMind tests (sanity) ----------
echo [3/5] Sanity-running NewsMind V4 tests (frozen) to ensure no regression...
python -m pytest newsmind\v4\tests\ --tb=line -q 2>&1
set "NEWS_EXIT=%errorlevel%"
if not "%NEWS_EXIT%"=="0" (
    echo  [X] NewsMind V4 tests broke ^(exit code %NEWS_EXIT%^)
    echo      MarketMind changes leaked into NewsMind frozen state. Abort.
    pause
    exit /b %NEWS_EXIT%
)
echo  [OK] NewsMind V4 still green.
echo.

REM ---------- Step 4: git add + commit ----------
echo [4/5] Committing MarketMind V4...
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "freeze: MarketMind V4.0 - 116+ tests, Red Team approved" -m "What this commit adds:" -m "- marketmind/v4/* (orchestrator + 5 rule modules + indicators + permission_engine + news_integration + currency_strength + correlation + contradictions + data_quality + cache + scoring + synthetic_dxy)" -m "- 116+ tests across 12 files (incl. test_hardening.py with 17 Red Team regression guards)" -m "- shared indicators.py (will be reused by ChartMind V4)" -m "- MarketState contract extends BrainOutput" -m "- NewsMind V4 integration: cap-only, never override upward" -m "" -m "Red Team breaks fixed:" -m "  M1 slow-drift baseline poisoning (CRITICAL): liquidity_rule.py multi-defense baseline" -m "  M2 NaN/Inf bypass (CRITICAL): models.py Bar.__post_init__ math.isfinite checks" -m "  M3 timestamp ordering (HIGH): data_quality.py monotonic check" -m "  M4 tautological no-lookahead tests (HIGH): full rewrite with LeakSafeBars + differential + meta-test" -m "  M5 contradiction high cap (MEDIUM): permission_engine cap-at-C not step_down" -m "  M6 momentum atr_series duplication (MEDIUM): now imports indicators.atr_series" -m "  M7 liquidity off-session uses bars[-1].ts (MEDIUM): now uses now_utc" -m "" -m "FROZEN: do not modify MarketMind V4 unless integration with ChartMind/GateMind reveals a real bug." -m "Test command: python -m pytest marketmind/v4/tests/ -v" >nul 2>&1
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

REM ---------- Step 5: tag + summary ----------
echo [5/5] Creating tag marketmind-v4.0-frozen...
git tag -f marketmind-v4.0-frozen -m "MarketMind V4 frozen: 116+ tests, Red Team approved, NewsMind integration clean" >nul 2>&1
echo  [OK]
echo.

REM ---------- Final summary ----------
echo  ============================================================
echo                          SUMMARY
echo  ============================================================
echo.
echo  >>>>> Latest commit:
git log --oneline -3
echo.
echo  >>>>> Tags in repo:
git tag -l
echo.
echo  >>>>> Working tree status:
git status --short
echo.
echo  ============================================================
echo            MarketMind V4 - OFFICIALLY FROZEN
echo  ============================================================
echo.
echo   NewsMind V4 + MarketMind V4 both frozen.
echo   Total tests: 49 + 116+ = 165+ all green.
echo.
echo   Next: ChartMind V4 with same protocol:
echo     V3 Audit -^> Build -^> Multi-Review -^> Red Team -^> Freeze
echo.
pause
