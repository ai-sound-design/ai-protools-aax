#!/bin/bash
# Install Python requirements for both ARM and Intel Python distributions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "Installing Python Requirements"
echo "=================================================="

REQUIREMENTS="../companion/ptsl_integration/requirements.txt"

# Install for ARM Python
if [ -d "python-macos" ]; then
    echo ""
    echo "Installing requirements for ARM (python-macos)..."
    ./python-macos/bin/python3 -m pip install -r "$REQUIREMENTS"
    
    # Install py-ptsl
    PY_PTSL_DIR="../../external/py-ptsl"
    if [ -d "$PY_PTSL_DIR" ]; then
        echo "Installing py-ptsl (editable)..."
        ./python-macos/bin/python3 -m pip install -e "$PY_PTSL_DIR"
    fi
    
    echo "✓ ARM requirements installed"
else
    echo "⚠ python-macos not found, skipping ARM"
fi

# Install for Intel Python
if [ -d "python-macintel" ]; then
    echo ""
    echo "Installing requirements for Intel (python-macintel)..."
    ./python-macintel/bin/python3 -m pip install -r "$REQUIREMENTS"
    
    # Install py-ptsl
    PY_PTSL_DIR="../../external/py-ptsl"
    if [ -d "$PY_PTSL_DIR" ]; then
        echo "Installing py-ptsl (editable)..."
        ./python-macintel/bin/python3 -m pip install -e "$PY_PTSL_DIR"
    fi
    
    echo "✓ Intel requirements installed"
else
    echo "⚠ python-macintel not found, skipping Intel"
fi

echo ""
echo "=================================================="
echo "✓ All requirements installed"
echo "=================================================="
