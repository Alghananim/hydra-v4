@echo off
chcp 65001 >nul
title HYDRA V4 - Install Dependencies
color 0E

cls
echo.
echo  ============================================================
echo            HYDRA V4 - Install Dependencies
echo  ============================================================
echo.
echo  Installing required Python packages:
echo    - tzdata     (timezone database for Windows)
echo    - pandas     (data manipulation, may already exist)
echo    - numpy      (numeric core)
echo    - PyYAML     (config loader)
echo    - requests   (network helper)
echo.
echo  Press any key to start ...
pause >nul

echo.
echo  ------------------------------------------------------------
echo  Installing: tzdata (CRITICAL — required for timezones)
echo  ------------------------------------------------------------
python -m pip install --upgrade tzdata
if errorlevel 1 (
    echo.
    echo  [X] tzdata install FAILED. Trying with --user flag ...
    python -m pip install --user --upgrade tzdata
)
echo.

echo  ------------------------------------------------------------
echo  Installing other helpers
echo  ------------------------------------------------------------
python -m pip install --upgrade pandas numpy PyYAML requests 2>nul
echo.

echo  ============================================================
echo  Done. All required deps should be installed.
echo  ============================================================
echo.
echo  Verifying tzdata is installed ...
python -c "import tzdata; print('  tzdata version:', tzdata.IANA_VERSION)"
if errorlevel 1 (
    echo  [X] tzdata still not importable. Check error above.
) else (
    echo  [OK] tzdata is ready.
)

echo.
echo  Verifying America/New_York timezone works ...
python -c "from zoneinfo import ZoneInfo; tz = ZoneInfo('America/New_York'); print('  Timezone OK:', tz)"
if errorlevel 1 (
    echo  [X] Timezone test FAILED.
) else (
    echo  [OK] Timezone works.
)

echo.
echo  ============================================================
echo  Next step: double-click START_HYDRA.bat to run the replay
echo  ============================================================
echo.
echo  Press any key to close.
pause >nul
