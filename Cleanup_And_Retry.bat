@echo off
chcp 65001 >nul
title HYDRA V4 - Cleanup Cache and Retry
color 0A

cls
echo.
echo  ============================================================
echo            HYDRA V4 - Cleanup Cache and Retry
echo  ============================================================
echo.
echo  This will:
echo    1. Delete the old corrupted cache (data_cache folder)
echo    2. Re-download fresh OANDA data (with the fix applied)
echo    3. Run the 2-year replay
echo.
echo  Press any key to start ...
pause >nul

echo.
echo  ------------------------------------------------------------
echo  Removing old data_cache folder ...
echo  ------------------------------------------------------------
if exist "%USERPROFILE%\Desktop\HYDRA V4\data_cache" (
    rmdir /s /q "%USERPROFILE%\Desktop\HYDRA V4\data_cache"
    echo  [OK] data_cache deleted
) else (
    echo  [OK] no old data_cache to delete
)

echo.
echo  ------------------------------------------------------------
echo  Removing old replay_results folder ...
echo  ------------------------------------------------------------
if exist "%USERPROFILE%\Desktop\HYDRA V4\replay_results" (
    rmdir /s /q "%USERPROFILE%\Desktop\HYDRA V4\replay_results"
    echo  [OK] replay_results deleted
) else (
    echo  [OK] no old replay_results to delete
)

echo.
echo  ============================================================
echo  Now running START_HYDRA ...
echo  ============================================================
echo.

cd /d "%USERPROFILE%\Desktop\HYDRA V4"
python setup_and_run.py
set "RC=%errorlevel%"

echo.
echo  ============================================================
echo  Exit code: %RC%
echo  ============================================================

if "%RC%"=="0" (
    if exist "replay_results\REAL_DATA_REPLAY_REPORT.md" (
        echo  Opening the report in Notepad ...
        start notepad "replay_results\REAL_DATA_REPLAY_REPORT.md"
    )
)

echo.
echo  Press any key to close.
pause >nul
