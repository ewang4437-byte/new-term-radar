# Vietnam edition: same new names, but sized and checked for Google Vietnam (vi).
# Uses its own state (state-vn) and skips X to avoid paying twice for the same posts.
Set-Location $PSScriptRoot
if (-not (Test-Path .env)) { Write-Host "Missing .env"; exit 1 }
foreach ($line in Get-Content .env) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
    }
}
$env:PYTHONUTF8 = "1"
$env:RADAR_LANGUAGE_CODE = "vi"
$env:RADAR_GL = "VN"
$env:RADAR_HL = "vi"
$env:RADAR_KEYWORD_HINT = "`nThe searchers are in Vietnam. Write each KEYWORD the way Vietnamese users type it into Google: in Vietnamese with diacritics (e.g. 'tao anh bang ai' written as 'tạo ảnh bằng ai', 'xóa phông ảnh', 'chuyển giọng nói thành văn bản'). Keep an English keyword only when Vietnamese users commonly search it in English (e.g. 'ai video generator')."
$date = Get-Date -Format yyyy-MM-dd
python -m radar daily --config config-vn.json --state state-vn --skip x,newsites --out "report-vn-$date.md"
