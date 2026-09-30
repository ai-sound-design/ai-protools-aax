#!/bin/bash

# === AAX Plugin Signing for macOS ===
# Based on PACE Eden SDK Lite with self-signed certificate
# Documentation: https://docs.paceap.com/lite/SDK/aax/platform_certificates/

# === Settings ===
# Account and wrap-configuration GUID come from the environment, nothing
# personal is kept in this file (see sign_aax_windows.ps1 for Windows):
#   ILOK_ACCOUNT  iLok user name
#   PACE_WCGUID   wrap-configuration GUID from PACE Central
WRAPTOOL="${WRAPTOOL:-/Applications/PACEAntiPiracy/Eden/Fusion/Current/bin/wraptool}"
ILOK_ACCOUNT="${ILOK_ACCOUNT:?set ILOK_ACCOUNT to your iLok user name}"
WCGUID="${PACE_WCGUID:?set PACE_WCGUID to the wrap-configuration GUID from PACE Central}"
SIGNID="your-certificate-common-name-here"  # Will be set below after certificate creation

# Plugin paths
PLUGIN_NAME="AI Sound Design"
BUILD_CONFIG="Release"  # Change to "Debug" for development
PROJECT_ROOT="/path/to/protools-aax"
PLUGIN_PATH="$PROJECT_ROOT/aax-plugin/build/pt_v2a_artefacts/$BUILD_CONFIG/AAX/$PLUGIN_NAME.aaxplugin"
INSTALL_DIR="$HOME/Library/Application Support/Avid/Audio/Plug-Ins"

echo "============================================================================"
echo "AAX Plugin Signing for $PLUGIN_NAME (macOS)"
echo "============================================================================"
echo ""
echo "Wraptool: $WRAPTOOL"
echo "Plugin: $PLUGIN_PATH"
echo "Account: $ILOK_ACCOUNT"
echo "Build Config: $BUILD_CONFIG"
echo ""


# === Validation ===
if [ ! -f "$WRAPTOOL" ]; then
    echo "ERROR: wraptool not found at $WRAPTOOL"
    echo ""
    echo "Please install PACE Eden SDK Lite:"
    echo "  https://www.paceap.com/pace-eden-sdk-lite.html"
    echo ""
    exit 1
fi

if [ ! -d "$PLUGIN_PATH" ]; then
    echo "ERROR: Plugin not found at $PLUGIN_PATH"
    echo ""
    echo "Build the plugin first:"
    echo "  cd $PROJECT_ROOT/aax-plugin/build"
    echo "  cmake --build . --config $BUILD_CONFIG --target PtV2A_AAX"
    echo ""
    exit 1
fi

# === Certificate Check ===
echo "Checking for self-signed certificate..."
CERT_NAME="AAX Self-Signed Developer"

# Check if certificate exists in keychain
if ! security find-certificate -c "$CERT_NAME" -p &>/dev/null; then
    echo ""
    echo "WARNING: Certificate '$CERT_NAME' not found in keychain!"
    echo ""
    echo "You need to create a self-signed certificate first."
    echo "Run the following commands:"
    echo ""
    echo "  # Create self-signed certificate"
    echo "  security create-keypair -a \"$CERT_NAME\""
    echo ""
    echo "  # Or use macOS Keychain Access:"
    echo "  # 1. Open Keychain Access.app"
    echo "  # 2. Keychain Access > Certificate Assistant > Create a Certificate"
    echo "  # 3. Name: AAX Self-Signed Developer"
    echo "  # 4. Identity Type: Self Signed Root"
    echo "  # 5. Certificate Type: Code Signing"
    echo "  # 6. Click Create"
    echo ""
    read -p "Do you want to create the certificate now? (y/n): " CREATE_CERT
    
    if [ "$CREATE_CERT" = "y" ] || [ "$CREATE_CERT" = "Y" ]; then
        echo ""
        echo "Creating self-signed certificate..."
        
        # Create certificate using certtool
        security create-keychain -p "" temp.keychain
        security default-keychain -s temp.keychain
        security unlock-keychain -p "" temp.keychain
        
        # Generate certificate
        openssl req -new -newkey rsa:2048 -nodes -keyout temp_key.pem -out temp_csr.pem \
            -subj "/CN=$CERT_NAME/O=Thesis Development/C=DE"
        
        openssl x509 -req -days 365 -in temp_csr.pem -signkey temp_key.pem -out temp_cert.pem
        
        # Import to keychain
        openssl pkcs12 -export -out temp_cert.p12 -inkey temp_key.pem -in temp_cert.pem -passout pass:
        security import temp_cert.p12 -k ~/Library/Keychains/login.keychain-db -P "" -T /usr/bin/codesign
        
        # Cleanup
        rm -f temp_key.pem temp_csr.pem temp_cert.pem temp_cert.p12
        security delete-keychain temp.keychain
        security default-keychain -s ~/Library/Keychains/login.keychain-db
        
        echo "✓ Certificate created successfully!"
        echo ""
    else
        echo ""
        echo "Please create the certificate and run this script again."
        exit 1
    fi
fi

SIGNID="$CERT_NAME"

# === Password Input ===
echo ""
echo "NOTE: Your iLok password will be stored securely in macOS Keychain."
echo "      You may see a dialog asking to allow 'wraptool' access - click 'Always Allow'."
echo ""
read -sp "Enter your iLok password: " ILOK_PASSWORD
echo ""
echo ""

# === Signing ===
echo "Signing plugin with self-signed certificate..."
echo ""

# Try to unlock keychain first
security unlock-keychain ~/Library/Keychains/login.keychain-db 2>/dev/null || true

"$WRAPTOOL" sign \
    --verbose \
    --account "$ILOK_ACCOUNT" \
    --password "$ILOK_PASSWORD" \
    --wcguid "$WCGUID" \
    --signid "$SIGNID" \
    --signtool /usr/bin/codesign \
    --in "$PLUGIN_PATH" \
    --out "$PLUGIN_PATH" \
    --autoinstall off \
    2>&1 | tee /tmp/wraptool.log

WRAP_EXIT_CODE=${PIPESTATUS[0]}

if [ $WRAP_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "============================================================================"
    echo "ERROR: Signing failed with code $WRAP_EXIT_CODE"
    echo "============================================================================"
    echo ""
    echo "Common issues:"
    echo "  1. Certificate not in macOS Keychain"
    echo "  2. Wrong certificate name (SIGNID)"
    echo "  3. iLok account/password incorrect"
    echo "  4. Plugin not built properly"
    echo ""
    echo "Your certificate: $SIGNID"
    echo ""
    echo "To verify certificate:"
    echo "  security find-certificate -c \"$SIGNID\" -p"
    echo ""
    exit 1
fi

echo ""
echo "============================================================================"
echo "SUCCESS: $PLUGIN_NAME.aaxplugin wrapped and signed successfully!"
echo "============================================================================"
echo ""

# === Installation ===
echo "Installing plugin to: $INSTALL_DIR"
echo ""

# Remove old version if exists
if [ -d "$INSTALL_DIR/$PLUGIN_NAME.aaxplugin" ]; then
    echo "Removing old version..."
    rm -rf "$INSTALL_DIR/$PLUGIN_NAME.aaxplugin"
fi

# Copy signed plugin
cp -R "$PLUGIN_PATH" "$INSTALL_DIR/"

if [ $? -eq 0 ]; then
    echo "✓ Plugin installed successfully!"
    echo ""
    echo "Signed plugin: $PLUGIN_PATH"
    echo "Install location: $INSTALL_DIR/$PLUGIN_NAME.aaxplugin"
    echo ""
    echo "Next steps:"
    echo "  1. Launch Pro Tools Ultimate"
    echo "  2. Go to Setup > Plug-ins"
    echo "  3. Verify $PLUGIN_NAME appears in the list"
    echo ""
else
    echo "ERROR: Failed to install plugin"
    exit 1
fi
