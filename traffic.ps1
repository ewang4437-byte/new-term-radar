# Usage: powershell -ExecutionPolicy Bypass -File traffic.ps1 [domain ...]
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
python scripts\traffic.py @args
