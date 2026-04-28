# HYDRA_DIAGNOSE.ps1 (simplified, PS 5.1 compatible)
# Verbose diagnostic that logs every step status WITHOUT logging any secret.

$ErrorActionPreference = "Continue"
$proj    = Join-Path $env:USERPROFILE "Desktop\HYDRA V4"
$secrets = Join-Path $proj "secrets"
$envFile = Join-Path $secrets ".env"
$desktop = [Environment]::GetFolderPath('Desktop')
$keysExpected = Join-Path $desktop "API_KEYS\ALL KEYS AND TOKENS.txt"

function Log {
    param([string]$Status, [string]$Msg)
    Write-Host ("[{0,-5}] {1}" -f $Status, $Msg)
}

Log "INFO" "=========================================="
Log "INFO" "HYDRA V4 Diagnostic - local-only, no secrets logged"
Log "INFO" "=========================================="
Log "INFO" ("PowerShell version: " + $PSVersionTable.PSVersion)
Log "INFO" ("User: " + $env:USERNAME)
Log "INFO" ("Desktop: " + $desktop)

# Step 1: HYDRA V4 folder
if (Test-Path $proj) {
    Log "OK" ("HYDRA V4 project folder found at: " + $proj)
} else {
    Log "FAIL" ("HYDRA V4 NOT found at: " + $proj)
    Log "INFO" "Cannot continue without HYDRA V4 folder."
    exit 1
}

# Step 2: keys file
if (Test-Path $keysExpected) {
    Log "OK" ("Keys file found at: " + $keysExpected)
} else {
    Log "WARN" ("Expected keys file NOT at: " + $keysExpected)
    $apidir = Join-Path $desktop "API_KEYS"
    if (Test-Path $apidir) {
        Log "INFO" ("Files actually in " + $apidir + ":")
        Get-ChildItem -Path $apidir -ErrorAction SilentlyContinue | Select-Object -First 10 | ForEach-Object {
            Log "INFO" ("  - " + $_.Name)
        }
    } else {
        Log "WARN" ("Folder API_KEYS not found on Desktop")
    }
}

# Step 3: read keys file (locally, count chars only — never log content)
if (Test-Path $keysExpected) {
    try {
        $content = Get-Content -Raw -Path $keysExpected -ErrorAction Stop
        Log "OK" ("Keys file read: " + $content.Length + " chars (content NOT logged)")

        # Detect patterns
        $hasAnthropic   = $content -match 'sk-ant-[A-Za-z0-9_\-]{20,}'
        $hasAcct        = $content -match '\d{3}-\d{3}-\d{8}-\d{3}'
        $hasLongHex     = $content -match '\b[a-f0-9\-]{40,90}\b'
        $hasLabelToken  = $content -match '(?im)(OANDA[_\s]*API[_\s]*TOKEN|TOKEN|BEARER)\s*[:=]'

        $statusA = "FAIL"; if ($hasAnthropic)  { $statusA = "OK" }
        $statusB = "FAIL"; if ($hasAcct)       { $statusB = "OK" }
        $statusC = "WARN"; if ($hasLongHex)    { $statusC = "OK" }
        $statusD = "WARN"; if ($hasLabelToken) { $statusD = "OK" }

        Log $statusA ("Anthropic key pattern (sk-ant-*) detected: " + $hasAnthropic)
        Log $statusB ("OANDA account pattern (NNN-NNN-NNNNNNNN-NNN): " + $hasAcct)
        Log $statusC ("Long hex token (40-90 chars): " + $hasLongHex)
        Log $statusD ("Token label keyword found: " + $hasLabelToken)
    } catch {
        Log "FAIL" ("Could not read keys file: " + $_.Exception.Message)
    }
}

# Step 4: Python
$pythonOk = $false
try {
    $pyver = & python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log "OK" ("Python: " + $pyver)
        $pythonOk = $true
    } else {
        Log "FAIL" "Python version command failed"
    }
} catch {
    Log "FAIL" ("Python not in PATH: " + $_.Exception.Message)
}

# Step 5: HYDRA V4 critical files
$critFiles = @(
    "live_data\live_order_guard.py",
    "live_data\oanda_readonly_client.py",
    "live_data\data_loader.py",
    "anthropic_bridge\bridge.py",
    "replay\two_year_replay.py",
    "run_live_replay.py",
    "orchestrator\v4\HydraOrchestratorV4.py"
)

$missing = 0
foreach ($f in $critFiles) {
    $p = Join-Path $proj $f
    if (Test-Path $p) {
        Log "OK" ("Found: " + $f)
    } else {
        Log "FAIL" ("Missing: " + $f)
        $missing++
    }
}
Log "INFO" ("Critical files: " + ($critFiles.Count - $missing) + "/" + $critFiles.Count + " present")

# Step 6: secrets folder + .env state
if (Test-Path $secrets) {
    Log "OK" "secrets/ folder exists"
} else {
    Log "WARN" "secrets/ folder missing"
}

if (Test-Path $envFile) {
    Log "OK" (".env file exists at " + $envFile)
} else {
    Log "WARN" ".env file NOT yet created"
}

# Step 7: HYDRA scripts on Desktop
$scripts = @("HYDRA_AUTO_RUN.bat", "HYDRA_AUTO_RUN_HELPER.ps1", "Run_Two_Year_Replay.bat", "Setup_Secrets.bat")
foreach ($s in $scripts) {
    $p = Join-Path $desktop $s
    if (Test-Path $p) {
        Log "OK" ("Script exists on Desktop: " + $s)
    } else {
        Log "WARN" ("Script missing on Desktop: " + $s)
    }
}

Log "INFO" "=========================================="
Log "INFO" "Diagnostic complete. NO secrets were logged."
Log "INFO" "Send the entire log content to Claude."
Log "INFO" "=========================================="

exit 0
