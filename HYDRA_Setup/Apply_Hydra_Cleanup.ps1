# Apply_Hydra_Cleanup.ps1
# يطبّق تنظيف HYDRA V3 على الـ repo المحلي:
#   - أرشفة المجلدات القديمة (ChartMind, MarketMind, ...) إلى archive/
#   - نقل YAML configs إلى config/news/
#   - تحديث Dockerfile ليشغّل main_v3.py
#   - إضافة main_v3.py shim في الجذر
#
# الاستخدام: نقر يمين على هذا الملف ← Run with PowerShell

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Write-Title {
    param($Text)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

function Write-Step    { param($Text); Write-Host "[*] $Text" -ForegroundColor Yellow }
function Write-OK      { param($Text); Write-Host "[OK] $Text" -ForegroundColor Green }
function Write-WarnMsg { param($Text); Write-Host "[!] $Text" -ForegroundColor DarkYellow }
function Write-Err     { param($Text); Write-Host "[X] $Text" -ForegroundColor Red }

Write-Title "HYDRA V3 — Cleanup script"

# ---------- Locate repo ----------
$repo = Join-Path $env:USERPROFILE "Documents\hydra-v3"
if (-not (Test-Path (Join-Path $repo ".git"))) {
    Write-Err "Repo not found at: $repo"
    Write-Host "  Run setup_hydra_v3.bat first or clone the repo to that location."
    pause
    exit 1
}
Set-Location $repo
Write-OK "Repo: $repo"

# ---------- Locate patch file ----------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$patch     = Join-Path $scriptDir "hydra_v3_cleanup.patch"
if (-not (Test-Path $patch)) {
    Write-Err "Patch file not found: $patch"
    Write-Host "  hydra_v3_cleanup.patch must sit next to this script."
    pause
    exit 1
}
Write-OK "Patch: $patch"

# ---------- Show current state ----------
Write-Title "1) Current repo state (before)"
git status --short | Select-Object -First 15
Write-Host ""

# ---------- Backup branch ----------
$backupBranch = "backup/before-hydra-cleanup-$(Get-Date -Format yyyyMMdd-HHmmss)"
Write-Step "Creating backup branch: $backupBranch"
git branch $backupBranch 2>&1 | Out-Null
Write-OK  "Backup branch created (you can roll back any time with: git reset --hard $backupBranch)"

# ---------- Stash any local changes ----------
$dirty = git status --porcelain
if ($dirty) {
    Write-Step "Stashing your local uncommitted changes..."
    git stash push -u -m "Auto-stash before HYDRA cleanup" 2>&1 | Out-Null
    Write-OK "Stashed (restore later with: git stash pop)"
}

# ---------- Make sure case-sensitivity awareness is on ----------
git config core.ignorecase false 2>&1 | Out-Null

# ---------- Apply the patch ----------
Write-Title "2) Applying cleanup patch"
Write-Step "Running: git am --3way --keep-cr ..."

$amResult = git am --3way --keep-cr $patch 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "git am failed. Output:"
    Write-Host $amResult
    Write-Host ""
    Write-WarnMsg "Aborting and rolling back..."
    git am --abort 2>&1 | Out-Null
    Write-Host "Try:  git reset --hard $backupBranch"
    pause
    exit 1
}
Write-OK "Patch applied cleanly"

# ---------- Verify ----------
Write-Title "3) Verifying new structure"
$expected = @(
    "chartmind\v3\ChartMindV3.py",
    "marketmind\v3\MarketMindV3.py",
    "newsmind\v2\NewsMindV2.py",
    "gatemind\v3\GateMindV3.py",
    "smartnotebook\v3\SmartNoteBookV3.py",
    "engine\v3\EngineV3.py",
    "llm\openai_brain.py",
    "config\news\events.yaml",
    "config\news\sources.yaml",
    "main_v3.py",
    "archive\README.md"
)
$missing = @()
foreach ($p in $expected) {
    if (Test-Path $p) {
        Write-Host "  [OK] $p" -ForegroundColor Green
    } else {
        Write-Host "  [X]  $p" -ForegroundColor Red
        $missing += $p
    }
}

if ($missing.Count -gt 0) {
    Write-WarnMsg "Some expected paths are missing. The patch applied but the working tree may be incomplete."
    Write-Host    "  This usually means your Windows clone had case-collision drops at clone time."
    Write-Host    "  Recommended next step: re-clone after the cleanup is pushed to GitHub."
}

# ---------- Quick import smoke test ----------
Write-Title "4) Smoke test: importing all 5 brains"
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-WarnMsg "venv not found at $venvPython — skipping import test."
} else {
    $py = @"
import sys
sys.path.insert(0, '.')
mods = ['chartmind.v3', 'marketmind.v3', 'newsmind.v2',
        'gatemind.v3', 'smartnotebook.v3', 'engine.v3', 'llm']
for m in mods:
    try:
        __import__(m)
        print('[OK] ' + m)
    except Exception as e:
        print('[X]  ' + m + ' :: ' + str(e)[:120])
"@
    & $venvPython -c $py
}

# ---------- Done ----------
Write-Title "5) Done"
Write-OK "Cleanup applied locally."
Write-Host ""
Write-Host "  Safety net (rollback if something feels wrong):"
Write-Host "    cd `"$repo`""
Write-Host "    git reset --hard $backupBranch"
Write-Host ""
Write-Host "  To publish the cleanup to GitHub (your origin):"
Write-Host "    cd `"$repo`""
Write-Host "    git push origin HEAD"
Write-Host ""
Write-Host "  After pushing, your repo on GitHub will mirror this clean structure"
Write-Host "  and any future Hostinger rebuild picks up main_v3.py automatically."
Write-Host ""
pause
