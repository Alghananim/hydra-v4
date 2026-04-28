@echo off
chcp 65001 >nul
title HYDRA V4 - Phase 2 Cleanup FIX (pycache only)
color 0E

cls
echo.
echo  ============================================================
echo            HYDRA V4 - PHASE 2 CLEANUP FIX
echo  ============================================================
echo.
echo  Previous run completed sections A and B successfully.
echo  This script ONLY redoes section C (pycache cleanup).
echo.
echo  Output: %USERPROFILE%\Desktop\PHASE2_CLEANUP_FIX_LOG.txt
echo.
echo  Press any key to start.
pause >nul

set "ROOT=%USERPROFILE%\Desktop\HYDRA V4"
set "LOG=%USERPROFILE%\Desktop\PHASE2_CLEANUP_FIX_LOG.txt"

cd /d "%ROOT%"

echo HYDRA V4 - PHASE 2 CLEANUP FIX LOG > "%LOG%"
echo Started: %DATE% %TIME% >> "%LOG%"
echo Working dir: %CD% >> "%LOG%"
echo. >> "%LOG%"

echo === DELETE __pycache__\ DIRS RECURSIVELY (fixed loop) === >> "%LOG%"
REM 'for /d /r' walks all subdirs and matches the pattern; safe with spaces.
for /d /r %%D in (__pycache__) do (
    if exist "%%D" (
        rd /s /q "%%D"
        echo DELETED: %%D >> "%LOG%"
    )
)
echo. >> "%LOG%"

echo === DELETE STANDALONE *.pyc FILES (fixed) === >> "%LOG%"
del /s /q *.pyc >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo === COUNT REMAINING pyc FILES (should be 0) === >> "%LOG%"
set "REMAINING=0"
for /r %%F in (*.pyc) do set /a REMAINING+=1
echo Remaining .pyc count: should be 0 >> "%LOG%"
dir /s /b *.pyc >> "%LOG%" 2>nul
echo. >> "%LOG%"

echo === REMAINING __pycache__ DIRS (should be 0) === >> "%LOG%"
dir /s /b /ad __pycache__ >> "%LOG%" 2>nul
echo. >> "%LOG%"

echo === FIVE BRAINS PRESENCE CHECK === >> "%LOG%"
if exist "newsmind\v4\NewsMindV4.py" (echo   newsmind: OK >> "%LOG%") else (echo   newsmind: MISSING >> "%LOG%")
if exist "marketmind\v4\MarketMindV4.py" (echo   marketmind: OK >> "%LOG%") else (echo   marketmind: MISSING >> "%LOG%")
if exist "chartmind\v4\ChartMindV4.py" (echo   chartmind: OK >> "%LOG%") else (echo   chartmind: MISSING >> "%LOG%")
if exist "gatemind\v4\GateMindV4.py" (echo   gatemind: OK >> "%LOG%") else (echo   gatemind: MISSING >> "%LOG%")
if exist "smartnotebook\v4\SmartNoteBookV4.py" (echo   smartnotebook: OK >> "%LOG%") else (echo   smartnotebook: MISSING >> "%LOG%")
if exist "orchestrator\v4\HydraOrchestratorV4.py" (echo   orchestrator: OK >> "%LOG%") else (echo   orchestrator: MISSING >> "%LOG%")
if exist "replay\replay_calendar.py" (echo   replay_calendar: OK >> "%LOG%") else (echo   replay_calendar: MISSING >> "%LOG%")
if exist "replay\replay_newsmind.py" (echo   replay_newsmind: OK >> "%LOG%") else (echo   replay_newsmind: MISSING >> "%LOG%")
if exist "archive\replay_news_stub.py.SUPERSEDED-2026-04-27" (echo   archive\stub: OK >> "%LOG%") else (echo   archive\stub: MISSING >> "%LOG%")
echo. >> "%LOG%"

echo Finished: %DATE% %TIME% >> "%LOG%"
echo === DONE === >> "%LOG%"

echo.
echo  ============================================================
echo  Fix complete. Log: %LOG%
echo  ============================================================
echo.
echo  Press any key to close.
pause >nul
exit /b 0
