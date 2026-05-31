$ErrorActionPreference = "Continue"
$path = "c:\Users\thang\Desktop\Agentic-AI\src\AgenticAI\node_modules"

# Kill any processes using this folder
Get-Process | Where-Object { $_.Path -like "*AgenticAI*" } | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

# Try to rename
try {
    $newName = "node_modules_$(Get-Random)"
    Move-Item -Path $path -Destination $newName -Force -ErrorAction Stop
    Write-Host "Renamed to $newName"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    # Try alternative - just delete if we can
    $items = Get-ChildItem -Path $path -Force -ErrorAction SilentlyContinue
    Write-Host "Items in folder: $($items.Count)"
}
