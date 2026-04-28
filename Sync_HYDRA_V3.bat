@echo off
chcp 65001 >nul
title Sync HYDRA V3 - Latest Code
color 0E

REM ============================================================
REM  Sync_HYDRA_V3.bat
REM  Copies the latest HYDRA V3 code from Claude's outputs folder
REM  to BOTH:
REM    - Documents\hydra-v3   (where venv lives, used to RUN)
REM    - Desktop\HYDRA V3     (organized desktop folder)
REM
REM  PRESERVES:
REM    - .venv\               (your Python environment)
REM    - .env                 (your API keys)
REM    - .git\                (your git history if any)
REM    - SmartNoteBook DB files in NewsMind\state\
REM
REM  Just double-click. It tells you what it did.
REM ============================================================

set "SRC=%APPDATA%\Claude\local-agent-mode-sessions\393e4fb2-e8b5-41ad-bcbf-1d3d3655f9a4\bee5bd3d-3bcc-4380-b94e-58e959304727\local_b11bf4d4-59c3-489b-87d0-e22ae0eab430\outputs\HYDRA_V3_LATEST"
set "DOCS=%USERPROFILE%\Documents\hydra-v3"
set "DESK=%USERPROFILE%\Desktop\HYDRA V3"

cls
echo.
echo  ============================================================
echo                   HYDRA V3 - SYNC LATEST CODE
echo  ============================================================
echo.
echo   Source: outputs\HYDRA_V3_LATEST  (Claude's sandbox copy)
echo   Targets:
echo     1) %DOCS%
echo     2) %DESK%
echo.
echo   Preserved (NOT overwritten):
echo     - .venv\        (Python environment)
echo     - .env          (API keys)
echo     - .git\         (git history)
echo     - NewsMind\state\  (SmartNoteBook DB)
echo  ============================================================
echo.

if not exist "%SRC%" (
    echo  [X] Source folder not found:
    echo      %SRC%
    echo.
    echo  Wait for Claude to finish preparing files, then re-run.
    pause
    exit /b 1
)

REM ---- Backup current Documents\hydra-v3 first ----
set "BACKUP=%USERPROFILE%\Documents\hydra-v3-backup-%DATE:~10,4%%DATE:~4,2%%DATE:~7,2%-%TIME:~0,2%%TIME:~3,2%"
set "BACKUP=%BACKUP: =0%"
if exist "%DOCS%" (
    echo [*] Creating safety backup of Documents\hydra-v3 ...
    echo     %BACKUP%
    xcopy "%DOCS%" "%BACKUP%\" /E /I /Q /Y >nul 2>&1
    if errorlevel 1 (
        echo     WARNING: Backup may have failed. Aborting.
        pause
        exit /b 1
    )
    echo     OK
) else (
    echo [!] Documents\hydra-v3 does not exist yet. Will create.
)

echo.
echo [*] Step 1/2: Sync to Documents\hydra-v3 ...

REM xcopy with /E /I /Y /Q copies recursively, creating dirs, overwriting files.
REM It does NOT delete files that exist in destination but not in source.
REM So .venv, .env, .git, NewsMind\state\ are preserved automatically.
xcopy "%SRC%" "%DOCS%\" /E /I /Y /Q >nul 2>&1
if errorlevel 1 (
    echo     FAILED. Restore from %BACKUP% if needed.
    pause
    exit /b 1
)
echo     OK
echo.

echo [*] Step 2/2: Sync to Desktop\HYDRA V3 ...
xcopy "%SRC%" "%DESK%\" /E /I /Y /Q >nul 2>&1
if errorlevel 1 (
    echo     FAILED.
    pause
    exit /b 1
)
echo     OK
echo.

REM ---- Verify backtest_v2 made it ----
echo [*] Verifying critical files ...
set "OK=1"
if not exist "%DOCS%\backtest_v2\runner.py"            ( echo     [X] Documents\backtest_v2\runner.py MISSING & set "OK=0" ) else ( echo     [OK] Documents\backtest_v2\runner.py )
if not exist "%DOCS%\engine\v3\EngineV3.py"            ( echo     [X] Documents\engine\v3\EngineV3.py MISSING  & set "OK=0" ) else ( echo     [OK] Documents\engine\v3\EngineV3.py  )
if not exist "%DOCS%\gatemind\v3\test_strict_mode.py"  ( echo     [X] Documents\gatemind\v3\test_strict_mode.py MISSING & set "OK=0" ) else ( echo     [OK] Documents\gatemind\v3\test_strict_mode.py )
if not exist "%DESK%\backtest_v2\runner.py"            ( echo     [X] Desktop\HYDRA V3\backtest_v2\runner.py MISSING & set "OK=0" ) else ( echo     [OK] Desktop\HYDRA V3\backtest_v2\runner.py )

echo.
echo  ============================================================
if "%OK%"=="1" (
    echo   SUCCESS - Both folders are now up-to-date.
    echo.
    echo   To run HYDRA V3:
    echo     cd "%DOCS%"
    echo     .venv\Scripts\python.exe main_v3.py
    echo.
    echo   To run all 46 tests:
    echo     cd "%DOCS%"
    echo     .venv\Scripts\python.exe -m pytest -v
    echo.
    echo   Backup of old code saved at:
    echo     %BACKUP%
    echo   ^(safe to delete after you confirm new code works^)
) else (
    echo   FAILED - Some critical files did not copy correctly.
    echo   Restore from backup if needed:
    echo     %BACKUP%
)
echo  ============================================================
echo.
pause
