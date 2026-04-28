# Install_to_Desktop.ps1
# يثبّت اختصار HYDRA V3 على سطح المكتب
# الاستخدام: من PowerShell الصق:
#   irm "$PWD\Install_to_Desktop.ps1" | iex
# أو: انسخ هذا الملف إلى مجلد المشروع، ثم نقر يمين → Run with PowerShell

$ErrorActionPreference = "Stop"

$installDir = Join-Path $env:USERPROFILE "Documents\hydra-v3"
$batPath    = Join-Path $installDir "HYDRA_V3.bat"
$desktop    = [Environment]::GetFolderPath("Desktop")
$shortcut   = Join-Path $desktop "HYDRA V3.lnk"

# Make sure HYDRA_V3.bat exists in the project folder
$batSourceCandidate = $batPath
if (-not (Test-Path $batSourceCandidate)) {
    # Look next to this script
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $localBat  = Join-Path $scriptDir "HYDRA_V3.bat"
    if (Test-Path $localBat) {
        Write-Host "Copying HYDRA_V3.bat into project folder..."
        Copy-Item -Path $localBat -Destination $batPath -Force
    } else {
        Write-Host "[X] HYDRA_V3.bat not found in either:"
        Write-Host "      $batPath"
        Write-Host "      $localBat"
        Write-Host ""
        Write-Host "Place HYDRA_V3.bat next to this script and re-run."
        pause
        exit 1
    }
}

Write-Host "Creating desktop shortcut..."
$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($shortcut)
$lnk.TargetPath       = $batPath
$lnk.WorkingDirectory = $installDir
$lnk.IconLocation     = "$env:SystemRoot\System32\imageres.dll,109"  # green play-style icon
$lnk.Description      = "HYDRA V3 — 5-Brain Trading System"
$lnk.WindowStyle      = 1
$lnk.Save()

Write-Host ""
Write-Host "[OK] Shortcut placed at:"
Write-Host "     $shortcut"
Write-Host ""
Write-Host "Now you can double-click 'HYDRA V3' on your desktop to launch the system."
Write-Host ""
pause
