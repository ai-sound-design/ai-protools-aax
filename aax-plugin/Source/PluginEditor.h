#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_basics/juce_gui_basics.h>
#include "SoundRecommendationsComponent.h"
#include "AdapterProfile.h"
#include <map>

// Forward declaration to avoid circular include
// (PluginProcessor.h already includes this file)
class PtV2AProcessor;

/**
 * @class PtV2AEditor
 * @brief Plugin GUI displayed in Pro Tools
 * 
 * This is the visual interface that appears when user opens the plugin in Pro Tools.
 * 
 * Current UI Elements (Phase 1 - Prototype):
 *   - Text input for audio generation prompt
 *   - "Generate Sound" button to trigger generation
 * 
 * Workflow:
 *   1. User enters text prompt (e.g., "thunder and rain")
 *   2. User clicks "Generate Sound"
 *   3. Editor validates API availability
 *   4. Editor reads timeline selection via PTSL (asynchronously!)
 *   5. Editor finds video file in Pro Tools session
 *   6. Editor calls processor.generateAudioFromVideo()
 *   7. Shows progress feedback via button text
 *   8. Displays success/error dialog
 * 
 * Async PTSL Communication:
 *   - Uses Timer to poll PTSL process (non-blocking!)
 *   - Keeps Pro Tools responsive during PTSL calls
 *   - Prevents deadlock when PTSL waits for Pro Tools response
 * 
 * @note This GUI is embedded directly in Pro Tools - NOT a standalone window
 */
class PtV2AEditor : public juce::AudioProcessorEditor,
                    private juce::Timer  // For async PTSL polling
{
public:
    //==============================================================================
    // Construction / Destruction
    //==============================================================================
    
    /**
     * Constructor - creates and initializes all GUI components
     * @param p Reference to the processor (provides business logic)
     */
    explicit PtV2AEditor (PtV2AProcessor& p);
    
    /**
     * Destructor - JUCE handles component cleanup automatically
     */
    ~PtV2AEditor() override;

    //==============================================================================
    // JUCE Component Lifecycle
    //==============================================================================
    
    /**
     * Paint the component background
     * Called automatically by JUCE when component needs redrawing
     * @param g Graphics context for drawing
     */
    void paint (juce::Graphics& g) override;
    
    /**
     * Layout child components when window is resized
     * Called automatically by JUCE when component size changes
     * Sets positions and sizes of all UI elements (prompt, button, etc.)
     */
    void resized() override;
    static constexpr int designWidth = 750;
    bool editorReady = false;                              ///< set once the constructor chose the size; resizes before that are not remembered                ///< the width the layout is designed for; the window width scales it

private:
    //==============================================================================
    // Member Variables
    //==============================================================================
    
    /** Reference to the processor (business logic and API calls) */
    PtV2AProcessor& processor;

    //==============================================================================
    // GUI Components
    //==============================================================================
    
    /**
     * Viewport for scrolling the plugin UI
     * Allows plugin content to exceed fixed Pro Tools plugin window height
     */
    juce::Viewport viewport;
    
    /**
     * Content component that holds all UI elements
     * Placed inside viewport for scrolling
     */
    juce::Component contentComponent;
    
    //==============================================================================
    // Workflow Mode Selection
    //==============================================================================
    
    /**
     * Mode selection radio buttons
     * User chooses between Spotting (vision-language model), Sound Generation (generative AI),
     * Sound Recommendation (database) and Hybrid (one generated sound per sound event)
     */
    juce::Label modeLabel { {}, "Mode:" };
    juce::TextButton audioGenModeButton {"Sound Generation" };
    juce::TextButton soundRecModeButton {"Sound Recommendation" };
    juce::TextButton autoSpottingModeButton {"Spotting" };
    juce::TextButton hybridModeButton { "Hybrid" };

    /** Hybrid only: the session's memory locations are the events and scenes; what is missing is spotted/detected. */
    /** Hybrid: where the events come from. 1 the backend spots everything, 2 the memory
        locations in the range, a clip without any is spotted, 3 the memory locations alone. */
    juce::Label eventsSourceLabel { {}, "Events:" };
    juce::ComboBox eventsSourceBox;
    /** Hybrid: the range on the tracks of earlier runs ("(gen)", "(db)") is cleared first. */
    juce::ToggleButton replaceEarlierToggle { "Replace earlier hybrid clips in the range" };
    void updateKindsEnabled();               ///< the five kinds follow Detect events / the events source
    /** Hybrid only: library recordings that sound like each generated sound, instead of it ... */
    juce::ToggleButton useDatabaseSoundsToggle { "Use database sounds" };
    /** ... or, with this on, on tracks underneath the generated sound, which then stays. */
    juce::ToggleButton keepGeneratedToggle { "Keep generated sounds" };
    /** Hybrid only: ambience pieces keep the seconds set in Settings before and after for fades (off: hard cut). */
    juce::ToggleButton ambienceHandlesToggle { "Keep ambience handles" };
    /** Hybrid only: a fade-in over the handle before and a fade-out over the handle after, written into the file. */
    juce::ToggleButton autoFadeToggle { "Auto fade" };
    /** Spotting: group the clips of the range into scenes first, one memory location per scene. */
    juce::ToggleButton detectScenesToggle { "Detect scenes" };
    /** Spotting: look for sound events at all, and which kinds (the backend's categories). */
    juce::ToggleButton detectEventsToggle { "Detect sound events" };
    juce::Label eventKindsLabel { {}, "Events:" };
    juce::ToggleButton dialogueToggle { "Dialogue" }, foleyToggle { "Foley" }, sfxToggle { "SFX" },
                       ambienceToggle { "Ambience" }, musicToggle { "Music" };
    /** What the hybrid backend's health says about library matches (search service up, audio index present). */
    bool hybridMatchAvailable = true;
    juce::String hybridMatchReason;
    int hybridHealthRequest = 0;
    void refreshHybridBackendHealth();
    void applyHybridMatchAvailability();
    

    /**
     * Which backends are there: a mode whose kind has no adapter profile, or whose
     * selected profile does not answer its health address, is greyed out with the
     * reason in its tooltip. Probed in the background when the editor opens, after
     * the settings were saved, and every 30 s after that.
     */
    struct BackendAvailability
    {
        bool available = true;
        bool missed = false;
        juce::String reason;
        double minSeconds = 0.0, maxSeconds = 0.0;   ///< generation: the lengths the health answer named (0: none)
    };
    std::map<juce::String, BackendAvailability> backendAvailability;   // kind -> state
    int availabilityRequest = 0;
    void refreshBackendAvailability();
    void applyBackendAvailability();

    /** Spotting only: run over every clip of the video track instead of the selection. */
    juce::TextButton spotWholeTrackButton { "Spot Entire Track..." };
    /** Hybrid only: the whole video track, after an estimate of how long that takes. */
    juce::TextButton hybridWholeTrackButton { "Run on entire track..." };
    /** Which video track the selection or the whole-track run is mapped onto: "Topmost" (then
        the selection's own video track when it lies on one, else the first with video under
        the range) or a named track of the session. The list is asked of Pro Tools only
        when the user opens it, every time, on a
        background thread: Pro Tools answers PTSL on its message thread, the one this
        editor runs on, so waiting here would lock both; and a PTSL request while Pro
        Tools is still loading a session or showing a dialog has crashed it, so nothing
        is asked at editor open. */
    struct VideoTrackBox : public juce::ComboBox
    {
        std::function<bool()> beforePopup;                  ///< false: the list opens later, when the answer is in
        void showPopup() override { if (beforePopup && ! beforePopup()) return; juce::ComboBox::showPopup(); }
    };
    juce::Label videoTrackLabel { {}, "Video track:" };
    VideoTrackBox videoTrackComboBox;
    juce::StringArray videoTrackNames;
    bool videoTracksFresh = false;                          ///< set while the list is opened programmatically after an answer
    bool openVideoTrackList = false;                        ///< open the list when the answer arrives
    int videoTracksRequest = 0;                             ///< the latest refresh; older answers are dropped
    bool requestVideoTracks();                              ///< true: the list is current, open it now
    void refreshVideoTracks();                              ///< asks in the background, fills the list when it answers
    void setVideoTracks (const juce::StringArray& names);   ///< rebuilds the list, keeps the chosen name when it still exists
    juce::String chosenVideoTrack() const;                 ///< empty: topmost / automatic
    void addVideoTrackArg (juce::StringArray& args) const;
    static juce::String warningsOf (const juce::var& json);   ///< the companion's "warnings", joined
    juce::String resolveWarnings;                         ///< of the last segment resolve (generation)

    /** Progress of a running multi-clip operation; hidden while idle. */
    double progressValue = 0.0;                 // declared before progressBar, which binds to it; set through setProgressTarget
    /** The bar follows the run's reports (clips, backend steps) but does not stand still
        between them: it glides towards the next expected report at the pace of the
        previous ones, stopping short of it until the report comes. A step reported by
        a model call that takes a minute thus shows movement during that minute. */
    double progressTarget = -1.0;               ///< the last reported value (-1: busy, nothing measurable)
    double progressStepSize = 0.0;              ///< size of the last reported rise
    double progressStepSeconds = 0.0;           ///< smoothed seconds between rises
    /** A generation in parts (the gateway's windows): the parts are alike, so the bar runs
        linearly through each one at the pace the previous parts took (learned per run and
        kept for the next), and lands on k/n when part k+1 begins. */
    int lastProgressCurrent = 0;
    int generationPart = 0;
    juce::Time generationPartStart;
    double generationSecondsPerPart = 20.0;
    juce::Time progressTargetTime;              ///< when the target last rose
    void setProgressTarget (double value);      ///< a reported value; -1 for the busy animation
    void animateProgress();                     ///< every timer tick: the glide between reports
    juce::ProgressBar progressBar { progressValue };
    juce::Label progressLabel;
    
    /**
     * Unified action button - changes function based on selected mode
     * Sound Generation mode: "Generate Sound"
     * Sound Recommendation mode: "Recommend Sounds"
     */
    juce::TextButton actionButton { "Generate Sound" };
    
    /**
     * Button to trigger audio generation with dummy video (for presentation)
     * Uses predefined test video file instead of Pro Tools timeline extraction
     * 
     * States:
     *   - "Render (dummy video)" (default, ready)
     *   - "Generating..." (processing, disabled)
     */
    // juce::TextButton renderDummyButton { "Render (dummy video)" }; // (deprecated TODO remove in future)
    
    /**
     * Button to open log file in default text editor
     * Useful for debugging and viewing generation history
     */
    juce::TextButton openLogButton { "Open Log" };

    /** Opens the settings dialog (backend URLs, optional tunnel token). */
    juce::TextButton settingsButton { "Settings..." };

    
    /** Shown only when the tunnel is on but no token is saved. */
    juce::Label apiWarningLabel;

    /**
     * Sound recommendations component for displaying BBC Sound Search results
     * Shows search results with navigation, preview, and import functionality
     * Placed below the action button
     */
    SoundRecommendationsComponent soundRecommendations;
    
    /**
     * Toggle button to show/hide sound recommendations
     * Only appears when search results are available
     */
    juce::TextButton toggleSoundResultsButton { "Show Database Sounds" };
    
    /**
     * Label for video clip offset input (deprecated TODO remove in future)
     */
   // juce::Label videoOffsetLabel { {}, "Video Clip Start (to be removed):" };
    
    /**
     * Text input for video clip start position on timeline
     * Format: Timecode (e.g., "00:02" or "00:00:02:00")
     * 
     * Purpose:
     *   When user wants to render only part of a video clip, they need to
     *   specify where the video clip starts on the Pro Tools timeline.
     *   
     * Example:
     *   - Video clip placed at 00:00:02:00 on timeline
     *   - User selects region from 00:00:05:00 to 00:00:12:00
     *   - User enters "00:02" in this field
     *   - System calculates: offset_in_video = 5 - 2 = 3 seconds
     *   - FFmpeg trims video: -ss 3 -t 7 (from second 3, duration 7)
     * 
     * Notes:
     *   - Leave empty if video clip starts at 00:00:00:00 (timeline beginning)
     *   - Format is flexible: "02", "00:02", "00:00:02:00" all work
     *   - Used only when trimming video with FFmpeg
     *   - System automatically detects trimmed clips when possible
     */
    // juce::TextEditor videoOffsetInput; (deprecated TODO remove in future)
    
    //==============================================================================
    // Advanced Generation Parameters
    //==============================================================================
        
    /**
     * Text input for audio generation prompt
     * Example prompts: "thunder and rain", "footsteps on wood", "car engine starting"
     */
    juce::TextEditor prompt;
    juce::Label promptLabel { {}, "Prompt:" };


    /**
     * Negative prompt input field
     * 
     * Specifies audio elements to avoid during generation (e.g., "voices, music").
     * Helps guide the model away from unwanted audio characteristics.
     * 
     * Default: "voices, music" (generates only sound effects)
     */
    juce::TextEditor negativePromptInput;
    juce::Label negativePromptLabel { {}, "Negative:" };
    
    /**
     * Random seed input field
     * 
     * Controls randomness in audio generation. Same seed = reproducible results.
     *
     * Default: -1, a random seed per run; the seed used is logged and part of the file name.
     * Format: Integer (e.g., "-1", "42", "12345")
     */
    juce::TextEditor seedInput;
    juce::Label seedLabel { {}, "Seed:" };

    // Choice between V2A and T2A generation modes:
    juce::TextButton v2aModeButton {"V2A (from Video)" };
    juce::TextButton t2aModeButton {"T2A (Text Only)" };
    /** Recommendation: what the query is made of. "From video": the video under the
        selection (as before). "From sound": the audio of the clips under the selection on
        the tracks it lies on, mixed when there are several; the results say where in each
        recording the match lies and the import takes just that stretch. The prompt counts
        in both cases. */
    juce::TextButton fromVideoButton { "From video" };
    juce::TextButton fromSoundButton { "From sound" };
    /** "From sketch": the clips under the selection are a sketch (voice, taps) of how the
        sound runs; the prompt says what it is. The archive is searched by the words, and
        the stretch inside each recording is chosen by loudness shape. */
    juce::TextButton fromSketchButton { "From sketch" };
    enum class RecQuery { Video, Sound, Sketch };
    RecQuery recQuery = RecQuery::Video;
    /** How an imported recording is placed, as in Hybrid: trimmed to the selection with
        the rest of the file as handles, a handle fetched before the matched stretch, and
        Pro Tools' own fades. Handle length, preset and fade place come from the Hybrid
        profile's match settings (Settings, Hybrid tab). */
    juce::ToggleButton recCutToggle { "Cut to the selection" };
    juce::ToggleButton recHandlesToggle { "Keep handles" };
    juce::ToggleButton recFadeToggle { "Auto fade" };
    AdapterProfile clipSettings() const;        ///< the selected hybrid profile, or the defaults
    float pendingHandleBefore = 0.0f;           ///< seconds of the downloaded stretch that lie before the selection
    float generationLeadSeconds = 0.0f;         ///< a short range made at the model's minimum: video taken this much before it
    juce::String generationCutOut;              ///< ... and the sound cut back to the selection, which ends here
    juce::String currentAudioQueryPath;         ///< the selection's audio, written by the companion
    juce::Label durationLabel { {}, "Duration:" };
    juce::ComboBox durationComboBox;       
    /**
     * High precision mode toggle (deprecated TODO remove in future)
     * 
     * When enabled:
     *   - Uses torch.float32 (higher quality, slower, more memory)
     * When disabled:
     *   - Uses torch.bfloat16 (default, faster, less memory)
     * 
     * Default: Off (bfloat16)
     * 
     * Note: With RTX A6000 (48GB VRAM), float32 is recommended for production use
     */
    // juce::ToggleButton highPrecisionModeToggle { "High Precision Mode (float32)" };
    
    //==============================================================================
    // Model Selection
    //==============================================================================
    
    /**
     * Backend list: the adapter profiles of the current mode's kind
     * (generation, search or spotting). The plugin knows no model; a profile
     * describes where a backend runs and how it is spoken to.
     */
    juce::Label modelLabel { {}, "Backend:" };
    juce::ComboBox modelProviderComboBox;                          ///< adapter profiles of the current mode's kind
    std::vector<AdapterProfile> adapterChoices;    ///< item id = index + 1

    /** "generation", "search" or "spotting" for the current workflow mode. */
    juce::String currentAdapterKind() const;
    /** Fill the Backend list with the profiles of the current mode and select the saved one. */
    void refreshAdapterCombo();
    /** The profile currently shown in the Backend list (invalid if none). */
    AdapterProfile currentAdapter() const;
    void handleAdapterChanged();
    /** Enable the parameter rows the selected generation adapter supports. */
    void applyAdapterCapabilities();
    
    //==============================================================================
    // Event Handlers
    //==============================================================================
    
    /** 
     * Handle render button click - main workflow entry point
     * 
     * Steps:
     *   1. Validate API availability (HTTP health check)
     *   2. Locate test video file (hardcoded for Phase 1)
     *   3. Call processor.generateAudioFromVideo() with prompt
     *   4. Update button state during processing
     *   5. Show success/error dialog
     * 
     * @note This is called on the GUI thread - processor handles async Python subprocess
     * 
     * TODO Phase 2: Replace hardcoded video path with FileChooser dialog
     * TODO Phase 3: Extract video from Pro Tools timeline instead of file selector
     */
    void handleRenderButtonClicked();
    
    /**
     * Handle render dummy button click - simplified workflow for presentation
     * 
     * Steps:
     *   1. Validate API availability
     *   2. Use predefined test video (sora_galloping.mp4)
     *   3. Generate audio and import to Pro Tools
     * 
     * @note Skips Pro Tools timeline extraction - uses hardcoded video path
     */
    void handleRenderDummyButtonClicked();
    
    /**
     * Handle open log button click
     * Opens the log file in the system's default text editor
     * Shows error if log file doesn't exist
     */
    void handleOpenLogButtonClicked();
    
    /**
     * Handle generation mode change (V2A <-> T2A)
     * Updates UI state: enables/disables duration selection and model provider
     */
    void handleGenerationModeChange();
    
    /**
     * Handle workflow mode change (Spotting, Sound Generation, Sound Recommendation, Hybrid)
     * Updates UI: enables/disables relevant fields, changes action button text
     */
    void handleWorkflowModeChange();
    
    /**
     * Handle Spotting button click.
     *
     * Runs spotting_client.py --from-selection. The script resolves the video clips
     * under the timeline selection (made on any track) through PTSL, cuts each clip
     * range, sends it to the spotting backend and places one memory location per
     * sound event. Progress is read from a small JSON file the script keeps updated.
     */
    void handleAutoSpottingButtonClicked();
    void handleHybridButtonClicked();
    /** Start hybrid_client.py over the selection: one generated sound per event, each on its own track. */
    /** Start hybrid_client.py over the selection or the whole track; `resume` continues the journal of an
        earlier run over the same range; `estimate` only counts clips and answers with a duration estimate. */
    void startHybrid (bool wholeTrack, bool resume, bool estimate = false);
    /** Kill the running spotting/hybrid script; what it placed so far stays. */
    void stopRun();

    /** Start spotting_client.py over the selection or, with wholeTrack, over the whole video track. */
    void startSpotting (bool wholeTrack);

    /** Read the script's progress file into the progress bar and label. */
    void updateSpottingProgress();

    /** Re-enable the buttons and hide the progress widgets after a spotting run. */
    void resetSpottingUi();
    juce::String idleActionButtonText() const;
    juce::String modeInfoTitle() const;

    //==============================================================================
    // Video segments: the selection (made on any track) mapped onto the video track
    //==============================================================================

    /** Which workflow asked for the segments. */
    enum class ResolveTarget { Generation, SoundSearch, SoundSearchAudio };
    ResolveTarget resolveTarget = ResolveTarget::Generation;

    /** Recommendation "From sound": run standalone_api_client.py --action export_selection_audio
        (async, timer-polled like the resolve); its answer starts the search by sound. */
    void startSelectionAudioExport();

    /** Run standalone_api_client.py --action resolve_video_segments (async, timer-polled). */
    void startVideoSegmentResolve (ResolveTarget target);

    /** Parse the resolver's JSON; start the per-clip generation queue or the sound search. */
    void handleVideoSegmentsResult (const juce::String& output);

    /** Generation queue: take the next usable segment, or finish the run. */
    void startNextSegmentGeneration();

    /** Record the current segment as failed and continue with the next one. */
    void segmentFailed (const juce::String& reason);

    /** Progress bar and label for the current segment. */
    void updateSegmentProgress (const juce::String& stage);

    /** End of a generation run: summary (if report), queue cleared, buttons restored. */
    void finishSegmentGeneration (bool report);

    /** Restore the action button for the current workflow mode, hide progress, state Idle. */
    void resetActionUi();

    /** Segments of the current run (JSON objects from the resolver) and the queue position. */
    juce::Array<juce::var> pendingSegments;
    int currentSegmentIndex = -1;
    int segmentsGenerated = 0;
    juce::StringArray skippedSegments;
    
    /** Show the tunnel-token warning when the tunnel is on and no token is saved. */
    void updateBackendStatus();

    /** True unless the tunnel is on without a token; then explains and returns false. */
    bool tunnelTokenPresent (const juce::String& action);

    /**
     * Handle T2A render button click - text-to-audio workflow without video
     * 
     * Steps:
     *   1. Parse duration from dropdown (e.g., "8s" -> 8.0f)
     *   2. Check API availability
     *   3. Read timeline selection from Pro Tools
     *   4. Generate audio via T2A API (no video input)
     *   5. Import generated audio at timeline selection start
     * 
     * @note Now uses timeline selection like V2A for consistent behavior
     */
    void handleT2ARenderButtonClicked();
    
    /**
     * Handle sound download button click
     * Downloads the selected sound file from the API
     * @param sound The sound to download
     */
    void handleSoundDownload (const SoundResult& sound);
    
    /**
     * Handle sound import button click
     * Imports the selected sound to Pro Tools timeline at current position
     * @param sound The sound to import
     */
    void handleSoundImport (const SoundResult& sound);
    void startSoundImportProcess (const SoundResult& sound, const juce::String& timecode);
    
    /** Open the settings dialog. */
    void showSettings();


    //==============================================================================
    // Async PTSL Communication
    //==============================================================================
    
    /**
     * Timer callback - checks PTSL process status every 100ms
     * 
     * This allows Pro Tools to remain responsive while waiting for PTSL.
     * When process finishes, reads output and continues workflow.
     * 
     * States:
     *   - Process running: Do nothing, Pro Tools stays responsive
     *   - Process finished: Read output, stop timer, continue workflow
     *   - Timeout: Kill process, show error
     */
    void timerCallback() override;
    
    /**
     * Start async timeline selection read (T2A workflow - timeline only, no video)
     * Launches PTSL process with get_timeline_selection and starts timer for polling
     */
    void startTimelineSelectionReadOnly();
    
    /**
     * Handle timeline selection result (called from timer callback)
     * @param output Raw output from PTSL process (JSON string)
     */
    void handleTimelineSelectionResult (const juce::String& output);
    
    /**
     * Start async audio generation and polling (V2A workflow)
     * Launches Python process and starts timer to poll for output file
     * @param videoPath Path to video file
     * @param promptText User's audio prompt
     */
    void startAudioGeneration (const juce::String& videoPath, const juce::String& promptText);
    
    /**
     * Start async T2A audio generation (text-only, no video)
     * Launches Python process and starts timer to poll for output file
     * @param promptText User's audio prompt
     * @param duration Duration in seconds (4-12s)
     */
    void startT2AAudioGeneration (const juce::String& promptText, float duration);
    
    /**
     * Check if audio generation is complete (output file exists)
     * Called from timer callback
     */
    void checkAudioGenerationComplete();
    
    /**
     * Import generated audio to Pro Tools (async with PTSL)
     * @param audioPath Path to generated audio file
     */
    void startAudioImport (const juce::String& audioPath);
    
    /**
     * Handle audio import result (called from timer callback)
     * @param output Raw output from PTSL import process
     */
    void handleAudioImportResult (const juce::String& output);
    
    /**
     * Get source video file duration via FFprobe
     * @param videoPath Path to video file
     * @return Duration in seconds, or 0.0f if failed
     */
    float getSourceVideoDuration (const juce::String& videoPath);
    
    //==============================================================================
    // Sound Search Integration
    //==============================================================================
    
    /**
     * Trigger sound search after successful audio generation.
     * Searches BBC Sound Archive for sounds matching video and prompt.
     * Results are displayed in SoundRecommendationsComponent.
     * 
     * @param videoPath Path to video file (optional, can be empty for T2A)
     * @param prompt Text prompt used for generation
     * @param videoOffset Timeline position where video starts (e.g., "00:02")
     * @param timelineStart Timeline selection start in seconds
     * @param timelineEnd Timeline selection end in seconds
     * @param clipStartSeconds Clip start in source video (seconds)
     * @param clipEndSeconds Clip end in source video (seconds)
     * @param autoDetectClipBounds If true, use clip bounds; if false, use manual offset
     */
    void triggerSoundSearch (
        const juce::String& videoPath, 
        const juce::String& prompt,
        const juce::String& videoOffset = "",
        float timelineStart = 0.0f,
        float timelineEnd = 0.0f,
        float clipStartSeconds = -1.0f,
        float clipEndSeconds = -1.0f,
        bool autoDetectClipBounds = false,
        const juce::String& audioPath = "",     ///< "From sound"/"From sketch": the query audio instead of a video
        bool sketch = false                     ///< the audio is a sketch: words decide, the shape locates
    );
    
    /**
     * Handle sound search completion (called from timer or async callback).
     * Parses JSON response and populates SoundRecommendationsComponent.
     * 
     * @param output Raw JSON output from sound_search_api_client.py
     */
    void handleSoundSearchResult (const juce::String& output);
    
    /**
     * Toggle visibility of sound recommendations component.
     * Shows/hides the results panel and updates button text.
     */
    void handleToggleSoundResults();
    
    /**
     * Handle "Recommend Sounds" button click.
     * Manually triggers sound search using current video and prompt.
     */
    void handleRecommendSoundsButtonClicked();
    
    //==============================================================================
    // Async State
    //==============================================================================
    
    /** Current async operation state */
    enum class AsyncState
    {
        Idle,                              // No operation in progress
        ReadingTimeline,                   // Reading timeline selection via PTSL (T2A: import position only)
        ReadingTimelineForSoundImport,     // Reading timeline selection via PTSL (before sound import)
        ResolvingVideoSegments,            // resolve_video_segments: selection (any track) -> video clips beneath
        GeneratingAudio,                   // Python generating audio (polling for output file)
        SearchingSounds,                   // Python searching sounds (polling for JSON output)
        DownloadingSingleSound,            // Python downloading single sound (polling for JSON output)
        ImportingAudio,                    // Importing generated audio to Pro Tools via PTSL
        ImportingSoundFX,                  // Importing sound library audio to Pro Tools via PTSL
        SpottingAnalysis,                  // spotting_client.py: selection -> clips -> backend -> markers
        HybridGeneration,                  // hybrid_client.py: selection -> clips -> backend -> tracks per scene
        HybridEstimate                     // hybrid_client.py --estimate: clip count and duration before a long run
};
    
    AsyncState currentAsyncState = AsyncState::Idle;
    
    /** Workflow mode selection */
    enum class WorkflowMode
    {
        AudioGeneration,
        SoundRecommendation,
        AutoSpotting,
        Hybrid                 ///< one generated sound per sound event, each on its own track
    };
    
    WorkflowMode currentWorkflowMode = WorkflowMode::AudioGeneration;
    juce::String modeDescription (WorkflowMode mode) const;   // what a mode does, for the mode buttons' tooltips
    
    /** PTSL process handle (for async timeline selection and import) */
    std::unique_ptr<juce::ChildProcess> ptslProcess;

    /** Progress document written by spotting_client.py while it runs. */
    juce::File spottingProgressFile;
    juce::Time spottingProgressMtime;
    int lastProgressTotal = 0;                  ///< "total" of the last progress document read (parts or clips)
    void watchGenerationProgress();             ///< a single generation: follow the gateway's parts through the companion's file
    void endGenerationProgress();               ///< ...and take the bar down when the sound is in
    
    /** Sound search process handle (kept alive during search, no stdout reading) */
    std::unique_ptr<juce::ChildProcess> soundSearchProcess;
    
    /** Sound download process handle (for downloading single sound) */
    std::unique_ptr<juce::ChildProcess> soundDownloadProcess;
    
    /** Sound import process handle (for importing BBC sounds to timeline) */
    std::unique_ptr<juce::ChildProcess> soundImportProcess;
    
    /** Time when sound search started (for timeout and polling) */
    juce::Time soundSearchStartTime;
    
    /** Time when current async operation started (the "(40s)" on the button) */
    juce::Time asyncOperationStartTime;
    /** Last sign of life from a multi-clip script (progress file changed); the timeout counts from here */
    juce::Time lastProgressTime;
    /** The "no sign of life" dialog is open (spotting/hybrid): do not ask twice. */
    bool staleDialogOpen = false;
    /** The user stopped the running script: report where it was instead of a failure. */
    bool runStopped = false;
    
    /** Expected output file path (for audio generation polling) */
    juce::String expectedAudioOutputPath;
    
    /** Expected sound search output JSON file path (for file polling) */
    juce::String expectedSoundSearchOutputPath;
    
    /** Expected sound download output JSON file path (for file polling) */
    juce::String expectedSoundDownloadOutputPath;
    
    /** Current sound being downloaded (stored for download process) */
    SoundResult currentDownloadingSound;

    /** Import button pressed on a sound that is not downloaded yet: import it once it is. */
    int autoImportSoundId = -1;

    /** Play a result: from its downloaded file, from the preview cache, or fetched from the backend. */
    void startSoundPreview (const SoundResult& sound);
    
    /** Video path and prompt (stored for generation process) */
    juce::String currentVideoPath;
    juce::String currentPrompt;
    
    /** Timeline selection timecode (stored for audio import positioning) */
    juce::String timelineInTime;  // e.g., "00:00:07:00"
    float timelineFps = 30.0f;    // timecode rate of the session, from get_video_info

    /** Pending sound import (stored while reading timeline position) */
    SoundResult pendingSoundImport;
    juce::String currentTimecodeOut;   ///< end of the selection read for the sound import
    
    /** Timeline selection in seconds (for video trimming calculations) */
    float timelineInSeconds = 0.0f;
    float timelineOutSeconds = 0.0f;
    
    /** Clip boundaries in seconds (for auto-trim workflow) */
    float clipStartSeconds = -1.0f;  // -1 = not set
    float clipEndSeconds = -1.0f;    // -1 = not set
    
    /** Flag indicating if video clip is trimmed (shorter than source) */
    bool clipIsTrimmed = false;
    
    /** Current generation mode: true = T2A (text-only), false = V2A (video-to-audio) */
    bool isT2AMode = false;
    
    /** T2A length in seconds; 0 = "Auto", resolved from the marked range once it is read. */
    float t2aDuration = 0.0f;
    
    /** Timeout for PTSL calls (milliseconds) */
    static constexpr int PTSL_TIMEOUT_MS = 10000;  // 10 seconds: quick PTSL reads
    static constexpr int IMPORT_TIMEOUT_MS = 120000;  // 2 minutes: Pro Tools converts and copies the file on import
    
    /** Timeout for audio generation (milliseconds) */
    /** Outcome of the last action, shown in the line under the buttons instead of a dialog.
        Pro Tools' own operations (render, import) finish without modal confirmation; the
        result on the timeline is the confirmation. Dialogs are kept for failures only. */
    void showStatus (const juce::String& text, bool warning = false);

    /** --track-name / --clip-name for the import_audio action (own track, readable clip name). */
    void addImportTargetArgs (juce::StringArray& commandArray, const juce::String& clipLabel);
    juce::String currentImportClipLabel() const;

    static constexpr int GENERATION_TIMEOUT_MS = 1800000;   // 30 minutes, the shipped profile's timeout: a long range is made in windows
    
    /** Timer polling interval (milliseconds) */
    static constexpr int TIMER_INTERVAL_MS = 100;  // Check every 100ms

    /** Shows the tooltips of this editor's components; parented so it stays inside the plugin window. */
    juce::TooltipWindow tooltipWindow { this, 400 };

    //==============================================================================
    // JUCE Leak Detector (Debug builds only)
    //==============================================================================
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PtV2AEditor)
};
