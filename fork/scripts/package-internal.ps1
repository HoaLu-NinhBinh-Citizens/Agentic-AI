<#
  Package an already-built fork into an INTERNAL portable zip (no signing, no
  installer — teammates unzip and run). Run AFTER build.ps1 has produced
  fork/build/VSCode-win32-x64.

  Output: fork/dist/aircode-win32-x64-<version>-<date>-<sha>.zip (+ .sha256 + version.json)

  Usage: pwsh fork/scripts/package-internal.ps1
#>
$ErrorActionPreference = "Stop"
$forkDir = Split-Path -Parent $PSScriptRoot
$target = if ($env:TARGET) { $env:TARGET } else { "win32-x64" }
$appDir = Join-Path $forkDir "build/VSCode-$target"
$distDir = Join-Path $forkDir "dist"

if (-not (Test-Path $appDir)) {
  throw "Build output not found: $appDir. Run fork/scripts/build.ps1 first."
}

# Version stamp: upstream vscode version + UTC date + short fork commit.
$vscodeVer = (Get-Content (Join-Path $forkDir "build/vscode/package.json") | ConvertFrom-Json).version
$date = (Get-Date).ToUniversalTime().ToString("yyyyMMdd")
$sha = (git -C $forkDir rev-parse --short HEAD).Trim()
$stamp = "$vscodeVer-$date-$sha"
$name = "aircode-$target-$stamp"

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
$zip = Join-Path $distDir "$name.zip"
Write-Host "Zipping $appDir -> $zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$appDir/*" -DestinationPath $zip -CompressionLevel Optimal

# Provenance for internal traceability.
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$hash  $name.zip" | Set-Content (Join-Path $distDir "$name.zip.sha256")
@{
  channel   = "internal"
  app       = "aircode"
  target    = $target
  vscode    = $vscodeVer
  builtUtc  = (Get-Date).ToUniversalTime().ToString("o")
  forkCommit = $sha
  sha256    = $hash
} | ConvertTo-Json | Set-Content (Join-Path $distDir "$name.version.json")

Write-Host ""
Write-Host "Internal build ready:"
Write-Host "  $zip"
Write-Host "  sha256: $hash"
Write-Host ""
Write-Host "Teammates: unzip anywhere, run aircode.exe (Windows SmartScreen -> More info -> Run anyway, unsigned internal build)."
