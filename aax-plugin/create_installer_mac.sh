#!/bin/bash
# Create macOS PKG installer for AI Sound Design AAX plugin
# Usage: ./create_installer_mac.sh [intel|arm]

set -e  # Exit on error

ARCH=$1
if [ "$ARCH" != "intel" ] && [ "$ARCH" != "arm" ]; then
    echo "ERROR: Usage: $0 [intel|arm]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="0.1.0"
if [ "$ARCH" == "intel" ]; then
    INSTALLER_NAME="AI-Sound-Design-macOS-Intel-v${VERSION}"
    ARCH_DISPLAY="Intel (x86_64)"
else
    INSTALLER_NAME="AI-Sound-Design-macOS-AppleSilicon-v${VERSION}"
    ARCH_DISPLAY="Apple Silicon (arm64)"
fi

PLUGIN_PATH="$HOME/Library/Application Support/Avid/Audio/Plug-Ins/AI Sound Design.aaxplugin"
STAGING_DIR="installer_staging_mac"
OUTPUT_DIR="installer_output"
COMPONENT_PKG="$STAGING_DIR/${INSTALLER_NAME}-component.pkg"
FINAL_PKG="$OUTPUT_DIR/${INSTALLER_NAME}.pkg"

echo "Creating macOS installer for $ARCH_DISPLAY..."

# Clean staging directory
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy signed plugin to staging
echo "Copying signed plugin..."
cp -R "$PLUGIN_PATH" "$STAGING_DIR/"

# Verify plugin architecture matches
PLUGIN_PYTHON_ARCH=$(file "$STAGING_DIR/AI Sound Design.aaxplugin/Contents/Resources/python/bin/python3.12" | grep -o "x86_64\|arm64")
if [ "$ARCH" == "intel" ] && [ "$PLUGIN_PYTHON_ARCH" != "x86_64" ]; then
    echo "ERROR: Plugin contains wrong architecture (expected x86_64, got $PLUGIN_PYTHON_ARCH)"
    exit 1
elif [ "$ARCH" == "arm" ] && [ "$PLUGIN_PYTHON_ARCH" != "arm64" ]; then
    echo "ERROR: Plugin contains wrong architecture (expected arm64, got $PLUGIN_PYTHON_ARCH)"
    exit 1
fi
echo "✓ Architecture verified: $PLUGIN_PYTHON_ARCH"

# Create proper install root structure
echo "Preparing install structure..."
INSTALL_ROOT="$STAGING_DIR/install_root"
mkdir -p "$INSTALL_ROOT"
mv "$STAGING_DIR/AI Sound Design.aaxplugin" "$INSTALL_ROOT/"

# Create component package
echo "Building component package..."
pkgbuild \
    --root "$INSTALL_ROOT" \
    --identifier "com.ai-sound-design.plugin.installer" \
    --version "$VERSION" \
    --install-location "/Library/Application Support/Avid/Audio/Plug-Ins" \
    "$COMPONENT_PKG"

# Create distribution XML
cat > "$STAGING_DIR/distribution.xml" << EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>AI Sound Design ($ARCH_DISPLAY)</title>
    <welcome file="welcome.html"/>
    <conclusion file="conclusion.html"/>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="false" hostArchitectures="$PLUGIN_PYTHON_ARCH"/>
    <choices-outline>
        <line choice="default">
            <line choice="com.ai-sound-design.plugin.installer"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="com.ai-sound-design.plugin.installer" visible="false">
        <pkg-ref id="com.ai-sound-design.plugin.installer"/>
    </choice>
    <pkg-ref id="com.ai-sound-design.plugin.installer" version="$VERSION" onConclusion="none">
        ${INSTALLER_NAME}-component.pkg
    </pkg-ref>
</installer-gui-script>
EOF

# Create welcome message
cat > "$STAGING_DIR/welcome.html" << EOF
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 13px; }
        h1 { font-size: 18px; font-weight: 600; }
    </style>
</head>
<body>
    <h1>Welcome to AI Sound Design</h1>
    <p>This installer will install the PTV2A AAX plugin for Pro Tools.</p>
    <p><strong>Architecture:</strong> $ARCH_DISPLAY</p>
    <p>The plugin uses AI to generate audio from video content and provides sound effect search capabilities.</p>
    <p><strong>Tested on:</strong></p>
    <ul>
        <li>Pro Tools 2025.06 and 2025.12</li>
        <li>$([ "$ARCH" == "intel" ] && echo "Intel Mac (x86_64)" || echo "Apple Silicon Mac (arm64)")</li>
    </ul>
</body>
</html>
EOF

# Create conclusion message
cat > "$STAGING_DIR/conclusion.html" << EOF
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 13px; }
        h1 { font-size: 18px; font-weight: 600; }
    </style>
</head>
<body>
    <h1>Installation Complete</h1>
    <p>AI Sound Design has been successfully installed.</p>
    <p>The plugin is now available in Pro Tools under:</p>
    <p><strong>Audiosuite → Utility → AI Sound Design</strong></p>
    <p>Please restart Pro Tools if it is currently running.</p>
</body>
</html>
EOF

# Build final distribution package
echo "Building distribution package..."
productbuild \
    --distribution "$STAGING_DIR/distribution.xml" \
    --resources "$STAGING_DIR" \
    --package-path "$STAGING_DIR" \
    "$FINAL_PKG"

# Clean up staging
rm -rf "$STAGING_DIR"

echo ""
echo "✓ Installer created: $FINAL_PKG"
echo "  Size: $(du -h "$FINAL_PKG" | cut -f1)"
