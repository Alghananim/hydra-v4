# HYDRA_AUTO_RUN_HELPER.ps1
# Local-only orchestration. NEVER sends anything outside the machine.
# All file reads, parses, and key handling happen in this PowerShell process
# on the user's laptop. Claude (the chat side) never sees the file content.

$ErrorActionPreference = "Stop"

function Write-Step($n, $total, $msg) {
    Write-Host ""
    Write-Host "  [$n/$total] $msg" -ForegroundColor Cyan
}

function Write-OK($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "    [X]  $msg" -ForegroundColor Red }
function Write-Warn($msg) { Write-Host "    [!]  $msg" -ForegroundColor Yellow }

$proj    = Join-Path $env:USERPROFILE "Desktop\HYDRA V4"
$secrets = Join-Path $proj "secrets"
$envFile = Join-Path $secrets ".env"
$desktop = [Environment]::GetFolderPath('Desktop')

# ---------- Step 1: locate project ----------
Write-Step 1 7 "Locating HYDRA V4..."
if (-not (Test-Path $proj)) {
    Write-Err "Project folder not found at: $proj"
    Read-Host "Press Enter to exit"; exit 1
}
Write-OK "Found at $proj"

# ---------- Step 2: AUTO-DETECT keys file ----------
Write-Step 2 7 "Searching for keys file automatically..."

# Search the spots the user mentioned + common fallbacks
$searchPatterns = @(
    "$desktop\API_KEYS\ALL KEYS AND TOKENS*",
    "$desktop\API_KEYS\*.txt",
    "$desktop\API_KEYS\*",
    "$desktop\ALL KEYS AND TOKENS*",
    "$desktop\API_KEYS.txt",
    "$desktop\api_keys.txt",
    "$desktop\keys.txt",
    "$desktop\*KEYS*.txt"
)

$keysFile = $null
foreach ($pat in $searchPatterns) {
    $hit = Get-ChildItem -Path $pat -ErrorAction SilentlyContinue | Where-Object {
        -not $_.PSIsContainer
    } | Select-Object -First 1
    if ($hit) { $keysFile = $hit.FullName; break }
}

if (-not $keysFile) {
    Write-Warn "Keys file not auto-detected. Opening file picker..."
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.InitialDirectory = $desktop
    $dialog.Filter = "All key files (*.txt;*.env;*.key;*.cfg)|*.txt;*.env;*.key;*.cfg|Any file (*.*)|*.*"
    $dialog.Title  = "HYDRA V4 - Pick your keys file (LOCAL ONLY)"
    if ($dialog.ShowDialog() -ne 'OK') {
        Write-Err "No file selected. Aborting."
        Read-Host "Press Enter to exit"; exit 1
    }
    $keysFile = $dialog.FileName
}

# Display only the file path, never its content
Write-OK "Using keys file: $keysFile"

# ---------- Step 3: read + parse LOCALLY ----------
Write-Step 3 7 "Reading + parsing keys file LOCALLY (nothing sent anywhere)..."
$content = Get-Content -Raw -Path $keysFile

$anthropicKey = $null
$oandaToken   = $null
$oandaAccount = $null
$oandaEnv     = "live"

# Anthropic key: starts with sk-ant-
if ($content -match 'sk-ant-[A-Za-z0-9_\-]{20,}') {
    $anthropicKey = $matches[0]
}

# OANDA account id pattern: 3-3-8-3 digits
if ($content -match '\d{3}-\d{3}-\d{8}-\d{3}') {
    $oandaAccount = $matches[0]
}

# Try various labels for OANDA token
$tokenLabels = @(
    'OANDA[_\s]*API[_\s]*TOKEN', 'OANDA[_\s]*TOKEN',
    'OANDA[_\s]*BEARER', 'OANDA[_\s]*KEY',
    'API[_\s]*TOKEN', 'BEARER[_\s]*TOKEN',
    'TOKEN', 'BEARER'
)
foreach ($lbl in $tokenLabels) {
    $pattern = "(?im)$lbl\s*[:=]\s*([A-Za-z0-9\-]{30,})"
    if ($content -match $pattern) {
        if ($matches[1] -ne $anthropicKey) {
            $oandaToken = $matches[1]
            break
        }
    }
}

# Fallback: hex-shaped 40-80 char token
if (-not $oandaToken) {
    $hexMatches = [regex]::Matches($content, '\b[a-f0-9\-]{40,90}\b')
    foreach ($m in $hexMatches) {
        if ($m.Value -ne $anthropicKey -and $m.Value -notmatch '^\d{3}-\d{3}-\d{8}-\d{3}$') {
            $oandaToken = $m.Value
            break
        }
    }
}

# Look for env hint
if ($content -match '(?im)OANDA[_\s]*ENV\s*[:=]\s*(practice|live|demo)') {
    $oandaEnv = $matches[1].ToLower()
}

Write-Host ""
Write-Host "    Detected (only last 4 chars shown for verification):"
function Mask-Tail($s) {
    if (-not $s) { return $null }
    if ($s.Length -le 4) { return "****" }
    return ("..." + $s.Substring($s.Length - 4))
}
if ($anthropicKey) { Write-OK ("ANTHROPIC_API_KEY = sk-ant-" + (Mask-Tail $anthropicKey)) } else { Write-Warn "ANTHROPIC_API_KEY = NOT FOUND" }
if ($oandaToken)   { Write-OK ("OANDA_API_TOKEN   = "       + (Mask-Tail $oandaToken))   } else { Write-Warn "OANDA_API_TOKEN  = NOT FOUND" }
if ($oandaAccount) { Write-OK ("OANDA_ACCOUNT_ID  = $oandaAccount") }                       else { Write-Warn "OANDA_ACCOUNT_ID = NOT FOUND" }
Write-OK ("OANDA_ENV         = $oandaEnv")

if (-not $anthropicKey -or -not $oandaToken -or -not $oandaAccount) {
    Write-Host ""
    Write-Err "One or more keys could not be auto-detected from your file."
    Write-Host "    Opening Notepad on the keys file AND on a fresh .env template."
    Write-Host "    Copy each value across, save .env, close Notepad."
    Write-Host ""

    if (-not (Test-Path $secrets)) { New-Item -ItemType Directory -Path $secrets -Force | Out-Null }
    if (-not (Test-Path $envFile)) {
@"
# HYDRA V4 - Local secrets (gitignored)
ANTHROPIC_API_KEY=sk-ant-REPLACE_ME
OANDA_API_TOKEN=REPLACE_ME
OANDA_ACCOUNT_ID=001-001-XXXXXXXX-001
OANDA_ENV=$oandaEnv
"@ | Set-Content -Path $envFile -Encoding UTF8
    }
    Read-Host "Press Enter to open Notepad on both files"
    Start-Process notepad -ArgumentList "`"$keysFile`""
    Start-Process notepad -ArgumentList "`"$envFile`"" -Wait
    Write-OK "Notepad closed. Continuing with whatever you saved."
}
else {
    # ---------- Step 4: write .env LOCALLY ----------
    Write-Step 4 7 "Writing secrets\.env locally..."
    if (-not (Test-Path $secrets)) { New-Item -ItemType Directory -Path $secrets -Force | Out-Null }

@"
# HYDRA V4 - Local secrets (gitignored)
# Auto-generated by HYDRA_AUTO_RUN. Source file: $keysFile
ANTHROPIC_API_KEY=$anthropicKey
OANDA_API_TOKEN=$oandaToken
OANDA_ACCOUNT_ID=$oandaAccount
OANDA_ENV=$oandaEnv
"@ | Set-Content -Path $envFile -Encoding UTF8

    Write-OK "Wrote $envFile"

    # Make sure .gitignore protects it
    $gitignore = Join-Path $proj ".gitignore"
    $needAdd = $true
    if (Test-Path $gitignore) {
        $gi = Get-Content $gitignore -Raw
        if ($gi -match 'secrets/.env') { $needAdd = $false }
    }
    if ($needAdd) {
        Add-Content -Path $gitignore -Value "`nsecrets/.env`nreplay_results/`ndata_cache/`n"
        Write-OK ".gitignore updated"
    } else {
        Write-OK ".gitignore already protects secrets/"
    }
}

# ---------- Step 5: confirm Python ----------
Write-Step 5 7 "Verifying Python..."
$pythonOk = $false
try {
    $pyver = & python --version 2>&1
    if ($LASTEXITCODE -eq 0) { Write-OK "$pyver"; $pythonOk = $true }
} catch { }
if (-not $pythonOk) {
    Write-Err "Python not found in PATH. Install from python.org and re-run."
    Read-Host "Press Enter to exit"; exit 1
}

# ---------- Step 6: run replay ----------
Write-Step 6 7 "Running HYDRA V4 two-year replay..."
Write-Host "    This may take 30-60 minutes on first run (downloads + replay)."
Write-Host ""
Write-Host "  ------------------------------------------------------------" -ForegroundColor DarkGray

$runBat = Join-Path $env:USERPROFILE "Desktop\Run_Two_Year_Replay.bat"
if (Test-Path $runBat) {
    & $runBat
    $rc = $LASTEXITCODE
} else {
    Write-Warn "Run_Two_Year_Replay.bat not found. Falling back to direct Python."
    Push-Location $proj
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
        }
    }
    & python "run_live_replay.py"
    $rc = $LASTEXITCODE
    Pop-Location
}
Write-Host "  ------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# ---------- Step 7: open report ----------
Write-Step 7 7 "Opening final report..."
$report = Join-Path $proj "replay_results\REAL_DATA_REPLAY_REPORT.md"
if (Test-Path $report) {
    Write-OK "Report at: $report"
    Start-Process notepad -ArgumentList "`"$report`""
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "            REPLAY COMPLETE" -ForegroundColor Green
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Send Claude ONLY the report content. NEVER the secrets file."
} else {
    Write-Err "Report not found at: $report"
    if ($rc -ne 0) {
        Write-Host "    Replay exit code: $rc"
        Write-Host "    Send Claude the console output above (NO secrets in it - safe)."
    }
}

Write-Host ""
Read-Host "Press Enter to close"
