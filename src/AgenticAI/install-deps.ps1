# Install npm dependencies for AgenticAI
$ErrorActionPreference = "Continue"

$projectPath = "C:\Users\thang\Desktop\Agentic-AI\src\AgenticAI"

Write-Host "Installing dependencies in $projectPath..."

# First, remove node_modules
$nodeModulesPath = Join-Path $projectPath "node_modules"
if (Test-Path $nodeModulesPath) {
    Write-Host "Removing existing node_modules..."
    Remove-Item -Path $nodeModulesPath -Recurse -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

# Now install
Push-Location $projectPath
try {
    npm install --legacy-peer-deps 2>&1
    Write-Host "npm install completed"
} catch {
    Write-Host "npm install error: $_"
}
Pop-Location

# Verify key packages
$openaiPath = Join-Path $projectPath "node_modules\openai"
$anthropicPath = Join-Path $projectPath "node_modules\@anthropic-ai\sdk"
$electronStorePath = Join-Path $projectPath "node_modules\electron-store"

Write-Host ""
Write-Host "Verification:"
Write-Host "  openai: $(Test-Path $openaiPath)"
Write-Host "  @anthropic-ai/sdk: $(Test-Path $anthropicPath)"
Write-Host "  electron-store: $(Test-Path $electronStorePath)"
