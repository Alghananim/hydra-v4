@echo off
chcp 65001 >nul
title HYDRA V4 - AUTO RUN

REM ===================================================================
REM  AUTO_RUN.bat — zero prompts, zero pauses.
REM  Just double-click ONCE. Output goes to:
REM    %USERPROFILE%\Desktop\HYDRA_AUTO_OUTPUT.txt
REM    %USERPROFILE%\Desktop\HYDRA_REPLAY.log
REM  Claude will read these directly.
REM ===================================================================

cls
echo.
echo  HYDRA V4 - AUTO RUN
echo  -------------------
echo  Running silently. Do NOT close this window.
echo  Output will be saved to:
echo    %USERPROFILE%\Desktop\HYDRA_AUTO_OUTPUT.txt
echo    %USERPROFILE%\Desktop\HYDRA_REPLAY.log
echo.

REM Clean only old replay results, keep the cache.
if exist "%USERPROFILE%\Desktop\HYDRA V4\replay_results" (
    rmdir /s /q "%USERPROFILE%\Desktop\HYDRA V4\replay_results"
)

cd /d "%USERPROFILE%\Desktop\HYDRA V4"

REM Pipe "Y" to auto-confirm the "Run replay now?" prompt.
REM Redirect ALL output (stdout+stderr) to HYDRA_AUTO_OUTPUT.txt.
echo Y | python setup_and_run.py > "%USERPROFILE%\Desktop\HYDRA_AUTO_OUTPUT.txt" 2>&1
set "RC=%errorlevel%"

echo.
echo  ============================================================
echo  Finished. Exit code: %RC%
echo  ============================================================
echo.
echo  Output files (Claude will read these):
echo    %USERPROFILE%\Desktop\HYDRA_AUTO_OUTPUT.txt
echo    %USERPROFILE%\Desktop\HYDRA_REPLAY.log
echo.
echo  You can close this window now and tell Claude "done".
echo.

REM Auto-close after 5 seconds.
timeout /t 5 /nobreak >nul
exit /b %RC%
