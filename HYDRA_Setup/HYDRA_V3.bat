@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title HYDRA V3 - 5-Brain Trading System

color 0A
mode con: cols=100 lines=40

echo.
echo  ====================================================================
echo                     H Y D R A    V 3
echo                  5-Brain Trading System
echo  ====================================================================
echo.

set "INSTALL_DIR=%USERPROFILE%\Documents\hydra-v3"

if not exist "%INSTALL_DIR%\main_v3.py" (
    echo  [X] HYDRA V3 not found at: %INSTALL_DIR%
    echo.
    echo      Please make sure you cloned the project there.
    echo      Expected: %INSTALL_DIR%\main_v3.py
    echo.
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%\.venv\Scripts\python.exe" (
    echo  [X] Python virtual environment not found.
    echo      Expected: %INSTALL_DIR%\.venv\Scripts\python.exe
    echo.
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%\.env" (
    echo  [WARN] .env file not found - keys are not configured.
    echo         You will see "LLM enabled: False" and OANDA disabled.
    echo.
    timeout /t 3 >nul
)

echo  Project: %INSTALL_DIR%
echo  Python:  %INSTALL_DIR%\.venv\Scripts\python.exe
echo.
echo  --------------------------------------------------------------------
echo   What runs:  main_v3.py  (Engine V3 with all 5 brains + LLM layer)
echo   How to stop: press Ctrl+C
echo  --------------------------------------------------------------------
echo.

cd /d "%INSTALL_DIR%"

REM Load .env into environment
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "K=%%a"
        if not "!K!"=="" if not "!K:~0,1!"=="#" (
            set "%%a=%%b"
        )
    )
)

REM Set Python path so submodules are found
set "PYTHONPATH=%INSTALL_DIR%"

REM Run main_v3.py
".venv\Scripts\python.exe" main_v3.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo  ====================================================================
echo   HYDRA V3 stopped (exit code !EXIT_CODE!)
echo  ====================================================================
echo.
pause
endlocal
