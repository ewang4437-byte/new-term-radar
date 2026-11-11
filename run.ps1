# new-term-radar launcher (Windows PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File run.ps1 [daily|sources]
param([string]$Cmd = "daily")
Set-Location $PSScriptRoot

if (-not (Test-Path .env)) {
    Write-Host "Missing .env - create it with:  Set-Content .env 'AISA_API_KEY=your-key'"
    exit 1
}

# Load KEY=VALUE lines from .env into this process (values are not printed)
foreach ($line in Get-Content .env) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
    }
}

$env:PYTHONUTF8 = "1"
$date = Get-Date -Format yyyy-MM-dd

if ($Cmd -eq "daily") {
    python -m radar daily --skip newsites --out "report-$date.md"
} else {
    python -m radar $Cmd --out "$Cmd-$date.md"
}
