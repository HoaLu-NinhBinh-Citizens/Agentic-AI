# AI_SUPPORT - Start System (One Command)
# Usage: .\start_system.ps1

Write-Host ""
Write-Host "========================================================"
Write-Host "   AI_SUPPORT - Embedded Engineering Assistant"
Write-Host "========================================================"
Write-Host ""

# Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "ERROR: Python not found!" -ForegroundColor Red
    Write-Host "Install from: https://www.python.org/downloads/"
    pause
    exit 1
}

Write-Host "Python: $(python --version)" -ForegroundColor Green

# Check dependencies
$checkResult = python -c "import fastapi, uvicorn" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    python -m pip install fastapi uvicorn[standard] websockets pydantic aiohttp
}

# Set PYTHONPATH (handles both "from src.xxx" and "from core.xxx" imports)
$ProjectRoot = $PSScriptRoot
$SrcDir = Join-Path $ProjectRoot "src"
$env:PYTHONPATH = "$ProjectRoot;$SrcDir"

Write-Host ""
Write-Host "PYTHONPATH: $env:PYTHONPATH" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Starting server on http://localhost:8000 ..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Endpoints:" -ForegroundColor Yellow
Write-Host "  Health:     http://localhost:8000/health"
Write-Host "  AI Status:  http://localhost:8000/api/ai/config/status"
Write-Host "  AI Test:    http://localhost:8000/api/ai/test"
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""

# Start server
Set-Location $SrcDir
python -m uvicorn interfaces.server.main:app --host 0.0.0.0 --port 8000 --reload
Set-Location $ProjectRoot
