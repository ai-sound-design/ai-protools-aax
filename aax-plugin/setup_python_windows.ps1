# Setup Python for Windows using python-build-standalone
# This script downloads and configures Python 3.12 with only required dependencies

param(
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

$PYTHON_VERSION = "3.12.7"
$RELEASE_DATE = "20241016"
$BUILD_TYPE = "install_only_stripped"
$ARCH = "x86_64-pc-windows-msvc"
$BUILD_NAME = "cpython-${PYTHON_VERSION}+${RELEASE_DATE}-${ARCH}-${BUILD_TYPE}"
$DOWNLOAD_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_DATE}/${BUILD_NAME}.tar.gz"

$SCRIPT_DIR = $PSScriptRoot
$PYTHON_DIR = Join-Path $SCRIPT_DIR "python-windows"
$OLD_PYTHON_DIR = Join-Path $SCRIPT_DIR "python"
$DOWNLOAD_FILE = Join-Path $SCRIPT_DIR "${BUILD_NAME}.tar.gz"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Python Setup for Windows (python-build-standalone)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python already exists
if (Test-Path $PYTHON_DIR) {
    if (-not $Force) {
        Write-Host "✓ Python already installed at: $PYTHON_DIR" -ForegroundColor Green
        Write-Host "Use -Force flag to reinstall" -ForegroundColor Yellow
        exit 0
    }
    Write-Host "Removing existing Python installation..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $PYTHON_DIR
}

# Backup old Python if exists
if (Test-Path $OLD_PYTHON_DIR) {
    $BACKUP_DIR = "${OLD_PYTHON_DIR}_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Write-Host "Backing up old Python to: $BACKUP_DIR" -ForegroundColor Yellow
    Move-Item $OLD_PYTHON_DIR $BACKUP_DIR
}

# Download Python
Write-Host "Downloading Python ${PYTHON_VERSION}..." -ForegroundColor Cyan
Write-Host "URL: $DOWNLOAD_URL" -ForegroundColor Gray

try {
    # Use System.Net.WebClient for better progress
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile($DOWNLOAD_URL, $DOWNLOAD_FILE)
    Write-Host "✓ Download complete" -ForegroundColor Green
} catch {
    Write-Host "✗ Download failed: $_" -ForegroundColor Red
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
    
    Write-Host "✓ Extraction complete" -ForegroundColor Green
} catch {
    Write-Host "✗ Extraction failed: $_" -ForegroundColor Red
    Write-Host "Trying alternative method..." -ForegroundColor Yellow
    
    # Fallback: Use 7zip if available
    $sevenZip = "C:\Program Files\7-Zip\7z.exe"
    if (Test-Path $sevenZip) {
        & $sevenZip x $DOWNLOAD_FILE -o"$SCRIPT_DIR" -y
        Write-Host "✓ Extraction complete (via 7zip)" -ForegroundColor Green
    } else {
        Write-Host "✗ Please install tar or 7-Zip to extract the archive" -ForegroundColor Red
        exit 1
    }
}

# Verify Python executable
$PYTHON_EXE = Join-Path $PYTHON_DIR "python.exe"
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "✗ Python executable not found at: $PYTHON_EXE" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Python installed successfully" -ForegroundColor Green

# Test Python
Write-Host ""
Write-Host "Testing Python..." -ForegroundColor Cyan
& $PYTHON_EXE --version
& $PYTHON_EXE -c "import sys; print(f'Python path: {sys.executable}')"

# Upgrade pip
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor Cyan
& $PYTHON_EXE -m ensurepip --upgrade
& $PYTHON_EXE -m pip install --upgrade pip

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
    & $PYTHON_EXE -m pip install --no-cache-dir $package
}

# Install py-ptsl (editable mode for development)
Write-Host ""
Write-Host "Installing py-ptsl (editable)..." -ForegroundColor Cyan
$PY_PTSL_DIR = Join-Path $SCRIPT_DIR "..\..\..\external\py-ptsl"
if (Test-Path $PY_PTSL_DIR) {
    & $PYTHON_EXE -m pip install -e $PY_PTSL_DIR
    Write-Host "✓ py-ptsl installed" -ForegroundColor Green
} else {
    Write-Host "⚠ py-ptsl not found at: $PY_PTSL_DIR" -ForegroundColor Yellow
    Write-Host "Installing from git..." -ForegroundColor Yellow
    & $PYTHON_EXE -m pip install git+https://github.com/iluvcapra/py-ptsl.git
}

# Verify installations
Write-Host ""
Write-Host "Verifying installations..." -ForegroundColor Cyan

$testScript = @"
import sys
print(f'Python: {sys.version}')
print(f'Executable: {sys.executable}')
print()

packages = ['grpcio', 'httpx', 'soundfile', 'numpy', 'imageio_ffmpeg', 'psycopg2']
for pkg in packages:
    try:
        mod = __import__(pkg)
        version = getattr(mod, '__version__', 'unknown')
        print(f'✓ {pkg}: {version}')
    except ImportError as e:
        print(f'✗ {pkg}: MISSING')
        sys.exit(1)
"@

& $PYTHON_EXE -c $testScript

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "✓ Python setup complete!" -ForegroundColor Green
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
    Write-Host "✗ Setup failed - some packages missing" -ForegroundColor Red
    exit 1
}
