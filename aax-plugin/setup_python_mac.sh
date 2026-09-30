#!/bin/bash
# Setup Python for macOS using python-build-standalone
# This script downloads and configures Python 3.12 Universal2 with only required dependencies

set -e

PYTHON_VERSION="3.12.7"
RELEASE_DATE="20241016"
BUILD_TYPE="install_only_stripped"

# Detect architecture
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    BUILD_ARCH="aarch64-apple-darwin"
else
    BUILD_ARCH="x86_64-apple-darwin"
fi

BUILD_NAME="cpython-${PYTHON_VERSION}+${RELEASE_DATE}-${BUILD_ARCH}-${BUILD_TYPE}"
DOWNLOAD_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_DATE}/${BUILD_NAME}.tar.gz"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="${SCRIPT_DIR}/python-macos"
OLD_PYTHON_DIR="${SCRIPT_DIR}/python"
DOWNLOAD_FILE="${SCRIPT_DIR}/${BUILD_NAME}.tar.gz"

echo "================================================"
echo "Python Setup for macOS (python-build-standalone)"
echo "================================================"
echo ""
echo "Architecture: ${ARCH}"
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

# Backup old Python if exists
if [ -d "$OLD_PYTHON_DIR" ]; then
    BACKUP_DIR="${OLD_PYTHON_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    echo "Backing up old Python to: $BACKUP_DIR"
    mv "$OLD_PYTHON_DIR" "$BACKUP_DIR"
fi

# Download Python
echo "Downloading Python ${PYTHON_VERSION}..."
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

# Verify it's a Universal Binary (if possible)
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

# Install py-ptsl: the pinned submodule external/py-ptsl, as a real copy. Never
# editable (that only leaves a path link to this checkout, and the plugin fails on
# every other machine) and never from upstream git (a different version).
echo ""
echo "Installing py-ptsl..."
PY_PTSL_DIR="${SCRIPT_DIR}/../external/py-ptsl"
if [ ! -f "$PY_PTSL_DIR/pyproject.toml" ]; then
    echo "py-ptsl submodule not checked out, fetching it..."
    git -C "${SCRIPT_DIR}/.." submodule update --init external/py-ptsl
fi
if [ -f "$PY_PTSL_DIR/pyproject.toml" ]; then
    "$PYTHON_EXE" -m pip install --no-cache-dir "$PY_PTSL_DIR"
    echo "✓ py-ptsl installed from $PY_PTSL_DIR"
else
    echo "✗ py-ptsl not found at: $PY_PTSL_DIR (run: git submodule update --init external/py-ptsl)"
    exit 1
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
    echo "✓ Python setup complete!"
    echo "================================================"
    echo ""
    echo "Python location: $PYTHON_DIR"
    echo "Executable: $PYTHON_EXE"
    echo ""
    echo "Next steps:"
    echo "1. Create symlink: ln -s python-macos python"
    echo "2. Build plugin: cmake --build build --target pt_v2a_AAX"
else
    echo ""
    echo "✗ Setup failed - some packages missing"
    exit 1
fi
