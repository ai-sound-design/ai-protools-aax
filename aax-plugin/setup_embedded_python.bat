@echo off
REM Embedded Python Setup Script for AAX Plugin
REM Run this script from: aax-plugin/Resources/

echo ========================================
echo Embedded Python Setup for pt_v2a Plugin
echo ========================================
echo.

cd /d "%~dp0"

REM Check if python folder exists
if not exist "python\python.exe" (
    echo ERROR: Embedded Python not found!
    echo.
    echo Please download python-3.12.x-embed-amd64.zip from:
    echo https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip
    echo.
    echo Extract to: %CD%\python\
    echo.
    pause
    exit /b 1
)

echo [1/5] Found embedded Python
echo.

REM Check if site-packages is enabled
findstr /C:"import site" python\python312._pth >nul
if errorlevel 1 (
    echo WARNING: site-packages not enabled!
    echo Edit python\python312._pth and uncomment: import site
    echo.
    pause
)

echo [2/5] Installing pip...
python\python.exe python\get-pip.py
if errorlevel 1 (
    echo ERROR: pip installation failed
    pause
    exit /b 1
)
echo.

echo [3/5] Installing py-ptsl...
python\python.exe -m pip install -e ..\..\external\py-ptsl
if errorlevel 1 (
    echo ERROR: py-ptsl installation failed
    pause
    exit /b 1
)
echo.

echo [4/5] Installing dependencies...
python\python.exe -m pip install grpcio protobuf soundfile poetry
if errorlevel 1 (
    echo ERROR: Dependencies installation failed
    pause
    exit /b 1
)
echo.

echo [5/5] Creating symlinks for development...
echo.
echo Creating ptsl_integration symlink...
cd python\Lib\site-packages
if exist ptsl_integration (
    echo   Symlink already exists
) else (
    mklink /D ptsl_integration ..\..\..\..\..\..\companion\ptsl_integration
    if errorlevel 1 (
        echo   WARNING: Failed to create symlink ^(requires Admin or Developer Mode^)
        echo   CMake will copy files on build instead
    )
)
cd ..\..\..

echo.
echo Creating standalone_api_client.py symlink...
cd Scripts
if exist standalone_api_client.py (
    echo   Symlink already exists
) else (
    mklink standalone_api_client.py ..\..\..\..\companion\standalone_api_client.py
    if errorlevel 1 (
        echo   WARNING: Failed to create symlink ^(requires Admin or Developer Mode^)
        echo   CMake will copy files on build instead
    )
)
cd ..

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Testing imports...
python.exe -c "import ptsl; print('  OK py-ptsl')"
python.exe -c "from ptsl_integration import import_audio_to_pro_tools; print('  OK ptsl_integration')"
echo.
echo Ready to build plugin!
echo.
pause
