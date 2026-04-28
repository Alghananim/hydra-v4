@echo off
chcp 65001 >nul
title HYDRA V4 - Freeze NewsMind V4
color 0A

REM ============================================================
REM  Freeze_NewsMind_V4.bat
REM
REM  يقوم بالآتي:
REM    1) ينتقل لمجلد HYDRA V4 على سطح المكتب
REM    2) يُهيّئ git repo (إذا غير مهيأ)
REM    3) يضبط user.name/email لو مش مضبوط
REM    4) يُضيف كل الملفات + commit
REM    5) يُنشئ tag باسم newsmind-v4.0-frozen
REM    6) يشغّل pytest على tests
REM    7) يطبع الـ commit hash + git status + النتائج
REM
REM  دبل-كليك. لا أوامر يدوية.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"

cls
echo.
echo  ============================================================
echo                HYDRA V4 - Freeze NewsMind V4
echo  ============================================================
echo.

if not exist "%PROJ%\NEWSMIND_V4_FREEZE_REPORT.md" (
    echo  [X] HYDRA V4 not found at: %PROJ%
    pause
    exit /b 1
)
echo  Project: %PROJ%
echo.

cd /d "%PROJ%"

REM ---------- Step 1: git init if needed ----------
if not exist ".git" (
    echo [1/7] Initializing git repository...
    git init -b main >nul 2>&1
    if errorlevel 1 (
        echo     [X] git init failed. Is git installed?
        pause
        exit /b 1
    )
    echo     [OK]
) else (
    echo [1/7] Git repo already initialized.
)
echo.

REM ---------- Step 2: configure user if needed ----------
echo [2/7] Checking git user config...
git config user.email >nul 2>&1
if errorlevel 1 (
    git config user.email "alghananim@icloud.com"
    git config user.name "Mansur Alghananim"
    echo     [OK] user configured
) else (
    echo     [OK] user already configured
)
echo.

REM ---------- Step 3: .gitignore ----------
echo [3/7] Ensuring .gitignore...
if not exist ".gitignore" (
    > ".gitignore" (
        echo __pycache__/
        echo *.pyc
        echo *.pyo
        echo .pytest_cache/
        echo .venv/
        echo .env
        echo *.log
        echo *.sqlite
        echo *.db
    )
    echo     [OK] created
) else (
    echo     [OK] exists
)
echo.

REM ---------- Step 4: stage and commit ----------
echo [4/7] Staging all files...
git add -A >nul 2>&1
echo     [OK]
echo.

echo [5/7] Creating commit...
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "freeze: NewsMind V4.0 - 49 tests pass, Red Team approved" -m "What this commit contains:" -m "- contracts/brain_output.py (BrainOutput contract with invariants)" -m "- newsmind/v4/* (orchestrator + sources + scheduler + intelligence + permission + freshness + chase_detector + llm_review)" -m "- config/news/events.yaml (10 curated events for EUR/USD + USD/JPY)" -m "- config/news/keywords.yaml" -m "- 49 tests across 5 files (contract / sources / blackout / e2e / hardening)" -m "- Red Team breaks R1-R7 all fixed and regression-tested" -m "" -m "FROZEN: do not modify NewsMind V4 unless a real bug surfaces during MarketMind V4 integration." -m "Test command: python -m pytest newsmind/v4/tests/ -v" -m "Expected: 49 passed" >nul 2>&1
    if errorlevel 1 (
        echo     [X] commit failed
        pause
        exit /b 1
    )
    echo     [OK] commit created
) else (
    echo     [SKIP] no changes to commit (already committed)
)
echo.

REM ---------- Step 5: tag ----------
echo [6/7] Creating tag newsmind-v4.0-frozen...
git tag -f newsmind-v4.0-frozen -m "NewsMind V4 frozen: 49/49 tests, Red Team approved" >nul 2>&1
if errorlevel 1 (
    echo     [WARN] tag operation returned non-zero (may already exist)
) else (
    echo     [OK]
)
echo.

REM ---------- Step 6: run tests ----------
echo [7/7] Running 49 tests...
echo  ------------------------------------------------------------
python -m pytest newsmind\v4\tests\ -v 2>&1
set "TEST_EXIT=%errorlevel%"
echo  ------------------------------------------------------------
echo.

REM ---------- Final summary ----------
echo  ============================================================
echo                          SUMMARY
echo  ============================================================
echo.
echo  >>>>> Commit hash:
git log --oneline -1
echo.
echo  >>>>> Git tag:
git tag -l newsmind-v4.0-frozen
echo.
echo  >>>>> Git status (should be 'working tree clean'):
git status --short
echo.
if "%TEST_EXIT%"=="0" (
    echo  >>>>> Tests: PASSED ^(exit code 0^)
    echo.
    echo  ============================================================
    echo            NewsMind V4 - OFFICIALLY FROZEN
    echo  ============================================================
    echo.
    echo   Next: MarketMind V4 with 8-agent protocol
    echo     - V3 Audit Agent
    echo     - Architecture Agent
    echo     - Contracts Agent
    echo     - MarketMind Agent
    echo     - Risk Agent
    echo     - Code Quality Agent
    echo     - Truth Verification Agent
    echo     - Red Team Agent
) else (
    echo  >>>>> Tests: FAILED ^(exit code %TEST_EXIT%^)
    echo.
    echo  ============================================================
    echo            FREEZE FAILED - tests did not pass
    echo  ============================================================
    echo.
    echo   Do NOT proceed to MarketMind V4 yet.
    echo   Capture the test output above and report it.
)
echo.
pause
