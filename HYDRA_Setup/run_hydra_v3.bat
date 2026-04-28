@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title HYDRA V3 - Run

REM ---------- Find install path ----------
set "PATH_FILE=%~dp0hydra_v3_path.txt"
if not exist "!PATH_FILE!" (
    echo [X] Could not find hydra_v3_path.txt next to this script.
    echo     Please run setup_hydra_v3.bat first.
    pause
    exit /b 1
)

set /p INSTALL_DIR=<"!PATH_FILE!"
if not exist "!INSTALL_DIR!\main_v3.py" (
    echo [X] main_v3.py not found at:
    echo     !INSTALL_DIR!
    echo Please re-run setup_hydra_v3.bat.
    pause
    exit /b 1
)

echo ============================================================
echo   HYDRA V3 - 5-Brain Trading System
echo   Path: !INSTALL_DIR!
echo ============================================================
echo.

REM ---------- Choose entry point ----------
echo Which entry point do you want to run?
echo   [1] main_v3.py   - HYDRA V3 (5 brains + LLM layer)  [recommended]
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
echo Starting HYDRA V3 :: !ENTRY! ...
echo (Press Ctrl+C to stop the loop gracefully.)
echo ============================================================
echo.

python "!ENTRY!"

set "EXIT_CODE=!errorlevel!"
echo.
echo ============================================================
echo   HYDRA V3 stopped with exit code !EXIT_CODE!.
echo ============================================================
popd
pause
endlocal
