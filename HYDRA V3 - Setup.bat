@echo off
chcp 65001 >nul
title HYDRA V3 - Setup
color 0A

REM ============================================================
REM  HYDRA V3 - One-Click Desktop Setup
REM  Just double-click this file. It does everything.
REM ============================================================

set "DESKTOP=%USERPROFILE%\Desktop"
set "SRC=%APPDATA%\Claude\local-agent-mode-sessions\393e4fb2-e8b5-41ad-bcbf-1d3d3655f9a4\bee5bd3d-3bcc-4380-b94e-58e959304727\local_b11bf4d4-59c3-489b-87d0-e22ae0eab430\outputs"

cls
echo.
echo  ============================================================
echo                    HYDRA V3 - Desktop Setup
echo  ============================================================
echo.
echo   Source: outputs folder
echo   Target: %DESKTOP%
echo.
echo   This script copies these 6 folders to your Desktop:
echo     - ChartMind V3       (Brain #1)
echo     - MarketMind V3      (Brain #2)
echo     - NewsMind V3        (Brain #3)
echo     - GateMind V3        (Brain #4)
echo     - SmartNoteBook V3   (Brain #5)
echo     - HYDRA V3           (Master integrated project)
echo.
echo  ============================================================
echo.

if not exist "%SRC%\HYDRA V3" (
    echo  [X] Source folder not found:
    echo      %SRC%
    echo.
    echo  This means Claude has not finished preparing the files yet.
    echo  Wait until Claude says "ready", then run this script again.
    pause
    exit /b 1
)

set "ERRORS=0"

for %%B in ("ChartMind V3" "MarketMind V3" "NewsMind V3" "GateMind V3" "SmartNoteBook V3" "HYDRA V3") do (
    echo [*] Copying %%~B ...
    if not exist "%SRC%\%%~B" (
        echo     SKIP: not found in source
    ) else (
        if exist "%DESKTOP%\%%~B" (
            echo     [removing existing folder first]
            rmdir /S /Q "%DESKTOP%\%%~B" 2>nul
        )
        xcopy "%SRC%\%%~B" "%DESKTOP%\%%~B\" /E /I /Y /Q >nul 2>&1
        if errorlevel 1 (
            echo     FAILED
            set /a ERRORS+=1
        ) else (
            echo     OK
        )
    )
)

echo.
echo  ============================================================
if "%ERRORS%"=="0" (
    echo   SUCCESS - All 6 folders are now on your Desktop.
) else (
    echo   Done with %ERRORS% failure(s). Check messages above.
)
echo  ============================================================
echo.
echo   Now look at your Desktop. You should see 6 new folders.
echo.
echo   Open HYDRA V3 to see the full integrated project.
echo   Open any individual brain folder to see just that brain.
echo.
echo   You can now safely DELETE this script if you want
echo   ^(it has done its job^).
echo.
pause
