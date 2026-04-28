# Setup_Desktop_Layout.ps1
# يبني تخطيط HYDRA V3 على سطح المكتب:
#
#   Desktop\
#   ├── HYDRA V3\           ← اختصار للمشروع الكامل (المدمج)
#   ├── ChartMind V3\       ← اختصار لمجلد العقل #1
#   ├── MarketMind V3\      ← اختصار لمجلد العقل #2
#   ├── NewsMind V3\        ← اختصار لمجلد العقل #3
#   ├── GateMind V3\        ← اختصار لمجلد العقل #4
#   ├── SmartNoteBook V3\   ← اختصار لمجلد العقل #5
#   └── HYDRA V3 - Run.lnk  ← اختصار يشغّل main_v3.py مباشرة
#
# الاختصارات تفتح الـ folder الفعلي في Documents\hydra-v3\... فلا يحدث ازدواج
# في الكود — أي تعديل تسويه على HYDRA V3 ينعكس فوراً على كل عقل.
#
# الاستخدام: نقر يمين على هذا الملف ← Run with PowerShell

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Write-Title { param($T); Write-Host ""; Write-Host ("=" * 70) -ForegroundColor Cyan; Write-Host "  $T" -ForegroundColor Cyan; Write-Host ("=" * 70) -ForegroundColor Cyan }
function Write-OK    { param($T); Write-Host "[OK] $T" -ForegroundColor Green }
function Write-Step  { param($T); Write-Host "[*]  $T" -ForegroundColor Yellow }
function Write-Err   { param($T); Write-Host "[X]  $T" -ForegroundColor Red }

Write-Title "HYDRA V3 — Desktop Layout Setup"

# ---------- Locate repo ----------
$repo = Join-Path $env:USERPROFILE "Documents\hydra-v3"
if (-not (Test-Path $repo)) {
    Write-Err "Repo not found at: $repo"
    Write-Host "  Run Apply_All_Cleanup.ps1 first."
    pause; exit 1
}
Write-OK "Repo: $repo"

$desktop = [Environment]::GetFolderPath("Desktop")
Write-OK "Desktop: $desktop"

# ---------- Define what we want on the desktop ----------
$brains = @(
    @{ Name = "ChartMind V3";       Target = (Join-Path $repo "chartmind\v3");      Icon = "shell32.dll,235" },
    @{ Name = "MarketMind V3";      Target = (Join-Path $repo "marketmind\v3");     Icon = "shell32.dll,237" },
    @{ Name = "NewsMind V3";        Target = (Join-Path $repo "newsmind\v3");       Icon = "shell32.dll,238" },
    @{ Name = "GateMind V3";        Target = (Join-Path $repo "gatemind\v3");       Icon = "shell32.dll,239" },
    @{ Name = "SmartNoteBook V3";   Target = (Join-Path $repo "smartnotebook\v3");  Icon = "shell32.dll,234" }
)

$wsh = New-Object -ComObject WScript.Shell

# ---------- HYDRA V3 master folder shortcut ----------
Write-Title "1) Creating master folder shortcut"
$hydraLnk = Join-Path $desktop "HYDRA V3.lnk"
if (Test-Path $hydraLnk) { Remove-Item $hydraLnk -Force }
$lnk = $wsh.CreateShortcut($hydraLnk)
$lnk.TargetPath       = $repo
$lnk.WorkingDirectory = $repo
$lnk.IconLocation     = "imageres.dll,109"   # green folder icon
$lnk.Description      = "HYDRA V3 — Full integrated project (5 brains + engine + LLM)"
$lnk.Save()
Write-OK "HYDRA V3 -> $repo"

# ---------- 5 brain folder shortcuts ----------
Write-Title "2) Creating 5 brain folder shortcuts"
foreach ($b in $brains) {
    $name   = $b.Name
    $target = $b.Target
    $icon   = $b.Icon

    if (-not (Test-Path $target)) {
        Write-Err "$name target missing: $target"
        continue
    }

    $lnkPath = Join-Path $desktop "$name.lnk"
    if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }

    $lnk = $wsh.CreateShortcut($lnkPath)
    $lnk.TargetPath       = $target
    $lnk.WorkingDirectory = $target
    $lnk.IconLocation     = $icon
    $lnk.Description      = "$name brain source code (read-only view)"
    $lnk.Save()
    Write-OK "$name -> $target"
}

# ---------- HYDRA V3 - Run launcher ----------
Write-Title "3) Creating run launcher"

# 3a) Drop a fresh HYDRA_V3.bat into the repo
$batBody = @"
@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title HYDRA V3 - Running
color 0A

set "INSTALL_DIR=$repo"

if not exist "%INSTALL_DIR%\main_v3.py" (
    echo [X] HYDRA V3 not found at: %INSTALL_DIR%
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%\.venv\Scripts\python.exe" (
    echo [X] Python venv not found.
    echo     Run setup again to recreate it.
    pause
    exit /b 1
)

echo  ============================================================
echo            HYDRA V3 - 5-Brain Trading System
echo  ============================================================
echo.
echo   Project: %INSTALL_DIR%
echo   Stop:    press Ctrl+C
echo  ------------------------------------------------------------
echo.

cd /d "%INSTALL_DIR%"

REM Load .env into environment
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "K=%%a"
        if not "!K!"=="" if not "!K:~0,1!"=="#" (
            set "%%a=%%b"
        )
    )
)

set "PYTHONPATH=%INSTALL_DIR%"
".venv\Scripts\python.exe" main_v3.py

echo.
echo  ============================================================
echo   HYDRA V3 stopped.
echo  ============================================================
pause
endlocal
"@
$batPath = Join-Path $repo "HYDRA_V3.bat"
$batBody | Out-File -FilePath $batPath -Encoding ASCII -Force
Write-OK "Launcher script: $batPath"

# 3b) Desktop shortcut to the .bat
$runLnk = Join-Path $desktop "HYDRA V3 - Run.lnk"
if (Test-Path $runLnk) { Remove-Item $runLnk -Force }
$lnk = $wsh.CreateShortcut($runLnk)
$lnk.TargetPath       = $batPath
$lnk.WorkingDirectory = $repo
$lnk.IconLocation     = "imageres.dll,76"  # play-button-ish
$lnk.Description      = "Run HYDRA V3 (main_v3.py)"
$lnk.Save()
Write-OK "Run shortcut: $runLnk"

# ---------- Summary ----------
Write-Title "Done — Desktop layout"
Write-Host ""
Write-Host "  Now on your Desktop you have:" -ForegroundColor Cyan
Write-Host "    HYDRA V3            (folder shortcut)"
Write-Host "    ChartMind V3        (brain #1)"
Write-Host "    MarketMind V3       (brain #2)"
Write-Host "    NewsMind V3         (brain #3)"
Write-Host "    GateMind V3         (brain #4)"
Write-Host "    SmartNoteBook V3    (brain #5)"
Write-Host "    HYDRA V3 - Run      (double-click to launch)"
Write-Host ""
Write-Host "  Single source of truth: $repo" -ForegroundColor Gray
Write-Host "  Any edit you make in HYDRA V3 reflects immediately everywhere." -ForegroundColor Gray
Write-Host ""
pause
