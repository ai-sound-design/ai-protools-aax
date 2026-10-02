#!/bin/bash
# Build AI Sound Design AAX plugin for macOS Apple Silicon (arm64)

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "Building AI Sound Design for macOS Apple Silicon (arm64)"
echo "=================================================="

# 1. Set symlink to ARM Python
echo ""
echo "Step 1/5: Setting Python symlink to ARM..."
cd Resources
rm -f python
ln -s ../python-macos python
echo "✓ Symlink: Resources/python -> ../python-macos"
cd ..

# Verify architecture
PYTHON_ARCH=$(file Resources/python/bin/python3.12 | grep -o "x86_64\|arm64")
if [ "$PYTHON_ARCH" != "arm64" ]; then
    echo "ERROR: Python is not ARM (arm64), got: $PYTHON_ARCH"
    exit 1
fi
echo "✓ Verified: Python is arm64"

# 2. Clean previous builds
echo ""
echo "Step 2/5: Cleaning previous builds..."
sudo rm -rf "/Library/Application Support/Avid/Audio/Plug-Ins/AI Sound Design.aaxplugin"
rm -rf "$HOME/Library/Application Support/Avid/Audio/Plug-Ins/AI Sound Design.aaxplugin"
# Also remove old signed plugin (wraptool can't delete root-owned files)
sudo rm -rf "build/pt_v2a_artefacts/Release/AAX/AI Sound Design.aaxplugin"
echo "✓ Removed previous plugin installations"

# 3. Build Release
echo ""
echo "Step 3/5: Building Release configuration..."
cmake --build build --config Release --target pt_v2a_AAX
echo "✓ Build complete"

# 4. Sign with PACE
echo ""
echo "Step 4/5: Signing with PACE..."
bash sign_aax_mac.sh
echo "✓ Plugin signed"

# 5. Create installer
echo ""
echo "Step 5/5: Creating PKG installer..."
bash create_installer_mac.sh arm
echo "✓ Installer created"

echo ""
echo "=================================================="
echo "✓ ARM build complete!"
echo "Installer: installer_output/AI-Sound-Design-macOS-AppleSilicon-v0.1.1.pkg"
echo "=================================================="
