@echo off
chcp 65001 >nul
title HYDRA V4 - Freeze GateMind V4
color 0A

REM ============================================================
REM  Freeze_GateMind_V4.bat
REM
REM  ١) ينتقل لمجلد HYDRA V4
REM  ٢) يشغّل tests/gatemind (يجب يكون 138+ pass)
REM  ٣) sanity على tests/newsmind و tests/marketmind و tests/chartmind
REM  ٤) git add + commit + tag gatemind-v4.0-frozen
REM  ٥) يطبع commit hash + status + النتائج
REM
REM  دبل-كليك. لا أوامر يدوية.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo                HYDRA V4 - Freeze GateMind V4
echo  ============================================================
echo.

if not exist "%PROJ%\gatemind\v4\GateMindV4.py" (
    echo  [X] GateMind V4 not found at: %PROJ%\gatemind\v4\
    pause
    exit /b 1
)
echo  Project: %PROJ%
echo.

cd /d "%PROJ%"

REM ---------- Step 1: confirm git ----------
if not exist ".git" (
    echo [X] HYDRA V4 is not a git repo. Run earlier freeze scripts first.
    pause
    exit /b 1
)
echo [1/7] Git repo confirmed.
echo.

REM ---------- Step 2: GateMind tests ----------
echo [2/7] Running GateMind V4 tests (~138 expected)...
echo  ------------------------------------------------------------
python -m pytest gatemind\v4\tests\ -v --tb=short 2>&1
set "GM_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
echo.

if not "%GM_EXIT%"=="0" (
    echo  [X] GateMind tests FAILED ^(exit code %GM_EXIT%^)
    echo      Do NOT freeze. Capture output above and report.
    pause
    exit /b %GM_EXIT%
)
echo  [OK] GateMind tests pass.
echo.

REM ---------- Step 3-5: sanity NewsMind + MarketMind + ChartMind ----------
echo [3/7] Sanity: NewsMind V4 still green...
python -m pytest newsmind\v4\tests\ --tb=line -q 2>&1
set "NM_EXIT=%errorlevel%"
if not "%NM_EXIT%"=="0" (
    echo  [X] NewsMind broke. GateMind changes leaked. Abort.
    pause
    exit /b %NM_EXIT%
)
echo  [OK]
echo.

echo [4/7] Sanity: MarketMind V4 still green...
python -m pytest marketmind\v4\tests\ --tb=line -q 2>&1
set "MM_EXIT=%errorlevel%"
if not "%MM_EXIT%"=="0" (
    echo  [X] MarketMind broke. Abort.
    pause
    exit /b %MM_EXIT%
)
echo  [OK]
echo.

echo [5/7] Sanity: ChartMind V4 still green...
python -m pytest chartmind\v4\tests\ --tb=line -q 2>&1
set "CM_EXIT=%errorlevel%"
if not "%CM_EXIT%"=="0" (
    echo  [X] ChartMind broke. Abort.
    pause
    exit /b %CM_EXIT%
)
echo  [OK]
echo.

REM ---------- Step 6: git add + commit ----------
echo [6/7] Committing GateMind V4...
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "freeze: GateMind V4.0 - 138 tests, Red Team verdict A" -m "What this commit adds:" -m "- gatemind/v4/* (orchestrator + 8-rule ladder + schema_validator + session_check + consensus_check + risk_flag_classifier + trade_candidate_builder + llm_safety + audit_log + gatemind_constants)" -m "- 138 tests across 13 files" -m "- GateDecision + TradeCandidate frozen dataclasses with invariants" -m "- 8 testable rules: Schema, Session, Grade, BrainBlock, KillFlag, Direction, UnanimousWait, Enter" -m "- Zero broker SDK / HTTP / socket calls (verified at runtime)" -m "- LLM downgrade-only enforced at Enum type level" -m "- DST-aware via zoneinfo America/New_York" -m "- Stateless (LRU-bounded audit cache, persistent journaling defers to SmartNoteBook V4)" -m "" -m "Multi-Reviewer + Red Team findings (Red Team verdict: A):" -m "  G1 audit_store unbounded (MEDIUM): now LRU OrderedDict cap 10,000" -m "  G2 DST tests superficial (MEDIUM): added 5 boundary tests for spring-forward gap + fall-back ambiguity" -m "  G3 fetch_audit not deep-copy (LOW): now copy.deepcopy" -m "  G4 missing whitespace/ZWSP evidence test (LOW): tightened _is_meaningful_evidence + 5 tests" -m "  G5 audit_id format inconsistent (LOW): unified gm- prefix" -m "  G6 silent except Exception (LOW): added logger and 6 warnings" -m "  G7 LLM enum naming (LOW): aliases doc + spec map" -m "" -m "FROZEN: do not modify GateMind V4 unless SmartNoteBook V4 or Risk/Execution layer reveals a real bug." -m "Test command: python -m pytest gatemind/v4/tests/ -v" -m "Expected: 138 passed" >nul 2>&1
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

REM ---------- Step 7: tag + summary ----------
echo [7/7] Creating tag gatemind-v4.0-frozen...
git tag -f gatemind-v4.0-frozen -m "GateMind V4 frozen: 138 tests, Red Team A, 4-of-5 brains complete" >nul 2>&1
echo  [OK]
echo.

REM ---------- Final summary ----------
echo  ============================================================
echo                          SUMMARY
echo  ============================================================
echo.
echo  ^>^>^>^>^> Latest commits:
git log --oneline -5
echo.
echo  ^>^>^>^>^> Tags in repo:
git tag -l
echo.
echo  ^>^>^>^>^> Working tree status:
git status --short
echo.
echo  ============================================================
echo            GateMind V4 - OFFICIALLY FROZEN
echo  ============================================================
echo.
echo   HYDRA V4 progress:
echo     - NewsMind V4    : FROZEN (49 tests)
echo     - MarketMind V4  : FROZEN (116+ tests)
echo     - ChartMind V4   : FROZEN (120 tests)
echo     - GateMind V4    : FROZEN (138 tests)  ^<-- just now
echo     - SmartNoteBook V4: pending
echo.
echo   Total V4 tests: 423+
echo   4 of 5 brains frozen. The HARD PART is done.
echo.
echo   Next: SmartNoteBook V4 with same protocol:
echo     V3 Audit -^> Build -^> Multi-Review -^> Red Team -^> Freeze
echo.
pause
