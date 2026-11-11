# Once-per-day wrapper for the scheduled task.
# Runs run.ps1 only if it is past $StartHour and today's run has not succeeded yet.
param([int]$StartHour = 9)
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force logs, state | Out-Null

$today = Get-Date -Format yyyy-MM-dd
$doneFile = "state\last_success.txt"
$lockFile = "state\running.lock"

if ((Get-Date).Hour -lt $StartHour) { exit 0 }
if ((Test-Path $doneFile) -and ((Get-Content $doneFile -Raw).Trim() -eq $today)) { exit 0 }

# Skip if another run is in progress (stale lock older than 2h is ignored)
if ((Test-Path $lockFile) -and ((Get-Item $lockFile).LastWriteTime -gt (Get-Date).AddHours(-2))) { exit 0 }
Set-Content $lockFile $PID

# Wait up to 5 minutes for the network after boot
for ($i = 0; $i -lt 30; $i++) {
    try { [System.Net.Dns]::GetHostAddresses("api.github.com") | Out-Null; break } catch {}
    Start-Sleep -Seconds 10
}

$log = "logs\$today.log"
# Log in UTF-8: Windows PowerShell 5.1 writes UTF-16 with *>> and reads Python's UTF-8 output as the ANSI codepage
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
function Write-Log { process { Add-Content $log "$_" -Encoding UTF8 } }
try {
    & "$PSScriptRoot\run.ps1" *>&1 | Write-Log
    if ($LASTEXITCODE -eq 0) {
        Set-Content $doneFile $today
        "[$(Get-Date -Format s)] OK" | Write-Log
        & "$PSScriptRoot\run-vn.ps1" *>&1 | Write-Log
        "[$(Get-Date -Format s)] VN exit=$LASTEXITCODE" | Write-Log
        python scripts\vn_social.py *>&1 | Write-Log
        "[$(Get-Date -Format s)] VN social exit=$LASTEXITCODE" | Write-Log
        python scripts\balance.py *>&1 | Write-Log
        python scripts\to_obsidian.py *>&1 | Write-Log
        "[$(Get-Date -Format s)] Obsidian import exit=$LASTEXITCODE" | Write-Log
    } else {
        "[$(Get-Date -Format s)] FAILED exit=$LASTEXITCODE, will retry next hour" | Write-Log
    }
} finally {
    Remove-Item $lockFile -ErrorAction SilentlyContinue
}

# Notify: always a short "done" toast with balances; louder text if a balance is low
function Show-Toast([string]$title, [string]$text) {
    Add-Type -AssemblyName System.Windows.Forms
    $n = New-Object System.Windows.Forms.NotifyIcon
    $n.Icon = [System.Drawing.SystemIcons]::Information
    $n.Visible = $true
    $n.ShowBalloonTip(15000, $title, $text, [System.Windows.Forms.ToolTipIcon]::Info)
    Start-Sleep -Seconds 16
    $n.Dispose()
}
if ((Test-Path $doneFile) -and ((Get-Content $doneFile -Raw).Trim() -eq $today) -and (Test-Path "state\balance.json")) {
    $b = Get-Content "state\balance.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    $msg = "AIsa: $($b.aisa) USD   GoAnyAPI: $($b.goanyapi) USD"
    if (Test-Path "state\balance_alert.txt") {
        $msg = (Get-Content "state\balance_alert.txt" -Raw -Encoding UTF8)
        Show-Toast "Radar: API balance LOW" $msg
    } elseif (-not (Test-Path "state\notified.txt") -or ((Get-Content "state\notified.txt" -Raw).Trim() -ne $today)) {
        Show-Toast "Radar done $today" $msg
    }
    Set-Content "state\notified.txt" $today
}
