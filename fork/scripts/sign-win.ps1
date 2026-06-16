<#
  Authenticode-sign the Windows build. Requires a code-signing certificate
  (EV or OV). Nothing here is secret-bearing — supply the cert via env/params.

  Required (DO NOT hardcode):
    $env:WIN_CERT_PFX    path to the .pfx
    $env:WIN_CERT_PASS   pfx password
  Optional:
    $env:TIMESTAMP_URL   default http://timestamp.digicert.com

  Usage: pwsh fork/scripts/sign-win.ps1 -AppDir ..\VSCode-win32-x64
#>
param([Parameter(Mandatory = $true)][string]$AppDir)
$ErrorActionPreference = "Stop"

if (-not $env:WIN_CERT_PFX) { throw "Set WIN_CERT_PFX to your .pfx path" }
if (-not $env:WIN_CERT_PASS) { throw "Set WIN_CERT_PASS" }
$ts = if ($env:TIMESTAMP_URL) { $env:TIMESTAMP_URL } else { "http://timestamp.digicert.com" }

# signtool ships with the Windows SDK.
$targets = Get-ChildItem -Path $AppDir -Recurse -Include *.exe, *.dll
foreach ($f in $targets) {
  & signtool sign /f $env:WIN_CERT_PFX /p $env:WIN_CERT_PASS `
    /fd SHA256 /tr $ts /td SHA256 /d "aircode" $f.FullName
}
Write-Host "Signed $($targets.Count) binaries."
# For the Inno installer .exe, sign it the same way after gulp produces it.
