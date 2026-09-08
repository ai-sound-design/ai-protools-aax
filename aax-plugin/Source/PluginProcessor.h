#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_audio_formats/juce_audio_formats.h>  // TASK 7: Audio format I/O for preview
#include <juce_audio_devices/juce_audio_devices.h>  // TASK 7: AudioTransportSource for preview

/**
 * @class PtV2AProcessor
 * @brief Pro Tools Video-to-Audio Plugin Processor
 * 
 * This AudioProcessor handles the core plugin logic:
 * - Audio pass-through (no real-time processing)
 * - Video-to-Audio generation via MMAudio API
 * - Integration with Pro Tools via PTSL (Pro Tools Scripting Library)
 * - Embedded Python runtime for API communication
 * 
 * Architecture:
 *   User Action (GUI) → generateAudioFromVideo() → Python subprocess → MMAudio API
 *   → Audio file → PTSL Import → Pro Tools Session
 */
class PtV2AProcessor : public juce::AudioProcessor
{
public:
    //==============================================================================
    // Construction / Destruction
    //==============================================================================
    
    PtV2AProcessor();
    ~PtV2AProcessor() override = default;

    //==============================================================================
    // Audio Processing Lifecycle (JUCE AudioProcessor Interface)
    //==============================================================================
    
    /** 
     * Called before playback starts
     * Prepares the processor for audio processing with given sample rate and block size
     * @param sampleRate      The sample rate that will be used for processing (e.g., 48000 Hz)
     * @param samplesPerBlock The maximum number of samples that will be in each processing block
     */
    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    
    /** 
     * Called after playback stops
     * Release any resources allocated in prepareToPlay()
     * Note: This is a pass-through plugin, so no resources need to be released
     */
    void releaseResources() override;
    
    /** 
     * Validate audio bus layout (channel configuration)
     * This plugin requires matching input/output channel counts (mono or stereo only)
     * @param layouts The proposed bus layout to validate
     * @return true if layout is supported, false otherwise
     */
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    
    /** 
     * Process audio block in real-time
     * This is a utility plugin that does NOT modify audio (pass-through only)
     * Audio generation happens asynchronously via MMAudio API, not in real-time
     * @param buffer Audio buffer to process (input/output)
     * @param midiMessages MIDI messages (unused - plugin doesn't process MIDI)
     */
    void processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midiMessages) override;

    //==============================================================================
    // Editor (GUI) Management
    //==============================================================================
    
    /** Creates the plugin GUI editor */
    juce::AudioProcessorEditor* createEditor() override;
    
    /** Returns true if plugin has a GUI editor */
    bool hasEditor() const override { return true; }

    //==============================================================================
    // Plugin Metadata (JUCE AudioProcessor Interface)
    //==============================================================================
    
    /** Plugin name displayed in Pro Tools */
    const juce::String getName() const override { return "PTV2A"; }  // Match CMakeLists.txt PRODUCT_NAME
    
    /** This plugin does not accept MIDI input */
    bool acceptsMidi() const override { return false; }
    
    /** This plugin does not produce MIDI output */
    bool producesMidi() const override { return false; }
    
    /** This is not a MIDI effect plugin */
    bool isMidiEffect() const override { return false; }
    
    /** No audio tail/reverb - plugin stops immediately when audio stops */
    double getTailLengthSeconds() const override { return 0.0; }

    //==============================================================================
    // Preset/Program Management (JUCE AudioProcessor Interface)
    //==============================================================================
    // This plugin does not use presets/programs - all state is in the GUI
    
    /** Number of programs/presets (1 = no program support) */
    int getNumPrograms() override { return 1; }
    
    /** Currently selected program index (always 0) */
    int getCurrentProgram() override { return 0; }
    
    /** Set current program (no-op - no presets) */
    void setCurrentProgram (int index) override { juce::ignoreUnused(index); }
    
    /** Get program name (empty - no presets) */
    const juce::String getProgramName (int index) override { juce::ignoreUnused(index); return {}; }
    
    /** Change program name (no-op - no presets) */
    void changeProgramName (int index, const juce::String& newName) override 
    { 
        juce::ignoreUnused(index, newName); 
    }

    //==============================================================================
    // State Serialization (JUCE AudioProcessor Interface)
    //==============================================================================
    
    /** 
     * Save plugin state to binary data
     * Called when Pro Tools session is saved
     * TODO: Currently stores empty JSON - should save UI parameters (prompt, seed, etc.)
     * @param destData Output buffer to write state to
     */
    void getStateInformation (juce::MemoryBlock& destData) override;
    
    /** 
     * Restore plugin state from binary data
     * Called when Pro Tools session is loaded
     * TODO: Currently ignores data - should restore UI parameters
     * @param data Pointer to state data
     * @param sizeInBytes Size of state data in bytes
     */
    void setStateInformation (const void* data, int sizeInBytes) override;

    //==============================================================================
    // MMAudio API Integration (Custom Plugin Functionality)
    //==============================================================================
    
    /**
     * Model provider selection
     * Determines which API to use for audio generation
     */
    enum class ModelProvider
    {
        MMAudio,              ///< MMAudio API (port 8000, 16kHz/44.1kHz)
        HunyuanVideoFoley    ///< HunyuanVideo-Foley API (port 8001, 48kHz professional Foley)
    };
    
    // Default configuration values
    static constexpr int DEFAULT_SEED = 42;                    ///< Default random seed for reproducibility
    static const juce::String DEFAULT_NEGATIVE_PROMPT;         ///< Default sounds to avoid ("voices, music")
    static const juce::String DEFAULT_API_URL;                 ///< Default MMAudio API endpoint
    
    /** 
     * Generate audio from video file using MMAudio or HunyuanVideo-Foley API
     * 
     * This method spawns a Python subprocess that:
     * 1. Uploads video to selected API (FastAPI server)
     * 2. Sends text prompt with generation parameters
     * 3. Waits for audio generation (can take 30-60 seconds)
     * 4. Downloads generated audio file (WAV format)
     * 5. Automatically imports audio into Pro Tools via PTSL
     * 
     * The process is non-blocking - GUI remains responsive during generation.
     * 
     * @param videoFile         Path to input video file (MP4, MOV, AVI, MKV, etc.)
     * @param prompt            Text prompt describing desired audio (e.g., "thunder and rain")
     * @param negativePrompt    Sounds to avoid (default: "voices, music")
     * @param seed              Random seed for reproducibility (default: 42)
     * @param modelProvider     Which API to use (MMAudio or HunyuanVideoFoley)
     * @param modelSize         Model size string (e.g., "large_44k_v2", "xl", "xxl")
     * @param videoClipOffset   Timeline position where video clip starts (e.g., "00:02")
     *                          Used to calculate offset into source video for trimming.
     *                          Empty string means video starts at timeline beginning (00:00:00:00)
     * @param timelineInSeconds Timeline selection start in seconds (for trimming calculation)
     * @param timelineOutSeconds Timeline selection end in seconds (for trimming calculation)
     * @param errorMessage      [OUT] Pointer to string that will receive error details on failure
     *                          Pass nullptr if you don't need error details
     * 
     * @return Path to generated audio file (WAV) on success, empty string on failure
     *         Check errorMessage parameter for failure reason
     * 
     * @note This is an asynchronous operation - the method spawns a subprocess
     *       and returns immediately. Check process output for completion status.
     */
    juce::String generateAudioFromVideo (
        const juce::File& videoFile,
        const juce::String& prompt,
        const juce::String& negativePrompt = DEFAULT_NEGATIVE_PROMPT,
        int seed = DEFAULT_SEED,
        ModelProvider modelProvider = ModelProvider::MMAudio,
        const juce::String& modelSize = "large_44k_v2",
        const juce::String& videoClipOffset = "",
        float timelineInSeconds = 0.0f,
        float timelineOutSeconds = 0.0f,
        bool autoDetectClipBounds = false,
        float clipStartSeconds = -1.0f,
        float clipEndSeconds = -1.0f,
        bool fullPrecision = false,
        juce::String* errorMessage = nullptr
    );
    
    /**
     * Generate audio from text prompt only (T2A mode) - no video input
     * 
     * T2A (Text-to-Audio) workflow:
     * - Uses MMAudio model only (HunyuanVideo-Foley not supported)
     * - Generates audio based on text prompt and specified duration
     * - No video file required
     * 
     * @param prompt Text description of desired audio (e.g., "thunder and rain")
     * @param duration Audio duration in seconds (4-12s supported)
     * @param negativePrompt Negative prompt (things to avoid)
     * @param seed Random seed for reproducibility
     * @param modelSize MMAudio model size ("large_44k_v2", etc.)
     * @param errorMessage Optional output parameter for error details
     * 
     * @return Path to generated audio file (WAV) on success, empty string on failure
     * 
     * @note Asynchronous operation - returns immediately, audio generation runs in subprocess
     */
    juce::String generateAudioTextOnly (
        const juce::String& prompt,
        float duration,
        const juce::String& negativePrompt = DEFAULT_NEGATIVE_PROMPT,
        int seed = DEFAULT_SEED,
        const juce::String& modelSize = "large_44k_v2",
        juce::String* errorMessage = nullptr
    );
    
    /** 
     * Get configured API URL from config.json
     * Reads companion/api/config.json and returns appropriate URL based on use_cloudflared setting
     * 
     * @param service Service name ("mmaudio" or "hunyuan")
     * @return Configured API URL (cloudflared or direct), or DEFAULT_API_URL on error
     */
    juce::String getConfiguredAPIUrl (const juce::String& service = "mmaudio");
    
    /** 
     * Check if MMAudio API server is reachable
     * Sends HTTP GET request to /health endpoint
     * 
     * @param apiUrl API base URL (default: "http://localhost:8000")
     * @return true if API responds successfully, false otherwise
     */
    bool isAPIAvailable (const juce::String& apiUrl = DEFAULT_API_URL);
    
    //==============================================================================
    // Cloudflare Access Credential Management
    //==============================================================================
    
    /**
     * Get Cloudflare Access Client ID from config.json
     * @return Client ID string, or empty string if not configured
     */
    juce::String getCloudflareClientId();
    
    /**
     * Get Cloudflare Access Client Secret from config.json
     * @return Client Secret string, or empty string if not configured
     */
    juce::String getCloudflareClientSecret();
    
    /**
     * Save Cloudflare Access credentials to config.json
     * Updates existing config while preserving other settings
     * 
     * @param clientId CF-Access-Client-Id (Service Token identifier)
     * @param clientSecret CF-Access-Client-Secret (Service Token secret)
     * @return true if credentials saved successfully, false on file write error
     */
    bool saveCloudflareCredentials (const juce::String& clientId, 
                                    const juce::String& clientSecret);
    
    /**
     * Test Cloudflare Access credentials by connecting to API
     * Calls Python subprocess to validate credentials
     * 
     * @param clientId CF-Access-Client-Id to test
     * @param clientSecret CF-Access-Client-Secret to test
     * @param errorMessage [OUT] Error details if test fails
     * @return true if credentials are valid and API accessible
     */
    bool testCloudflareCredentials (const juce::String& clientId,
                                    const juce::String& clientSecret,
                                    juce::String* errorMessage = nullptr);
    
    /** 
     * Get path to Python API client script (standalone_api_client.py)
     * Searches in following locations (in order):
     * 1. Embedded in plugin bundle: Resources/python/Scripts/standalone_api_client.py
     * 2. Development fallback: ../../companion/standalone_api_client.py
     * 
     * @return File object pointing to API client script
     */
    juce::File getAPIClientScript();
    
    /** 
     * Get path to Python executable
     * Searches in following locations (in order):
     * 1. Embedded Python: Resources/python/python.exe (self-contained)
     * 2. System Python: "python.exe" (fallback, may lack dependencies)
     * 
     * @return Path to python.exe
     */
    juce::String getPythonExecutable();
    
    //==============================================================================
    // Logging
    //==============================================================================
    
    /**
     * Initialize file-based logging system
     * Creates log file in user's AppData directory
     * Should be called once during plugin initialization
     * 
     * Log file location:
     *   Windows: C:\Users\[username]\AppData\Roaming\anonymous\PTV2A\PTV2A.log
     *   macOS: ~/Library/Application Support/anonymous/PTV2A/PTV2A.log
     * 
     * @return true if logger initialized successfully
     */
    static bool initializeLogger();
    
    /**
     * Get path to current log file
     * @return Full path to log file, or empty string if logger not initialized
     */
    static juce::File getLogFile();

    //==============================================================================
    // Timeline Selection & Video Trimming
    //==============================================================================
    
    /**
     * Video selection information from Pro Tools timeline
     * Returned by getVideoSelectionInfo()
     */
    struct VideoSelectionInfo
    {
        bool success;                  ///< True if selection read successfully
        juce::String inTime;           ///< In-point timecode (e.g., "00:00:05:00")
        juce::String outTime;          ///< Out-point timecode (e.g., "00:00:10:00")
        float durationSeconds;         ///< Duration in seconds (e.g., 5.0)
        float inSeconds;               ///< In-point in seconds (e.g., 5.0)
        float outSeconds;              ///< Out-point in seconds (e.g., 10.0)
        float fps;                     ///< Frame rate (e.g., 30.0, 29.97, 24.0)
        juce::String errorMessage;     ///< Error details if success=false
    };
    
    /**
     * Check if FFmpeg is available for video trimming
     * FFmpeg is required for Phase 3B timeline selection support
     * 
     * @return true if FFmpeg found in system PATH with valid version
     * 
     * Example:
     *   if (!processor.isFFmpegAvailable()) {
     *       showError("FFmpeg required. Please install FFmpeg.");
     *   }
     */
    bool isFFmpegAvailable();
    
    /**
     * Get timeline selection from Pro Tools using py-ptsl
     * Reads In/Out points from Pro Tools timeline
     * 
     * @return VideoSelectionInfo struct with selection details
     *         Check success field to determine if operation succeeded
     * 
     * Example:
     *   auto selection = processor.getVideoSelectionInfo();
     *   if (selection.success) {
     *       DBG("Selection: " << selection.durationSeconds << "s");
     *   } else {
     *       showError(selection.errorMessage);
     *   }
     */
    VideoSelectionInfo getVideoSelectionInfo();
    
    /**
     * Get video file path from Pro Tools session using py-ptsl
     * Searches for video files in current Pro Tools session
     * 
     * @param errorMessage [OUT] Error details on failure (optional)
     * @return Path to first video file found, or empty string if none found
     * 
     * Example:
     *   juce::String error;
     *   juce::String videoPath = processor.getVideoFileFromProTools(&error);
     *   if (videoPath.isEmpty()) {
     *       showError("No video found: " + error);
     *   }
     */
    juce::String getVideoFileFromProTools(juce::String* errorMessage = nullptr);
    
    /**
     * Trim video segment using FFmpeg
     * Creates temporary trimmed video file for specified time range
     * 
     * @param videoPath     Path to source video file
     * @param startSeconds  Start time in seconds (from In-point)
     * @param endSeconds    End time in seconds (from Out-point)
     * @param errorMessage  [OUT] Error details on failure (optional)
     * @return Path to trimmed video file (in temp directory), or empty string on failure
     * 
     * Example:
     *   juce::String error;
     *   juce::String trimmedPath = processor.trimVideoSegment(
     *       "C:/video.mp4", 5.0, 10.0, &error
     *   );
     *   if (!trimmedPath.isEmpty()) {
     *       // Use trimmed video for audio generation
     *       // Remember to delete temp file afterward!
     *   }
     * 
     * @note Caller is responsible for deleting temporary trimmed file
     * @note Uses FFmpeg's `-c copy` for fast trimming (no re-encoding)
     */
    juce::String trimVideoSegment(
        const juce::String& videoPath,
        float startSeconds,
        float endSeconds,
        juce::String* errorMessage = nullptr
    );
    
    /**
     * Validate video duration against maximum allowed (10 seconds)
     * MMAudio was trained on 8-second clips, so we enforce 10s maximum
     * 
     * @param durationSeconds Video duration in seconds
     * @param maxDuration     Maximum allowed duration (default: 10.0s)
     * @param errorMessage    [OUT] Error details if validation fails (optional)
     * @return true if duration is valid (> 0 and <= maxDuration)
     * 
     * Example:
     *   juce::String error;
     *   if (!processor.validateVideoDuration(selection.durationSeconds, 10.0, &error)) {
     *       showError("Selection too long: " + error);
     *       return;
     *   }
     */
    bool validateVideoDuration(
        float durationSeconds,
        float maxDuration = 10.0f,
        juce::String* errorMessage = nullptr
    );
    
    /**
     * Get video file duration using FFprobe
     * Queries video duration via Python script (calls FFprobe)
     * 
     * @param videoPath     Path to video file
     * @param errorMessage  [OUT] Error details on failure (optional)
     * @return Video duration in seconds, or -1.0 on failure
     * 
     * Example:
     *   juce::String error;
     *   float duration = processor.getVideoDuration("C:/video.mp4", &error);
     *   if (duration < 0.0f) {
     *       showError("Failed to get duration: " + error);
     *   } else {
     *       DBG("Video is " << duration << " seconds long");
     *   }
     */
    float getVideoDuration(
        const juce::String& videoPath,
        juce::String* errorMessage = nullptr
    );

    //==============================================================================
    // Sound Preview System (TASK 7)
    //==============================================================================
    
    /**
     * Start playing audio preview (plugin-internal, system audio output).
     * Preview runs parallel to Pro Tools audio engine - no timeline interference.
     * 
     * @param audioPath Path to audio file to preview (.wav, .mp3, .flac, etc.)
     * @return true if preview started successfully, false on error
     */
    bool startSoundPreview (const juce::String& audioPath);
    
    /**
     * Stop currently playing audio preview.
     */
    void stopSoundPreview();
    
    /**
     * Check if audio preview is currently playing.
     * @return true if preview is active
     */
    bool isSoundPreviewPlaying() const;

private:
    //==============================================================================
    // Private Members
    //==============================================================================
    
    // File logger instance (shared across all plugin instances)
    static std::unique_ptr<juce::FileLogger> fileLogger;
    
    // Currently no persistent state - all parameters are transient in GUI
    // TODO: Add state variables if we want to persist UI settings:
    //   - juce::String lastPrompt;
    //   - juce::String lastNegativePrompt;
    //   - int lastSeed;
    //   - juce::File lastVideoFile;
    
    //==============================================================================
    // Audio Preview System (Private Members)
    //==============================================================================
    
    /** Audio format manager for loading preview files */
    juce::AudioFormatManager formatManager;
    
    /** Transport source for preview playback control */
    juce::AudioTransportSource previewTransport;
    
    /** Reader source for current preview audio file */
    std::unique_ptr<juce::AudioFormatReaderSource> previewSource;
    
    /** Mixing buffer for combining preview with plugin audio */
    juce::AudioBuffer<float> previewMixBuffer;
    
    //==============================================================================
    // Private Helper Methods
    //==============================================================================
    
    /**
     * Get path to config.json file in plugin bundle
     * @return File object pointing to config.json
     */
    juce::File getConfigFilePath();
    
    //==============================================================================
    // JUCE Leak Detector (Debug builds only)
    // Ensures no memory leaks in this class
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PtV2AProcessor)
};
