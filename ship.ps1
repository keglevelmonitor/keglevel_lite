# ship.ps1
# Usage: .\ship.ps1
#
# Replaces the final step of your workflow:
#   git add .
#   git commit -m "your message"
#   .\ship.ps1          <-- bumps version, commits version.py, then pushes
#
# Run this from the repo root (same folder as this script).

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "Bumping version..." -ForegroundColor Cyan
python bump_version.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Version bump failed. Push aborted." -ForegroundColor Red
    exit 1
}

git add src/version.py
git commit -m "bump version"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Git commit failed. Push aborted." -ForegroundColor Red
    exit 1
}

git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Git push failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Done! Version bumped and pushed to origin/main." -ForegroundColor Green
