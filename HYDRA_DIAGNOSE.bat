@echo off
chcp 65001 >nul
title HYDRA V4 Quick Check
color 0E

set "LOG=%USERPROFILE%\Desktop\HYDRA_DIAGNOSE.log"

cls
echo.
echo  ============================================================
echo            HYDRA V4 - Quick Check
echo  ============================================================
echo.
echo  This will check the system and write a log file.
echo  Log file: %LOG%
echo.
echo  Press any key to start...
pause >nul

echo HYDRA V4 Quick Check > "%LOG%"
echo Started: %DATE% %TIME% >> "%LOG%"
echo Username: %USERNAME% >> "%LOG%"
echo Desktop: %USERPROFILE%\Desktop >> "%LOG%"
echo. >> "%LOG%"
echo ========== CHECKS ========== >> "%LOG%"

echo.
echo  Running checks...
echo  ------------------------------------------------------------

REM Check 1: HYDRA V4 folder
if exist "%USERPROFILE%\Desktop\HYDRA V4\" (
    echo [OK]   HYDRA V4 folder exists >> "%LOG%"
    echo [OK]   HYDRA V4 folder exists
) else (
    echo [FAIL] HYDRA V4 folder NOT found >> "%LOG%"
    echo [FAIL] HYDRA V4 folder NOT found
)

REM Check 2: API_KEYS folder
if exist "%USERPROFILE%\Desktop\API_KEYS\" (
    echo [OK]   API_KEYS folder exists >> "%LOG%"
    echo [OK]   API_KEYS folder exists
) else (
    echo [FAIL] API_KEYS folder NOT found >> "%LOG%"
    echo [FAIL] API_KEYS folder NOT found
)

REM Check 3: keys file at expected path
if exist "%USERPROFILE%\Desktop\API_KEYS\ALL KEYS AND TOKENS.txt" (
    echo [OK]   Keys file at expected path: ALL KEYS AND TOKENS.txt >> "%LOG%"
    echo [OK]   Keys file at expected path: ALL KEYS AND TOKENS.txt
) else (
    echo [FAIL] Keys file NOT at: ALL KEYS AND TOKENS.txt >> "%LOG%"
    echo [FAIL] Keys file NOT at: ALL KEYS AND TOKENS.txt
    echo. >> "%LOG%"
    echo Files actually in API_KEYS folder: >> "%LOG%"
    if exist "%USERPROFILE%\Desktop\API_KEYS\" (
        dir /b "%USERPROFILE%\Desktop\API_KEYS\" >> "%LOG%" 2>&1
    ) else (
        echo   ^(folder doesn't exist^) >> "%LOG%"
    )
)

REM Check 4: Python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do (
        echo [OK]   %%i >> "%LOG%"
        echo [OK]   %%i
    )
) else (
    echo [FAIL] Python NOT in PATH >> "%LOG%"
    echo [FAIL] Python NOT in PATH
)

REM Check 5: Git
git --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('git --version 2^>^&1') do (
        echo [OK]   %%i >> "%LOG%"
        echo [OK]   %%i
    )
) else (
    echo [WARN] git NOT in PATH ^(not critical^) >> "%LOG%"
    echo [WARN] git NOT in PATH ^(not critical^)
)

echo. >> "%LOG%"
echo ========== HYDRA V4 FILES ========== >> "%LOG%"

REM Critical files
call :checkfile "contracts\brain_output.py"
call :checkfile "newsmind\v4\NewsMindV4.py"
call :checkfile "marketmind\v4\MarketMindV4.py"
call :checkfile "chartmind\v4\ChartMindV4.py"
call :checkfile "gatemind\v4\GateMindV4.py"
call :checkfile "smartnotebook\v4\SmartNoteBookV4.py"
call :checkfile "orchestrator\v4\HydraOrchestratorV4.py"
call :checkfile "live_data\live_order_guard.py"
call :checkfile "live_data\oanda_readonly_client.py"
call :checkfile "live_data\data_loader.py"
call :checkfile "anthropic_bridge\bridge.py"
call :checkfile "replay\two_year_replay.py"
call :checkfile "run_live_replay.py"

echo. >> "%LOG%"
echo ========== SECRETS STATE ========== >> "%LOG%"

if exist "%USERPROFILE%\Desktop\HYDRA V4\secrets\" (
    echo [OK]   secrets\ folder exists >> "%LOG%"
    echo [OK]   secrets\ folder exists
) else (
    echo [WARN] secrets\ folder missing >> "%LOG%"
    echo [WARN] secrets\ folder missing
)

if exist "%USERPROFILE%\Desktop\HYDRA V4\secrets\.env" (
    echo [OK]   .env file exists >> "%LOG%"
    echo [OK]   .env file exists
) else (
    echo [WARN] .env file NOT yet created >> "%LOG%"
    echo [WARN] .env file NOT yet created
)

echo. >> "%LOG%"
echo ========== Done ========== >> "%LOG%"
echo Finished: %DATE% %TIME% >> "%LOG%"

echo  ------------------------------------------------------------
echo.
echo  ============================================================
echo  Diagnostic complete.
echo  Log: %LOG%
echo.
echo  Opening Notepad in 3 seconds ...
echo  ============================================================
timeout /t 3 >nul
start notepad "%LOG%"

echo.
echo  Press any key to close this window.
pause >nul
goto :eof

:checkfile
if exist "%USERPROFILE%\Desktop\HYDRA V4\%~1" (
    echo [OK]   %~1 >> "%LOG%"
    echo [OK]   %~1
) else (
    echo [FAIL] %~1 MISSING >> "%LOG%"
    echo [FAIL] %~1 MISSING
)
goto :eof
