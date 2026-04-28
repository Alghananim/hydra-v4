@echo off
chcp 65001 >nul
title HYDRA V4 - Phase 1 Git Audit (READ-ONLY)
color 0B

cls
echo.
echo  ============================================================
echo            HYDRA V4 - PHASE 1: GIT AUDIT (READ-ONLY)
echo  ============================================================
echo.
echo  This script ONLY READS git state. It does NOT modify anything.
echo  Output saved to: %USERPROFILE%\Desktop\PHASE1_GIT_AUDIT.txt
echo.

cd /d "%USERPROFILE%\Desktop\HYDRA V4"

set "OUT=%USERPROFILE%\Desktop\PHASE1_GIT_AUDIT.txt"

echo HYDRA V4 - PHASE 1 GIT AUDIT > "%OUT%"
echo Generated: %DATE% %TIME% >> "%OUT%"
echo Working dir: %CD% >> "%OUT%"
echo. >> "%OUT%"

echo === [1] git --version === >> "%OUT%"
git --version >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [2] Repository root === >> "%OUT%"
git rev-parse --show-toplevel >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [3] Current branch === >> "%OUT%"
git branch --show-current >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [4] All branches === >> "%OUT%"
git branch -a >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [5] Latest commit (HEAD) === >> "%OUT%"
git log -1 --format="%%H%%n  Author: %%an ^<%%ae^>%%n  Date:   %%ad%%n  Subject: %%s" >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [6] Last 20 commits (oneline) === >> "%OUT%"
git log --oneline -20 >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [7] Tags === >> "%OUT%"
git tag -l >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [8] git status (porcelain) === >> "%OUT%"
git status --porcelain >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [9] git status (full) === >> "%OUT%"
git status >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [10] Files tracked by git (count) === >> "%OUT%"
for /f %%i in ('git ls-files ^| find /v /c ""') do echo Tracked files: %%i >> "%OUT%"
echo. >> "%OUT%"

echo === [11] Files containing potentially-secret patterns IN GIT === >> "%OUT%"
echo (searching tracked files only - won't see secrets/.env which is gitignored) >> "%OUT%"
git grep -n -E "sk-ant-[A-Za-z0-9_\-]{10,}" 2>nul >> "%OUT%"
git grep -n -E "[0-9]{3}-[0-9]{3}-[0-9]{8}-[0-9]{3}" 2>nul >> "%OUT%"
git grep -n -E "ANTHROPIC_API_KEY\s*=\s*[A-Za-z0-9]" 2>nul >> "%OUT%"
git grep -n -E "OANDA_API_TOKEN\s*=\s*[A-Za-z0-9]" 2>nul >> "%OUT%"
echo (end of secret scan) >> "%OUT%"
echo. >> "%OUT%"

echo === [12] .gitignore content === >> "%OUT%"
type .gitignore >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === [13] secrets folder status === >> "%OUT%"
if exist "secrets\" (
    echo secrets/ folder EXISTS on disk >> "%OUT%"
    dir /b secrets >> "%OUT%" 2>&1
    echo. >> "%OUT%"
    echo Is secrets/.env tracked by git? >> "%OUT%"
    git ls-files secrets/ >> "%OUT%" 2>&1
    git check-ignore -v secrets/.env >> "%OUT%" 2>&1
) else (
    echo secrets/ folder does NOT exist >> "%OUT%"
)
echo. >> "%OUT%"

echo === [14] data_cache folder status === >> "%OUT%"
if exist "data_cache\" (
    echo data_cache/ folder EXISTS on disk >> "%OUT%"
    echo Is it tracked? >> "%OUT%"
    git ls-files data_cache/ ^| head -5 >> "%OUT%" 2>&1
) else (
    echo data_cache/ folder does NOT exist >> "%OUT%"
)
echo. >> "%OUT%"

echo === [15] Working tree clean check === >> "%OUT%"
git diff --stat >> "%OUT%" 2>&1
echo --- staged --- >> "%OUT%"
git diff --cached --stat >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === END OF AUDIT === >> "%OUT%"

echo.
echo  ============================================================
echo  Audit saved to: %OUT%
echo  ============================================================
echo.

REM Auto-close after 3 seconds
timeout /t 3 /nobreak >nul
exit /b 0
