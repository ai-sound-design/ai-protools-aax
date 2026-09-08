# Mac Build Guide for PTV2A AAX Plugin

This guide explains how to build the PTV2A plugin for macOS, including setting up embedded Python and creating a Universal Binary that works on both Apple Silicon (M1/M2/M3) and Intel Macs.

## Prerequisites

### 1. Development Tools
- **Xcode** 12.0 or later (includes Apple Clang compiler)
- **CMake** 3.21 or later: `brew install cmake`
- **Git** (for submodules): `brew install git`

### 2. AAX SDK
Download AAX SDK 2.9.0 from Avid Developer:
```bash
# Set AAX SDK path environment variable
export AAX_SDK_PATH="/path/to/aax-sdk-2-9-0"
```

Add to `~/.zshrc` or `~/.bash_profile` for persistence:
```bash
echo 'export AAX_SDK_PATH="/path/to/aax-sdk-2-9-0"' >> ~/.zshrc
```

### 3. PACE Eden SDK (for Code Signing)
Download from iLok.com:
- Install **PACE Eden 5 SDK** for macOS
- Includes `wraptool` at `/Applications/PACEAntiPiracy/Eden/Fusion/Current/bin/wraptool`

---

## Step 1: Prepare Embedded Python (Universal Binary)

### Download Python Universal2 Build

**Option A: Python.org (Recommended)**
1. Download "macOS 64-bit universal2 installer" from [python.org](https://www.python.org/downloads/macos/)
2. Install to default location (`/Library/Frameworks/Python.framework/`)

**Option B: python-build-standalone**
```bash
# Download prebuilt Universal2 Python
curl -L -O https://github.com/indygreg/python-build-standalone/releases/download/20231002/cpython-3.12.0+20231002-aarch64-apple-darwin-install_only.tar.gz
curl -L -O https://github.com/indygreg/python-build-standalone/releases/download/20231002/cpython-3.12.0+20231002-x86_64-apple-darwin-install_only.tar.gz

# Extract both
tar -xzf cpython-3.12.0+20231002-aarch64-apple-darwin-install_only.tar.gz -C python-arm64
tar -xzf cpython-3.12.0+20231002-x86_64-apple-darwin-install_only.tar.gz -C python-x86_64

# Create Universal Binary using lipo (merge both architectures)
# This requires manual binary merging - use Option A instead for simplicity
```

### Create Embedded Python Directory

```bash
cd aax-plugin/Resources

# Create python-macos directory structure
mkdir -p python-macos/bin
mkdir -p python-macos/lib

# Copy Python from installed location (Option A)
cp /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 python-macos/bin/
cp -R /Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12 python-macos/lib/

# Verify Universal Binary
file python-macos/bin/python3
# Should show: Mach-O universal binary with 2 architectures: [x86_64:Mach-O 64-bit executable x86_64] [arm64:Mach-O 64-bit executable arm64]
```

### Install Python Dependencies

```bash
cd aax-plugin/Resources/python-macos

# Install dependencies into embedded Python
bin/python3 -m ensurepip
bin/python3 -m pip install --upgrade pip

# Install required packages
bin/python3 -m pip install \
    httpx \
    soundfile \
    numpy \
    torch \
    torchvision \
    torchaudio \
    imageio-ffmpeg \
    grpcio \
    psycopg2-binary

# Install py-ptsl (for Pro Tools integration)
bin/python3 -m pip install --no-cache-dir git+https://github.com/iluvcapra/py-ptsl.git

# Verify installation
bin/python3 -c "import httpx, soundfile, torch; print('✓ All packages installed')"
```

### Alternative: Create `_pth` File for Portable Python

For a truly relocatable Python, create `python312._pth`:
```bash
cd aax-plugin/Resources/python-macos

cat > python312._pth << EOF
python312.zip
.
lib/python3.12
lib/python3.12/lib-dynload
lib/python3.12/site-packages

# Uncomment to run site.main() automatically
import site
EOF
```

---

## Step 2: Configure CMake Build

### Generate Build System
```bash
cd aax-plugin
mkdir -p build
cd build

# Configure for Release build (Universal Binary)
cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=10.15

# Expected output:
# -- Building Universal Binary for macOS (arm64 + x86_64)
# -- Using AAX SDK: /path/to/aax-sdk-2-9-0
```

### Build Plugin
```bash
# Build AAX target
cmake --build . --config Release --target pt_v2a_AAX -j8

# Output location: build/pt_v2a_artefacts/AAX/PTV2A.aaxplugin
```

### Verify Universal Binary
```bash
cd build/pt_v2a_artefacts/AAX/PTV2A.aaxplugin/Contents/MacOS

# Check plugin binary
file PTV2A
# Should show: Mach-O universal binary with 2 architectures: [x86_64] [arm64e]

# Check embedded Python
file ../Resources/python/bin/python3
# Should show: Mach-O universal binary with 2 architectures: [x86_64] [arm64]
```

---

## Step 3: Sign Plugin with PACE

### Manual Signing
```bash
cd build/pt_v2a_artefacts/AAX

# Sign with PACE wraptool
/Applications/PACEAntiPiracy/Eden/Fusion/Current/bin/wraptool sign \
    --verbose \
    --account YOUR_DEVELOPER_ACCOUNT \
    --password YOUR_PASSWORD \
    --wcguid YOUR_DEVELOPER_WCGUID \
    --in PTV2A.aaxplugin \
    --out PTV2A.aaxplugin

# Verify signature
/Applications/PACEAntiPiracy/Eden/Fusion/Current/bin/wraptool verify \
    --in PTV2A.aaxplugin
```

### Automated Signing (Optional)

Add to `aax-plugin/CMakeLists.txt`:
```cmake
if(APPLE)
    set(PACE_WRAPTOOL "/Applications/PACEAntiPiracy/Eden/Fusion/Current/bin/wraptool")
    set(PACE_ACCOUNT "your_account" CACHE STRING "PACE Account")
    set(PACE_WCGUID "your_wcguid" CACHE STRING "PACE WCGUID")
    
    add_custom_command(TARGET pt_v2a_AAX POST_BUILD
        COMMAND ${PACE_WRAPTOOL} sign
            --verbose
            --account ${PACE_ACCOUNT}
            --wcguid ${PACE_WCGUID}
            --in $<TARGET_FILE_DIR:pt_v2a_AAX>/../..
            --out $<TARGET_FILE_DIR:pt_v2a_AAX>/../..
        COMMENT "Signing AAX Plugin with PACE..."
    )
endif()
```

---

## Step 4: Install Plugin

### Manual Installation
```bash
# Copy to Pro Tools AAX folder
sudo cp -R build/pt_v2a_artefacts/AAX/PTV2A.aaxplugin \
    "/Library/Application Support/Avid/Audio/Plug-Ins/"

# Set correct permissions
sudo chmod -R 755 "/Library/Application Support/Avid/Audio/Plug-Ins/PTV2A.aaxplugin"

# Restart Pro Tools
killall "Pro Tools" 2>/dev/null
```

### Create Installer Script
Create `aax-plugin/install_mac.sh`:
```bash
#!/bin/bash
set -e

PLUGIN_NAME="PTV2A.aaxplugin"
BUILD_PATH="build/pt_v2a_artefacts/AAX/${PLUGIN_NAME}"
INSTALL_PATH="/Library/Application Support/Avid/Audio/Plug-Ins"

echo "Installing ${PLUGIN_NAME} to Pro Tools..."

# Check if plugin exists
if [ ! -d "${BUILD_PATH}" ]; then
    echo "❌ Plugin not found at ${BUILD_PATH}"
    echo "Run: cmake --build build --config Release --target pt_v2a_AAX"
    exit 1
fi

# Install (requires sudo)
sudo cp -R "${BUILD_PATH}" "${INSTALL_PATH}/"
sudo chmod -R 755 "${INSTALL_PATH}/${PLUGIN_NAME}"

echo "✓ Plugin installed successfully"
echo "Restart Pro Tools to load the plugin"
```

Make executable: `chmod +x install_mac.sh`

---

## Step 5: Create DMG Installer (Optional)

### Using `hdiutil`
```bash
cd build/pt_v2a_artefacts/AAX

# Create DMG
hdiutil create -volname "PTV2A Plugin v0.1.0" \
    -srcfolder PTV2A.aaxplugin \
    -ov -format UDZO \
    PTV2A_v0.1.0_macOS.dmg

# Output: PTV2A_v0.1.0_macOS.dmg (ready for distribution)
```

Users drag `PTV2A.aaxplugin` from DMG to `/Library/Application Support/Avid/Audio/Plug-Ins/`

---

## Troubleshooting

### Plugin Not Loading in Pro Tools

**Check signatures:**
```bash
/Applications/PACEAntiPiracy/Eden/Fusion/Current/bin/wraptool verify \
    --in "/Library/Application Support/Avid/Audio/Plug-Ins/PTV2A.aaxplugin"
```

**Check console logs:**
```bash
# Open Console.app and filter for "Pro Tools"
# Or use command line:
log stream --predicate 'process == "Pro Tools"' --level debug
```

**Common issues:**
- Unsigned plugin → Sign with PACE
- Missing dependencies → Check embedded Python
- Wrong architecture → Verify Universal Binary with `file` command

### Python Not Found

**Check embedded Python structure:**
```bash
cd "/Library/Application Support/Avid/Audio/Plug-Ins/PTV2A.aaxplugin/Contents/Resources"
ls -la python/bin/python3
```

**Test Python:**
```bash
./python/bin/python3 -c "import sys; print(sys.version)"
```

### FFmpeg Issues

**Check imageio-ffmpeg:**
```bash
./python/bin/python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

Should output Universal Binary FFmpeg path.

---

## Directory Structure (Final)

```
PTV2A.aaxplugin/
├── Contents/
│   ├── Info.plist
│   ├── MacOS/
│   │   └── PTV2A              # Universal Binary (arm64 + x86_64)
│   └── Resources/
│       └── python/
│           ├── bin/
│           │   └── python3    # Universal Binary Python
│           └── lib/
│               └── python3.12/
│                   └── site-packages/
│                       ├── httpx/
│                       ├── soundfile/
│                       ├── torch/
│                       ├── imageio_ffmpeg/
│                       ├── ptsl_integration/
│                       ├── api/
│                       └── video/
```

---

## Next Steps

1. **Test on Apple Silicon Mac** (M1/M2/M3)
2. **Test on Intel Mac** (x86_64)
3. **Verify Pro Tools integration** (PTSL, audio import)
4. **Create release DMG** for distribution

---

## Additional Resources

- [JUCE macOS Guide](https://docs.juce.com/master/tutorial_ios_application_basics.html)
- [AAX SDK Documentation](https://www.avid.com/alliance-partner-program/aax)
- [PACE Code Signing Guide](https://www.ilok.com/#!license-manager)
- [Python Universal Binaries](https://github.com/indygreg/python-build-standalone)
