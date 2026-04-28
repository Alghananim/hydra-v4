@echo off
REM ============================================================
REM   This file has been RENAMED to run_hydra_v3.bat
REM   Please use that file instead. This stub stays for safety.
REM ============================================================
echo This file is deprecated. Use:  run_hydra_v3.bat
pause
exit /b 0

setlocal EnableDelayedExpansion
chcp 65001 >nul
title NewsMind Trading System - Run (DEPRECATED)

REM ---------- Find install path ----------
set "PATH_FILE=%~dp0newsmind_path.txt"
if not exist "!PATH_FILE!" (
    echo [X] Could not find newsmind_path.txt next to this script.
    echo     Please run setup_newsmind.bat first.
    pause
    exit /b 1
)

set /p INSTALL_DIR=<"!PATH_FILE!"
if not exist "!INSTALL_DIR!\main_v3.py" (
    echo [X] main_v3.py not found at:
    echo     !INSTALL_DIR!
    echo Please re-run setup_newsmind.bat.
    pause
    exit /b 1
)

echo ============================================================
echo   NewsMind Trading System - Engine V3
echo   Path: !INSTALL_DIR!
echo ============================================================
echo.

REM ---------- Choose entry point ----------
echo Which entry point do you want to run?
echo   [1] main_v3.py   - Engine V3 (5 brains + LLM layer)  [recommended]
echo   [2] main.py      - legacy v1 loop
echo.
set /p "CHOICE=Enter 1 or 2: "
if "!CHOICE!"=="" set "CHOICE=1"

if "!CHOICE!"=="1" (
    set "ENTRY=main_v3.py"
) else (
    set "ENTRY=main.py"
)

pushd "!INSTALL_DIR!"
call ".venv\Scripts\activate.bat"

REM ---------- Load .env into environment ----------
if exist ".env" (
    echo Loading .env...
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "LINE=%%a"
        REM Skip comments and blank lines
        if not "!LINE!"=="" if not "!LINE:~0,1!"=="#" (
            set "%%a=%%b"
        )
    )
)

echo.
echo Starting !ENTRY! ...
echo (Press Ctrl+C to stop the loop gracefully.)
echo ============================================================
echo.

python "!ENTRY!"

set "EXIT_CODE=!errorlevel!"
echo.
echo ============================================================
echo   Stopped with exit code !EXIT_CODE!.
echo ============================================================
popd
pause
endlocal
