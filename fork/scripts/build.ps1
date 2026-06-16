<#
  End-to-end fork build (Windows). Produces a rebranded, aircode-bundled
  VS Code under build/vscode/../VSCode-win32-x64.

  Prerequisites (this machine, NOT auto-installed):
    - Node 18+ and npm
    - Python 3 (node-gyp)
    - Visual Studio Build Tools (C++ workload) — vscode native modules
    - Rust + protoc (PROTOC env) to build the aircore daemon

  Run from repo root:  pwsh fork/scripts/build.ps1
#>
$ErrorActionPreference = "Stop"
$forkDir = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content "$forkDir/config/fork.config.json" | ConvertFrom-Json
$cloneDir = Join-Path $forkDir $cfg.cloneDir

Write-Host "==> 1/5 clone VS Code @ $($cfg.pinnedTag)"
node "$forkDir/scripts/clone.mjs"

Write-Host "==> 2/5 build aircore daemon (release)"
if (-not $env:PROTOC) { Write-Warning "PROTOC not set; LanceDB build may fail. See editor-core/README.md" }
Push-Location (Join-Path $forkDir $cfg.daemonCrateDir)
cargo build --release
Pop-Location

Write-Host "==> 3/5 compile aircode extension"
Push-Location (Join-Path $forkDir $cfg.extensionDir)
npm ci
npm run compile
Pop-Location

Write-Host "==> 4/5 rebrand + bundle"
node "$forkDir/scripts/rebrand.mjs" --product "$cloneDir/product.json"
node "$forkDir/scripts/bundle.mjs"

Write-Host "==> 5/5 build VS Code (gulp)"
Push-Location $cloneDir
npm ci
# Minified app build; output goes to ..\VSCode-win32-x64
npm run gulp -- vscode-win32-x64-min
# Optional installer (Inno Setup): npm run gulp -- vscode-win32-x64-system-setup
Pop-Location

Write-Host "DONE. App at: $(Join-Path (Split-Path $cloneDir) 'VSCode-win32-x64')"
Write-Host "Next: sign with fork/scripts/sign-win.ps1"
