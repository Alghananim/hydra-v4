@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title HYDRA V3 - Setup

echo ============================================================
echo   HYDRA V3 - 5-Brain Trading System
echo   Local Setup for Windows
echo ============================================================
echo.
echo   Brains: ChartMind ^| MarketMind ^| NewsMind ^| GateMind ^| SmartNoteBook
echo   Engine: EngineV3 + safety_rails (12 final checks)
echo   Source: https://github.com/Alghananim/newsmind.git
echo.

REM ---------- Choose install location ----------
set "DEFAULT_DIR=%USERPROFILE%\Documents\hydra-v3"
echo Project will be installed in:
echo   !DEFAULT_DIR!
echo.
set /p "INSTALL_DIR=Press Enter to accept, or type another full path: "
if "!INSTALL_DIR!"=="" set "INSTALL_DIR=!DEFAULT_DIR!"

echo.
echo Install path chosen: !INSTALL_DIR!
echo.

REM ---------- Check Python ----------
echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [X] Python NOT found in PATH.
    echo   Please install Python 3.10 or newer from:
    echo       https://www.python.org/downloads/
    echo   IMPORTANT: tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo   [OK] Python !PYVER! detected.

REM ---------- Check Git ----------
echo [2/6] Checking Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo   [X] Git NOT found in PATH.
    echo   Please install Git for Windows from:
    echo       https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)
echo   [OK] Git detected.

REM ---------- Clone repo ----------
echo [3/6] Cloning HYDRA V3 source from GitHub (newsmind.git repo)...
if exist "!INSTALL_DIR!\.git" (
    echo   Repo already exists. Pulling latest...
    pushd "!INSTALL_DIR!"
    git pull --ff-only
    if errorlevel 1 (
        echo   [WARN] git pull failed. You may have local changes.
    )
    popd
) else (
    if exist "!INSTALL_DIR!" (
        echo   [WARN] Folder exists but is not a git repo. Aborting to avoid data loss.
        echo   Either delete it or pick another path, then re-run setup.
        pause
        exit /b 1
    )
    git clone https://github.com/Alghananim/newsmind.git "!INSTALL_DIR!"
    if errorlevel 1 (
        echo   [X] Clone failed. Check internet / GitHub access.
        pause
        exit /b 1
    )
)
echo   [OK] HYDRA V3 source at !INSTALL_DIR!.

REM ---------- Create venv ----------
echo [4/6] Creating Python virtual environment (.venv)...
pushd "!INSTALL_DIR!"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo   [X] venv creation failed.
        popd
        pause
        exit /b 1
    )
)
echo   [OK] venv ready.

REM ---------- Install dependencies ----------
echo [5/6] Installing dependencies (PyYAML, pandas, numpy, requests)...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
    echo   [X] pip install failed.
    popd
    pause
    exit /b 1
)
echo   [OK] All packages installed.

REM ---------- Prepare .env ----------
echo [6/6] Preparing .env...
if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo   [OK] .env created from template.
    echo       Open it and fill OPENAI_API_KEY and OANDA_API_TOKEN.
) else (
    echo   [OK] .env already exists - left untouched.
)

popd
echo.
echo ============================================================
echo   HYDRA V3 setup complete!
echo ============================================================
echo.
echo Next steps:
echo   1) Open the .env file at:
echo        !INSTALL_DIR!\.env
echo      Fill in your real OPENAI_API_KEY and OANDA_API_TOKEN.
echo      Make sure OANDA_ENVIRONMENT=practice (NOT live) for first run.
echo.
echo   2) Run the system with:
echo        run_hydra_v3.bat
echo      (or manually: cd "!INSTALL_DIR!" then call .venv\Scripts\activate ^&^& python main_v3.py)
echo.
echo Saving install path for run_hydra_v3.bat...
> "%~dp0hydra_v3_path.txt" echo !INSTALL_DIR!
echo   [OK] Saved to %~dp0hydra_v3_path.txt
echo.
pause
endlocal
