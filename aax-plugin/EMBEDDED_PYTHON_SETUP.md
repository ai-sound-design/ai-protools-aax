# Embedded Python Setup for AAX Plugin

The plugin uses **python-build-standalone** for embedded Python 3.12 with optimized builds and minimal size.

## Why python-build-standalone?

- ✅ **Cross-platform**: Same setup for Windows + macOS
- ✅ **Optimized**: PGO + LTO builds (~20% faster)
- ✅ **Smaller**: ~90 MB less than python.org embed
- ✅ **Universal Binary**: macOS arm64 + x86_64 in one
- ✅ **Clean**: No unnecessary dev tools (poetry, pytest, etc.)

## Quick Setup (Automated) ⭐ Recommended

### Windows
```powershell
cd aax-plugin\Resources
.\setup_python_windows.ps1

# Optional: Create symlink (requires Admin)
# cmd /c mklink /D python python-windows
```

### macOS
```bash
cd aax-plugin/Resources
chmod +x setup_python_mac.sh
./setup_python_mac.sh

# Optional: Create symlink
# ln -s python-macos python
```

The automated scripts will:
1. Download python-build-standalone (optimized build)
2. Extract to `python-windows/` or `python-macos/`
3. Install only required runtime dependencies
4. Verify installation

**Result:** ~130 MB Python with all dependencies (vs ~215 MB with old setup)

---

## Manual Setup (Advanced)

If you prefer manual installation, follow the platform-specific steps below.

### Windows Manual Setup

#### 1. Download Python

```powershell
cd aax-plugin\Resources

# Download python-build-standalone
$VERSION = "3.12.7"
$DATE = "20241016"
$BUILD = "cpython-$VERSION+$DATE-x86_64-pc-windows-msvc-install_only_stripped"
$URL = "https://github.com/astral-sh/python-build-standalone/releases/download/$DATE/$BUILD.tar.gz"

Invoke-WebRequest -Uri $URL -OutFile python.tar.gz
```

#### 2. Extract

```powershell
# Extract using tar (Windows 10+)
tar -xzf python.tar.gz
Rename-Item "python" "python-windows"
Remove-Item python.tar.gz

# Optional: Create symlink (requires Administrator)
# cmd /c mklink /D python python-windows
```

#### 3. Install Dependencies

```powershell
cd python-windows

# Upgrade pip
.\python.exe -m ensurepip --upgrade
.\python.exe -m pip install --upgrade pip

# Install runtime dependencies (only what's needed)
.\python.exe -m pip install --no-cache-dir `
    grpcio>=1.60.0 `
    httpx>=0.27.0 `
    soundfile>=0.12.0 `
    numpy>=1.24.0 `
    imageio-ffmpeg>=0.5.0 `
    psycopg2-binary>=2.9.0

# Install py-ptsl as a real copy of the pinned submodule (not editable: that would only
# leave a path link to this checkout, and the plugin would fail on any other machine)
.\python.exe -m pip install ..\..\..\external\py-ptsl
```

---

### macOS Manual Setup

#### 1. Download Python

```bash
cd aax-plugin/Resources

# Detect architecture
ARCH=$(uname -m)
VERSION="3.12.7"
DATE="20241016"

if [ "$ARCH" = "arm64" ]; then
    BUILD="cpython-${VERSION}+${DATE}-aarch64-apple-darwin-install_only_stripped"
else
    BUILD="cpython-${VERSION}+${DATE}-x86_64-apple-darwin-install_only_stripped"
fi

# Download
curl -L -O "https://github.com/astral-sh/python-build-standalone/releases/download/${DATE}/${BUILD}.tar.gz"
```

#### 2. Extract

```bash
# Extract
mkdir python-macos
tar -xzf ${BUILD}.tar.gz -C python-macos --strip-components=1
rm ${BUILD}.tar.gz

# Optional: Create symlink
# ln -s python-macos python

# Verify it's a proper Python installation
file python-macos/bin/python3
# Should show: Mach-O 64-bit executable (arm64 or x86_64)
```

#### 3. Install Dependencies

```bash
cd python-macos

# Upgrade pip
./bin/python3 -m ensurepip --upgrade
./bin/python3 -m pip install --upgrade pip

# Install runtime dependencies
./bin/python3 -m pip install --no-cache-dir \
    grpcio>=1.60.0 \
    httpx>=0.27.0 \
    soundfile>=0.12.0 \
    numpy>=1.24.0 \
    imageio-ffmpeg>=0.5.0 \
    psycopg2-binary>=2.9.0

# Install py-ptsl as a real copy of the pinned submodule (not editable: that would only
# leave a path link to this checkout, and the plugin would fail on any other machine)
./bin/python3 -m pip install ../../../external/py-ptsl
```

---

## Verify Installation

### Windows
```powershell
cd aax-plugin\Resources\python-windows

# Test Python
.\python.exe --version
.\python.exe -c "import sys; print(sys.executable)"

# Test packages
.\python.exe -c @"
import grpcio, httpx, soundfile, numpy, imageio_ffmpeg, psycopg2
print('✓ All packages installed successfully')
"@
```

### macOS
```bash
cd aax-plugin/Resources/python-macos

# Test Python
./bin/python3 --version
./bin/python3 -c "import sys; print(sys.executable)"

# Test packages
./bin/python3 -c "
import grpcio, httpx, soundfile, numpy, imageio_ffmpeg, psycopg2
print('✓ All packages installed successfully')
"
```

---

## Directory Structure

### Windows
```
Resources/
├── python-windows/          # python-build-standalone
│   ├── python.exe
│   ├── python3.dll
│   ├── python312.dll
│   ├── Lib/
│   │   └── site-packages/
│   │       ├── grpcio/
│   │       ├── httpx/
│   │       ├── soundfile/
│   │       ├── numpy/
│   │       ├── imageio_ffmpeg/
│   │       ├── psycopg2/
│   │       ├── ptsl_integration/
│   │       ├── api/
│   │       └── video/
│   └── Scripts/
│       └── standalone_api_client.py
└── python -> python-windows/  # Optional symlink
```

### macOS
```
Resources/
├── python-macos/            # python-build-standalone
│   ├── bin/
│   │   └── python3          # Universal Binary (arm64 + x86_64)
│   └── lib/
│       └── python3.12/
│           └── site-packages/
│               ├── grpcio/
│               ├── httpx/
│               ├── soundfile/
│               ├── numpy/
│               ├── imageio_ffmpeg/
│               ├── psycopg2/
│               ├── ptsl_integration/
│               ├── api/
│               └── video/
└── python -> python-macos/  # Optional symlink
```

---

## Size Comparison

| Setup | Windows | macOS | Total |
|-------|---------|-------|-------|
| **Old (python.org embed)** | ~215 MB | N/A | ~215 MB |
| **New (python-build-standalone)** | ~130 MB | ~120 MB | ~250 MB |
| **Both platforms** | | | ~250 MB |

**Savings:** ~90 MB per platform by removing dev tools (poetry, pytest, build, etc.)

---

## Migration from Old Setup

If you have an existing python.org embedded Python:

### Backup Old Python
```powershell
# Windows
cd aax-plugin\Resources
Rename-Item python python_backup_$(Get-Date -Format 'yyyyMMdd')
```

```bash
# macOS
cd aax-plugin/Resources
mv python python_backup_$(date +%Y%m%d)
```

### Run Setup Script
Then run the automated setup script for your platform (see "Quick Setup" above).

---

## Troubleshooting

### Windows: "tar: command not found"

**Solution:** Install 7-Zip and extract manually:
```powershell
# Extract with 7-Zip
& "C:\Program Files\7-Zip\7z.exe" x python.tar.gz
& "C:\Program Files\7-Zip\7z.exe" x python.tar
```

### macOS: "Permission denied"

**Solution:** Make script executable:
```bash
chmod +x setup_python_mac.sh
```

### Package Installation Fails

**Solution:** Clear pip cache and retry:
```bash
# Windows
.\python.exe -m pip cache purge
.\python.exe -m pip install --no-cache-dir [package]

# macOS
./bin/python3 -m pip cache purge
./bin/python3 -m pip install --no-cache-dir [package]
```

### Import Error at Runtime

**Check embedded Python path in C++:**
```cpp
// PluginProcessor.cpp should find:
// Windows: Resources/python-windows/python.exe
// macOS: Resources/python-macos/bin/python3
```

---

## Development Workflow

### Python Scripts Sync

CMake automatically syncs companion/ Python scripts to Resources/ during build:

```cmake
# Synced automatically (PRE_BUILD):
companion/standalone_api_client.py → Resources/python/Scripts/
companion/ptsl_integration/        → Resources/python/Lib/site-packages/
companion/api/                     → Resources/python/Lib/site-packages/
companion/video/                   → Resources/python/Lib/site-packages/
```

### Live Editing (Optional)

For development, create symlinks instead of copying:

**Windows (requires Admin):**
```cmd
cd Resources\python-windows\Lib\site-packages
mklink /D ptsl_integration ..\..\..\..\companion\ptsl_integration
mklink /D api ..\..\..\..\companion\api
mklink /D video ..\..\..\..\companion\video
```

**macOS:**
```bash
cd Resources/python-macos/lib/python3.12/site-packages
ln -s ../../../../companion/ptsl_integration ptsl_integration
ln -s ../../../../companion/api api
ln -s ../../../../companion/video video
```

---

## Next Steps

1. ✅ Run setup script for your platform
2. ✅ Verify installation with test commands
3. ✅ Build plugin: `cmake --build build --target pt_v2a_AAX`
4. ✅ Test in Pro Tools

For Mac-specific build instructions, see [MAC_BUILD_GUIDE.md](MAC_BUILD_GUIDE.md)
