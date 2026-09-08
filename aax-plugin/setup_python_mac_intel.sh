#!/bin/bash
# Setup Python for macOS Intel (x86_64) using python-build-standalone
# This script downloads and configures Python 3.12 for Intel Macs

set -e

PYTHON_VERSION="3.12.7"
RELEASE_DATE="20241016"
BUILD_TYPE="install_only_stripped"

# Force Intel architecture
BUILD_ARCH="x86_64-apple-darwin"

BUILD_NAME="cpython-${PYTHON_VERSION}+${RELEASE_DATE}-${BUILD_ARCH}-${BUILD_TYPE}"
DOWNLOAD_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_DATE}/${BUILD_NAME}.tar.gz"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="${SCRIPT_DIR}/python-macintel"
DOWNLOAD_FILE="${SCRIPT_DIR}/${BUILD_NAME}.tar.gz"

echo "================================================"
echo "Python Setup for macOS Intel (x86_64)"
echo "================================================"
echo ""
echo "Build: ${BUILD_NAME}"
echo ""

# Check if Python already exists
if [ -d "$PYTHON_DIR" ]; then
    if [ "$1" != "--force" ]; then
        echo "✓ Python already installed at: $PYTHON_DIR"
        echo "Use --force flag to reinstall"
        exit 0
    fi
    echo "Removing existing Python installation..."
    rm -rf "$PYTHON_DIR"
fi

# Download Python
echo "Downloading Python ${PYTHON_VERSION} for Intel..."
echo "URL: $DOWNLOAD_URL"

if command -v curl &> /dev/null; then
    curl -L -o "$DOWNLOAD_FILE" "$DOWNLOAD_URL"
elif command -v wget &> /dev/null; then
    wget -O "$DOWNLOAD_FILE" "$DOWNLOAD_URL"
else
    echo "✗ Error: curl or wget required"
    exit 1
fi

echo "✓ Download complete"

# Extract archive
echo "Extracting archive..."
mkdir -p "$PYTHON_DIR"
tar -xzf "$DOWNLOAD_FILE" -C "$PYTHON_DIR" --strip-components=1
rm -f "$DOWNLOAD_FILE"
echo "✓ Extraction complete"

# Verify Python executable
PYTHON_EXE="${PYTHON_DIR}/bin/python3"
if [ ! -f "$PYTHON_EXE" ]; then
    echo "✗ Python executable not found at: $PYTHON_EXE"
    exit 1
fi

# Verify it's Intel binary
if command -v file &> /dev/null; then
    echo ""
    echo "Python binary info:"
    file "$PYTHON_EXE"
fi

echo "✓ Python installed successfully"

# Test Python
echo ""
echo "Testing Python..."
"$PYTHON_EXE" --version
"$PYTHON_EXE" -c "import sys; print(f'Python path: {sys.executable}')"

# Upgrade pip
echo ""
echo "Upgrading pip..."
"$PYTHON_EXE" -m ensurepip --upgrade
"$PYTHON_EXE" -m pip install --upgrade pip

# Install runtime dependencies
echo ""
echo "Installing runtime dependencies..."

REQUIREMENTS=(
    "grpcio>=1.60.0"
    "httpx>=0.27.0"
    "soundfile>=0.12.0"
    "numpy>=1.24.0"
    "imageio-ffmpeg>=0.5.0"
    "psycopg2-binary>=2.9.0"
)

for package in "${REQUIREMENTS[@]}"; do
    echo "Installing $package..."
    "$PYTHON_EXE" -m pip install --no-cache-dir "$package"
done

# Install py-ptsl (editable mode for development)
echo ""
echo "Installing py-ptsl (editable)..."
PY_PTSL_DIR="${SCRIPT_DIR}/../../../external/py-ptsl"
if [ -d "$PY_PTSL_DIR" ]; then
    "$PYTHON_EXE" -m pip install -e "$PY_PTSL_DIR"
    echo "✓ py-ptsl installed"
else
    echo "⚠ py-ptsl not found at: $PY_PTSL_DIR"
    echo "Installing from git..."
    "$PYTHON_EXE" -m pip install git+https://github.com/iluvcapra/py-ptsl.git
fi

# Verify installations
echo ""
echo "Verifying installations..."

"$PYTHON_EXE" -c "
import sys
print(f'Python: {sys.version}')
print(f'Executable: {sys.executable}')
print()

packages = ['grpcio', 'httpx', 'soundfile', 'numpy', 'imageio_ffmpeg', 'psycopg2']
failed = False
for pkg in packages:
    try:
        mod = __import__(pkg)
        version = getattr(mod, '__version__', 'unknown')
        print(f'✓ {pkg}: {version}')
    except ImportError as e:
        print(f'✗ {pkg}: MISSING')
        failed = True

if failed:
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "================================================"
    echo "✓ Python setup complete for Intel Mac!"
    echo "================================================"
    echo ""
    echo "Python location: $PYTHON_DIR"
    echo "Executable: $PYTHON_EXE"
    echo ""
    echo "Next steps:"
    echo "1. Link to this Python: rm python && ln -s python-macintel python"
    echo "2. Build plugin: cmake --build build --config Release --target pt_v2a_AAX"
    echo "3. Sign plugin: bash ../sign_aax_mac.sh"
else
    echo ""
    echo "✗ Setup failed - some packages missing"
    exit 1
fi
