@echo off
chcp 65001 >nul
title HYDRA V4 - Freeze Integration (FINAL)
color 0A

REM ============================================================
REM  Freeze_Integration_V4.bat
REM
REM  ١) ينتقل لمجلد HYDRA V4
REM  ٢) يشغّل tests/orchestrator (يجب يكون 94+ pass)
REM  ٣) sanity على الـ 5 brain suites (لا regression)
REM  ٤) git add + commit + tag orchestrator-v4.0-integrated
REM  ٥) tag إضافي: hydra-v4.0-complete
REM  ٦) HYDRA V4 يصير مكتملاً 100%
REM
REM  دبل-كليك. لا أوامر يدوية.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo            HYDRA V4 - Freeze Integration (FINAL)
echo  ============================================================
echo.

if not exist "%PROJ%\orchestrator\v4\HydraOrchestratorV4.py" (
    echo  [X] Orchestrator V4 not found.
    pause & exit /b 1
)
echo  Project: %PROJ%
echo.

cd /d "%PROJ%"

if not exist ".git" (
    echo [X] HYDRA V4 is not a git repo. Run earlier freeze scripts first.
    pause & exit /b 1
)
echo [1/9] Git repo confirmed.
echo.

echo [2/9] Running Orchestrator V4 integration tests (~94 expected)...
echo  ------------------------------------------------------------
python -m pytest orchestrator\v4\tests\ -v --tb=short 2>&1
set "ORCH_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
if not "%ORCH_EXIT%"=="0" (
    echo  [X] Orchestrator tests FAILED. Do NOT freeze.
    pause & exit /b %ORCH_EXIT%
)
echo  [OK] Orchestrator pass.
echo.

echo [3/9] Sanity: NewsMind V4...
python -m pytest newsmind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (echo [X] regression. abort.& pause & exit /b 1)
echo  [OK]
echo.

echo [4/9] Sanity: MarketMind V4...
python -m pytest marketmind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (echo [X] regression. abort.& pause & exit /b 1)
echo  [OK]
echo.

echo [5/9] Sanity: ChartMind V4...
python -m pytest chartmind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (echo [X] regression. abort.& pause & exit /b 1)
echo  [OK]
echo.

echo [6/9] Sanity: GateMind V4...
python -m pytest gatemind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (echo [X] regression. abort.& pause & exit /b 1)
echo  [OK]
echo.

echo [7/9] Sanity: SmartNoteBook V4...
python -m pytest smartnotebook\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (echo [X] regression. abort.& pause & exit /b 1)
echo  [OK]
echo.

echo [8/9] Committing Orchestrator V4 + integration...
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "freeze: Orchestrator V4.0 + Five-Minds Integration - 94 tests, Red Team A" -m "What this commit adds:" -m "- orchestrator/v4/* (HydraOrchestratorV4 + DecisionCycleResult + cycle_id + constants + errors)" -m "- 94 tests across 14 files (incl. test_orchestrator_hardening.py with 14 Red Team regression guards + test_16 real schema_invalid)" -m "- All files/ docs folder with HYDRA_V4_FIVE_MINDS_INTEGRATION_REPORT.md + README" -m "" -m "Five-minds integration:" -m "  Symbol + now_utc -^> NewsMind -^> MarketMind -^> ChartMind -^> GateMind -^> SmartNoteBook -^> DecisionCycleResult" -m "  Strict pipeline order, fail-CLOSED propagation, threading.RLock, no broker SDK." -m "" -m "Multi-Reviewer + Red Team findings (Red Team verdict: A after hardening, was B):" -m "  O1 happy-path SmartNoteBook crash (CRITICAL): try/except + return BLOCK" -m "  O2 concurrent run_cycle (MEDIUM): threading.RLock around notebook" -m "  O3 final_status divergence (HIGH): orchestrator_error: prefix in blocking_reason" -m "  O4 scenario 09 mislabel (MEDIUM): renamed + added test_16 real schema_invalid" -m "  O5 future-timestamp sanity (MEDIUM): 5-min clock drift tolerance" -m "  O6 timing measurement tautology (MEDIUM): real time.sleep test" -m "  O7 magic numbers + dead imports (LOW): MS_PER_SECOND + EVIDENCE_PER_BRAIN_LIMIT constants" -m "  O8 no INFO log (LOW): cycle_complete log at all 3 return points" -m "  O9 stricter injection (LOW): strict=True flag" -m "" -m "INTEGRATED: do not modify Orchestrator V4 unless next-phase integration reveals a real bug." -m "Total HYDRA V4 tests: 632 (538 brain + 94 orchestrator). All five brains + orchestrator FROZEN." >nul 2>&1
    if errorlevel 1 (
        echo  [X] commit failed
        pause & exit /b 1
    )
    echo  [OK] commit created.
) else (
    echo  [SKIP] no changes.
)
echo.

echo [9/9] Creating final tags...
git tag -f orchestrator-v4.0-integrated -m "Orchestrator V4 frozen: 94 tests, Red Team A" >nul 2>&1
git tag -f hydra-v4.0-complete -m "HYDRA V4 COMPLETE: 5 brains + orchestrator, 632 tests, all integrated" >nul 2>&1
echo  [OK]
echo.

REM ---------- Final summary ----------
echo  ============================================================
echo                  HYDRA V4 - 100%% COMPLETE
echo  ============================================================
echo.
echo  ^>^>^>^>^> All commits:
git log --oneline -10
echo.
echo  ^>^>^>^>^> All tags:
git tag -l
echo.
echo  ^>^>^>^>^> Working tree:
git status --short
echo.
echo  ============================================================
echo            HYDRA V4 IS COMPLETE
echo  ============================================================
echo.
echo   All 6 components frozen and integrated:
echo     - NewsMind V4    : FROZEN ^(49 tests^)
echo     - MarketMind V4  : FROZEN ^(116+ tests^)
echo     - ChartMind V4   : FROZEN ^(120 tests^)
echo     - GateMind V4    : FROZEN ^(138 tests^)
echo     - SmartNoteBook V4: FROZEN ^(115 tests^)
echo     - Orchestrator V4: INTEGRATED ^(94 tests^)
echo.
echo   Total V4 tests: 632
echo.
echo   What's next ^(allowed^):
echo     - Backtester V4 ^(historical OANDA data + verify_chain^)
echo     - Risk/Execution layer ^(consumes trade_candidate^)
echo     - Live monitoring dashboard
echo.
echo   Run anytime via: Run_HYDRA_V4.bat ^(safe, no live orders^)
echo.
pause
