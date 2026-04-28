@echo off
chcp 65001 >nul
title HYDRA V4 - One-Click Start
color 0A

cls
echo.
echo  ============================================================
echo            HYDRA V4 - One-Click Start (Python only)
echo  ============================================================
echo.
echo  This will:
echo    1. Read your keys file LOCALLY (nothing leaves laptop)
echo    2. Create secrets\.env file
echo    3. Run the 2-year replay
echo    4. Show you the report at the end
echo.
echo  Press any key to start ...
pause >nul

echo.
cd /d "%USERPROFILE%\Desktop\HYDRA V4"
python setup_and_run.py
set "RC=%errorlevel%"

echo.
echo  ============================================================
echo  Exit code: %RC%
echo  ============================================================
echo.

if "%RC%"=="0" (
    echo  Looking for the report...
    if exist "replay_results\REAL_DATA_REPLAY_REPORT.md" (
        echo  Opening report in Notepad...
        start notepad "replay_results\REAL_DATA_REPLAY_REPORT.md"
    ) else (
        echo  Report not generated. Check console output above.
    )
)

echo.
echo  Press any key to close.
pause >nul
