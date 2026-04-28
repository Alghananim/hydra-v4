# Apply_All_Cleanup.ps1
# يطبّق كل تنظيف HYDRA V3 على الـ repo المحلي:
#   ١) أرشفة V1/V2 إلى archive/
#   ٢) نقل YAML configs إلى config/news/
#   ٣) إعادة تسمية NewsMind V2 → V3
#   ٤) حذف ملفات Hostinger/Docker
#   ٥) إزالة /app hardcoding من main_v3.py
#   ٦) README جديد للابتوب فقط (لا VPS)
#
# الاستخدام: نقر يمين على هذا الملف ← Run with PowerShell

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Write-Title { param($T); Write-Host ""; Write-Host ("=" * 70) -ForegroundColor Cyan; Write-Host "  $T" -ForegroundColor Cyan; Write-Host ("=" * 70) -ForegroundColor Cyan }
function Write-Step  { param($T); Write-Host "[*] $T" -ForegroundColor Yellow }
function Write-OK    { param($T); Write-Host "[OK] $T" -ForegroundColor Green }
function Write-Warn2 { param($T); Write-Host "[!] $T" -ForegroundColor DarkYellow }
function Write-Err   { param($T); Write-Host "[X] $T" -ForegroundColor Red }

Write-Title "HYDRA V3 — Full Cleanup (V1/V2 archive + V3 rename + drop Docker)"

$repo = Join-Path $env:USERPROFILE "Documents\hydra-v3"
if (-not (Test-Path (Join-Path $repo ".git"))) {
    Write-Err "Repo not found at: $repo"
    pause; exit 1
}
Set-Location $repo
Write-OK "Repo: $repo"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$patch     = Join-Path $scriptDir "hydra_v3_full_cleanup.patch"
if (-not (Test-Path $patch)) {
    Write-Err "Patch file not found: $patch"
    Write-Host "  hydra_v3_full_cleanup.patch must sit next to this script."
    pause; exit 1
}
Write-OK "Patch: $patch"

# Backup branch
$backup = "backup/before-hydra-cleanup-$(Get-Date -Format yyyyMMdd-HHmmss)"
Write-Step "Creating backup branch: $backup"
git branch $backup 2>&1 | Out-Null
Write-OK "Rollback any time:  git reset --hard $backup"

# Stash dirty state
if (git status --porcelain) {
    Write-Step "Stashing local changes..."
    git stash push -u -m "Auto-stash before HYDRA V3 cleanup" 2>&1 | Out-Null
}

# Make sure git is case-sensitive aware
git config core.ignorecase false 2>&1 | Out-Null

# Apply
Write-Title "Applying patch (2 commits)"
$out = git am --3way --keep-cr $patch 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "git am failed:"
    Write-Host $out
    Write-Warn2 "Aborting and rolling back..."
    git am --abort 2>&1 | Out-Null
    Write-Host "Run:  git reset --hard $backup"
    pause; exit 1
}
Write-OK "Patch applied successfully (2 commits added)"

# Verify expected layout
Write-Title "Verifying new structure"
$paths = @(
    "chartmind\v3\ChartMindV3.py",
    "marketmind\v3\MarketMindV3.py",
    "newsmind\v3\NewsMindV3.py",
    "gatemind\v3\GateMindV3.py",
    "smartnotebook\v3\SmartNoteBookV3.py",
    "engine\v3\EngineV3.py",
    "llm\openai_brain.py",
    "config\news\events.yaml",
    "main_v3.py",
    "archive\README.md"
)
$absent = @()
foreach ($p in $paths) {
    if (Test-Path $p) { Write-Host "  [OK] $p" -ForegroundColor Green }
    else { Write-Host "  [X]  $p" -ForegroundColor Red; $absent += $p }
}
$gone = @("Dockerfile", "docker-compose.yml", "hostinger-deploy.yml", "newsmind\v2", "Engine.py", "main.py")
foreach ($p in $gone) {
    if (Test-Path $p) { Write-Host "  [!]  $p still exists (should be gone)" -ForegroundColor DarkYellow }
    else { Write-Host "  [OK] $p removed" -ForegroundColor Green }
}

# Smoke test imports
Write-Title "Smoke test: importing all 5 brains"
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $py = @"
import sys
sys.path.insert(0, '.')
mods = [
    ('chartmind.v3',     ['ChartMindV3', 'Bar']),
    ('marketmind.v3',    ['MarketMindV3']),
    ('newsmind.v3',      ['NewsMindV3', 'NewsItem']),
    ('gatemind.v3',      ['GateMindV3']),
    ('smartnotebook.v3', ['SmartNoteBookV3']),
    ('engine.v3',        ['EngineV3']),
    ('llm',              ['review_brain_outputs']),
]
for m, names in mods:
    try:
        mod = __import__(m, fromlist=names)
        for n in names: getattr(mod, n)
        print('  [OK] ' + m + ' :: ' + ', '.join(names))
    except Exception as e:
        print('  [X]  ' + m + ' :: ' + str(e)[:120])
"@
    & $venvPython -c $py
} else {
    Write-Warn2 "venv missing — skipping import test"
}

Write-Title "Done"
Write-OK "Cleanup applied."
Write-Host ""
Write-Host "  To publish to GitHub:    git push origin HEAD" -ForegroundColor Gray
Write-Host "  To rollback any time:    git reset --hard $backup" -ForegroundColor Gray
Write-Host ""
Write-Host "  Next step: run Setup_Desktop_Layout.ps1 to put 6 folders on your Desktop." -ForegroundColor Cyan
Write-Host ""
pause
