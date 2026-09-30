<#
.SYNOPSIS
  Packs the signed AAX bundle into a one-click Windows installer (Inno Setup).

.DESCRIPTION
  Takes the built (and, for Pro Tools, PACE-signed) bundle and compiles
  installer_windows.iss into a single setup .exe that installs the plugin into
  Pro Tools' plug-in folder on any machine, for any user with admin rights,
  from wherever the .exe is run. The version comes from CMakeLists.txt.

  Needs Inno Setup 6 (winget install JRSoftware.InnoSetup). The compiler is
  found through the ISCC environment variable or its usual install folders.

.PARAMETER Bundle
  The "AI Sound Design.aaxplugin" folder. Default: the Release build next to the
  repository (build-aax-vs\pt_v2a_artefacts\Release\AAX).

.PARAMETER OutDir
  Where the setup .exe goes. Default: aax-plugin\installer_output.

.EXAMPLE
  .\build_installer_windows.ps1
  .\build_installer_windows.ps1 -Bundle "D:\builds\AI Sound Design.aaxplugin"
#>
param(
    [string] $Bundle = "",
    [string] $OutDir = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $Bundle) {
    $Bundle = Join-Path $here "..\..\build-aax-vs\pt_v2a_artefacts\Release\AAX\AI Sound Design.aaxplugin"
}
$Bundle = [System.IO.Path]::GetFullPath($Bundle)
if (-not $OutDir) { $OutDir = Join-Path $here "installer_output" }
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

# The bundle: the DLL and the embedded Python must both be there
$dll = Join-Path $Bundle "Contents\x64\AI Sound Design.aaxplugin"
$python = Join-Path $Bundle "Contents\Resources\python\python.exe"
if (-not (Test-Path $dll)) { throw "No plugin DLL under $Bundle (build the pt_v2a_AAX target first)" }
if (-not (Test-Path $python)) { throw "No embedded Python under $Bundle (see EMBEDDED_PYTHON_SETUP.md)" }
$signed = Select-String -Path $dll -Pattern "PACE Anti-Piracy Root" -Quiet
if (-not $signed) {
    Write-Warning "The DLL carries no PACE signature; Pro Tools will refuse it. Run sign_aax_windows.ps1 first."
}

# The version, from the CMake project
$cmake = Get-Content (Join-Path $here "CMakeLists.txt") -Raw
$version = "0.1.0"
if ($cmake -match "(?m)^\s*VERSION\s+(\d+\.\d+\.\d+)") { $version = $Matches[1] }

# Inno Setup's command-line compiler
$candidates = @(
    $env:ISCC,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $candidates) {
    throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup (or set ISCC to ISCC.exe)"
}
$iscc = @($candidates)[0]

Write-Host "bundle:  $Bundle"
Write-Host "version: $version"
Write-Host "ISCC:    $iscc"
Write-Host "Compiling the installer..."

& $iscc "/DBundleDir=$Bundle" "/DAppVer=$version" "/O$OutDir" "/Qp" (Join-Path $here "installer_windows.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

$exe = Join-Path $OutDir "AI-Sound-Design-Windows-Setup-v$version.exe"
$size = [math]::Round((Get-Item $exe).Length / 1MB)
Write-Host ""
Write-Host "Installer: $exe ($size MB)"
Write-Host "Run it (it asks for admin rights) with Pro Tools closed; it replaces an installed older version."
