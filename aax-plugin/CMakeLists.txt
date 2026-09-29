# ==============================================================================
# Project Configuration
# ==============================================================================
cmake_minimum_required(VERSION 3.21)

# Project metadata - version is used throughout the build
project(pt_v2a 
    VERSION 0.1.0 
    LANGUAGES CXX
    DESCRIPTION "Pro Tools Video-to-Audio Plugin with AI Generation"
)

# C++17 required for JUCE and modern features
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ==============================================================================
# Platform Configuration
# ==============================================================================
# Mac Universal Binary - supports both Apple Silicon (arm64) and Intel (x86_64)
if(APPLE)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "macOS architectures" FORCE)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "10.15" CACHE STRING "Minimum macOS version" FORCE)
    message(STATUS "Building Universal Binary for macOS (arm64 + x86_64)")
endif()

# ==============================================================================
# External Dependencies
# ==============================================================================

# JUCE Framework (submodule in external/JUCE)
# Provides audio plugin framework, GUI components, and AAX support
add_subdirectory(${CMAKE_SOURCE_DIR}/../external/JUCE ${CMAKE_BINARY_DIR}/juce_build)

# AAX SDK (Avid Audio eXtension SDK)
# Required for Pro Tools plugin compatibility
# Must be set as environment variable: set AAX_SDK_PATH=C:\path\to\aax-sdk-2-9-0
if (NOT DEFINED ENV{AAX_SDK_PATH})
  message(FATAL_ERROR 
    "AAX SDK not found!\n"
    "Set AAX_SDK_PATH environment variable to your AAX SDK root directory.\n"
    "Example: set AAX_SDK_PATH=C:\\SDKs\\aax-sdk-2-9-0"
  )
endif()
set(AAX_SDK_PATH $ENV{AAX_SDK_PATH})
message(STATUS "Using AAX SDK: ${AAX_SDK_PATH}")

# Build AAX SDK as part of this project
add_subdirectory(${AAX_SDK_PATH} ${CMAKE_BINARY_DIR}/aax_sdk_build)

# ==============================================================================
# Plugin Definition
# ==============================================================================
# Creates the AAX plugin target with all metadata
juce_add_plugin(pt_v2a
    # Version inherited from project() - keeps it consistent
    VERSION ${PROJECT_VERSION}
    
    # Plugin Identity (registered with Avid)
    COMPANY_NAME "AI Sound Design"
    PLUGIN_MANUFACTURER_CODE LUDE     # 4-char manufacturer code (must be registered)
    PLUGIN_CODE AISD                  # 4-char plugin ID (unique identifier)
    AAX_IDENTIFIER "com.ai-sound-design.plugin"

    # Plugin Metadata
    PRODUCT_NAME "AI Sound Design"    # Display name in Pro Tools and bundle name; PluginProcessor.h kPluginName must match
FORMATS AAX                       # AAX only (Pro Tools native format)
    PLUGIN_AAX_CATEGORY "Utility"     # Shows in "Utility" menu in Pro Tools
    
    # Plugin Type Configuration
    IS_SYNTH FALSE                    # Audio effect (not synthesizer)
    NEEDS_MIDI_INPUT FALSE            # No MIDI required
    NEEDS_MIDI_OUTPUT FALSE           # No MIDI output
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE # GUI doesn't capture keyboard
    
    # Resources Embedding - CRITICAL for embedded Python + FFmpeg
    COPY_PLUGIN_AFTER_BUILD FALSE     # Disabled - installer handles deployment
    
    # Mac-specific: Universal Binary support
    OSX_ARCHITECTURES "arm64;x86_64"  # Build for both Apple Silicon and Intel
)

# ==============================================================================
# Plugin Source Files
# ==============================================================================
target_sources(pt_v2a PRIVATE         # only for this target
    Source/PluginProcessor.cpp        # Audio processing and business logic
    Source/PluginEditor.cpp           # GUI implementation
    Source/SoundRecommendationsComponent.cpp  # Sound library UI component (TASK 6)
    Source/SettingsPanel.cpp          # Settings dialog: backend URLs, tunnel token
)

# ==============================================================================
# Python Scripts Sync (BEFORE embedding Resources)
# ==============================================================================
# Path configuration
set(COMPANION_DIR ${CMAKE_SOURCE_DIR}/../companion)
set(RESOURCES_DIR ${CMAKE_SOURCE_DIR}/Resources)
set(RESOURCES_PYTHON_DIR ${RESOURCES_DIR}/python)
set(RESOURCES_PYTHON_SCRIPTS ${RESOURCES_PYTHON_DIR}/Scripts)

# Platform-specific site-packages path
if(WIN32)
    set(RESOURCES_PYTHON_SITEPACKAGES ${RESOURCES_PYTHON_DIR}/Lib/site-packages)
elseif(APPLE)
    set(RESOURCES_PYTHON_SITEPACKAGES ${RESOURCES_PYTHON_DIR}/lib/python3.12/site-packages)
else()
    set(RESOURCES_PYTHON_SITEPACKAGES ${RESOURCES_PYTHON_DIR}/lib/python3.12/site-packages)
endif()

# STEP 1: Sync Python scripts from companion/ to Resources/ (runs FIRST)
add_custom_command(TARGET pt_v2a_AAX PRE_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Syncing Python scripts from companion/ to Resources/..."
    COMMAND ${CMAKE_COMMAND} -E make_directory ${RESOURCES_PYTHON_SCRIPTS}
    COMMAND ${CMAKE_COMMAND} -E make_directory ${RESOURCES_PYTHON_SITEPACKAGES}
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${COMPANION_DIR}/standalone_api_client.py
        ${RESOURCES_PYTHON_SCRIPTS}/standalone_api_client.py

    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${COMPANION_DIR}/sound_search_api_client.py
        ${RESOURCES_PYTHON_SCRIPTS}/sound_search_api_client.py
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${COMPANION_DIR}/spotting_client.py
        ${RESOURCES_PYTHON_SCRIPTS}/spotting_client.py
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${COMPANION_DIR}/hybrid_client.py
        ${RESOURCES_PYTHON_SCRIPTS}/hybrid_client.py
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${COMPANION_DIR}/ptsl_integration
        ${RESOURCES_PYTHON_SITEPACKAGES}/ptsl_integration
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${COMPANION_DIR}/api
        ${RESOURCES_PYTHON_SITEPACKAGES}/api
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${COMPANION_DIR}/video
        ${RESOURCES_PYTHON_SITEPACKAGES}/video
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${COMPANION_DIR}/cli
        ${RESOURCES_PYTHON_SITEPACKAGES}/cli
    COMMENT "Syncing companion/ Python modules to Resources/ before embedding"
    VERBATIM
)

# ==============================================================================
# Embed Resources Folder
# ==============================================================================
# JUCE's COPY_PLUGIN_AFTER_BUILD does NOT automatically copy the Resources/ folder!
# We must explicitly add a post-build command to copy it into the .aaxplugin bundle.
# STEP 2: Copy Resources/ to plugin bundle (runs AFTER Python sync)
add_custom_command(TARGET pt_v2a_AAX POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying Resources folder to plugin bundle..."
    # Copy only python/ and txt files (exclude python-macos and python-macintel source dirs)
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${CMAKE_CURRENT_SOURCE_DIR}/Resources/python
        $<TARGET_FILE_DIR:pt_v2a_AAX>/../Resources/python
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_CURRENT_SOURCE_DIR}/Resources/_embedded_python_here.txt
        $<TARGET_FILE_DIR:pt_v2a_AAX>/../Resources/_embedded_python_here.txt
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_CURRENT_SOURCE_DIR}/Resources/python_runtime_requirements.txt
        $<TARGET_FILE_DIR:pt_v2a_AAX>/../Resources/python_runtime_requirements.txt
    # Remove any accidentally copied source Python directories
    COMMAND ${CMAKE_COMMAND} -E remove_directory $<TARGET_FILE_DIR:pt_v2a_AAX>/../Resources/python-macos
    COMMAND ${CMAKE_COMMAND} -E remove_directory $<TARGET_FILE_DIR:pt_v2a_AAX>/../Resources/python-macintel
    COMMENT "Embedding Python runtime and scripts into plugin bundle"
    VERBATIM
)

# ==============================================================================
# Compile Options
# ==============================================================================
# Disable JUCE web browser component (not needed), enable cURL for HTTP requests
target_compile_definitions(pt_v2a PRIVATE
    JUCE_WEB_BROWSER=0                # No web browser component (reduces binary size)
    JUCE_USE_CURL=1                   # Enable cURL for MMAudio API calls
    JucePlugin_AAXDisableAudioSuite=1 # Insert-only: the plugin drives Pro Tools via PTSL, it is not an offline clip processor
    JucePlugin_AAXDisableDynamicProcessing=1 # AAX_eProperty_Constraint_AlwaysProcess: the sound preview is mixed into processBlock() on a silent track, which Pro Tools' Dynamic Plug-In Processing would otherwise stop calling
)

# ==============================================================================
# Link Dependencies
# ==============================================================================
target_link_libraries(pt_v2a PRIVATE
    juce::juce_audio_processors       # Core audio plugin framework
    juce::juce_audio_formats          # Audio file I/O (WAV, MP3, FLAC) - TASK 7
    juce::juce_audio_devices          # Audio I/O and transport - TASK 7
    juce::juce_gui_basics             # Basic GUI components
    juce::juce_gui_extra              # Extended GUI features (for rich UI)
)

# ==============================================================================
# Python Scripts Integration - NOTE: Moved to PRE_BUILD above!
# ==============================================================================
# Strategy: Python scripts are now synced during pt_v2a_AAX PRE_BUILD phase
# (see lines 78-103 above) to ensure they're always up-to-date when building
# the AAX target, which is what you typically use during development.
#
# DEVELOPMENT WORKFLOW:
#   Just build the AAX target - Python scripts sync automatically:
#     cmake --build . --config Debug --target pt_v2a_AAX
#   
#   The PRE_BUILD command syncs these modules from companion/ to Resources/:
#     - standalone_api_client.py → Scripts/
#     - ptsl_integration/ → site-packages/
#     - api/ → site-packages/
#     - video/ → site-packages/
#     - cli/ → site-packages/
#
# ALTERNATIVE (symbolic links for live editing):
#   Windows CMD:
#     cd Resources\python\Scripts
#     mklink standalone_api_client.py ..\..\..\..\companion\standalone_api_client.py
#     cd Resources\python\Lib\site-packages
#     mklink /D ptsl_integration ..\..\..\..\companion\ptsl_integration
#     mklink /D api ..\..\..\..\companion\api
#     mklink /D video ..\..\..\..\companion\video
#     mklink /D cli ..\..\..\..\companion\cli
#
#   Benefits: Edit companion/ files directly, changes immediately available
#   Note: Delete symlinks before release builds to ensure self-contained plugin

# ==============================================================================
# Embedded Python Runtime
# ==============================================================================
# IMPORTANT: JUCE copies Resources/ folder into the .aaxplugin bundle because
# we set COPY_PLUGIN_AFTER_BUILD TRUE in juce_add_plugin() above.
#
# Expected Resources/ structure (must be prepared manually):
#   Resources/
#     python/
#       python.exe                    # Python 3.12 embedded distribution
#       python312.dll
#       python312.zip                 # Standard library
#       Lib/
#         site-packages/              # Python packages (py-ptsl, grpcio, etc.)
#           ptsl_integration/         # ← Synced by CMake (see above)
#       Scripts/
#         standalone_api_client.py    # ← Synced by CMake (see above)
#
# The plugin runtime locates python.exe relative to the .aaxplugin bundle path.

# ==============================================================================
# Plugin Installation (Manual)
# ==============================================================================
# Pro Tools AAX plugins must be installed to:
#   C:\Program Files\Common Files\Avid\Audio\Plug-Ins\
#
# IMPORTANT: Requires Administrator permissions!
#
# Manual installation steps:
#   1. Build the project (generates build/pt_v2a_artefacts/AAX/pt_v2a.aaxplugin/)
#   2. Copy the .aaxplugin folder to Avid Plug-Ins directory (run as admin)
#   3. Restart Pro Tools
#