@echo off
chcp 65001 >nul
title HYDRA V4 - Setup Secrets (Local Only)
color 0E

REM ============================================================
REM  Setup_Secrets.bat
REM
REM  ينشئ ملف secrets\.env المحلي وحده، ويفتحه لك في Notepad
REM  لتلصق فيه المفاتيح. الملف:
REM    - محمي بـ .gitignore (لا يدخل git)
REM    - محلي فقط (لا يخرج من جهازك)
REM    - يُقرأ من Run_Two_Year_Replay.bat
REM
REM  المفاتيح ما تنتقل لـ Claude، لا الآن، لا أبداً.
REM ============================================================

set "PROJ=%USERPROFILE%\Desktop\HYDRA V4"
set "SECRETS=%PROJ%\secrets"
set "ENV_FILE=%SECRETS%\.env"

cls
echo.
echo  ============================================================
echo            HYDRA V4 - Setup Secrets (LOCAL ONLY)
echo  ============================================================
echo.

if not exist "%PROJ%" (
    echo  [X] HYDRA V4 not found at: %PROJ%
    pause
    exit /b 1
)
echo  Project: %PROJ%
echo.

echo [1/4] Creating secrets folder...
if not exist "%SECRETS%" mkdir "%SECRETS%"
echo      [OK] %SECRETS%
echo.

echo [2/4] Verifying .gitignore protection...
findstr /C:"secrets/.env" "%PROJ%\.gitignore" >nul 2>&1
if errorlevel 1 (
    echo secrets/.env >> "%PROJ%\.gitignore"
    echo replay_results/ >> "%PROJ%\.gitignore"
    echo data_cache/ >> "%PROJ%\.gitignore"
    echo      [OK] Added to .gitignore
) else (
    echo      [OK] Already protected
)
echo.

echo [3/4] Creating .env template...
if exist "%ENV_FILE%" (
    echo      [SKIP] %ENV_FILE% already exists
    echo             ^(if you need to re-edit, just open it manually^)
) else (
    > "%ENV_FILE%" (
        echo # HYDRA V4 - Local Secrets ^(gitignored^)
        echo # NEVER commit this file. NEVER share its content with anyone.
        echo # Read by Run_Two_Year_Replay.bat at runtime — does NOT leave your machine.
        echo #
        echo # Replace the placeholders below with your real values.
        echo.
        echo # ====== Anthropic Claude API ======
        echo # Get from: https://console.anthropic.com/settings/keys
        echo ANTHROPIC_API_KEY=sk-ant-REPLACE_ME
        echo.
        echo # Optional: pin a specific model. Defaults to Claude 3.5 Sonnet if unset.
        echo # LLM_MODEL=claude-3-5-sonnet-20241022
        echo.
        echo # ====== OANDA ^(LIVE account, READ-ONLY usage in this phase^) ======
        echo # WARNING: this is your LIVE token. The framework refuses to send orders.
        echo # Get from: OANDA -^> Manage API Access
        echo OANDA_API_TOKEN=REPLACE_ME
        echo OANDA_ACCOUNT_ID=001-001-XXXXXXXX-001
        echo OANDA_ENV=live
        echo.
        echo # ====== Optional ^(can leave defaults^) ======
        echo # REPLAY_END_DATE=2026-04-27       # ISO date, defaults to today UTC
        echo # REPLAY_PAIRS=EUR_USD,USD_JPY     # comma-separated, OANDA format
    )
    echo      [OK] Created %ENV_FILE%
)
echo.

echo [4/4] Opening .env in Notepad for you to fill in...
echo.
echo   IMPORTANT:
echo     1. Replace each "REPLACE_ME" with your real key/token/id.
echo     2. Save the file ^(Ctrl+S^) and close Notepad.
echo     3. The file stays LOCAL ^(in secrets folder, gitignored^).
echo     4. NEVER paste the content of this file in any chat.
echo.
echo  ============================================================
echo.
echo  Notepad opens now. Fill in, save, close.
echo.
pause

start /WAIT notepad "%ENV_FILE%"

echo.
echo  ============================================================
echo            Secrets file edit closed.
echo  ============================================================
echo.

REM Quick sanity check (without printing values)
findstr /C:"REPLACE_ME" "%ENV_FILE%" >nul 2>&1
if not errorlevel 1 (
    echo  [WARN] Some fields still show "REPLACE_ME".
    echo         Re-run this script to edit again, OR open manually:
    echo         %ENV_FILE%
    echo.
    echo  Until all keys are filled, Run_Two_Year_Replay.bat will refuse.
) else (
    echo  [OK] No REPLACE_ME placeholders remain.
    echo.
    echo  Next step:
    echo    Double-click Run_Two_Year_Replay.bat on your Desktop
    echo.
    echo  Reminders:
    echo    - The keys NEVER leave your machine.
    echo    - LIVE_ORDER_GUARD blocks any trade attempt structurally.
    echo    - Send me only the OUTPUT report ^(replay_results\REAL_DATA_REPLAY_REPORT.md^),
    echo      NEVER the secrets file.
)
echo.
pause
