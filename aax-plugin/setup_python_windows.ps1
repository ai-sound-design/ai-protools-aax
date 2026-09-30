# Setup Python for Windows using python-build-standalone
# This script downloads and configures Python 3.12 with only required dependencies

param(
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

# Native programs (python, pip) write progress and warnings to stderr. Under
# $ErrorActionPreference = "Stop", Windows PowerShell 5.1 turns those lines into
# terminating errors even when the program exits with 0. Run them with error
# handling relaxed and judge success by the exit code instead.
function Invoke-Native {
    param([Parameter(Mandatory)][string]$Exe, [string[]]$Arguments, [switch]$AllowFailure)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @Arguments
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "$Exe $($Arguments -join ' ') failed with exit code $code"
    }
    return $code
}

$PYTHON_VERSION = "3.12.7"
$RELEASE_DATE = "20241016"
$BUILD_TYPE = "install_only_stripped"
$ARCH = "x86_64-pc-windows-msvc"
$BUILD_NAME = "cpython-${PYTHON_VERSION}+${RELEASE_DATE}-${ARCH}-${BUILD_TYPE}"
$DOWNLOAD_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_DATE}/${BUILD_NAME}.tar.gz"

$SCRIPT_DIR = $PSScriptRoot
# Install straight into Resources\python: that is where both CMakeLists.txt and
# the plugin's runtime lookup (PluginProcessor::findPythonExecutable) expect it.
# Installing anywhere else means the build copies nothing and the plugin finds
# no interpreter.
$RESOURCES_DIR = Join-Path $SCRIPT_DIR "Resources"
$PYTHON_DIR = Join-Path $RESOURCES_DIR "python"
$DOWNLOAD_FILE = Join-Path $env:TEMP "${BUILD_NAME}.tar.gz"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Python Setup for Windows (python-build-standalone)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python already exists
if (Test-Path $PYTHON_DIR) {
    if (-not $Force) {
        Write-Host "[OK] Python already installed at: $PYTHON_DIR" -ForegroundColor Green
        Write-Host "Use -Force flag to reinstall" -ForegroundColor Yellow
        exit 0
    }
    Write-Host "Removing existing Python installation..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $PYTHON_DIR
}

# Make sure Resources/ exists before extracting into it
if (-not (Test-Path $RESOURCES_DIR)) {
    New-Item -ItemType Directory -Force -Path $RESOURCES_DIR | Out-Null
}

# Download Python
Write-Host "Downloading Python ${PYTHON_VERSION}..." -ForegroundColor Cyan
Write-Host "URL: $DOWNLOAD_URL" -ForegroundColor Gray

try {
    # Use System.Net.WebClient for better progress
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile($DOWNLOAD_URL, $DOWNLOAD_FILE)
    Write-Host "[OK] Download complete" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Download failed: $_" -ForegroundColor Red
    exit 1
}

# Extract archive
Write-Host "Extracting archive..." -ForegroundColor Cyan

try {
    # Create temp extraction directory
    $TEMP_EXTRACT = Join-Path $SCRIPT_DIR "temp_extract"
    New-Item -ItemType Directory -Path $TEMP_EXTRACT -Force | Out-Null
    
    # Extract using tar (available in Windows 10+)
    tar -xzf $DOWNLOAD_FILE -C $TEMP_EXTRACT
    
    # Move python directory
    $extractedPython = Get-ChildItem $TEMP_EXTRACT -Directory | Select-Object -First 1
    Move-Item $extractedPython.FullName $PYTHON_DIR
    
    # Cleanup
    Remove-Item -Recurse -Force $TEMP_EXTRACT
    Remove-Item -Force $DOWNLOAD_FILE
    
    Write-Host "[OK] Extraction complete" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Extraction failed: $_" -ForegroundColor Red
    Write-Host "Trying alternative method..." -ForegroundColor Yellow
    
    # Fallback: Use 7zip if available
    $sevenZip = "C:\Program Files\7-Zip\7z.exe"
    if (Test-Path $sevenZip) {
        & $sevenZip x $DOWNLOAD_FILE -o"$SCRIPT_DIR" -y
        Write-Host "[OK] Extraction complete (via 7zip)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Please install tar or 7-Zip to extract the archive" -ForegroundColor Red
        exit 1
    }
}

# Verify Python executable
$PYTHON_EXE = Join-Path $PYTHON_DIR "python.exe"
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "[FAIL] Python executable not found at: $PYTHON_EXE" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Python installed successfully" -ForegroundColor Green

# Test Python
Write-Host ""
Write-Host "Testing Python..." -ForegroundColor Cyan
Invoke-Native $PYTHON_EXE @("--version") | Out-Null
Invoke-Native $PYTHON_EXE @("-c", "import sys; print(sys.executable)") | Out-Null

# Upgrade pip
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor Cyan
Invoke-Native $PYTHON_EXE @("-m", "ensurepip", "--upgrade") -AllowFailure | Out-Null
Invoke-Native $PYTHON_EXE @("-m", "pip", "install", "--upgrade", "pip") | Out-Null

# Install runtime dependencies
Write-Host ""
Write-Host "Installing runtime dependencies..." -ForegroundColor Cyan

$REQUIREMENTS = @(
    "grpcio>=1.60.0",
    "httpx>=0.27.0",
    "soundfile>=0.12.0",
    "numpy>=1.24.0",
    "imageio-ffmpeg>=0.5.0",
    "psycopg2-binary>=2.9.0"
)

foreach ($package in $REQUIREMENTS) {
    Write-Host "Installing $package..." -ForegroundColor Gray
    Invoke-Native $PYTHON_EXE @("-m", "pip", "install", "--no-cache-dir", $package) | Out-Null
}

# Install py-ptsl: the pinned submodule external/py-ptsl, as a real copy. Never editable
# (that only leaves a path link to this checkout, and the plugin fails on every other
# machine) and never from upstream git (a different version).
Write-Host ""
Write-Host "Installing py-ptsl..." -ForegroundColor Cyan
$PY_PTSL_DIR = Join-Path $SCRIPT_DIR "..\external\py-ptsl"
if (-not (Test-Path (Join-Path $PY_PTSL_DIR "pyproject.toml"))) {
    Write-Host "py-ptsl submodule not checked out, fetching it..." -ForegroundColor Yellow
    git -C (Join-Path $SCRIPT_DIR "..") submodule update --init external/py-ptsl
}
if (Test-Path (Join-Path $PY_PTSL_DIR "pyproject.toml")) {
    Invoke-Native $PYTHON_EXE @("-m", "pip", "install", "--no-cache-dir", $PY_PTSL_DIR) | Out-Null
    Write-Host "[OK] py-ptsl installed" -ForegroundColor Green
} else {
    Write-Host "[WARN] py-ptsl not found at: $PY_PTSL_DIR" -ForegroundColor Yellow
    Write-Host "Installing from git..." -ForegroundColor Yellow
    Invoke-Native $PYTHON_EXE @("-m", "pip", "install", "git+https://github.com/iluvcapra/py-ptsl.git") | Out-Null
}

# Verify installations
Write-Host ""
Write-Host "Verifying installations..." -ForegroundColor Cyan

$testScript = @"
import sys
print(f'Python: {sys.version}')
print(f'Executable: {sys.executable}')
print()

# Import names, not PyPI names: grpcio installs the module 'grpc'.
packages = ['grpc', 'httpx', 'soundfile', 'numpy', 'imageio_ffmpeg', 'psycopg2', 'ptsl']
for pkg in packages:
    try:
        mod = __import__(pkg)
        version = getattr(mod, '__version__', 'unknown')
        print(f'[OK] {pkg}: {version}')
    except ImportError as e:
        print(f'[FAIL] {pkg}: MISSING')
        sys.exit(1)
"@

& $PYTHON_EXE -c $testScript

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "[OK] Python setup complete!" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Python location: $PYTHON_DIR" -ForegroundColor Cyan
    Write-Host "Executable: $PYTHON_EXE" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Create symlink: mklink /D python python-windows" -ForegroundColor Gray
    Write-Host "2. Build plugin: cmake --build build --target pt_v2a_AAX" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "[FAIL] Setup failed - some packages missing" -ForegroundColor Red
    exit 1
}
