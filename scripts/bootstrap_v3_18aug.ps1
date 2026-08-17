param(
    [string]$Python = ".\venv\Scripts\python.exe",
    [switch]$Upload
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Python)) {
    throw "Python environment not found at $Python"
}

& $Python scripts\bootstrap_v3_official_data.py --date 2026-08-18
if ($LASTEXITCODE -ne 0) {
    Write-Host "V3 readiness is BLOCKED. Review output\v3_bootstrap_result.json. Nothing was uploaded."
    exit $LASTEXITCODE
}

Write-Host "V3 operational readiness PASSED."
if ($Upload) {
    git add market_data\index_history.csv corporate_data\normalized
    git add -f output\nse_corporate_health.json output\v3_operational_readiness.json output\v3_bootstrap_result.json
    git commit -m "Backfill official NSE data for V3 activation"
    git push
    if ($LASTEXITCODE -ne 0) { throw "Git push failed" }
    Write-Host "Normalized V3 data uploaded."
} else {
    Write-Host "Re-run with -Upload after reviewing the readiness report."
}
