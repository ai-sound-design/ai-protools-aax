# Python Setup for AI Sound Design plugin

This directory contains Python runtime setup for the AAX plugin.

## 🚀 Quick Start

### Automated Setup (Recommended)

**Windows:**
```powershell
.\setup_python_windows.ps1
```

**macOS:**
```bash
chmod +x setup_python_mac.sh
./setup_python_mac.sh
```

---

## 📁 Files Overview

| File | Description |
|------|-------------|
| `setup_python_windows.ps1` | **Automated Windows setup** - Downloads python-build-standalone, installs dependencies |
| `setup_python_mac.sh` | **Automated macOS setup** - Downloads Universal2 Python, installs dependencies |
| `python_runtime_requirements.txt` | **Minimal dependencies** - Only runtime packages (no dev tools) |
| `EMBEDDED_PYTHON_SETUP.md` | **Complete guide** - Migration, manual setup, troubleshooting |

---

## 🎯 What's New

### Migration to python-build-standalone

We've switched from **python.org embedded distribution** to **python-build-standalone** for:

✅ **Cross-platform consistency** - Same Python source for Windows + Mac  
✅ **Smaller size** - ~90 MB saved per platform  
✅ **Better performance** - PGO + LTO optimized builds  
✅ **Universal Binary** - macOS arm64 + x86_64 in one  
✅ **Cleaner** - No dev tools (poetry, pytest, etc.)

### Size Comparison

```
Old Setup (python.org):
├── python.exe + stdlib:      ~15 MB
├── site-packages (bloated): ~200 MB
├── Dev tools (poetry, etc):  ~80 MB
└── Total:                   ~215 MB ❌

New Setup (python-build-standalone):
├── Python + stdlib:          ~25 MB
├── site-packages (minimal): ~105 MB
└── Total:                   ~130 MB ✅

Savings: ~90 MB per platform!
```

---

## 📦 What Gets Installed

### Runtime Dependencies Only

```
grpcio          # Pro Tools PTSL communication
httpx           # API calls (MMAudio, Sound Search)
soundfile       # Audio file I/O
numpy           # Array operations
imageio-ffmpeg  # FFmpeg binaries (cross-platform)
psycopg2-binary # PostgreSQL (Sound Search database)
py-ptsl         # Pro Tools integration library
```

### What's NOT Installed (Old Setup Had These)

```
❌ poetry        # Build tool (not needed at runtime)
❌ pytest        # Testing framework
❌ build         # Build frontend
❌ virtualenv    # Virtual environment manager
❌ dulwich       # Git implementation
❌ pygments      # Syntax highlighting
❌ zstandard     # Compression (unused)
❌ keyring       # Credential storage (unused)
```

---

## 🔧 Directory Structure

### After Setup

**Windows:**
```
Resources/
└── python-windows/
    ├── python.exe
    ├── python3.dll
    ├── python312.dll
    ├── Lib/
    │   └── site-packages/
    │       ├── grpcio/
    │       ├── httpx/
    │       ├── soundfile/
    │       ├── numpy/
    │       ├── imageio_ffmpeg/
    │       ├── psycopg2/
    │       ├── ptsl_integration/  # Synced from companion/
    │       ├── api/               # Synced from companion/
    │       └── video/             # Synced from companion/
    └── Scripts/
        └── standalone_api_client.py  # Synced from companion/
```

**macOS:**
```
Resources/
└── python-macos/
    ├── bin/
    │   └── python3  # Universal Binary (arm64 + x86_64)
    └── lib/
        └── python3.12/
            └── site-packages/
                ├── grpcio/
                ├── httpx/
                ├── soundfile/
                ├── numpy/
                ├── imageio_ffmpeg/
                ├── psycopg2/
                ├── ptsl_integration/  # Synced from companion/
                ├── api/               # Synced from companion/
                └── video/             # Synced from companion/
```

---

## 🛠️ Troubleshooting

### Setup Script Fails

**Check internet connection:**
```bash
# Test download URL
curl -I https://github.com/astral-sh/python-build-standalone/releases
```

**Run with force flag:**
```powershell
# Windows
.\setup_python_windows.ps1 -Force

# macOS
./setup_python_mac.sh --force
```

### Package Import Errors

**Verify installation:**
```powershell
# Windows
.\python-windows\python.exe -c "import grpcio, httpx, soundfile; print('OK')"

# macOS
./python-macos/bin/python3 -c "import grpcio, httpx, soundfile; print('OK')"
```

**Reinstall packages:**
```bash
python -m pip install --force-reinstall --no-cache-dir [package]
```

---

## 📚 Documentation

- **Full Setup Guide:** [EMBEDDED_PYTHON_SETUP.md](EMBEDDED_PYTHON_SETUP.md)
- **Mac Build Guide:** [MAC_BUILD_GUIDE.md](MAC_BUILD_GUIDE.md)

---

## 🔄 Migration from Old Setup

If you have existing `python/` directory from python.org:

1. **Backup:**
   ```bash
   mv python python_backup_$(date +%Y%m%d)
   ```

2. **Run new setup:**
   ```bash
   ./setup_python_windows.ps1  # or setup_python_mac.sh
   ```

3. **Test:**
   ```bash
   # Should work without changes to C++ code
   cmake --build build --target pt_v2a_AAX
   ```

4. **Remove backup (after testing):**
   ```bash
   rm -rf python_backup_*
   ```

---

## ⚙️ CMake Integration

Python scripts are automatically synced during build:

```cmake
# PRE_BUILD: Sync Python modules from companion/
add_custom_command(TARGET pt_v2a_AAX PRE_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${COMPANION_DIR}/ptsl_integration
        ${RESOURCES_PYTHON_SITEPACKAGES}/ptsl_integration
    # ... more modules
)

# POST_BUILD: Copy Resources/ to plugin bundle
add_custom_command(TARGET pt_v2a_AAX POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${CMAKE_CURRENT_SOURCE_DIR}/Resources
        $<TARGET_FILE_DIR:pt_v2a_AAX>/../Resources
)
```

---

## 🎓 Additional Resources

- [python-build-standalone GitHub](https://github.com/astral-sh/python-build-standalone)
- [Python Packaging Guide](https://packaging.python.org/)
- [JUCE AAX Format Documentation](https://docs.juce.com/master/tutorial_create_projucer_basic_plugin.html)
