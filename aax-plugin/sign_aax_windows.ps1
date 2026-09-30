<#
.SYNOPSIS
    Signs the built AAX plugin with PACE's wraptool so that it loads in the
    regular Pro Tools (the Developer Build loads unsigned plugins as well).

.DESCRIPTION
    Requirements (see aax-plugin/MAC_BUILD_GUIDE.md for the macOS counterpart):
      - PACE "Code Signing For AAX SDK" for Windows installed (wraptool.exe),
        or WRAPTOOL pointing at the executable
      - the "PACE Tools" licence (Fusion 6; "Eden Tools" is for wraptool 5) on
        an iLok USB key that is plugged in, or -AllowSigningService with an
        iLok Cloud session
      - a Windows SDK (signtool.exe); wraptool finds it in the default location
      - your iLok developer account and the wrap-configuration GUID (WCGUID)
        from PACE Central

    Nothing personal is stored in this file. Account, WCGUID and password come
    from environment variables or are asked for:
      ILOK_ACCOUNT       iLok user name
      ILOK_PASSWORD      iLok password (optional: wraptool keeps it in the
                         Windows credential store after the first run)
      PACE_WCGUID        wrap-configuration GUID
      WRAPTOOL           path to wraptool.exe (optional)
      AAX_PFX            code-signing certificate, PKCS#12 (optional)
      AAX_PFX_PASSWORD   its password (optional)

    The Authenticode certificate is only needed because wraptool wraps
    signtool. Pro Tools checks PACE's signature, not the certificate chain, so
    a self-signed certificate is enough for a research build; the script
    creates one on first use (valid ten years) and exports it to
    %LOCALAPPDATA%\AI Sound Design\signing\aax-signing.pfx.

.EXAMPLE
    $env:ILOK_ACCOUNT = "myaccount"; $env:PACE_WCGUID = "XXXXXXXX-XXXX-..."
    .\sign_aax_windows.ps1
    .\sign_aax_windows.ps1 -Plugin "D:\build\Release\AAX\AI Sound Design.aaxplugin" -VerifyOnly
#>
[CmdletBinding()]
param(
    # The .aaxplugin bundle folder produced by the build
    [string] $Plugin = (Join-Path $PSScriptRoot "..\..\build-aax-vs\pt_v2a_artefacts\Release\AAX\AI Sound Design.aaxplugin"),
    # Only run "wraptool verify" on the plugin
    [switch] $VerifyOnly,
    # Use PACE's signing service when no signing iLok is plugged in (needs account + password)
    [switch] $AllowSigningService
)

$ErrorActionPreference = "Stop"

function Find-Wraptool {
    if ($env:WRAPTOOL -and (Test-Path $env:WRAPTOOL)) { return $env:WRAPTOOL }
    $roots = @("C:\Program Files\PACEAntiPiracy\Eden\Fusion\Versions",
               "C:\Program Files\PACE\Eden\Fusion\Versions")
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $hit = Get-ChildItem $root -Directory | Sort-Object { [int]($_.Name -replace '\D', '0') } -Descending |
               ForEach-Object { Join-Path $_.FullName "bin\wraptool.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    throw "wraptool.exe not found. Install the PACE Code Signing For AAX SDK or set WRAPTOOL to the executable."
}

function Get-Certificate {
    $pfx = $env:AAX_PFX
    if (-not $pfx) { $pfx = Join-Path $env:LOCALAPPDATA "AI Sound Design\signing\aax-signing.pfx" }
    $password = $env:AAX_PFX_PASSWORD
    if (-not $password) { $password = "aax-signing" }
    if (-not (Test-Path $pfx)) {
        Write-Host "Creating a self-signed code-signing certificate: $pfx"
        New-Item -ItemType Directory -Force (Split-Path $pfx) | Out-Null
        # wraptool loads the key through CryptoAPI: a CNG key (the default
        # provider) is rejected as "doesn't contain a valid signing certificate"
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=AI Sound Design AAX" `
                    -KeyExportPolicy Exportable -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
                    -KeySpec Signature -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider" `
                    -NotAfter (Get-Date).AddYears(10) -CertStoreLocation Cert:\CurrentUser\My
        $secure = ConvertTo-SecureString $password -AsPlainText -Force
        Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $secure | Out-Null
    }
    return @{ File = $pfx; Password = $password }
}

$Plugin = [System.IO.Path]::GetFullPath($Plugin)
if (-not (Test-Path $Plugin)) { throw "Plugin not found: $Plugin  (build it first, or pass -Plugin)" }
$binary = Join-Path $Plugin "Contents\x64\$(Split-Path $Plugin -Leaf)"
if (-not (Test-Path $binary)) { throw "No 64-bit binary in the bundle: $binary" }

$wraptool = Find-Wraptool
# The SDK installer sets PACE_FUSION_HOME system-wide; a copied wraptool needs it too
if (-not $env:PACE_FUSION_HOME) { $env:PACE_FUSION_HOME = Split-Path (Split-Path $wraptool) }
Write-Host "wraptool: $wraptool"
Write-Host "plugin:   $Plugin"

if ($VerifyOnly) {
    # "verify" wants the DLL on Windows, "sign" takes the bundle folder
    & $wraptool verify --verbose --in $binary
    exit $LASTEXITCODE
}

$account = $env:ILOK_ACCOUNT
if (-not $account) { $account = Read-Host "iLok account" }
$wcguid = $env:PACE_WCGUID
if (-not $wcguid) { $wcguid = Read-Host "Wrap configuration GUID (PACE Central)" }
if (-not $account -or -not $wcguid) { throw "ILOK_ACCOUNT and PACE_WCGUID are required." }

$cert = Get-Certificate

$wrapArgs = @("sign", "--verbose",
          "--account", $account,
          "--wcguid", $wcguid,
          "--keyfile", $cert.File, "--keypassword", $cert.Password,
          "--in", $Plugin, "--out", $Plugin,
          "--autoinstall", "off")
if ($env:ILOK_PASSWORD) { $wrapArgs += @("--password", $env:ILOK_PASSWORD) }
if ($AllowSigningService) { $wrapArgs += "--allowsigningservice" }

Write-Host "Signing (the iLok with the PACE Tools licence must be plugged in)..."
& $wraptool @wrapArgs
if ($LASTEXITCODE -ne 0) { throw "wraptool sign failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "Verifying..."
& $wraptool verify --verbose --in $binary
if ($LASTEXITCODE -ne 0) { throw "wraptool verify failed with exit code $LASTEXITCODE" }
Write-Host ""
Write-Host "Signed: $Plugin"
Write-Host "Install it with the usual robocopy while Pro Tools is closed."
