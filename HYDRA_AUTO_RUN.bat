@echo off
chcp 65001 >nul
title HYDRA V4 - Auto Setup + Run
color 0A

REM ============================================================
REM  HYDRA_AUTO_RUN.bat
REM
REM  ضغطة واحدة. السكربت يسوي كل شي على جهازك:
REM    1) يفتح لك file picker — تختار ملف المفاتيح اللي عندك
REM    2) يقرأه محلياً (ما يطلع منه شي خارج جهازك)
REM    3) يستخرج المفاتيح ويحطها في secrets\.env
REM    4) يشغّل الـ replay الكامل
REM    5) يفتح لك التقرير لما يخلص
REM
REM  المفاتيح ما تنتقل لـ Claude. كل شي محلي.
REM ============================================================

cls
echo.
echo  ============================================================
echo               HYDRA V4 - One-Click Auto Run
echo  ============================================================
echo.
echo   What this does ^(all on YOUR machine^):
echo     1. Asks you to pick your keys file ^(file picker opens^)
echo     2. Reads it locally — nothing leaves your laptop
echo     3. Sets up secrets\.env automatically
echo     4. Runs the full HYDRA V4 replay
echo     5. Opens the report when done
echo.
echo   Reminders:
echo     - Live orders are STRUCTURALLY blocked ^(LIVE_ORDER_GUARD^)
echo     - Keys never leave your machine
echo     - Send me only the final report file
echo.
echo  ============================================================
echo.
pause

REM Run the PowerShell helper
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0HYDRA_AUTO_RUN_HELPER.ps1"

echo.
echo  ============================================================
echo  HYDRA_AUTO_RUN finished. Press any key to close.
echo  ============================================================
pause >nul
