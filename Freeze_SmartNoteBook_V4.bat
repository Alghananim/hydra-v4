@echo off
chcp 65001 >nul
title HYDRA V4 - Freeze SmartNoteBook V4 (FINAL BRAIN)
color 0E

REM ============================================================
REM  Freeze_SmartNoteBook_V4.bat
REM
REM  ١) ينتقل لمجلد HYDRA V4
REM  ٢) يشغّل tests/smartnotebook (يجب يكون 115+ pass)
REM  ٣) sanity على tests للعقول الأربعة المُجمَّدة
REM  ٤) git add + commit + tag smartnotebook-v4.0-frozen
REM  ٥) tag إضافي: hydra-v4.0-complete
REM
REM  دبل-كليك. لا أوامر يدوية.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo            HYDRA V4 - Freeze SmartNoteBook V4
echo                THE FINAL BRAIN
echo  ============================================================
echo.

if not exist "%PROJ%\smartnotebook\v4\SmartNoteBookV4.py" (
    echo  [X] SmartNoteBook V4 not found at: %PROJ%\smartnotebook\v4\
    pause
    exit /b 1
)
echo  Project: %PROJ%
echo.

cd /d "%PROJ%"

if not exist ".git" (
    echo [X] HYDRA V4 is not a git repo. Run earlier freeze scripts first.
    pause
    exit /b 1
)
echo [1/8] Git repo confirmed.
echo.

echo [2/8] Running SmartNoteBook V4 tests (~115 expected)...
echo  ------------------------------------------------------------
python -m pytest smartnotebook\v4\tests\ -v --tb=short 2>&1
set "SN_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
echo.

if not "%SN_EXIT%"=="0" (
    echo  [X] SmartNoteBook tests FAILED ^(exit code %SN_EXIT%^)
    echo      Do NOT freeze. Capture output above and report.
    pause
    exit /b %SN_EXIT%
)
echo  [OK] SmartNoteBook tests pass.
echo.

echo [3/8] Sanity: NewsMind V4 still green...
python -m pytest newsmind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (
    echo  [X] NewsMind broke. Abort.
    pause & exit /b 1
)
echo  [OK]
echo.

echo [4/8] Sanity: MarketMind V4 still green...
python -m pytest marketmind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (
    echo  [X] MarketMind broke. Abort.
    pause & exit /b 1
)
echo  [OK]
echo.

echo [5/8] Sanity: ChartMind V4 still green...
python -m pytest chartmind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (
    echo  [X] ChartMind broke. Abort.
    pause & exit /b 1
)
echo  [OK]
echo.

echo [6/8] Sanity: GateMind V4 still green...
python -m pytest gatemind\v4\tests\ --tb=line -q 2>&1
if errorlevel 1 (
    echo  [X] GateMind broke. Abort.
    pause & exit /b 1
)
echo  [OK]
echo.

echo [7/8] Committing SmartNoteBook V4...
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "freeze: SmartNoteBook V4.0 - 115 tests, Red Team A (post-hardening)" -m "What this commit adds:" -m "- smartnotebook/v4/* (15 production modules: orchestrator + storage + chain_hash + secret_redactor + time_integrity + attribution + classifier + lesson_engine + diagnostics + reports + error_handling + models + record_types + notebook_constants)" -m "- 115 tests across 15 files (incl. test_hardening.py with 22 Red Team regression guards)" -m "- 8 testable rules R1-R8 enforced" -m "- HMAC-SHA256 chain hashing (forge resistance with HYDRA_NOTEBOOK_HMAC_KEY env)" -m "- NFKC + Unicode-obfuscation-aware secret redaction" -m "- __slots__=() + _FrozenDict bypass-proof immutability" -m "- Atomic concurrent writes (no chain fork)" -m "- Integration with all 4 frozen brains (NewsMind/MarketMind/ChartMind/GateMind)" -m "" -m "Multi-Reviewer + Red Team findings (Red Team verdict: A after hardening, was C):" -m "  S1 concurrent write chain fork (CRITICAL): atomic recompute inside lock" -m "  S2 chain forging undetectable (CRITICAL): HMAC-SHA256 mode" -m "  S3 secret redactor escapes (HIGH): NFKC + AWS + JWT + Unicode patterns" -m "  S4 object.__setattr__ bypass (HIGH): __slots__=() + _FrozenDict" -m "  S5 backwards timestamps (MEDIUM): NonMonotonicTimestampError" -m "  S6 SQLite-JSONL divergence (MEDIUM): verify_storage_consistency" -m "  S7 cross-process sequence_id collisions (MEDIUM): seed from MAX(sequence_id)" -m "  S8 magic numbers + no logging (LOW): constants + warnings" -m "" -m "FROZEN: do not modify SmartNoteBook V4 unless Orchestrator V4 integration reveals a real bug." -m "Test command: python -m pytest smartnotebook/v4/tests/ -v" -m "Expected: 115 passed" >nul 2>&1
    if errorlevel 1 (
        echo  [X] commit failed
        pause & exit /b 1
    )
    echo  [OK] commit created.
) else (
    echo  [SKIP] no changes to commit.
)
echo.

echo [8/8] Creating tags...
git tag -f smartnotebook-v4.0-frozen -m "SmartNoteBook V4 frozen: 115 tests, Red Team A" >nul 2>&1
git tag -f hydra-v4.0-complete -m "HYDRA V4 COMPLETE: 5 of 5 brains frozen, 538 tests total" >nul 2>&1
echo  [OK]
echo.

echo  ============================================================
echo                          SUMMARY
echo  ============================================================
echo.
echo  ^>^>^>^>^> Latest commits:
git log --oneline -6
echo.
echo  ^>^>^>^>^> All tags in repo:
git tag -l
echo.
echo  ^>^>^>^>^> Working tree status:
git status --short
echo.
echo  ============================================================
echo            HYDRA V4 - COMPLETE!
echo  ============================================================
echo.
echo   ALL FIVE BRAINS FROZEN:
echo     - NewsMind V4    : FROZEN ^(49 tests^)
echo     - MarketMind V4  : FROZEN ^(116+ tests^)
echo     - ChartMind V4   : FROZEN ^(120 tests^)
echo     - GateMind V4    : FROZEN ^(138 tests^)
echo     - SmartNoteBook V4: FROZEN ^(115 tests^)  ^<-- just now
echo.
echo   Total V4 tests: 538
echo.
echo   THE HARD ENGINEERING WORK IS DONE.
echo.
echo   What's next ^(allowed^):
echo     - Orchestrator V4 ^(wires the 5 brains into a pipeline^)
echo     - Backtester V4 ^(on real OANDA data with chain verification^)
echo     - Risk/Execution layer ^(consumes TradeCandidate from GateMind^)
echo     - Live monitoring dashboard
echo.
echo   Golden rule: do NOT modify any frozen brain unless integration
echo   reveals a real, documented bug.
echo.
pause
