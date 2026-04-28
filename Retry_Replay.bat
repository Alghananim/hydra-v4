@echo off
chcp 65001 >nul
title HYDRA V4 - Retry Replay (keep cache)
color 0B

cls
echo.
echo  ============================================================
echo            HYDRA V4 - Retry Replay
echo  ============================================================
echo.
echo  Cache is GOOD - no need to re-download.
echo  Just re-running with the dedupe fix applied.
echo.
echo  Press any key to start ...
pause >nul

echo.
echo  ------------------------------------------------------------
echo  Removing only old replay_results (keep data_cache) ...
echo  ------------------------------------------------------------
if exist "%USERPROFILE%\Desktop\HYDRA V4\replay_results" (
    rmdir /s /q "%USERPROFILE%\Desktop\HYDRA V4\replay_results"
    echo  [OK] replay_results deleted
) else (
    echo  [OK] no old replay_results to delete
)

echo.
echo  ============================================================
echo  Running setup_and_run.py ...
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
