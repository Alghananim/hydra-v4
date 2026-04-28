@echo off
chcp 65001 >nul
title HYDRA V4 - Phase 2 Cleanup (SAFE MOVES + PYCACHE)
color 0E

cls
echo.
echo  ============================================================
echo            HYDRA V4 - PHASE 2 CLEANUP
echo  ============================================================
echo.
echo  Operations (no logic changes; only moves + pycache delete):
echo    A. Archive 1 obsolete file (replay_news_stub.py)
echo    B. Move 7 reports into All files\
echo    C. Delete all __pycache__\ recursively
echo.
echo  Output saved to: %USERPROFILE%\Desktop\PHASE2_CLEANUP_LOG.txt
echo.
echo  Press any key to start, or close window to abort.
pause >nul

set "ROOT=%USERPROFILE%\Desktop\HYDRA V4"
set "LOG=%USERPROFILE%\Desktop\PHASE2_CLEANUP_LOG.txt"

cd /d "%ROOT%"

echo HYDRA V4 - PHASE 2 CLEANUP LOG > "%LOG%"
echo Started: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"

echo === A. CREATE archive\ AND MOVE OBSOLETE FILES === >> "%LOG%"
if not exist "archive" (
    mkdir "archive"
    echo Created archive\ >> "%LOG%"
)
if exist "replay\replay_news_stub.py" (
    move "replay\replay_news_stub.py" "archive\replay_news_stub.py.SUPERSEDED-2026-04-27" >> "%LOG%" 2>&1
    echo MOVED: replay\replay_news_stub.py -^> archive\replay_news_stub.py.SUPERSEDED-2026-04-27 >> "%LOG%"
    echo   Reason: superseded by replay\replay_newsmind.py which uses real EventScheduler. >> "%LOG%"
) else (
    echo NOTE: replay\replay_news_stub.py already moved or absent. >> "%LOG%"
)
echo. >> "%LOG%"

echo === B. ENSURE All files\ EXISTS AND MOVE REPORTS === >> "%LOG%"
if not exist "All files" (
    mkdir "All files"
    echo Created All files\ >> "%LOG%"
)
for %%F in (
    "NEWSMIND_V4_FREEZE_REPORT.md"
    "MARKETMIND_V4_FREEZE_REPORT.md"
    "CHARTMIND_V4_FREEZE_REPORT.md"
    "GATEMIND_V4_FREEZE_REPORT.md"
    "SMARTNOTEBOOK_V4_FREEZE_REPORT.md"
    "HYDRA_V4_PHASE_1_BASELINE_FREEZE_REPORT.md"
) do (
    if exist "%%~F" (
        move "%%~F" "All files\%%~F" >> "%LOG%" 2>&1
        echo MOVED: %%~F -^> All files\ >> "%LOG%"
    )
)
if exist "newsmind\v4\NEWSMIND_V4_REPORT.md" (
    move "newsmind\v4\NEWSMIND_V4_REPORT.md" "All files\NEWSMIND_V4_REPORT.md" >> "%LOG%" 2>&1
    echo MOVED: newsmind\v4\NEWSMIND_V4_REPORT.md -^> All files\ >> "%LOG%"
)
echo. >> "%LOG%"

echo === C. DELETE __pycache__\ DIRS RECURSIVELY === >> "%LOG%"
echo (gitignored auto-generated cache; will regenerate on next test run) >> "%LOG%"
set "PYCACHE_COUNT=0"
for /f "delims=" %%D in ('dir /b /s /ad __pycache__ 2^>nul') do (
    rd /s /q "%%D"
    set /a PYCACHE_COUNT+=1
    echo DELETED: %%D >> "%LOG%"
)
echo. >> "%LOG%"

echo === D. DELETE STANDALONE *.pyc FILES === >> "%LOG%"
set "PYC_COUNT=0"
for /f "delims=" %%F in ('dir /b /s *.pyc 2^>nul') do (
    del /q "%%F" 2>nul
    set /a PYC_COUNT+=1
)
echo Deleted standalone *.pyc files. >> "%LOG%"
echo. >> "%LOG%"

echo === E. POST-CLEANUP VERIFICATION === >> "%LOG%"
echo Five brain main classes still on disk? >> "%LOG%"
if exist "newsmind\v4\NewsMindV4.py" (echo   newsmind\v4\NewsMindV4.py - OK >> "%LOG%") else (echo   newsmind\v4\NewsMindV4.py - MISSING [ERROR] >> "%LOG%")
if exist "marketmind\v4\MarketMindV4.py" (echo   marketmind\v4\MarketMindV4.py - OK >> "%LOG%") else (echo   marketmind\v4\MarketMindV4.py - MISSING [ERROR] >> "%LOG%")
if exist "chartmind\v4\ChartMindV4.py" (echo   chartmind\v4\ChartMindV4.py - OK >> "%LOG%") else (echo   chartmind\v4\ChartMindV4.py - MISSING [ERROR] >> "%LOG%")
if exist "gatemind\v4\GateMindV4.py" (echo   gatemind\v4\GateMindV4.py - OK >> "%LOG%") else (echo   gatemind\v4\GateMindV4.py - MISSING [ERROR] >> "%LOG%")
if exist "smartnotebook\v4\SmartNoteBookV4.py" (echo   smartnotebook\v4\SmartNoteBookV4.py - OK >> "%LOG%") else (echo   smartnotebook\v4\SmartNoteBookV4.py - MISSING [ERROR] >> "%LOG%")
echo. >> "%LOG%"
if exist "orchestrator\v4\HydraOrchestratorV4.py" (echo Orchestrator: OK >> "%LOG%") else (echo Orchestrator: MISSING [ERROR] >> "%LOG%")
if exist "replay\replay_newsmind.py" (echo Replay news (new): OK >> "%LOG%") else (echo Replay news (new): MISSING [ERROR] >> "%LOG%")
if exist "replay\replay_calendar.py" (echo Replay calendar: OK >> "%LOG%") else (echo Replay calendar: MISSING [ERROR] >> "%LOG%")
echo. >> "%LOG%"

echo === DONE === >> "%LOG%"
echo Finished: %DATE% %TIME% >> "%LOG%"

echo.
echo  ============================================================
echo  Cleanup complete. Log: %LOG%
echo  ============================================================
echo.
echo  Press any key to close.
pause >nul
exit /b 0
