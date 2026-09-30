#include "PluginEditor.h"
#include "PluginProcessor.h"
#include "SettingsPanel.h"

namespace
{
    // One segment of a segmented switch: a text button that stays lit while it is
    // the selected member of its radio group. Used for choices that are mutually
    // exclusive, where check boxes would suggest several could be ticked at once.
    void setUpSegment (juce::TextButton& button, int radioGroupId, int connectedEdges)
    {
        button.setClickingTogglesState (true);
        button.setRadioGroupId (radioGroupId);
        button.setConnectedEdges (connectedEdges);
        button.setColour (juce::TextButton::buttonOnColourId,  juce::Colour (0xff2f7fe0));
        button.setColour (juce::TextButton::textColourOnId,    juce::Colours::white);
        button.setColour (juce::TextButton::buttonColourId,    juce::Colour (0xff353535));
        button.setColour (juce::TextButton::textColourOffId,   juce::Colour (0xffa8a8a8));
    }
}

//==============================================================================
// Constructor - Initialize GUI Components
//==============================================================================
PtV2AEditor::PtV2AEditor (PtV2AProcessor& p)
: AudioProcessorEditor (&p), processor (p)
{
    // Setup viewport for scrolling
    addAndMakeVisible (viewport);
    viewport.setViewedComponent (&contentComponent, false);  // false = we manage the content component's lifetime
    viewport.setScrollBarsShown (true, true);  // Vertical and horizontal scrollbars
    
    // Configure text input for prompt
    prompt.setMultiLine (true);  // Allow line breaks
    prompt.setReturnKeyStartsNewLine (true);  // Enter = new line
    prompt.setScrollbarsShown (true);  // Show scrollbar if needed
    promptLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (promptLabel);
    contentComponent.addAndMakeVisible (prompt);
    
    // Configure workflow mode selection
    modeLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (modeLabel);
    
    // The four workflows are one segmented switch of three rows, exactly one lit:
    //   Spotting                        (find the sound events)
    //   Sound Generation     |
    //                        | Hybrid   (one generated sound per event)
    //   Sound Recommendation |
    setUpSegment (autoSpottingModeButton, 1000, juce::Button::ConnectedOnBottom);
    setUpSegment (audioGenModeButton,     1000, juce::Button::ConnectedOnTop | juce::Button::ConnectedOnBottom | juce::Button::ConnectedOnRight);
    setUpSegment (soundRecModeButton,     1000, juce::Button::ConnectedOnTop | juce::Button::ConnectedOnRight);
    setUpSegment (hybridModeButton,       1000, juce::Button::ConnectedOnTop | juce::Button::ConnectedOnLeft);
    audioGenModeButton.setToggleState (true, juce::dontSendNotification);  // Default: Sound Generation
    for (auto* button : { &autoSpottingModeButton, &audioGenModeButton, &soundRecModeButton, &hybridModeButton })
    {
        button->onClick = [this] { handleWorkflowModeChange(); };
        contentComponent.addAndMakeVisible (*button);
    }

    // Hybrid: whether the session's memory locations define the sound events
    useMemoryLocationsToggle.setToggleState (true, juce::dontSendNotification);
    useMemoryLocationsToggle.setTooltip ("On: the memory locations inside the selection (a spotting run, or markers you "
                                         "set) are the sound events. Off: the backend finds the events itself.");
    useMemoryLocationsToggle.setVisible (false);
    useMemoryLocationsToggle.onClick = [this] { autoSpotToggle.setEnabled (useMemoryLocationsToggle.getToggleState()
                                                                            && useMemoryLocationsToggle.isEnabled()); };
    contentComponent.addAndMakeVisible (useMemoryLocationsToggle);
    autoSpotToggle.setToggleState (true, juce::dontSendNotification);
    autoSpotToggle.setTooltip ("On: a clip in the selection without memory locations is spotted by the backend first. "
                               "Off: such a clip is skipped.");
    autoSpotToggle.setVisible (false);
    contentComponent.addAndMakeVisible (autoSpotToggle);

    // Hybrid: library recordings that sound like the generated sounds, instead of or next to them
    useDatabaseSoundsToggle.setTooltip ("On: for every generated sound the backend finds library recordings that "
                                        "sound like it, stitched from at most the pieces per 10 s set in Settings, "
                                        "and places them instead of the generated sound (which stays only where "
                                        "nothing matched).");
    useDatabaseSoundsToggle.setVisible (false);
    useDatabaseSoundsToggle.onClick = [this]
    {
        const bool on = useDatabaseSoundsToggle.getToggleState() && useDatabaseSoundsToggle.isEnabled();
        keepGeneratedToggle.setEnabled (on);
        ambienceHandlesToggle.setEnabled (on);
    };
    contentComponent.addAndMakeVisible (useDatabaseSoundsToggle);
    keepGeneratedToggle.setTooltip ("On: the generated sound is placed too, on its own track above the library pieces. "
                                    "Off: only the library pieces are placed.");
    keepGeneratedToggle.setEnabled (false);
    keepGeneratedToggle.setVisible (false);
    contentComponent.addAndMakeVisible (keepGeneratedToggle);
    ambienceHandlesToggle.setToggleState (true, juce::dontSendNotification);
    ambienceHandlesToggle.setTooltip ("On: an ambience piece keeps the seconds set in Settings (Ambience handles) of "
                                      "its recording before and after the event, so it can be faded in and out. "
                                      "Off: the piece is cut to the event.");
    ambienceHandlesToggle.setEnabled (false);
    ambienceHandlesToggle.setVisible (false);
    contentComponent.addAndMakeVisible (ambienceHandlesToggle);
    // Spotting and Hybrid: scenes across clips
    detectScenesToggle.setTooltip ("On: the backend first groups the clips of the range into scenes (same place, "
                                   "continuous time) and names them; one memory location per scene. Costs a model "
                                   "call per cut.");
    detectScenesToggle.setVisible (false);
    contentComponent.addAndMakeVisible (detectScenesToggle);

    // (i) next to the mode switch: hover for what the mode does, click for the same text as a dialog
    audioGenModeButton.setTooltip (modeDescription (WorkflowMode::AudioGeneration));
    soundRecModeButton.setTooltip (modeDescription (WorkflowMode::SoundRecommendation));
    autoSpottingModeButton.setTooltip (modeDescription (WorkflowMode::AutoSpotting));
    modeInfoButton.setColour (juce::TextButton::buttonColourId, juce::Colour (0xff353535));
    modeInfoButton.setColour (juce::TextButton::textColourOffId, juce::Colour (0xffa8a8a8));
    modeInfoButton.onClick = [this]
    {
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::InfoIcon,
                                                modeInfoTitle(), modeDescription (currentWorkflowMode), "OK");
    };
    contentComponent.addAndMakeVisible (modeInfoButton);
    updateModeInfo();

    // Spotting only: the whole video track, after a word about how long that takes
    spotWholeTrackButton.onClick = [this]
    {
        juce::AlertWindow::showOkCancelBox (
            juce::MessageBoxIconType::QuestionIcon,
            "Spot the entire track?",
            "Every clip on the video track is analysed one after another.\n\n"
            "Expect roughly half a minute per clip while the backend is warm, and a few "
            "minutes for the first clip if the backend has to load its model.",
            "Start", "Cancel", this,
            juce::ModalCallbackFunction::create ([this] (int result)
            {
                if (result == 1)
                    startSpotting (true);
            }));
    };
    contentComponent.addChildComponent (spotWholeTrackButton);   // shown in spotting mode only

    // Hybrid only: the whole track; the script first counts the clips and estimates the
    // duration, the dialog with those numbers follows in timerCallback (HybridEstimate)
    hybridWholeTrackButton.setTooltip ("Every clip on the video track: scenes, events, sounds and placement, "
                                       "which takes hours for a film. Shows an estimate first.");
    hybridWholeTrackButton.onClick = [this] { startHybrid (true, false, true); };
    contentComponent.addChildComponent (hybridWholeTrackButton);

    // Progress of multi-clip runs; shown while a run is active
    progressBar.setPercentageDisplay (false);
    progressBar.setColour (juce::ProgressBar::foregroundColourId, juce::Colour (0xff2f7fe0));   // same blue as the lit segment
    progressBar.setColour (juce::ProgressBar::backgroundColourId, juce::Colour (0xff2a2a2a));
    progressLabel.setJustificationType (juce::Justification::centred);
    contentComponent.addChildComponent (progressBar);
    contentComponent.addChildComponent (progressLabel);

    // Configure unified action button (changes based on workflow mode)
    actionButton.onClick = [this]
    {
        if ((currentAsyncState == AsyncState::SpottingAnalysis || currentAsyncState == AsyncState::HybridGeneration)
            && ptslProcess != nullptr)
        {
            juce::AlertWindow::showOkCancelBox (
                juce::MessageBoxIconType::QuestionIcon, "Stop the run?",
                "What was placed so far stays in the session. A hybrid run over the same range can be "
                "continued later with \"Run on entire track...\".",
                "Stop", "Keep running", this,
                juce::ModalCallbackFunction::create ([this] (int result) { if (result == 1) stopRun(); }));
            return;
        }
        if (currentWorkflowMode == WorkflowMode::AudioGeneration)
            handleRenderButtonClicked();
        else if (currentWorkflowMode == WorkflowMode::SoundRecommendation)
            handleRecommendSoundsButtonClicked();
        else if (currentWorkflowMode == WorkflowMode::AutoSpotting)
            handleAutoSpottingButtonClicked();
        else if (currentWorkflowMode == WorkflowMode::Hybrid)
            handleHybridButtonClicked();
    };
    contentComponent.addAndMakeVisible (actionButton);
    
    // Configure open log button with click handler
    openLogButton.onClick = [this]
    {
        handleOpenLogButtonClicked();
    };
    contentComponent.addAndMakeVisible (openLogButton);

    // Configure settings button with click handler
    settingsButton.onClick = [this] { showSettings(); };
contentComponent.addAndMakeVisible (settingsButton);
    
    // Configure API warning label
    apiWarningLabel.setJustificationType (juce::Justification::centredLeft);
    apiWarningLabel.setColour (juce::Label::textColourId, juce::Colours::orange);
    apiWarningLabel.setFont (juce::Font (14.0f, juce::Font::bold));
    contentComponent.addAndMakeVisible (apiWarningLabel);
    
    // Configure sound recommendations component
    soundRecommendations.onDownload = [this] (const SoundResult& sound)
    {
        handleSoundDownload (sound);
    };
    soundRecommendations.onImport = [this] (const SoundResult& sound)
    {
        handleSoundImport (sound);
    };
    soundRecommendations.onPreview = [this] (const SoundResult& sound, bool start)
    {
        if (start)
            startSoundPreview (sound);
        else
            processor.stopSoundPreview();
    };
    soundRecommendations.isPreviewPlaying = [this] { return processor.isSoundPreviewPlaying(); };
    contentComponent.addAndMakeVisible (soundRecommendations);

    // Configure video offset label (deprecated TODO remove in future)
    // videoOffsetLabel.setJustificationType (juce::Justification::centredLeft);
    // addAndMakeVisible (videoOffsetLabel);
    
    // Configure video offset input (deprecated TODO remove in future)
    // videoOffsetInput.setMultiLine (false);
    // videoOffsetInput.setReturnKeyStartsNewLine (false);
    // videoOffsetInput.setTextToShowWhenEmpty ("e.g., 00:02 (leave empty if video starts at timeline beginning)", juce::Colours::grey);
    // addAndMakeVisible (videoOffsetInput);
    
    // Configure negative prompt label
    negativePromptLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (negativePromptLabel);
    
    // Configure negative prompt input
    negativePromptInput.setMultiLine (true);
    negativePromptInput.setReturnKeyStartsNewLine (true);
    negativePromptInput.setScrollbarsShown (true);
    negativePromptInput.setTextToShowWhenEmpty ("voices, music, melody, singing, speech,interference", juce::Colours::grey);
    negativePromptInput.setText ("voices, music, melody, singing, speech, interference");  // Set default value
    contentComponent.addAndMakeVisible (negativePromptInput);
    
    // Configure seed label
    seedLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (seedLabel);
    
    // Configure seed input
    seedInput.setMultiLine (false);
    seedInput.setReturnKeyStartsNewLine (false);
    seedInput.setTextToShowWhenEmpty ("-1 = random", juce::Colours::grey);
    seedInput.setText ("-1");  // Default: a fresh random seed per run
    seedInput.setTooltip ("-1 (or empty): a random seed each run; the seed used is logged and part of the file name. "
                          "Any other number reproduces a result.");
    contentComponent.addAndMakeVisible (seedInput);
    
    // Configure generation mode radio buttons (V2A vs T2A)
    setUpSegment (v2aModeButton, 1001, juce::Button::ConnectedOnRight);
    setUpSegment (t2aModeButton, 1001, juce::Button::ConnectedOnLeft);
    v2aModeButton.setToggleState (true, juce::dontSendNotification);  // Default: V2A mode
    v2aModeButton.onClick = [this] { handleGenerationModeChange(); };
    t2aModeButton.onClick = [this] { handleGenerationModeChange(); };
    contentComponent.addAndMakeVisible (v2aModeButton);
    contentComponent.addAndMakeVisible (t2aModeButton);

    // Configure duration dropdown (for T2A mode)
    durationLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (durationLabel);
    
    // Items come from the selected backend's profile, see applyAdapterCapabilities()
    durationComboBox.setEnabled (false);  // Initially disabled (V2A mode)
    contentComponent.addAndMakeVisible (durationComboBox);
    
    // Configure high precision mode toggle (deprecated TODO remove in future)
    // highPrecisionModeToggle.setToggleState (false, juce::dontSendNotification);  // Default: off (bfloat16)
    // addAndMakeVisible (highPrecisionModeToggle);
    
    // Configure model selection labels
    modelLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (modelLabel);
    
    // Configure model ComboBox with integrated sizes
    modelProviderComboBox.onChange = [this] { handleAdapterChanged(); };
    contentComponent.addAndMakeVisible (modelProviderComboBox);
    refreshAdapterCombo();
    
    // Configure toggle button for sound recommendations
    toggleSoundResultsButton.onClick = [this] { handleToggleSoundResults(); };
    contentComponent.addChildComponent (toggleSoundResultsButton);  // hidden until a search has results

    // Initial UI state based on default workflow mode
    handleWorkflowModeChange();
    
    updateBackendStatus();
    refreshBackendAvailability();

    // Sound recommendations initially hidden
    soundRecommendations.setVisible (false);
    
    // Set fixed window size (not resizable in Pro Tools)
    // Pro Tools plugins typically have fixed UI layouts
    setResizable (true, true);
    setResizeLimits (400, 400, 1200, 1200);  // min/max width/height
    setSize (750, 660);  // Width x Height in pixels; matches the content height computed in resized()
}

//==============================================================================
// Event Handler - Render Button Click
//==============================================================================
void PtV2AEditor::handleRenderButtonClicked()
{
    juce::Logger::writeToLog ("=== Render Button Clicked ===");
    juce::Logger::writeToLog ("Prompt: " + prompt.getText());
    juce::Logger::writeToLog ("Mode: " + juce::String (isT2AMode ? "T2A" : "V2A"));
    
    if (! tunnelTokenPresent ("rendering audio"))
        return;

    // T2A mode validation and workflow
    if (isT2AMode)
    {
        // The adapter must be able to generate from text alone
        if (auto adapter = currentAdapter(); adapter.isValid() && ! adapter.supportsFeature ("text_only"))
        {
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon,
                "Backend Needs a Video",
                adapter.name + " cannot generate from text alone.\n\n"
                "Choose a backend whose profile lists \"text_only\", or switch to V2A.",
                "OK"
            );
            return;
        }
        
        // Start T2A workflow (text-to-audio without video)
        handleT2ARenderButtonClicked();
        return;
    }
    
    // Disable button during processing
    actionButton.setEnabled (false);
    actionButton.setButtonText ("Checking...");
    
    //==========================================================================
    // Step 1: Check API availability (uses config.json for cloudflared support)
    //==========================================================================
    // Determine which API to check based on selected provider
    auto adapter = currentAdapter();
    juce::String providerDisplayName = adapter.isValid() ? adapter.name : juce::String ("The generation backend");
    juce::String apiUrl = adapter.isValid() ? adapter.activeUrl (processor.getBackendSettings().useTunnel)
                                            : processor.getConfiguredAPIUrl ("mmaudio");
    if (!processor.isAPIAvailable (apiUrl))
    {
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "API Not Available",
            providerDisplayName + " API is not running!\n\n"
            "Please start the API server\n"
            "Trying to connect to: " + apiUrl,
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        return;
    }
    
    //==========================================================================
    // Step 2: which video clips lie under the timeline selection? (async)
    //==========================================================================
    // The selection may be on any track. Every clip beneath it is generated for
    // in turn and imported at its own position (handleVideoSegmentsResult).
    currentPrompt = prompt.getText();
    startVideoSegmentResolve (ResolveTarget::Generation);
}

//==============================================================================
// Event Handler - Open Log Button Click
//==============================================================================
void PtV2AEditor::handleOpenLogButtonClicked()
{
    juce::Logger::writeToLog ("=== Open Log Button Clicked ===");
    
    // Get log file path from processor
    auto logFile = PtV2AProcessor::getLogFile();

    if (logFile == juce::File())
    {
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::InfoIcon, "Log Saving Is Off",
                                                "Turn on \"Save a log file\" in the settings to write a log.", "OK");
        return;
    }

    if (!logFile.existsAsFile())
    {
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Log File Not Found",
            "Log file does not exist yet.\n\n"
            "The log file will be created automatically when the plugin starts.\n"
            "Try using the plugin first, then check the log.",
            "OK"
        );
        return;
    }
    
    // Open log file in default text editor
    // Windows: Opens with Notepad or associated .log editor
    // macOS: Opens with TextEdit or associated app
    if (!logFile.startAsProcess())
    {
        // Fallback: Show log file location in message box
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::InfoIcon,
            "Log File Location",
            "Could not open log file automatically.\n\n"
            "Log file location:\n" + logFile.getFullPathName() + "\n\n"
            "You can open it manually with any text editor.",
            "OK"
        );
    }
    
    juce::Logger::writeToLog ("Log file opened: " + logFile.getFullPathName());
}

//==============================================================================
// Event Handler - T2A Render Button Click
//==============================================================================
void PtV2AEditor::handleT2ARenderButtonClicked()
{
    juce::Logger::writeToLog ("=== T2A Render Button Clicked ===");
    
    // Parse duration from dropdown (e.g., "8s" -> 8.0f)
    juce::String durationText = durationComboBox.getText();
    float duration = durationText.dropLastCharacters(1).getFloatValue();  // Remove "s" suffix
    
    juce::Logger::writeToLog ("T2A Duration: " + juce::String(duration, 1) + "s");
    
    // Store duration for later use
    t2aDuration = duration;
    
    // Disable button during operation
    actionButton.setEnabled (false);
    actionButton.setButtonText ("Checking API...");
    
    // Check MMAudio API availability (T2A only supports MMAudio)
    juce::String apiUrl = processor.getConfiguredAPIUrl ("mmaudio");
    if (!processor.isAPIAvailable (apiUrl))
    {
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "API Not Available",
            "MMAudio API is not running!\n\n"
            "Please start the API server\n"
            "Trying to connect to: " + apiUrl,
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        return;
    }
    
    // Start async timeline-only read (T2A doesn't need video clips)
    actionButton.setButtonText ("Reading Selection...");
    startTimelineSelectionReadOnly();
}

//==============================================================================
// JUCE Component Lifecycle - Paint
//==============================================================================
void PtV2AEditor::paint (juce::Graphics& g)
{
    // Fill background with dark grey
    g.fillAll (juce::Colours::darkgrey);
}

//==============================================================================
// JUCE Component Lifecycle - Layout
//==============================================================================
void PtV2AEditor::resized()
{
    // Viewport takes full editor bounds
    viewport.setBounds (getLocalBounds());
    
    // Rows that the current mode hides take no space, so the Sound Recommendation
    // list gets the room the generation parameters would otherwise occupy.
    const bool isAudioGen = currentWorkflowMode == WorkflowMode::AudioGeneration;
    const bool isSoundRec = currentWorkflowMode == WorkflowMode::SoundRecommendation;
    const bool isHybrid   = currentWorkflowMode == WorkflowMode::Hybrid;
    const int audioRows = (isAudioGen || isHybrid) ? 1 : 0;         // negative prompt, seed
    const int hybridRows = isHybrid ? 3 : 0;                         // event switches, database switches, handles/scenes
    const int spottingRows = (currentWorkflowMode == WorkflowMode::AutoSpotting) ? 1 : 0;   // scene switch
    const int promptRows = (currentWorkflowMode == WorkflowMode::AutoSpotting) ? 0 : 1;   // no prompt in Spotting
    const int toggleHeight = (isSoundRec && toggleSoundResultsButton.isVisible()) ? 28 : 0;
    const int resultsHeight = (isSoundRec && soundRecommendations.isVisible())
                                  ? SoundRecommendationsComponent::heightForRows (8) : 0;

    int contentHeight = 24 +  // Top margin
                        3 * 28 +  // Mode switch, three rows
                        (20 + 28) * promptRows +  // Prompt row (all modes but Spotting)
                        (20 + 28) * audioRows +  // Negative prompt row
                        (20 + 28) * audioRows +  // Seed row
                        (20 + 28) +  // Backend row (every mode)
                        (20 + 28) * (hybridRows + spottingRows) +  // Hybrid switch rows, Spotting scene row
                        30 +  // Spacing before buttons
                        28 +  // Button row
                        8 + 28 +  // Whole-track button row
                        8 + 16 + 20 +  // Progress bar and label
                        15 +  // Spacing
                        toggleHeight +           // Toggle button row
                        (resultsHeight > 0 ? 10 + resultsHeight : 0) + // Sound recommendations list
                        10 +  // Spacing
                        28 +  // Settings button row
                        24;   // Bottom margin
    
    // Set content component size (width matches viewport for horizontal scroll, calculated height)
    int minContentWidth = 700;  // Minimum width to ensure all content fits
    int actualWidth = juce::jmax (getWidth(), minContentWidth);
    contentComponent.setSize (actualWidth, contentHeight);
    
    // Layout components within contentComponent with 24px margin around edges
    auto r = contentComponent.getLocalBounds().reduced (24);
    
    // Mode switch at the top: one block of three rows, label and (i) beside it
    auto modeBlock = r.removeFromTop (3 * 28);
    modeLabel.setBounds (modeBlock.removeFromLeft (65).removeFromTop (28));
    modeBlock.removeFromLeft (10);
    modeInfoButton.setBounds (modeBlock.removeFromRight (24).withSizeKeepingCentre (24, 24));   // the (i)
    modeBlock.removeFromRight (8);
    autoSpottingModeButton.setBounds (modeBlock.removeFromTop (28));
    auto leftColumn = modeBlock.removeFromLeft (modeBlock.getWidth() / 2);
    audioGenModeButton.setBounds (leftColumn.removeFromTop (28));
    soundRecModeButton.setBounds (leftColumn);
    hybridModeButton.setBounds (modeBlock);   // spans both rows beside the two
    
    // Prompt row (collapsed in Spotting, which has no text input)
    r.removeFromTop (20 * promptRows);
    auto promptRow = r.removeFromTop (28 * promptRows);

    // Prompt text input: full width, 28px height
    promptLabel.setBounds (promptRow.removeFromLeft (65));
    promptRow.removeFromLeft (10);    
    prompt.setBounds (promptRow);

    // 20px spacing between components (collapsed outside Sound Generation and Hybrid)
    r.removeFromTop (20 * audioRows);

    // Negative prompt row: Label + Input field
    auto negativePromptRow = r.removeFromTop (28 * audioRows);
    negativePromptLabel.setBounds (negativePromptRow.removeFromLeft (65));
    negativePromptRow.removeFromLeft (10);
    negativePromptInput.setBounds (negativePromptRow);

    // 20px spacing before next row (collapsed outside Sound Generation and Hybrid)
    r.removeFromTop (20 * audioRows);

    // Seed and generation mode row: Label + Input + Radio Buttons + Duration - responsive layout
    auto seedRow = r.removeFromTop (28 * audioRows);
    seedLabel.setBounds (seedRow.removeFromLeft (65));
    seedRow.removeFromLeft (10);
    
    // Fixed width for seed input
    seedInput.setBounds (seedRow.removeFromLeft (120));
    seedRow.removeFromLeft (20);
    
    // Calculate remaining space for V2A/T2A buttons and duration
    int remainingWidth = seedRow.getWidth();
    int v2aWidth = juce::jmin (140, remainingWidth * 3 / 10);  // Roughly 30% or 140px
    int t2aWidth = juce::jmin (130, remainingWidth * 3 / 10);  // Roughly 30% or 130px
    
    // Segmented switch for V2A/T2A mode
    v2aModeButton.setBounds (seedRow.removeFromLeft (v2aWidth));
    t2aModeButton.setBounds (seedRow.removeFromLeft (t2aWidth));
seedRow.removeFromLeft (20);
    
    // Duration controls (only active in T2A mode) - use remaining space
    if (seedRow.getWidth() > 155)  // Only show if enough space
    {
        durationLabel.setBounds (seedRow.removeFromLeft (70));
        seedRow.removeFromLeft (5);
        durationComboBox.setBounds (seedRow.removeFromLeft (80));
    }
    else
    {
        durationLabel.setBounds (seedRow.removeFromLeft (juce::jmin (70, seedRow.getWidth() / 2)));
        seedRow.removeFromLeft (5);
        durationComboBox.setBounds (seedRow);
    }
    
    // 20px spacing before the backend row
    r.removeFromTop (20);

    // Backend row: Label + adapter list (every mode)
    auto modelRow = r.removeFromTop (28);
    modelLabel.setBounds (modelRow.removeFromLeft (65));
    modelRow.removeFromLeft (10);
    modelProviderComboBox.setBounds (modelRow.removeFromLeft (230));

    // Hybrid: the event switches and the database switches under the backend row (collapsed elsewhere)
    const int hybridRowHeight = isHybrid ? 28 : 0;
    r.removeFromTop (isHybrid ? 20 : 0);
    auto memoryRow = r.removeFromTop (hybridRowHeight);
    memoryRow.removeFromLeft (75);
    useMemoryLocationsToggle.setBounds (memoryRow.removeFromLeft (230));
    memoryRow.removeFromLeft (20);
    autoSpotToggle.setBounds (memoryRow);
    r.removeFromTop (isHybrid ? 20 : 0);
    auto databaseRow = r.removeFromTop (hybridRowHeight);
    databaseRow.removeFromLeft (75);
    useDatabaseSoundsToggle.setBounds (databaseRow.removeFromLeft (230));
    databaseRow.removeFromLeft (20);
    keepGeneratedToggle.setBounds (databaseRow);
    r.removeFromTop (isHybrid ? 20 : 0);
    auto handlesRow = r.removeFromTop (hybridRowHeight);
    handlesRow.removeFromLeft (75);
    ambienceHandlesToggle.setBounds (handlesRow.removeFromLeft (230));
    handlesRow.removeFromLeft (20);
    if (isHybrid)
        detectScenesToggle.setBounds (handlesRow);
    // Spotting: the scene switch alone under the backend row
    const bool isSpottingMode = currentWorkflowMode == WorkflowMode::AutoSpotting;
    r.removeFromTop (isSpottingMode ? 20 : 0);
    auto scenesRow = r.removeFromTop (isSpottingMode ? 28 : 0);
    scenesRow.removeFromLeft (75);
    if (isSpottingMode)
        detectScenesToggle.setBounds (scenesRow);


    // 30px spacing before next row
    //r.removeFromTop (30);
    
    // Video offset row: Label + Input field (deprecated TODO remove in future)
    // auto offsetRow = r.removeFromTop (28);
    // Label: 220px wide (deprecated TODO remove in future)
    // videoOffsetLabel.setBounds (offsetRow.removeFromLeft (220));
    // 10px spacing between label and input
    // offsetRow.removeFromLeft (10);
    // Input field: fixed 80px width (deprecated TODO remove in future)
    // videoOffsetInput.setBounds (offsetRow.removeFromLeft (80));

    // 30px spacing before buttons section
    r.removeFromTop (30);

    // Main action button - centered
    auto buttonRow = r.removeFromTop (28);
    const int actionW = 160;
    buttonRow.removeFromLeft ((buttonRow.getWidth() - actionW) / 2);  // Center
    actionButton.setBounds (buttonRow.removeFromLeft (actionW));

    // Spotting only: whole-track button under the action button
    r.removeFromTop (8);
    auto spotAllRow = r.removeFromTop (28);
    const int spotAllW = 200;
    spotAllRow.removeFromLeft ((spotAllRow.getWidth() - spotAllW) / 2);
    spotWholeTrackButton.setBounds (spotAllRow.removeFromLeft (spotAllW));
    hybridWholeTrackButton.setBounds (spotWholeTrackButton.getBounds());

    // Progress of a running multi-clip operation
    r.removeFromTop (8);
    progressBar.setBounds (r.removeFromTop (16).reduced (40, 0));
    progressLabel.setBounds (r.removeFromTop (20));

    // Toggle button for sound recommendations - centered below render button
    r.removeFromTop (15);  // Spacing
    auto toggleButtonRow = r.removeFromTop (toggleHeight);
    toggleButtonRow.removeFromLeft ((toggleButtonRow.getWidth() - 200) / 2);  // Center
    toggleSoundResultsButton.setBounds (toggleButtonRow.removeFromLeft (200));

    // Sound recommendations list - eight rows when shown, nothing otherwise
    if (resultsHeight > 0)
        r.removeFromTop (10);  // Spacing
    soundRecommendations.setBounds (r.removeFromTop (resultsHeight));

    // Settings row at bottom: [Open Log] ... [Warning Label] [API Settings Button]
    auto settingsRow = r.removeFromBottom (28);
    r.removeFromBottom (10);  // Spacing
    
    // Left side button
    const int openLogW = 90;
    openLogButton.setBounds (settingsRow.removeFromLeft (openLogW));
    
    // Calculate positions for warning label and settings button (right-aligned)
    const int warningWidth = 160;
    const int settingsWidth = 180;
    const int settingsGap = 10;
    const int totalSettingsWidth = warningWidth + settingsGap + settingsWidth;
    
    settingsRow.removeFromLeft (contentComponent.getWidth() - openLogW - totalSettingsWidth - 24);  // Space between left and right
    apiWarningLabel.setBounds (settingsRow.removeFromLeft (warningWidth));
    settingsRow.removeFromLeft (settingsGap);
    settingsButton.setBounds (settingsRow.removeFromLeft (settingsWidth));

}

//==============================================================================
// Async PTSL Communication Implementation
//==============================================================================

//==============================================================================
// Async PTSL - Timeline Selection Read Only (T2A workflow - no video required)
//==============================================================================

void PtV2AEditor::startTimelineSelectionReadOnly()
{
    juce::Logger::writeToLog ("=== Starting Async Timeline Selection Read (T2A - No Video) ===");
    
    auto pythonExe = processor.getPythonExecutable();
    auto scriptFile = processor.getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: API client script not found");
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Script Error",
            "API client script not found.\n\n"
            "Please check plugin installation.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        return;
    }
    
    // Build command: Use get_timeline_selection (no video clip check)
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("get_video_selection");  // T2A: timeline only, no video file lookup
    
    juce::Logger::writeToLog ("Starting PTSL process (async)...");
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // Create and start process
    ptslProcess = std::make_unique<juce::ChildProcess>();
    
    if (!ptslProcess->start (commandArray))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start PTSL process");
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Process Error",
            "Failed to start Python process for timeline selection.\n\n"
            "Please check plugin installation.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        ptslProcess.reset();
        return;
    }
    
    // Record start time for timeout detection
    asyncOperationStartTime = juce::Time::getCurrentTime();
    currentAsyncState = AsyncState::ReadingTimeline;
    
    // Start timer to poll process status every 100ms
    startTimer (TIMER_INTERVAL_MS);
    
    juce::Logger::writeToLog ("Timeline selection started (T2A mode), timer polling every " + 
                              juce::String (TIMER_INTERVAL_MS) + "ms");
}

//==============================================================================
// Async PTSL - Cursor Position Read (T2A workflow)


void PtV2AEditor::timerCallback()
{
    auto elapsed = juce::Time::getCurrentTime() - asyncOperationStartTime;
    
    // Handle different async states
    switch (currentAsyncState)
    {
        case AsyncState::ReadingTimeline:
        {
            // Safety check
            if (!ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                return;
            }
            
            // Check for timeout
            if (elapsed.inMilliseconds() > PTSL_TIMEOUT_MS)
            {
                juce::Logger::writeToLog ("ERROR: Timeline selection timed out after " + 
                                          juce::String (PTSL_TIMEOUT_MS) + "ms");
                
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Timeout",
                    "Timeline selection read timed out.\n\n"
                    "Make sure:\n"
                    "1. Pro Tools is running\n"
                    "2. You have a timeline selection (In/Out points)\n"
                    "3. PTSL is enabled in Pro Tools preferences",
                    "OK"
                );
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Generate Sound");
                return;
            }
            
            // Check if process is still running
            if (ptslProcess->isRunning())
            {
                // Still running - keep waiting, Pro Tools stays responsive!
                return;
            }
            
            // Process finished! Read output and stop timer
            juce::Logger::writeToLog ("Timeline selection finished after " + 
                                      juce::String (elapsed.inMilliseconds()) + "ms");
            
            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            
            juce::Logger::writeToLog ("Timeline selection output:");
            juce::Logger::writeToLog (output);
            
            // Pass output to handler for parsing
            handleTimelineSelectionResult (output);
            break;
        }
        
        case AsyncState::ResolvingVideoSegments:
        {
            // standalone_api_client.py --action resolve_video_segments bisects the timeline
            // selection over PTSL: a few seconds per clip boundary, so a generous limit.
            constexpr int resolveTimeoutMs = 120000;

            if (! ptslProcess)
            {
                stopTimer();
                resetActionUi();
                return;
            }

            if (elapsed.inMilliseconds() > resolveTimeoutMs)
            {
                juce::Logger::writeToLog ("ERROR: resolve_video_segments timed out");
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();

                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Timeout",
                    "Reading the selection from Pro Tools timed out.\n\n"
                    "Make sure Pro Tools is running with PTSL enabled.",
                    "OK"
                );
                resetActionUi();
                return;
            }

            if (ptslProcess->isRunning())
                return;

            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            stopTimer();
            juce::Logger::writeToLog ("resolve_video_segments finished after "
                                      + juce::String (elapsed.inSeconds(), 1) + "s");
            juce::Logger::writeToLog (output);
            handleVideoSegmentsResult (output);
            break;
        }

        case AsyncState::ReadingTimelineForSoundImport:
        {
            // Reading timeline position for sound import (before actual import)
            if (!ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                juce::Logger::writeToLog ("ERROR: PTSL process lost during timeline read for sound import");
                return;
            }
            
            // Check for timeout (30 seconds for timeline read)
            if (elapsed.inMilliseconds() > 30000)
            {
                juce::Logger::writeToLog ("ERROR: Timeline read for sound import timed out after 30s");
                
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Timeout",
                    "Could not read timeline position.\n\n"
                    "Importing at session start instead.",
                    "OK"
                );
                
                // Fallback: Import at default position
                currentTimecodeOut.clear();
                startSoundImportProcess (pendingSoundImport, "");
                return;
            }
            
            // Check if process is still running
            if (ptslProcess->isRunning())
            {
                return;  // Keep waiting
            }
            
            // Process finished - read output
            juce::Logger::writeToLog ("Timeline read for sound import finished after " + 
                                      juce::String (elapsed.inMilliseconds()) + "ms");
            
            auto output = ptslProcess->readAllProcessOutput();
            juce::Logger::writeToLog ("Timeline output: " + output);
            
            ptslProcess.reset();
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            
            // Parse JSON to get in_time
            auto lines = juce::StringArray::fromLines (output);
            juce::String jsonOutput;
            for (const auto& line : lines)
            {
                if (line.trimStart().startsWith ("{"))
                {
                    jsonOutput = line.trim();
                    break;
                }
            }
            
            juce::String currentTimecode;
            if (jsonOutput.isNotEmpty())
            {
                auto json = juce::JSON::parse (jsonOutput);
                if (auto* obj = json.getDynamicObject())
                {
                    // For sound import, we only need timeline position (edit cursor), not a video clip
                    // So extract in_time even if success=false (which means no video clip selected)
                    currentTimecode = obj->getProperty ("in_time").toString();
                    currentTimecodeOut = obj->getProperty ("out_time").toString();
                    
                    if (currentTimecode.isNotEmpty() && currentTimecode != "00:00:00:00")
                    {
                        juce::Logger::writeToLog ("Current timeline position: " + currentTimecode);
                    }
                    else
                    {
                        juce::Logger::writeToLog ("No valid timeline position, using session start");
                        currentTimecode = "";  // Explicitly clear for session start
                    }
                }
            }
            
            // Now start the actual import with current timeline position
            startSoundImportProcess (pendingSoundImport, currentTimecode);
            
            break;
        }
        
        case AsyncState::GeneratingAudio:
        {
            // Poll for output file existence
            checkAudioGenerationComplete();
            break;
        }
        
        case AsyncState::SearchingSounds:
        {
            // Poll for sound search output file (fire-and-forget process, no ChildProcess to manage)
            // Check for timeout (120 seconds for video preprocessing + X-CLIP + downloads)
            if (elapsed.inMilliseconds() > 120000)
            {
                juce::Logger::writeToLog ("ERROR: Sound search timed out after 120s");
                
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                
                // Cleanup output file if exists
                juce::File outputFile (expectedSoundSearchOutputPath);
                if (outputFile.existsAsFile())
                    outputFile.deleteFile();
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Sound Search Timeout",
                    "Sound search timed out after 120 seconds.\n\n"
                    "This may be due to:\n"
                    "- Large video files\n"
                    "- Slow X-CLIP processing\n"
                    "- Network issues during sound downloads",
                    "OK"
                );
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Recommend Sounds");
                return;
            }
            
            // Check if output file exists (non-blocking file check)
            juce::File outputFile (expectedSoundSearchOutputPath);
            
            if (!outputFile.existsAsFile())
            {
                // Still processing, log progress every 5 seconds
                if ((elapsed.inMilliseconds() / 1000) % 5 == 0 && (elapsed.inMilliseconds() % 1000) < TIMER_INTERVAL_MS)
                {
                    juce::Logger::writeToLog ("Sound search still running... (" + 
                                              juce::String (elapsed.inSeconds(), 1) + "s elapsed)");
                }
                return;  // Keep polling
            }
            
            // Output file found! Read results
            juce::Logger::writeToLog ("Sound search completed after " + 
                                      juce::String (elapsed.inSeconds(), 1) + "s");
            juce::Logger::writeToLog ("Output file: " + outputFile.getFullPathName());
            
            auto jsonText = outputFile.loadFileAsString();
            
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            
            // Handle results (this will show error/success messages)
            handleSoundSearchResult (jsonText);
            
            // Re-enable button AFTER results are parsed
            actionButton.setEnabled (true);
            actionButton.setButtonText ("Recommend Sounds");
            
            // Cleanup output file
            outputFile.deleteFile();
            break;
        }
        
        case AsyncState::DownloadingSingleSound:
        {
            // Poll for sound download output file
            // Check for timeout (60 seconds for single sound download)
            if (elapsed.inMilliseconds() > 60000)
            {
                juce::Logger::writeToLog ("ERROR: Sound download timed out after 60s");
                
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                
                // Clear downloading state so user can retry
                soundRecommendations.clearDownloadingState (currentDownloadingSound.id);
                
                // Cleanup output file if exists
                juce::File outputFile (expectedSoundDownloadOutputPath);
                if (outputFile.existsAsFile())
                    outputFile.deleteFile();
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Download Timeout",
                    "Sound download timed out after 60 seconds.\n\n"
                    "Please check your network connection and try again.",
                    "OK"
                );
                
                return;
            }
            
            // Check if output file exists (non-blocking file check)
            juce::File outputFile (expectedSoundDownloadOutputPath);
            
            if (!outputFile.existsAsFile())
            {
                // Still downloading, log progress every 2 seconds
                if ((elapsed.inMilliseconds() / 1000) % 2 == 0 && (elapsed.inMilliseconds() % 1000) < TIMER_INTERVAL_MS)
                {
                    juce::Logger::writeToLog ("Downloading sound... (" + 
                                              juce::String (elapsed.inSeconds(), 1) + "s elapsed)");
                }
                return;  // Keep polling
            }
            
            // Output file found! Read results
            juce::Logger::writeToLog ("Sound download completed after " + 
                                      juce::String (elapsed.inSeconds(), 1) + "s");
            juce::Logger::writeToLog ("Output file: " + outputFile.getFullPathName());
            
            auto jsonText = outputFile.loadFileAsString();
            
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            
            // Parse JSON response
            auto jsonResult = juce::JSON::parse (jsonText);
            if (auto* jsonObject = jsonResult.getDynamicObject())
            {
                juce::String status = jsonObject->getProperty ("status").toString();
                
                if (status == "success")
                {
                    juce::String localPath = jsonObject->getProperty ("local_path").toString();
                    int soundId = currentDownloadingSound.id;
                    
                    juce::Logger::writeToLog ("✓ Sound downloaded successfully: ID=" + juce::String(soundId) + ", path=" + localPath);
                    
                    // Mark sound as downloaded in UI component
                    soundRecommendations.markSoundAsDownloaded (soundId, localPath);
                    if (autoImportSoundId == soundId)
                    {
                        autoImportSoundId = -1;
                        auto sound = currentDownloadingSound;
                        sound.localPath = localPath;
                        handleSoundImport (sound);
                        return;
                    }
                }
                else
                {
                    juce::String message = jsonObject->getProperty ("message").toString();
                    juce::Logger::writeToLog ("ERROR: Sound download failed: " + message);
                    
                    // Clear downloading state so user can retry
                    soundRecommendations.clearDownloadingState (currentDownloadingSound.id);
                    
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::WarningIcon,
                        "Download Failed",
                        "Failed to download sound:\n\n" + message,
                        "OK"
                    );
                }
            }
            
            // Cleanup output file
            outputFile.deleteFile();
            break;
        }
        
        case AsyncState::HybridEstimate:
        {
            // hybrid_client.py --estimate: a quick PTSL pass that counts the clips. Then the
            // dialog with the numbers, and the real run on "Start".
            if (! ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                resetSpottingUi();
                return;
            }
            if (ptslProcess->isRunning())
            {
                if (elapsed.inSeconds() > 120)
                {
                    juce::Logger::writeToLog ("ERROR: hybrid estimate did not finish in two minutes");
                    stopTimer();
                    ptslProcess->kill();
                    ptslProcess.reset();
                    currentAsyncState = AsyncState::Idle;
                    resetSpottingUi();
                    showStatus ("Could not read the video track (no answer in two minutes). Is Pro Tools open?", true);
                }
                return;
            }
            const int exitCode = ptslProcess->getExitCode();
            ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            auto resultFile = spottingProgressFile.withFileExtension ("result.json");
            auto json = juce::JSON::parse (resultFile.existsAsFile() ? resultFile.loadFileAsString() : juce::String());
            const juce::String scriptLog = spottingProgressFile.withFileExtension ("log").loadFileAsString();
            resetSpottingUi();
            if (exitCode != 0 || ! json.isObject() || ! (bool) json.getProperty ("success", false))
            {
                juce::Logger::writeToLog ("Hybrid estimate failed:\n" + scriptLog);
                showStatus ("Could not read the video track: " + json.getProperty ("error", "see the log").toString(), true);
                return;
            }
            const int clips = (int) json.getProperty ("clips", 0);
            const double seconds = (double) json.getProperty ("video_seconds", 0.0);
            const int estimate = (int) json.getProperty ("estimate_seconds", 0);
            const bool resumable = (bool) json.getProperty ("resumable", false);
            const int clipsDone = (int) json.getProperty ("clips_done", 0);
            const bool scenesKnown = (bool) json.getProperty ("scene_markers_present", false);
            auto minutes = [] (double s) { return juce::String (juce::roundToInt (s / 60.0)); };
            juce::String text = juce::String (clips) + (clips == 1 ? " clip, " : " clips, ")
                                + minutes (seconds) + " min of video on the track.\n\n"
                                + "Rough duration: " + (estimate >= 5400 ? juce::String (estimate / 3600.0, 1) + " hours"
                                                                        : minutes (estimate) + " minutes")
                                + " with a warm backend, more for the first clip.\n\n"
                                + (scenesKnown ? "The scene memory locations in the session are used as they are.\n"
                                               : detectScenesToggle.getToggleState()
                                                     ? "Scenes are detected first; a spotting run with Detect scenes "
                                                       "beforehand lets you correct them before this run.\n"
                                                     : juce::String())
                                + "Pro Tools is busy while sounds are placed. The Stop button ends the run; "
                                  "what was placed stays, and the run can be continued later.";
            if (resumable)
            {
                juce::AlertWindow::showYesNoCancelBox (
                    juce::MessageBoxIconType::QuestionIcon, "Continue the earlier run?",
                    "An earlier run over this range answered " + juce::String (clipsDone)
                    + (clipsDone == 1 ? " clip" : " clips") + " and was not finished.\n\n" + text,
                    "Continue", "Start over", "Cancel", this,
                    juce::ModalCallbackFunction::create ([this] (int result)
                    {
                        if (result == 1) startHybrid (true, true);
                        else if (result == 2) startHybrid (true, false);
                    }));
            }
            else
            {
                juce::AlertWindow::showOkCancelBox (
                    juce::MessageBoxIconType::QuestionIcon, "Run on the entire track?", text,
                    "Start", "Cancel", this,
                    juce::ModalCallbackFunction::create ([this] (int result) { if (result == 1) startHybrid (true, false); }));
            }
            return;
        }

        case AsyncState::SpottingAnalysis:
        case AsyncState::HybridGeneration:
        {
            // spotting_client.py or hybrid_client.py is running: cut, backend call, placement.
            // The script rewrites its progress file every few seconds (heartbeat), so the
            // run has no time limit; only when the file stops changing is the user asked.
            const bool hybrid = currentAsyncState == AsyncState::HybridGeneration;
            constexpr int staleMs = 5 * 60 * 1000;
            const juce::String what = hybrid ? "Hybrid generation" : "Spotting";

            if (!ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                resetSpottingUi();
                return;
            }

            const auto sinceProgress = juce::Time::getCurrentTime() - juce::jmax (asyncOperationStartTime, lastProgressTime);
            if (sinceProgress.inMilliseconds() > staleMs && ! staleDialogOpen && ptslProcess->isRunning())
            {
                // No sign of life for five minutes: the script is stuck (PTSL, ffmpeg, a
                // backend that hangs) or a stage is just very slow. The user decides.
                staleDialogOpen = true;
                const juce::String lastStage = progressLabel.getText();
                juce::Logger::writeToLog ("WARNING: " + what + ": no sign of life for five minutes. Last stage: " + lastStage);
                juce::AlertWindow::showOkCancelBox (
                    juce::MessageBoxIconType::WarningIcon, what + ": no sign of life",
                    "The script has not reported anything for five minutes.\n\nLast stage: "
                    + (lastStage.isNotEmpty() ? lastStage : juce::String ("unknown"))
                    + "\n\nKeep waiting, or stop the run? What was placed so far stays.",
                    "Keep waiting", "Stop", this,
                    juce::ModalCallbackFunction::create ([this] (int result)
                    {
                        staleDialogOpen = false;
                        if (currentAsyncState != AsyncState::SpottingAnalysis && currentAsyncState != AsyncState::HybridGeneration)
                            return;                     // finished meanwhile
                        if (result == 1)
                            lastProgressTime = juce::Time::getCurrentTime();
                        else
                            stopRun();
                    }));
            }

            if (ptslProcess->isRunning())
            {
                updateSpottingProgress();
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Stop  (" + juce::String ((int) elapsed.inSeconds()) + "s)");
                return;
            }

                        int exitCode = ptslProcess->getExitCode();
            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            const juce::String lastLabel = progressLabel.getText();
            if (runStopped)
            {
                runStopped = false;
                juce::Logger::writeToLog (what + " stopped by the user after " + juce::String (elapsed.inSeconds(), 1)
                                          + "s. Last stage: " + lastLabel);
                juce::Logger::writeToLog (spottingProgressFile.withFileExtension ("log").loadFileAsString());
                resetSpottingUi();
                showStatus (what + " stopped (" + (lastLabel.isNotEmpty() ? lastLabel : juce::String ("no stage reported"))
                            + "). What was placed stays" + (hybrid ? "; Run on entire track... can continue the run." : "."),
                            true);
                return;
            }

            // The script keeps its log and its result in files next to the progress
            // file (the pipe holds only 4 KB and is read after exit, so anything
            // larger would deadlock). Read both before resetSpottingUi() deletes them.
            auto scriptLog = spottingProgressFile.withFileExtension ("log").loadFileAsString();
            auto resultFile = spottingProgressFile.withFileExtension ("result.json");
            auto resultText = resultFile.existsAsFile() ? resultFile.loadFileAsString() : juce::String();
            resetSpottingUi();

            juce::Logger::writeToLog (what + " finished after " + juce::String (elapsed.inSeconds(), 1)
                                      + "s with exit code " + juce::String (exitCode));
            if (scriptLog.isNotEmpty())
                juce::Logger::writeToLog (scriptLog);
            juce::Logger::writeToLog (output);

            juce::String jsonOutput;
            for (const auto& line : juce::StringArray::fromLines (output))
                if (line.trimStart().startsWith ("{"))
                    jsonOutput = line.trim();

            auto json = juce::JSON::parse (jsonOutput);
            if (resultText.isNotEmpty())
            {
                auto fullResult = juce::JSON::parse (resultText);
                if (fullResult.isObject())
                    json = fullResult;
            }
            if (! json.isObject() && resultText.isEmpty() && scriptLog.isNotEmpty())
                output = scriptLog;             // so the failure dialog can quote the last log line
            bool success = exitCode == 0 && (bool) json.getProperty ("success", false);

            if (success && hybrid)
            {
                const int placed = (int) json.getProperty ("placed", 0);
                const int sounds = json.getProperty ("sounds", juce::var()).size();
                const int clips = (int) json.getProperty ("segments", 1);
                int failedClips = 0;
                for (const auto& clip : *json.getProperty ("clips", juce::Array<juce::var>()).getArray())
                    if (clip.hasProperty ("error"))
                        ++failedClips;
                const int dbPieces = (int) json.getProperty ("db_pieces", 0);
                const int dbPlaced = (int) json.getProperty ("db_placed", 0);
                const bool replaced = (bool) json.getProperty ("replaced", false);
                const int tracks = (int) json.getProperty ("tracks_used", 0);
                const int sceneCount = json.getProperty ("scenes", juce::var()).isArray()
                                           ? json.getProperty ("scenes", juce::var()).getArray()->size() : 0;
                juce::String message = juce::String (placed) + " of " + juce::String (sounds)
                                       + (replaced ? " sounds replaced by library pieces" : " sounds placed")
                                       + (tracks > 0 ? " on " + juce::String (tracks) + (tracks == 1 ? " track" : " tracks") : "")
                                       + (sceneCount > 0 ? " in " + juce::String (sceneCount) + (sceneCount == 1 ? " scene" : " scenes") : "")
                                       + ", from " + juce::String (clips) + (clips == 1 ? " clip" : " clips");
                if (const int dropped = (int) json.getProperty ("dropped_layers", 0); dropped > 0)
                    message += "; " + juce::String (dropped) + " extra library layer(s) left out (tracks per scene)";
                if (dbPieces > 0)
                    message += "; " + juce::String (dbPlaced) + " of " + juce::String (dbPieces) + " library pieces placed";
                if (const int markers = (int) json.getProperty ("markers_created", 0); markers > 0)
                    message += "; " + juce::String (markers) + " memory locations for the events the backend found";
                if (const int scenes = (int) json.getProperty ("scene_markers", 0); scenes > 0)
                    message += "; " + juce::String (scenes) + (scenes == 1 ? " scene" : " scenes") + " as memory locations";
                if (failedClips > 0)
                    message += "; " + juce::String (failedClips) + " clip(s) failed, see the log";
                showStatus (message, failedClips > 0 || placed < sounds || dbPlaced < dbPieces);
            }
            else if (success)
            {
                int created = (int) json.getProperty ("created", 0);
                int events = json.getProperty ("events", juce::var()).size();
                int fellBack = (int) json.getProperty ("fell_back_to_main_ruler", 0);
                juce::String model = json.getProperty ("model", "").toString();

                int clips = (int) json.getProperty ("segments", 1);
                int failedClips = 0;
                for (const auto& clip : *json.getProperty ("clips", juce::Array<juce::var>()).getArray())
                    if (clip.hasProperty ("error"))
                        ++failedClips;

                juce::String message = juce::String (created) + " markers placed for " + juce::String (events)
                                       + " sound events in " + juce::String (clips) + (clips == 1 ? " clip" : " clips");
                if (failedClips > 0)
                    message += "; " + juce::String (failedClips) + " clip(s) failed, see the log";
                if (fellBack > 0)
                    message += "; " + juce::String (fellBack) + " on the main ruler (marker ruler missing)";
                if (model.isNotEmpty())
                    message += "  [" + model + "]";
                showStatus (message, failedClips > 0);
            }
            else
            {
                juce::String error = json.getProperty ("error", "").toString();
                if (error.isEmpty())
                    error = output.trim().fromLastOccurrenceOf ("\n", false, false).substring (0, 300);

                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    what + " Failed",
                    "The run did not complete.\n\n" + error + "\n\n"
                    "Check that Pro Tools has a video selection, PTSL is enabled, and the "
                    + (hybrid ? juce::String ("hybrid") : juce::String ("spotting"))
                    + " backend is reachable at the URL in the settings.",
                    "OK"
                );
            }
            break;
        }

        case AsyncState::ImportingAudio:
        {
            // Safety check
            if (!ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                return;
            }
            
            // Check for timeout
            if (elapsed.inMilliseconds() > IMPORT_TIMEOUT_MS)
            {
                juce::Logger::writeToLog ("ERROR: Audio import timed out after " +
                                          juce::String (PTSL_TIMEOUT_MS) + "ms");

                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                if (! pendingSegments.isEmpty())
                {
                    segmentFailed ("import timed out");
                    return;
                }
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Import Timeout",
                    "Audio import to Pro Tools timed out.\n\n"
                    "The audio file was generated successfully but could not be imported.\n"
                    "You can manually import it from the temp directory.",
                    "OK"
                );
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Generate Sound");
                return;
            }
            
            // Check if process is still running
            if (ptslProcess->isRunning())
            {
                // Still running - keep waiting
                return;
            }
            
            // Process finished!
            juce::Logger::writeToLog ("Audio import finished after " + 
                                      juce::String (elapsed.inMilliseconds()) + "ms");
            
            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            
            juce::Logger::writeToLog ("Import output:");
            juce::Logger::writeToLog (output);
            
            // Handle import result
            handleAudioImportResult (output);
            break;
        }
        
        case AsyncState::ImportingSoundFX:
        {
            // Sound library import to 'Sound FX' track (same pattern as ImportingAudio)
            
            // Safety check
            if (!ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                return;
            }
            
            // Check for timeout (60s same as audio import)
            if (elapsed.inMilliseconds() > IMPORT_TIMEOUT_MS)
            {
                juce::Logger::writeToLog ("ERROR: Sound import timed out after " +
                                          juce::String (IMPORT_TIMEOUT_MS) + "ms");
                
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Sound Import Timeout",
                    "Sound import to Pro Tools timed out.\n\n"
                    "The import process did not complete within 2 minutes.",
                    "OK"
                );
                
                return;
            }
            
            // Check if process is still running
            if (ptslProcess->isRunning())
            {
                // Still running - keep waiting
                return;
            }
            
            // Process finished!
            juce::Logger::writeToLog ("Sound import finished after " + 
                                      juce::String (elapsed.inMilliseconds()) + "ms");
            
            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            
            juce::Logger::writeToLog ("Sound import output:");
            juce::Logger::writeToLog (output);
            
            // Parse output (look for success indicator)
            bool success = output.contains ("success") && output.contains ("true");
            
            if (success)
            {
                juce::Logger::writeToLog ("✅ Sound imported successfully to 'Sound FX' track");
            }
            else
            {
                juce::Logger::writeToLog ("⚠ Sound import may have failed - check output");
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Import Issue",
                    "Sound import completed but may have encountered issues.\n\n"
                    "Check the Pro Tools session to verify the sound was imported.",
                    "OK"
                );
            }
            
            break;
        }
        
        case AsyncState::Idle:
        default:
            // Nothing to do
            stopTimer();
            break;
    }
}

void PtV2AEditor::handleTimelineSelectionResult (const juce::String& output)
{
    // Parse output
    if (output.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: No output from PTSL process");
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Timeline Selection Error",
            "No output from PTSL process.\n\n"
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        return;
    }
    
    // Extract JSON from output (might have debug lines)
    auto lines = juce::StringArray::fromLines (output);
    juce::String jsonOutput;
    for (const auto& line : lines)
    {
        if (line.trimStart().startsWith ("{"))
        {
            jsonOutput = line.trim();
            break;
        }
    }
    
    if (jsonOutput.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: No JSON response in PTSL output");
        juce::Logger::writeToLog ("Full output: " + output);
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Timeline Selection Error",
            "No JSON response found in PTSL output.\n\n"
            "Check the log file for details.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        return;
    }
    
    // Parse JSON (now includes video_path from combined action!)
    auto json = juce::JSON::parse (jsonOutput);
    if (auto* obj = json.getDynamicObject())
    {
        bool success = obj->getProperty ("success");
        juce::String inTime = obj->getProperty ("in_time").toString();
        juce::String outTime = obj->getProperty ("out_time").toString();
        float durationSeconds = (float) (double) obj->getProperty ("duration_seconds");
        float inSeconds = (float) (double) obj->getProperty ("in_seconds");
        float outSeconds = (float) (double) obj->getProperty ("out_seconds");
        juce::String videoPath = obj->getProperty ("video_path").toString();
        juce::String errorMessage = obj->getProperty ("error").toString();
        
        if (!success)
        {
            juce::Logger::writeToLog ("Timeline selection FAILED: " + errorMessage);
            
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon,
                "Timeline Selection Error",
                "Could not read timeline selection:\n\n" +
                errorMessage + "\n\n"
                "Please:\n"
                "1. Mark a time range on the timeline (Selector tool)\n"
                "2. Pro Tools must be running with PTSL enabled",
                "OK"
            );
            
            actionButton.setEnabled (true);
            actionButton.setButtonText ("Generate Sound");
            return;
        }
        
        juce::Logger::writeToLog ("Timeline selection SUCCESS: " + inTime + " - " + outTime);
        juce::Logger::writeToLog ("Duration: " + juce::String (durationSeconds, 2) + "s");
        
        // Store timeline selection for audio import
        timelineInTime = inTime;
        timelineInSeconds = inSeconds;
        timelineOutSeconds = outSeconds;
        juce::Logger::writeToLog ("Stored timeline in-time: " + timelineInTime);
        juce::Logger::writeToLog ("Stored timeline in/out seconds: " + juce::String (inSeconds) + "s - " + juce::String (outSeconds) + "s");
        
        //======================================================================
        // T2A MODE: Skip video processing, start generation directly
        //======================================================================
        if (isT2AMode)
        {
            juce::Logger::writeToLog ("=== T2A Mode: Starting text-only audio generation ===");
            juce::Logger::writeToLog ("Duration: " + juce::String (t2aDuration, 1) + "s");
            juce::Logger::writeToLog ("Import position: " + inTime + " (" + juce::String (inSeconds, 2) + "s)");
            juce::Logger::writeToLog ("Prompt: " + prompt.getText());
            
            actionButton.setButtonText ("Generating Audio...");
            
            // Start T2A generation (no video processing needed)
            startT2AAudioGeneration (prompt.getText(), t2aDuration);
            return;  // Exit here - T2A workflow complete
        }
        
        // V2A no longer comes through here: it resolves the video segments under the
        // selection instead (startVideoSegmentResolve). Only T2A reads the bare selection.
        jassertfalse;
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        currentAsyncState = AsyncState::Idle;
    }
    else
    {
        juce::Logger::writeToLog ("ERROR: Failed to parse JSON response");
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Parse Error",
            "Failed to parse timeline selection response.\n\n"
            "Check the log file for details.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        currentAsyncState = AsyncState::Idle;
    }
}



//==============================================================================
// Async Audio Generation Implementation
//==============================================================================

void PtV2AEditor::startAudioGeneration (const juce::String& videoPath, const juce::String& promptText)
{
    juce::Logger::writeToLog ("=== Starting Async Audio Generation ===");
    juce::Logger::writeToLog ("Video: " + videoPath);
    juce::Logger::writeToLog ("Prompt: " + promptText);
    
    // Store parameters for later use
    currentVideoPath = videoPath;
    currentPrompt = promptText;
    
    // Get video clip offset from UI (if specified) (deprecated TODO remove in future)
    // juce::String videoOffset = videoOffsetInput.getText().trim();
    
    // Log clip bounds status
    if (clipStartSeconds >= 0.0f && clipEndSeconds >= 0.0f)
    {
        juce::Logger::writeToLog ("Using clip bounds: " + juce::String (clipStartSeconds, 3) + "s - " + juce::String (clipEndSeconds, 3) + "s");
    }
    // else if (videoOffset.isNotEmpty()) (deprecated TODO remove in future)
    // {
      //  juce::Logger::writeToLog ("Using manual video offset: " + videoOffset);
    // }
    else
    {
        juce::Logger::writeToLog ("No trimming - using full video");
    }
    
    // Read advanced parameters from UI
    juce::String negativePrompt = negativePromptInput.getText().trim();
    if (negativePrompt.isEmpty())
        negativePrompt = "voices, music";  // Default if empty
    
    juce::String seedText = seedInput.getText().trim();
    int seed = seedText.isEmpty() ? -1 : seedText.getIntValue();  // -1: random, drawn by the companion
    
    // bool useHighPrecision = highPrecisionModeToggle.getToggleState(); // (deprecated TODO remove in future)
    
    juce::Logger::writeToLog ("Backend: " + currentAdapter().name);
    juce::Logger::writeToLog ("Advanced params: negative_prompt=\"" + negativePrompt + "\", seed=" + juce::String(seed));
    
    // Call processor to start generation (returns immediately with expected output path)
    juce::String errorMessage;
    expectedAudioOutputPath = processor.generateAudioFromVideo (
        juce::File (videoPath),
        promptText,
        negativePrompt,  // User-controlled negative prompt
        seed,            // User-controlled seed
        "",              // No manual offset (deprecated TODO remove in future),
        timelineInSeconds,
        timelineOutSeconds,
        false,            // autoDetectClipBounds = false (legacy workflow, causes deadlock)
        clipStartSeconds, // Pass clip bounds if available
        clipEndSeconds,   // Pass clip bounds if available
        false,            // High precision mode flag (deprecated TODO remove in future)
        &errorMessage
    );
    
    if (expectedAudioOutputPath.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: Failed to start audio generation: " + errorMessage);
        if (! pendingSegments.isEmpty())
        {
            segmentFailed ("could not start: " + errorMessage);
            return;
        }
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Generation Failed",
            "Failed to start audio generation:\n\n" + errorMessage,
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    juce::Logger::writeToLog ("Expected output: " + expectedAudioOutputPath);
    juce::Logger::writeToLog ("Starting polling for output file...");
    
    // Switch to GeneratingAudio state
    currentAsyncState = AsyncState::GeneratingAudio;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    
    // Timer is already running from previous state, just continue polling
    if (!isTimerRunning())
        startTimer (TIMER_INTERVAL_MS);
}

//==============================================================================
// Async T2A Audio Generation (text-only, no video)
//==============================================================================

void PtV2AEditor::startT2AAudioGeneration (const juce::String& promptText, float duration)
{
    juce::Logger::writeToLog ("=== Starting T2A Audio Generation (text-only) ===");
    juce::Logger::writeToLog ("Prompt: " + promptText);
    juce::Logger::writeToLog ("Duration: " + juce::String (duration, 1) + "s");
    
    // Store parameters
    currentPrompt = promptText;
    
    // Read advanced parameters from UI
    juce::String negativePrompt = negativePromptInput.getText().trim();
    if (negativePrompt.isEmpty())
        negativePrompt = "voices, music";  // Default if empty
    
    juce::String seedText = seedInput.getText().trim();
    int seed = seedText.isEmpty() ? -1 : seedText.getIntValue();  // -1: random, drawn by the companion
    
    juce::Logger::writeToLog ("Backend: " + currentAdapter().name);
    juce::Logger::writeToLog ("Advanced params: negative_prompt=\"" + negativePrompt + "\", seed=" + juce::String(seed));
    
    // Call processor to start T2A generation (no video, just text + duration)
    juce::String errorMessage;
    expectedAudioOutputPath = processor.generateAudioTextOnly (
        promptText,
        duration,
        negativePrompt,
        seed,
        &errorMessage
    );

    if (expectedAudioOutputPath.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: Failed to start T2A generation: " + errorMessage);
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Generation Failed",
            "Failed to start T2A audio generation:\n\n" + errorMessage,
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    juce::Logger::writeToLog ("Expected T2A output: " + expectedAudioOutputPath);
    juce::Logger::writeToLog ("Starting polling for output file...");
    
    // Switch to GeneratingAudio state (same polling as V2A)
    currentAsyncState = AsyncState::GeneratingAudio;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    
    // Start timer to poll for output file
    if (!isTimerRunning())
        startTimer (TIMER_INTERVAL_MS);
}

//==============================================================================
// Source video duration via FFprobe (currently unused: PTSL clip bounds replaced it)
//==============================================================================

float PtV2AEditor::getSourceVideoDuration (const juce::String& videoPath)
{
    // Use Python script to call FFprobe and get video duration
    juce::Logger::writeToLog ("=== Checking Source Video Duration ===");
    juce::Logger::writeToLog ("Video: " + videoPath);
    
    // Get Python executable path
    juce::String pythonExe = processor.getPythonExecutable();
    juce::Logger::writeToLog ("Python: " + pythonExe);
    
    // Get API client script
    juce::File scriptFile = processor.getAPIClientScript();
    if (!scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: API client script not found at: " + scriptFile.getFullPathName());
        return 0.0f;
    }
    
    juce::Logger::writeToLog ("Script: " + scriptFile.getFullPathName());
    
    // Build command: python standalone_api_client.py --action get_duration --video "path"
    juce::StringArray args;
    args.add (pythonExe);
    args.add ("-X");
    args.add ("utf8");
    args.add (scriptFile.getFullPathName());
    args.add ("--action");
    args.add ("get_duration");
    args.add ("--video");
    args.add (videoPath);
    
    juce::Logger::writeToLog ("Command: " + args.joinIntoString (" "));
    
    // Execute command (synchronous, should be fast)
    juce::ChildProcess process;
    if (!process.start (args))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start Python process");
        return 0.0f;
    }
    
    // Wait for completion (max 5 seconds)
    bool finished = process.waitForProcessToFinish (5000);
    if (!finished)
    {
        juce::Logger::writeToLog ("ERROR: FFprobe check timed out");
        process.kill();
        return 0.0f;
    }
    
    // Read output
    juce::String output = process.readAllProcessOutput();
    juce::Logger::writeToLog ("FFprobe output: " + output);
    
    // Extract JSON from output (might have debug lines)
    auto lines = juce::StringArray::fromLines (output);
    juce::String jsonOutput;
    for (const auto& line : lines)
    {
        if (line.trimStart().startsWith ("{"))
        {
            jsonOutput = line.trim();
            break;
        }
    }
    
    if (jsonOutput.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: No JSON found in output");
        return 0.0f;
    }
    
    // Parse JSON response: {"success": true, "duration": 60.0}
    auto jsonResult = juce::JSON::parse (jsonOutput);
    if (jsonResult.isVoid())
    {
        juce::Logger::writeToLog ("ERROR: Failed to parse JSON response");
        return 0.0f;
    }
    
    bool success = jsonResult.getProperty ("success", false);
    if (!success)
    {
        juce::String error = jsonResult.getProperty ("error", "Unknown error");
        juce::Logger::writeToLog ("ERROR: FFprobe failed: " + error);
        return 0.0f;
    }
    
    float duration = (float) jsonResult.getProperty ("duration", 0.0);
    juce::Logger::writeToLog ("Source video duration: " + juce::String (duration, 2) + "s");
    
    return duration;
}

void PtV2AEditor::checkAudioGenerationComplete()
{
    // Check for timeout
    auto elapsed = juce::Time::getCurrentTime() - asyncOperationStartTime;
    if (elapsed.inMilliseconds() > GENERATION_TIMEOUT_MS)
    {
        juce::Logger::writeToLog ("ERROR: Audio generation timed out after " +
                                  juce::String (GENERATION_TIMEOUT_MS / 1000) + "s");
        if (! pendingSegments.isEmpty())
        {
            segmentFailed ("generation timed out");
            return;
        }

        stopTimer();
        currentAsyncState = AsyncState::Idle;
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Generation Timeout",
            "Audio generation timed out after 5 minutes.\n\n"
            "This might indicate:\n"
            "- API server is not responding\n"
            "- Network connection issues\n"
            "- Video is too complex to process\n\n"
            "Check the log file for details.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        return;
    }
    
    // expectedAudioOutputPath now contains the OUTPUT DIRECTORY (not specific file)
    // Find the newest .wav file in that directory
    juce::File outputDir (expectedAudioOutputPath);
    
    if (!outputDir.isDirectory())
    {
        // Fallback: treat as file path (backwards compatibility)
        juce::File outputFile (expectedAudioOutputPath);
        if (!outputFile.existsAsFile())
        {
            // Still generating, keep waiting
            int64_t elapsedMs = elapsed.inMilliseconds();
            if (elapsedMs > 0 && (elapsedMs / 1000) % 10 == 0 && (elapsedMs % 1000) < TIMER_INTERVAL_MS)
            {
                juce::Logger::writeToLog ("Still generating... (" + 
                                          juce::String (elapsedMs / 1000) + "s elapsed)");
            }
            return;
        }
        
        // File found! (backwards compatibility path)
        juce::Logger::writeToLog ("✓ Audio generation complete after " + 
                                  juce::String (elapsed.inSeconds()) + "s");
        juce::Logger::writeToLog ("Output file: " + expectedAudioOutputPath);
        
        stopTimer();
        actionButton.setButtonText ("Importing Audio...");
        updateSegmentProgress ("importing");
        
        // Sound search now triggered manually via "Recommend Sounds" button
        
        startAudioImport (expectedAudioOutputPath);
        return;
    }
    
    // Find newest .wav file in directory (server-generated filename with prompt snippet)
    juce::File newestWavFile;
    juce::Time newestTime;
    
    for (auto& entry : juce::RangedDirectoryIterator (outputDir, false, "*.wav"))
    {
        auto file = entry.getFile();
        auto modTime = file.getLastModificationTime();
        
        if (newestWavFile == juce::File() || modTime > newestTime)
        {
            newestWavFile = file;
            newestTime = modTime;
        }
    }
    
    // Check if a wav file was created after we started generation
    if (newestWavFile != juce::File() && newestTime >= asyncOperationStartTime)
    {
        // Found the generated audio file!
        juce::Logger::writeToLog ("✓ Audio generation complete after " + 
                                  juce::String (elapsed.inSeconds()) + "s");
        juce::Logger::writeToLog ("Output file: " + newestWavFile.getFullPathName());
        juce::Logger::writeToLog ("Filename: " + newestWavFile.getFileName());
        
        stopTimer();
        actionButton.setButtonText ("Importing Audio...");
        updateSegmentProgress ("importing");
        
        // Sound search now triggered manually via "Recommend Sounds" button
        
        startAudioImport (newestWavFile.getFullPathName());
    }
    else if (auto* proc = processor.getGenerationProcess(); proc != nullptr && ! proc->isRunning())
    {
        // The script has exited without producing a file: the backend refused or
        // dropped the request. Report its last lines now rather than after the timeout.
        auto scriptOutput = proc->readAllProcessOutput();
        juce::StringArray lines;
        lines.addLines (scriptOutput);
        lines.removeEmptyStrings();
        juce::String reason;
        for (int i = lines.size(); --i >= 0 && reason.isEmpty();)
            if (lines[i].containsIgnoreCase ("failed") || lines[i].containsIgnoreCase ("error"))
                reason = lines[i].trim();
        if (reason.isEmpty())
            reason = "exit code " + juce::String (proc->getExitCode());

        juce::Logger::writeToLog ("ERROR: generation script exited without an output file: " + reason);
        juce::Logger::writeToLog (scriptOutput);

        if (! pendingSegments.isEmpty())
        {
            segmentFailed ("backend: " + reason.substring (0, 120));
            return;
        }

        stopTimer();
        currentAsyncState = AsyncState::Idle;
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon, "Generation Failed",
            "The backend did not return audio.\n\n" + reason.substring (0, 300)
            + "\n\nIf the backend crashed while loading its model, give it more memory or "
              "stop other GPU programs and try again. Details are in the log.",
            "OK");
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
    }
    else
    {
        // Still generating, keep waiting
        int64_t elapsedMs = elapsed.inMilliseconds();
        if (elapsedMs > 0 && (elapsedMs / 1000) % 10 == 0 && (elapsedMs % 1000) < TIMER_INTERVAL_MS)
        {
            juce::Logger::writeToLog ("Still generating... (" +
                                      juce::String (elapsedMs / 1000) + "s elapsed)");
        }
    }
}

void PtV2AEditor::startAudioImport (const juce::String& audioPath)
{
    juce::Logger::writeToLog ("=== Starting Async Audio Import ===");
    juce::Logger::writeToLog ("Audio file: " + audioPath);
    
    auto pythonExe = processor.getPythonExecutable();
    auto scriptFile = processor.getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: API client script not found");
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Script Error",
            "API client script not found.\n\n"
            "Audio was generated successfully at:\n" + audioPath + "\n\n"
            "But automatic import failed.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Build command: python script.py --action import_audio --audio-path <path> --timecode <tc>
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("import_audio");
    commandArray.add ("--audio-path");
    commandArray.add (audioPath);
    
    // Add timecode position (same for both T2A and V2A - uses timeline selection start)
    juce::String importTimecode = timelineInTime;
    if (importTimecode.isNotEmpty())
    {
        juce::String modeLabel = isT2AMode ? "T2A" : "V2A";
        juce::Logger::writeToLog ("Import position (" + modeLabel + "): " + importTimecode);
    }
    
    if (importTimecode.isNotEmpty())
    {
        commandArray.add ("--timecode");
        commandArray.add (importTimecode);
    }
    else
    {
        juce::Logger::writeToLog ("Warning: No timeline position available, importing at session start");
    }

    // Onto the track this plugin sits on (new track only if that range is taken),
    // named after the video clip it belongs to.
    addImportTargetArgs (commandArray, currentImportClipLabel());
    
    juce::Logger::writeToLog ("Starting PTSL import process...");
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // Create and start process
    ptslProcess = std::make_unique<juce::ChildProcess>();
    
    if (!ptslProcess->start (commandArray))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start PTSL import process");
        if (! pendingSegments.isEmpty())
        {
            ptslProcess.reset();
            segmentFailed ("import could not start");
            return;
        }
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Import Error",
            "Failed to start audio import process.\n\n"
            "Audio was generated successfully at:\n" + audioPath + "\n\n"
            "You can manually import it to Pro Tools.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Generate Sound");
        ptslProcess.reset();
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Record start time for timeout detection
    asyncOperationStartTime = juce::Time::getCurrentTime();
    currentAsyncState = AsyncState::ImportingAudio;
    
    // Start timer to poll process status
    startTimer (TIMER_INTERVAL_MS);
    
    juce::Logger::writeToLog ("PTSL import started, timer polling...");
}

void PtV2AEditor::handleAudioImportResult (const juce::String& output)
{
    stopTimer();
    currentAsyncState = AsyncState::Idle;
    
    juce::Logger::writeToLog ("=== Audio Import Result ===");
    juce::Logger::writeToLog (output);
    
    // Parse output (look for success indicator)
    bool success = output.contains ("success") && output.contains ("true");

    if (! pendingSegments.isEmpty())
    {
        // One clip of a multi-clip run: count it and move on; the summary comes at the end.
        if (success)
            ++segmentsGenerated;
        else
            skippedSegments.add (pendingSegments[currentSegmentIndex].getProperty ("clip_name", "").toString()
                                 + " (import failed)");
        startNextSegmentGeneration();
        return;
    }

    if (success)
    {
        juce::Logger::writeToLog ("✓ Audio successfully imported to Pro Tools timeline!");
        showStatus ("Audio generated and placed at " + (timelineInTime.isNotEmpty() ? timelineInTime : juce::String ("session start"))
                    + (processor.getHostTrackName().isNotEmpty() ? " on track '" + processor.getHostTrackName() + "'" : juce::String()));
    }
    else
    {
        juce::Logger::writeToLog ("⚠️ Audio import may have failed");
        juce::Logger::writeToLog ("Output: " + output);
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Import Issue",
            "Audio was generated successfully, but import might have failed.\n\n"
            "Check the log file for details.\n"
            "You may need to manually import the audio file.",
            "OK"
        );
    }
    
    actionButton.setEnabled (true);
    actionButton.setButtonText ("Generate Sound");
}

//==============================================================================
// Video segments: the selection (made on any track) mapped onto the video track
//==============================================================================

void PtV2AEditor::startVideoSegmentResolve (ResolveTarget target)
{
    resolveTarget = target;
    auto scriptFile = processor.getAPIClientScript();

    if (! scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: API client script not found");
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon, "Script Error",
            "API client script not found.\n\nPlease check plugin installation.", "OK");
        resetActionUi();
        return;
    }

    // python -X utf8 standalone_api_client.py --action resolve_video_segments
    juce::StringArray args { processor.getPythonExecutable(), "-X", "utf8", scriptFile.getFullPathName(),
                             "--action", "resolve_video_segments" };
    juce::Logger::writeToLog ("Resolving video segments: " + args.joinIntoString (" "));

    ptslProcess = std::make_unique<juce::ChildProcess>();
    if (! ptslProcess->start (args))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start resolve_video_segments");
        ptslProcess.reset();
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon, "Process Error",
            "Failed to start the Python process that reads the selection.\n\nPlease check plugin installation.", "OK");
        resetActionUi();
        return;
    }

    actionButton.setEnabled (false);
    actionButton.setButtonText ("Reading selection...");
    progressValue = -1.0;   // no measurable progress yet: busy animation
    progressLabel.setText ("Looking up the video clips under the selection...", juce::dontSendNotification);
    progressBar.setVisible (true);
    progressLabel.setVisible (true);
    currentAsyncState = AsyncState::ResolvingVideoSegments;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    startTimer (TIMER_INTERVAL_MS);
}

void PtV2AEditor::handleVideoSegmentsResult (const juce::String& output)
{
    juce::String jsonLine;
    for (const auto& line : juce::StringArray::fromLines (output))
        if (line.trimStart().startsWith ("{"))
            jsonLine = line.trim();

    auto json = juce::JSON::parse (jsonLine);
    bool success = (bool) json.getProperty ("success", false);
    juce::String error = json.getProperty ("error", "").toString();
    auto segments = json.getProperty ("segments", juce::var());

    if (resolveTarget == ResolveTarget::SoundSearch)
    {
        progressBar.setVisible (false);
        progressLabel.setVisible (false);

        if (! success)
        {
            // No video under the selection (or no selection): search by text alone,
            // as the search always did when no video was available.
            juce::Logger::writeToLog ("Sound search without video: " + error);
            triggerSoundSearch ("", currentPrompt, "", 0.0f, 0.0f, -1.0f, -1.0f, false);
            return;
        }

        if (segments.size() != 1)
        {
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon, "Several Video Clips Selected",
                "The selection covers " + juce::String (segments.size()) + " video clips.\n\n"
                "Sound recommendation works on one clip at a time: narrow the selection "
                "so that it lies within a single clip.", "OK");
            resetActionUi();
            return;
        }

        auto seg = segments[0];
        float duration = (float) (double) seg.getProperty ("duration_seconds", 0.0);
        if (duration < 4.0f || duration > 12.0f)
        {
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon, "Selection Length",
                juce::String::formatted ("The selected video range is %.1f seconds long.\n\n"
                                         "Sound search needs a range of 4 to 12 seconds.", duration), "OK");
            resetActionUi();
            return;
        }

        currentVideoPath = seg.getProperty ("video_path", "").toString();
        timelineInTime = seg.getProperty ("in_time", "").toString();
        triggerSoundSearch (currentVideoPath, currentPrompt, "", 0.0f, 0.0f,
                            (float) (double) seg.getProperty ("source_start_seconds", -1.0),
                            (float) (double) seg.getProperty ("source_end_seconds", -1.0), true);
        if (! isTimerRunning())
            startTimer (TIMER_INTERVAL_MS);
        return;
    }

    // Generation: one run per clip under the selection
    if (! success)
    {
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon, "No Video Under the Selection",
            error + "\n\nMark a time range on any track; the video clips beneath it are used.", "OK");
        resetActionUi();
        return;
    }

    timelineFps = (float) (double) json.getProperty ("fps", 30.0);
    pendingSegments.clear();
    if (auto* array = segments.getArray())
        for (const auto& seg : *array)
        {
            // A selection edge that catches one frame of the neighbouring clip is not a
            // clip the user meant; leave it out of the queue and the summary.
            double duration = (double) seg.getProperty ("duration_seconds", 0.0);
            if (duration < 1.0)
                juce::Logger::writeToLog ("Ignoring " + seg.getProperty ("clip_name", "").toString()
                                          + ": only " + juce::String (duration, 3) + " s under the selection");
            else
                pendingSegments.add (seg);
        }
    currentSegmentIndex = -1;
    segmentsGenerated = 0;
    skippedSegments.clear();
    juce::Logger::writeToLog (juce::String (pendingSegments.size()) + " video segment(s) under the selection");
    startNextSegmentGeneration();
}

void PtV2AEditor::startNextSegmentGeneration()
{
    while (++currentSegmentIndex < pendingSegments.size())
    {
        auto seg = pendingSegments[currentSegmentIndex];
        juce::String name = seg.getProperty ("clip_name", "").toString();
        float duration = (float) (double) seg.getProperty ("duration_seconds", 0.0);

        if (const auto limits = currentAdapter(); limits.isValid() && ! limits.acceptsDuration (duration))
        {
            skippedSegments.add (name + " (" + juce::String (duration, 1) + " s, " + limits.name + " takes " + limits.durationRange() + ")");
            juce::Logger::writeToLog ("Skipping " + name + ": " + juce::String (duration, 2) + "s");
            continue;
        }

        currentVideoPath   = seg.getProperty ("video_path", "").toString();
        timelineInTime     = seg.getProperty ("in_time", "").toString();
        timelineInSeconds  = (float) (double) seg.getProperty ("in_seconds", 0.0);
        timelineOutSeconds = (float) (double) seg.getProperty ("out_seconds", 0.0);
        clipStartSeconds   = (float) (double) seg.getProperty ("source_start_seconds", -1.0);
        clipEndSeconds     = (float) (double) seg.getProperty ("source_end_seconds", -1.0);

        juce::Logger::writeToLog ("Segment " + juce::String (currentSegmentIndex + 1) + "/" + juce::String (pendingSegments.size())
                                  + ": " + name + " at " + timelineInTime + ", source "
                                  + juce::String (clipStartSeconds, 3) + "s-" + juce::String (clipEndSeconds, 3) + "s");
        updateSegmentProgress ("generating");
        actionButton.setButtonText ("Generating Audio...");
        startAudioGeneration (currentVideoPath, currentPrompt);
        return;
    }

    finishSegmentGeneration (true);
}

void PtV2AEditor::segmentFailed (const juce::String& reason)
{
    auto seg = pendingSegments[juce::jlimit (0, pendingSegments.size() - 1, currentSegmentIndex)];
    skippedSegments.add (seg.getProperty ("clip_name", "").toString() + " (" + reason + ")");
    juce::Logger::writeToLog ("Segment failed: " + reason);
    startNextSegmentGeneration();
}

void PtV2AEditor::updateSegmentProgress (const juce::String& stage)
{
    int total = pendingSegments.size();
    if (total == 0)
        return;

    auto seg = pendingSegments[juce::jlimit (0, total - 1, currentSegmentIndex)];
    progressValue = total > 1 ? (double) currentSegmentIndex / total : -1.0;   // -1: busy animation, no percentage from the backend
    progressLabel.setColour (juce::Label::textColourId, juce::Colours::lightgrey);
    progressLabel.setText ("Clip " + juce::String (currentSegmentIndex + 1) + " of " + juce::String (total) + ": "
                               + seg.getProperty ("clip_name", "").toString() + "  (" + stage + ")",
                           juce::dontSendNotification);
    progressBar.setVisible (true);
    progressLabel.setVisible (true);
}

void PtV2AEditor::finishSegmentGeneration (bool report)
{
    stopTimer();
    int total = pendingSegments.size();

    juce::String status;
    if (report && total > 0)
    {
        auto track = processor.getHostTrackName();
        status = juce::String (segmentsGenerated) + " of " + juce::String (total) + (total == 1 ? " clip" : " clips")
                 + " generated" + (track.isNotEmpty() ? " on track '" + track + "'" : juce::String());
        if (! skippedSegments.isEmpty())
            status += ". Skipped: " + skippedSegments.joinIntoString ("; ");

        if (segmentsGenerated == 0)
            juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Nothing Generated",
                                                    "No clip received audio.\n\n- " + skippedSegments.joinIntoString ("\n- "), "OK");
    }

    pendingSegments.clear();
    currentSegmentIndex = -1;
    resetActionUi();
    if (status.isNotEmpty())
        showStatus (status, ! skippedSegments.isEmpty());
}

void PtV2AEditor::showStatus (const juce::String& text, bool warning)
{
    progressBar.setVisible (false);
    progressLabel.setColour (juce::Label::textColourId,
                             warning ? juce::Colour (0xfff0a030) : juce::Colour (0xffa8d8a8));
    progressLabel.setText (text, juce::dontSendNotification);
    progressLabel.setVisible (true);
    juce::Logger::writeToLog ("Status: " + text);
}

juce::String PtV2AEditor::idleActionButtonText() const
{
    return currentWorkflowMode == WorkflowMode::AudioGeneration    ? "Generate Sound"
         : currentWorkflowMode == WorkflowMode::SoundRecommendation ? "Recommend Sounds"
         : currentWorkflowMode == WorkflowMode::Hybrid              ? "Generate Sound Events"
                                                                    : "Spot Selection";
}

juce::String PtV2AEditor::modeInfoTitle() const
{
    return currentWorkflowMode == WorkflowMode::AudioGeneration    ? "Sound Generation"
         : currentWorkflowMode == WorkflowMode::SoundRecommendation ? "Sound Recommendation"
         : currentWorkflowMode == WorkflowMode::Hybrid              ? "Hybrid"
                                                                    : "Spotting";
}

juce::String PtV2AEditor::modeDescription (WorkflowMode mode) const
{
    switch (mode)
    {
        case WorkflowMode::AudioGeneration:
            return "Mark a time range on any track. Sound is generated for each video clip beneath it, "
                   "from the picture and the optional prompt, and placed on this plugin's track at the clip's "
                   "position (or on a new track when it does not fit there). "
                   "T2A generates from the prompt alone, without video.";
        case WorkflowMode::SoundRecommendation:
            return "Mark a time range on any track, or type a prompt, and the sound archive is searched for "
                   "matching recordings. Preview them in the list and import one onto this plugin's track "
                   "at the selection.";
        case WorkflowMode::Hybrid:
            return "Mark a time range on any track. Instead of one mix, the backend returns one generated sound "
                   "per sound event in the range, and each is placed on its own new track, named after the event, "
                   "at the event's position. With 'Use existing memory locations' on, the memory locations inside "
                   "the range (a spotting run, or markers you set) define the events; a clip without any is spotted "
                   "by the backend first, or skipped when the second switch is off. With the first switch off, the "
                   "backend finds all events itself.";
        case WorkflowMode::AutoSpotting:
        default:
            return "Mark a time range on any track. The video clips beneath it are analysed one by one and a "
                   "memory location is placed for every sound event found, plus one at each clip boundary.";
    }
}

void PtV2AEditor::updateModeInfo()
{
    modeInfoButton.setTooltip (modeDescription (currentWorkflowMode));
}

void PtV2AEditor::resetActionUi()
{
    actionButton.setEnabled (true);
    actionButton.setButtonText (idleActionButtonText());
    spotWholeTrackButton.setEnabled (true);
    hybridWholeTrackButton.setEnabled (true);
    progressBar.setVisible (false);
    progressLabel.setVisible (false);
    currentAsyncState = AsyncState::Idle;
}

//==============================================================================
// Generation Mode Change Handler (V2A <-> T2A)
//==============================================================================
void PtV2AEditor::handleGenerationModeChange()
{
    isT2AMode = t2aModeButton.getToggleState();
    
    juce::Logger::writeToLog ("=== Generation Mode Changed ===");
    juce::Logger::writeToLog ("New mode: " + juce::String (isT2AMode ? "T2A (Text Only)" : "V2A (Video-to-Audio)"));
    
    // Duration controls: only enabled in T2A mode
    durationComboBox.setEnabled (isT2AMode);
    durationLabel.setEnabled (isT2AMode);
    
    // T2A needs a backend whose profile lists "text_only"; switch to the first such one.
    if (isT2AMode)
    {
        auto adapter = currentAdapter();
        if (adapter.isValid() && ! adapter.supportsFeature ("text_only"))
            for (size_t i = 0; i < adapterChoices.size(); ++i)
                if (adapterChoices[i].supportsFeature ("text_only"))
                {
                    juce::Logger::writeToLog ("T2A mode: switching backend to " + adapterChoices[i].name);
                    modelProviderComboBox.setSelectedId ((int) i + 1, juce::sendNotification);
                    break;
                }
    }
    applyAdapterCapabilities();
    
    repaint();
}

//==============================================================================
// API Credential Status Update
//==============================================================================
bool PtV2AEditor::tunnelTokenPresent (const juce::String& action)
{
    auto settings = processor.getBackendSettings();
    if (! settings.useTunnel || settings.clientSecret.isNotEmpty())
        return true;

    juce::AlertWindow::showMessageBoxAsync (
        juce::MessageBoxIconType::WarningIcon,
        "Tunnel Token Missing",
        "The backends are reached through a tunnel, but no access token is saved.\n\n"
        "Enter it under Settings before " + action + ", or switch the tunnel off there.",
        "OK"
    );
    return false;
}

void PtV2AEditor::updateBackendStatus()
{
    // Local backends need no token. Only a tunnel without a saved token is a
    // configuration the user has to act on before anything can work.
    auto settings = processor.getBackendSettings();
    const bool tokenMissing = settings.useTunnel && settings.clientSecret.isEmpty();

    apiWarningLabel.setText (juce::CharPointer_UTF8 ("\xe2\x9a\xa0 Tunnel enabled, token missing"),
                             juce::dontSendNotification);
    apiWarningLabel.setVisible (tokenMissing);

    // Open Log only makes sense while a log file is being written
    openLogButton.setEnabled (PtV2AProcessor::getLogFile() != juce::File());
}

//==============================================================================
// Workflow Mode Change Handler
//==============================================================================
void PtV2AEditor::handleWorkflowModeChange()
{
    // Update current workflow mode based on which button is selected
    if (audioGenModeButton.getToggleState())
        currentWorkflowMode = WorkflowMode::AudioGeneration;
    else if (soundRecModeButton.getToggleState())
        currentWorkflowMode = WorkflowMode::SoundRecommendation;
    else if (autoSpottingModeButton.getToggleState())
        currentWorkflowMode = WorkflowMode::AutoSpotting;
    else if (hybridModeButton.getToggleState())
        currentWorkflowMode = WorkflowMode::Hybrid;

    bool isAudioGen = (currentWorkflowMode == WorkflowMode::AudioGeneration);
    bool isSoundRec = (currentWorkflowMode == WorkflowMode::SoundRecommendation);
    bool isAutoSpotting = (currentWorkflowMode == WorkflowMode::AutoSpotting);
    bool isHybrid = (currentWorkflowMode == WorkflowMode::Hybrid);

    juce::Logger::writeToLog ("=== Workflow Mode Changed ===");
    juce::Logger::writeToLog ("New mode: " + modeInfoTitle());
    
    // Update action button text; a running operation keeps its "Spotting... (40s)" style
    // text, and its reset picks the idle text of whatever mode is current by then.
    if (actionButton.isEnabled())
        actionButton.setButtonText (idleActionButtonText());
    updateModeInfo();
    
    // Show/hide fields based on workflow mode
    // Prompt is visible in Audio Gen and Sound Rec, hidden in Auto Spotting
    prompt.setVisible (!isAutoSpotting);
    promptLabel.setVisible (!isAutoSpotting);
    
    // Whole-track button only visible in Auto Spotting mode
    spotWholeTrackButton.setVisible (isAutoSpotting);
    hybridWholeTrackButton.setVisible (isHybrid);
    
    // Generation parameters: Sound Generation and Hybrid
    negativePromptInput.setVisible (isAudioGen || isHybrid);
    negativePromptLabel.setVisible (isAudioGen || isHybrid);

    seedInput.setVisible (isAudioGen || isHybrid);
    seedLabel.setVisible (isAudioGen || isHybrid);
    useMemoryLocationsToggle.setVisible (isHybrid);
    autoSpotToggle.setVisible (isHybrid);
    useDatabaseSoundsToggle.setVisible (isHybrid);
    keepGeneratedToggle.setVisible (isHybrid);
    ambienceHandlesToggle.setVisible (isHybrid);
    detectScenesToggle.setVisible (isHybrid || currentWorkflowMode == WorkflowMode::AutoSpotting);
    
    // V2A/T2A toggle only visible in Sound Generation (not used in Sound Recommendation)
    // Sound Search automatically tries video detection first, then falls back to text-only
    v2aModeButton.setVisible (isAudioGen);
    t2aModeButton.setVisible (isAudioGen);
    
    // Duration and model always visible in Audio Gen (enabled state controlled by V2A/T2A)
    durationComboBox.setVisible (isAudioGen);
    durationLabel.setVisible (isAudioGen);
    
    // The Backend list is shown in every mode with that mode's adapter profiles
    modelProviderComboBox.setVisible (true);
    modelLabel.setVisible (true);
    refreshAdapterCombo();

    // Database results and their show/hide toggle belong to Sound Recommendation only
    const bool showResults = isSoundRec && soundRecommendations.hasResults();
    toggleSoundResultsButton.setVisible (showResults);
    soundRecommendations.setVisible (showResults);
    if (showResults)
        toggleSoundResultsButton.setButtonText ("Hide Database Sounds (" + juce::String (soundRecommendations.getResultCount()) + ")");

    if (! isSoundRec)
        processor.stopSoundPreview();
    resized();
    repaint();
}

//==============================================================================
// Cloudflare Access Credential Dialog
//==============================================================================
//==============================================================================
// Adapter profiles: the Backend list per mode
//==============================================================================
juce::String PtV2AEditor::currentAdapterKind() const
{
    return currentWorkflowMode == WorkflowMode::AudioGeneration    ? "generation"
         : currentWorkflowMode == WorkflowMode::SoundRecommendation ? "search"
         : currentWorkflowMode == WorkflowMode::Hybrid              ? "hybrid"
                                                                    : "spotting";
}

void PtV2AEditor::refreshAdapterCombo()
{
    const auto kind = currentAdapterKind();
    adapterChoices.clear();
    for (const auto& p : processor.getAdapterProfiles())
        if (p.kind == kind)
            adapterChoices.push_back (p);

    auto selected = processor.getSelectedAdapter (kind);
    modelProviderComboBox.clear (juce::dontSendNotification);
    int selectedId = 0;
    for (size_t i = 0; i < adapterChoices.size(); ++i)
    {
        modelProviderComboBox.addItem (adapterChoices[i].name, (int) i + 1);
        if (adapterChoices[i].file == selected.file)
            selectedId = (int) i + 1;
    }
    if (adapterChoices.empty())
    {
        modelProviderComboBox.addItem ("No adapter profile for this mode (see Settings)", 1);
        selectedId = 1;
    }
    modelProviderComboBox.setSelectedId (selectedId, juce::dontSendNotification);
    modelProviderComboBox.setEnabled (! adapterChoices.empty());
    applyAdapterCapabilities();
}

AdapterProfile PtV2AEditor::currentAdapter() const
{
    const int index = modelProviderComboBox.getSelectedId() - 1;
    if (index >= 0 && index < (int) adapterChoices.size())
        return adapterChoices[(size_t) index];
    return {};
}

void PtV2AEditor::handleAdapterChanged()
{
    auto adapter = currentAdapter();
    if (adapter.isValid())
        processor.setSelectedAdapter (currentAdapterKind(), adapter.file);
    applyAdapterCapabilities();
    updateBackendStatus();
}

void PtV2AEditor::applyAdapterCapabilities()
{
    if (currentWorkflowMode != WorkflowMode::AudioGeneration && currentWorkflowMode != WorkflowMode::Hybrid)
        return;
    auto adapter = currentAdapter();
    const bool known = adapter.isValid();
    const bool negative = ! known || adapter.supportsFeature ("negative_prompt");
    const bool seed = ! known || adapter.supportsFeature ("seed");
    const bool textOnly = ! known || adapter.supportsFeature ("text_only");
    negativePromptInput.setEnabled (negative);
    negativePromptLabel.setEnabled (negative);
    seedInput.setEnabled (seed);
    seedLabel.setEnabled (seed);
    if (currentWorkflowMode == WorkflowMode::Hybrid)
    {
        const bool memory = ! known || adapter.supportsFeature ("memory_locations");
        useMemoryLocationsToggle.setEnabled (memory);
        if (! memory)
            useMemoryLocationsToggle.setToggleState (false, juce::dontSendNotification);
        autoSpotToggle.setEnabled (memory && useMemoryLocationsToggle.getToggleState());
        // Database sounds: the profile must claim it, and the backend's health must confirm it
        // (search service reachable, audio index present); asked in the background.
        const bool claimed = ! known || adapter.supportsFeature ("database_match");
        hybridMatchAvailable = claimed;
        hybridMatchReason = claimed ? juce::String() : adapter.name + " does not offer database sounds";
        applyHybridMatchAvailability();
        if (known && claimed)
            refreshHybridBackendHealth();
        return;
    }
    t2aModeButton.setEnabled (textOnly);
    t2aModeButton.setTooltip (textOnly ? juce::String() : adapter.name + " needs a video");

    // T2A lengths: whole seconds between the profile's min and max (4-12 s when unknown),
    // the profile's default preselected, a still-valid earlier choice kept.
    const double lo = known ? adapter.minDuration : 4.0;
    const double hi = known ? adapter.maxDuration : 12.0;
    const double preset = known ? adapter.defaultDuration : 8.0;
    const double previous = durationComboBox.getText().dropLastCharacters (1).getDoubleValue();
    const int step = juce::jmax (1, (int) std::ceil ((hi - lo) / 40.0));    // never more than ~40 items
    durationComboBox.clear (juce::dontSendNotification);
    int id = 0, selected = 0, nearestDefault = 0;
    double nearestGap = 1.0e9;
    for (double s = std::ceil (lo); s <= hi + 1.0e-9; s += step)
    {
        durationComboBox.addItem (juce::String ((int) s) + "s", ++id);
        if (previous > 0.0 && std::abs (s - previous) < 1.0e-6) selected = id;
        if (std::abs (s - preset) < nearestGap) { nearestGap = std::abs (s - preset); nearestDefault = id; }
    }
    if (id == 0)      // range narrower than a second: offer the maximum
    {
        durationComboBox.addItem (juce::String (hi, 1) + "s", ++id);
        nearestDefault = id;
    }
    durationComboBox.setSelectedId (selected > 0 ? selected : nearestDefault, juce::dontSendNotification);
}

void PtV2AEditor::refreshBackendAvailability()
{
    struct Probe { juce::String kind, name, url; };
    std::vector<Probe> probes;
    const bool tunnel = processor.getBackendSettings().useTunnel;
    for (auto* kind : { "spotting", "generation", "search", "hybrid" })
    {
        auto adapter = processor.getSelectedAdapter (kind);
        probes.push_back ({ kind, adapter.name,
                            adapter.isValid() ? adapter.activeUrl (tunnel) + adapter.health : juce::String() });
    }
    const int request = ++availabilityRequest;
    juce::Component::SafePointer<PtV2AEditor> safeThis (this);
    juce::Thread::launch ([safeThis, probes, request, tunnel]
    {
        std::map<juce::String, BackendAvailability> results;
        for (const auto& probe : probes)
        {
            BackendAvailability state;
            if (probe.url.isEmpty())
            {
                state.available = false;
                state.reason = "no " + probe.kind + " backend profile in the adapters folder (Settings)";
            }
            else if (tunnel)
            {
                state.available = true;          // the tunnel needs the token; the Python side checks that
            }
            else
            {
                int status = 0;
                auto stream = juce::URL (probe.url).createInputStream (
                    juce::URL::InputStreamOptions (juce::URL::ParameterHandling::inAddress)
                        .withConnectionTimeoutMs (3000).withStatusCode (&status));
                if (stream != nullptr)
                    stream->readEntireStreamAsString();
                state.available = stream != nullptr && status >= 200 && status < 300;
                if (! state.available)
                    state.reason = probe.name + " does not answer at " + probe.url
                                   + (status > 0 ? " (" + juce::String (status) + ")" : juce::String());
            }
            results[probe.kind] = state;
        }
        juce::MessageManager::callAsync ([safeThis, request, results]
        {
            if (safeThis == nullptr || request != safeThis->availabilityRequest)
                return;                                    // a newer probe superseded this one
            safeThis->backendAvailability = results;
            safeThis->applyBackendAvailability();
            juce::Timer::callAfterDelay (30000, [safeThis, request]
            {
                if (safeThis != nullptr && request == safeThis->availabilityRequest)
                    safeThis->refreshBackendAvailability();
            });
        });
    });
}

void PtV2AEditor::applyBackendAvailability()
{
    const std::pair<juce::TextButton*, std::pair<juce::String, WorkflowMode>> modes[] = {
        { &autoSpottingModeButton, { "spotting",   WorkflowMode::AutoSpotting } },
        { &audioGenModeButton,     { "generation", WorkflowMode::AudioGeneration } },
        { &soundRecModeButton,     { "search",     WorkflowMode::SoundRecommendation } },
        { &hybridModeButton,       { "hybrid",     WorkflowMode::Hybrid } },
    };
    for (const auto& [button, info] : modes)
    {
        const auto state = backendAvailability.find (info.first);
        const bool available = state == backendAvailability.end() || state->second.available;
        button->setEnabled (available);
        button->setTooltip (available ? modeDescription (info.second)
                                      : "Not available: " + state->second.reason + "\n\n" + modeDescription (info.second));
    }
}

void PtV2AEditor::applyHybridMatchAvailability()
{
    useDatabaseSoundsToggle.setEnabled (hybridMatchAvailable);
    if (! hybridMatchAvailable)
        useDatabaseSoundsToggle.setToggleState (false, juce::dontSendNotification);
    useDatabaseSoundsToggle.setTooltip (hybridMatchAvailable
        ? juce::String ("On: for every generated sound the backend finds library recordings that sound like it, "
                        "stitched from at most the pieces per 10 s set in Settings, and places them instead of the "
                        "generated sound (which stays only where nothing matched).")
        : "Not available: " + hybridMatchReason);
    keepGeneratedToggle.setEnabled (hybridMatchAvailable && useDatabaseSoundsToggle.getToggleState());
    ambienceHandlesToggle.setEnabled (hybridMatchAvailable && useDatabaseSoundsToggle.getToggleState());
}

void PtV2AEditor::refreshHybridBackendHealth()
{
    // GET <backend>/health in the background; "database_match": {"available", "reason"} decides
    // whether the database switch is usable. A backend that says nothing keeps the profile's word.
    auto adapter = currentAdapter();
    if (! adapter.isValid())
        return;
    const int request = ++hybridHealthRequest;
    juce::URL url (adapter.activeUrl (processor.getBackendSettings().useTunnel) + adapter.health);
    juce::Component::SafePointer<PtV2AEditor> safeThis (this);
    juce::Thread::launch ([safeThis, url, request]() mutable
    {
        int statusCode = 0;
        juce::String body;
        if (auto stream = url.createInputStream (juce::URL::InputStreamOptions (juce::URL::ParameterHandling::inAddress)
                                                     .withConnectionTimeoutMs (4000).withStatusCode (&statusCode)))
            body = stream->readEntireStreamAsString();
        juce::MessageManager::callAsync ([safeThis, request, statusCode, body]
        {
            if (safeThis == nullptr || request != safeThis->hybridHealthRequest)
                return;                                    // stale: a newer check is on its way
            bool available = safeThis->hybridMatchAvailable;
            juce::String reason = safeThis->hybridMatchReason;
            if (statusCode <= 0 || statusCode >= 400)
            {
                available = false;
                reason = "the backend does not answer (" + juce::String (statusCode) + ")";
            }
            else if (auto json = juce::JSON::parse (body); json.isObject() && json.hasProperty ("database_match"))
            {
                auto match = json.getProperty ("database_match", juce::var());
                available = (bool) match.getProperty ("available", false);
                reason = match.getProperty ("reason", "").toString();
                if (! available && reason.isEmpty())
                    reason = "the backend reports no library match";
            }
            safeThis->hybridMatchAvailable = available;
            safeThis->hybridMatchReason = reason;
            safeThis->applyHybridMatchAvailability();
        });
    });
}

void PtV2AEditor::showSettings()
{
    juce::Component::SafePointer<PtV2AEditor> safeThis (this);

    juce::DialogWindow::LaunchOptions options;
    options.dialogTitle = juce::String (PtV2AProcessor::kPluginName) + " - Settings";
    options.dialogBackgroundColour = getLookAndFeel().findColour (juce::ResizableWindow::backgroundColourId);
    options.content.setOwned (new SettingsPanel (processor, [safeThis]
    {
        if (safeThis != nullptr)
        {
            safeThis->updateBackendStatus();
            safeThis->refreshAdapterCombo();     // profiles or addresses may have changed
            safeThis->refreshBackendAvailability();
        }
    }));
    options.componentToCentreAround = this;
    options.useNativeTitleBar = true;
    options.resizable = false;
    options.escapeKeyTriggersCloseButton = true;

    // Async, like every other dialog here: a blocking modal loop would stall Pro Tools.
    options.launchAsync();
}

//==============================================================================
// Sound Search Event Handlers
//==============================================================================

void PtV2AEditor::startSoundPreview (const SoundResult& sound)
{
    // Diagnostics: does Pro Tools run this track's audio at all? The preview is mixed
    // into processBlock(), so without calls there is nothing to hear.
    {
        auto callsAtStart = processor.getProcessBlockCount();
        juce::Logger::writeToLog ("Preview: processBlock calls so far " + juce::String (callsAtStart)
                                  + ", engine sample rate " + juce::String (processor.getCurrentSampleRateReported()));
        juce::Component::SafePointer<PtV2AEditor> safeThis (this);
        juce::Timer::callAfterDelay (2000, [safeThis, callsAtStart]
        {
            if (safeThis == nullptr)
                return;
            auto now = safeThis->processor.getProcessBlockCount();
            juce::Logger::writeToLog ("Preview: processBlock calls after 2 s " + juce::String (now)
                                      + ", transport playing = " + juce::String ((int) safeThis->processor.isSoundPreviewPlaying()));
            if (now == callsAtStart)
                safeThis->showStatus ("Pro Tools is not processing this track, so the preview cannot be heard "
                                      "(check the track's output and that the engine is running).", true);
        });
    }

    // Already on disk (downloaded for import)? Play that.
    if (sound.localPath.isNotEmpty() && juce::File (sound.localPath).existsAsFile())
    {
        if (processor.startSoundPreview (sound.localPath))
            soundRecommendations.setPreviewing (sound.id);
        return;
    }

    // Preview cache in the temp folder, one file per sound id; the extension comes
    // from the server's content type because the decoder is chosen by extension.
    auto cacheDir = juce::File::getSpecialLocation (juce::File::tempDirectory).getChildFile ("ai_sound_design_previews");
    cacheDir.createDirectory();
    for (const auto& entry : juce::RangedDirectoryIterator (cacheDir, false, "preview_" + juce::String (sound.id) + ".*"))
    {
        if (entry.getFile().getSize() > 0 && processor.startSoundPreview (entry.getFile().getFullPathName()))
        {
            soundRecommendations.setPreviewing (sound.id);
            return;
        }
    }
    auto target = cacheDir.getChildFile ("preview_" + juce::String (sound.id) + ".mp3");

    // Fetch <sound_search>/sounds/<id>/preview off the message thread, then play.
    auto settings = processor.getBackendSettings();
    juce::URL url (processor.getConfiguredAPIUrl ("sound_search").trimCharactersAtEnd ("/") + "/sounds/" + juce::String (sound.id) + "/preview");
    juce::String headers;
    if (settings.useTunnel && settings.clientSecret.isNotEmpty())
        headers = "CF-Access-Client-Id: " + settings.clientId + "\r\nCF-Access-Client-Secret: " + settings.clientSecret + "\r\n";

    soundRecommendations.setPreviewLoading (sound.id);
    juce::Component::SafePointer<PtV2AEditor> safeThis (this);
    const int id = sound.id;
    juce::Logger::writeToLog ("Fetching preview: " + url.toString (false));

    juce::Thread::launch ([safeThis, url, headers, target, id]() mutable
    {
        bool ok = false;
        juce::StringPairArray responseHeaders;
        int statusCode = 0;
        auto options = juce::URL::InputStreamOptions (juce::URL::ParameterHandling::inAddress)
                           .withConnectionTimeoutMs (8000)
                           .withExtraHeaders (headers)
                           .withResponseHeaders (&responseHeaders)
                           .withStatusCode (&statusCode);
        if (auto stream = url.createInputStream (options); stream != nullptr && statusCode < 400)
        {
            auto type = responseHeaders.getValue ("Content-Type", "").toLowerCase();
            juce::String ext = type.contains ("wav")  ? ".wav"
                             : type.contains ("flac") ? ".flac"
                             : type.contains ("aiff") ? ".aiff"
                             : type.contains ("ogg")  ? ".ogg"
                                                      : ".mp3";
            target = target.withFileExtension (ext);
            juce::TemporaryFile temp (target);
            if (auto out = temp.getFile().createOutputStream())
            {
                out->writeFromInputStream (*stream, -1);
                out.reset();
                ok = temp.getFile().getSize() > 0 && temp.overwriteTargetFileWithTemporary();
            }
        }
        juce::MessageManager::callAsync ([safeThis, target, id, ok]
        {
            if (safeThis == nullptr)
                return;
            if (ok && safeThis->processor.startSoundPreview (target.getFullPathName()))
                safeThis->soundRecommendations.setPreviewing (id);
            else
            {
                safeThis->soundRecommendations.setPreviewing (-1);
                safeThis->showStatus ("Preview not available; check that the sound search backend is reachable.", true);
            }
        });
    });
}

void PtV2AEditor::handleSoundDownload (const SoundResult& sound)
{
    juce::Logger::writeToLog ("=== Sound Download Clicked ===");
    juce::Logger::writeToLog ("Sound ID: " + juce::String (sound.id));
    juce::Logger::writeToLog ("Description: " + sound.description);
    
    // Store current sound for download process
    currentDownloadingSound = sound;
    
    // Get Python executable and sound_search_api_client.py (sibling to standalone_api_client.py)
    auto pythonExe = processor.getPythonExecutable();
    auto scriptFile = processor.getAPIClientScript();
    auto soundSearchClientScript = scriptFile.getParentDirectory().getChildFile ("sound_search_api_client.py");
    
    if (!soundSearchClientScript.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: sound_search_api_client.py not found at: " + soundSearchClientScript.getFullPathName());
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Script Error",
            "Sound search client script not found.\n\n"
            "Please check plugin installation.",
            "OK"
        );
        return;
    }
    
    // Generate session ID for output file
    auto sessionId = juce::Uuid().toString().replaceCharacter ('-', '_');
    expectedSoundDownloadOutputPath = juce::File::getSpecialLocation (juce::File::tempDirectory)
                                           .getChildFile ("sound_download_" + sessionId + ".json")
                                           .getFullPathName();
    
    // Build command: python sound_search_api_client.py --action download --sound-id <id> --session-id <id> --output-json <path>
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (soundSearchClientScript.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("download");
    commandArray.add ("--sound-id");
    commandArray.add (juce::String (sound.id));
    commandArray.add ("--session-id");
    commandArray.add (sessionId);
    commandArray.add ("--output-json");
    commandArray.add (expectedSoundDownloadOutputPath);
    commandArray.add ("--quiet");
    
    juce::Logger::writeToLog ("Starting sound download process...");
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // Start process
    soundDownloadProcess = std::make_unique<juce::ChildProcess>();
    
    if (!soundDownloadProcess->start (commandArray))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start sound download process");
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Process Error",
            "Failed to start sound download process.\n\n"
            "Please check plugin installation.",
            "OK"
        );
        soundDownloadProcess.reset();
        return;
    }
    
    juce::Logger::writeToLog ("✓ Sound download process started");
    
    // Mark sound as downloading in UI
    soundRecommendations.markSoundAsDownloading (sound.id);
    
    // Start async polling
    currentAsyncState = AsyncState::DownloadingSingleSound;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    startTimer (TIMER_INTERVAL_MS);
}

void PtV2AEditor::handleSoundImport (const SoundResult& sound)
{
    if (sound.localPath.isEmpty() || ! juce::File (sound.localPath).existsAsFile())
    {
        // One click does both: fetch the file, then place it (see the download branch of timerCallback).
        autoImportSoundId = sound.id;
        handleSoundDownload (sound);
        return;
    }
    juce::Logger::writeToLog ("=== Sound Import Clicked ===");
    juce::Logger::writeToLog ("Sound ID: " + juce::String (sound.id));
    juce::Logger::writeToLog ("Description: " + sound.description);
    juce::Logger::writeToLog ("Local Path: " + sound.localPath);
    
    // TASK 8: Import sound to Pro Tools timeline
    // Verify file exists
    juce::File audioFile (sound.localPath);
    if (!audioFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: Sound file not found: " + sound.localPath);
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "File Not Found",
            "Sound file not found:\n\n" + sound.localPath + "\n\n"
            "The file may have been deleted or moved.",
            "OK"
        );
        return;
    }
    
    // Store sound for after reading timeline position
    pendingSoundImport = sound;
    
    // First, read current timeline position (same pattern as V2A/T2A import)
    juce::Logger::writeToLog ("Reading current timeline position before import...");
    
    // Get Python executable and script
    auto pythonExe = processor.getPythonExecutable();
    auto scriptFile = processor.getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: API client script not found");
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Script Error",
            "API client script not found.\n\n"
            "Cannot read timeline position.",
            "OK"
        );
        return;
    }
    
    // Build timeline reading command: only the in-point is needed, no video lookup
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("get_video_selection");
    
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // Start PTSL timeline reading process
    ptslProcess = std::make_unique<juce::ChildProcess>();
    
    if (!ptslProcess->start (commandArray))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start timeline reading process");
        ptslProcess.reset();
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Timeline Read Error",
            "Failed to read timeline position.\n\n"
            "Importing at session start instead.",
            "OK"
        );
        // Fallback: Import at default position
        startSoundImportProcess (sound, "");
        return;
    }
    
    juce::Logger::writeToLog ("✓ Timeline reading process started");
    
    // Set async state and start polling for timeline info
    currentAsyncState = AsyncState::ReadingTimelineForSoundImport;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    
    // Start timer if not already running
    if (!isTimerRunning())
        startTimer (TIMER_INTERVAL_MS);
    
    juce::Logger::writeToLog ("Timeline reading polling started...");
}

void PtV2AEditor::addImportTargetArgs (juce::StringArray& commandArray, const juce::String& clipLabel)
{
    auto track = processor.getHostTrackName();
    if (track.isNotEmpty())
    {
        commandArray.add ("--track-name");
        commandArray.add (track);
    }
    else
    {
        juce::Logger::writeToLog ("Host has not reported a track name; importing to a new track");
    }
    if (clipLabel.isNotEmpty())
    {
        commandArray.add ("--clip-name");
        commandArray.add (clipLabel);
    }
}

juce::String PtV2AEditor::currentImportClipLabel() const
{
    juce::String base;
    if (currentSegmentIndex >= 0 && currentSegmentIndex < pendingSegments.size())
        base = pendingSegments[currentSegmentIndex].getProperty ("clip_name", "").toString();
    if (base.isEmpty() && currentVideoPath.isNotEmpty())
        base = juce::File (currentVideoPath).getFileNameWithoutExtension();
    if (base.isEmpty())
        base = currentPrompt.trim().substring (0, 30);
    if (base.isEmpty())
        base = "generated";
    return base + " AI";
}

void PtV2AEditor::startSoundImportProcess (const SoundResult& sound, const juce::String& timecode)
{
    juce::Logger::writeToLog ("=== Starting Sound Import Process ===");
    juce::Logger::writeToLog ("Sound: " + sound.description);
    juce::Logger::writeToLog ("Timecode: " + (timecode.isEmpty() ? "(session start)" : timecode));
    
    // Get Python executable and script
    auto pythonExe = processor.getPythonExecutable();
    auto scriptFile = processor.getAPIClientScript();
    
    // Build import command
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("import_audio");
    commandArray.add ("--audio-path");
    commandArray.add (sound.localPath);
    
    // Add timecode if provided (from current timeline position)
    if (timecode.isNotEmpty())
    {
        commandArray.add ("--timecode");
        commandArray.add (timecode);
        juce::Logger::writeToLog ("Import position: " + timecode);
        if (currentTimecodeOut.isNotEmpty() && currentTimecodeOut != timecode)
        {
            commandArray.add ("--timecode-out");
            commandArray.add (currentTimecodeOut);
        }
    }
    else
    {
        juce::Logger::writeToLog ("No timeline position, importing at session start");
    }
    addImportTargetArgs (commandArray, sound.description.substring (0, 40).trim());
    
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // Start import process
    soundImportProcess = std::make_unique<juce::ChildProcess>();
    
    if (!soundImportProcess->start (commandArray))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start import process");
        soundImportProcess.reset();
        currentAsyncState = AsyncState::Idle;
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Import Failed",
            "Failed to start import process.\n\n"
            "Sound: " + sound.description,
            "OK"
        );
        return;
    }
    
    juce::Logger::writeToLog ("✓ Sound import process started");
    
    // Set async state and start polling for completion
    currentAsyncState = AsyncState::ImportingSoundFX;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    
    // Move soundImportProcess to ptslProcess for polling
    ptslProcess = std::move(soundImportProcess);
    
    // Start timer if not already running
    if (!isTimerRunning())
        startTimer (TIMER_INTERVAL_MS);
    
    juce::Logger::writeToLog ("Sound import polling started...");
}

//==============================================================================
// Sound Search Integration (TASK 6)
//==============================================================================

void PtV2AEditor::triggerSoundSearch (
    const juce::String& videoPath, 
    const juce::String& prompt,
    const juce::String& videoOffset,
    float timelineStart,
    float timelineEnd,
    float clipStartSeconds,
    float clipEndSeconds,
    bool autoDetectClipBounds
)
{
    juce::Logger::writeToLog ("=== Triggering Sound Search ===");
    juce::Logger::writeToLog ("Video: " + (videoPath.isEmpty() ? "none (T2A mode)" : videoPath));
    juce::Logger::writeToLog ("Prompt: " + prompt);
    juce::Logger::writeToLog ("Video Offset: " + videoOffset);
    juce::Logger::writeToLog ("Timeline: " + juce::String(timelineStart) + "s - " + juce::String(timelineEnd) + "s");
    juce::Logger::writeToLog ("Clip Bounds: " + juce::String(clipStartSeconds) + "s - " + juce::String(clipEndSeconds) + "s");
    juce::Logger::writeToLog ("Auto-detect Clip Bounds: " + juce::String(autoDetectClipBounds ? "true" : "false"));
    juce::Logger::writeToLog ("Prompt: " + prompt);
    
    // Get Python executable and sound search script
    auto pythonExe = processor.getPythonExecutable();
    auto scriptFile = processor.getAPIClientScript();
    
    juce::Logger::writeToLog ("Python exe: " + pythonExe);
    juce::Logger::writeToLog ("Script dir: " + scriptFile.getParentDirectory().getFullPathName());
    
    if (!scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: Sound search script not found");
        soundRecommendations.clearResults();
        return;
    }
    
    // Get sound_search_api_client.py (sibling to standalone_api_client.py)
    auto soundSearchScript = scriptFile.getParentDirectory().getChildFile ("sound_search_api_client.py");
    
    if (!soundSearchScript.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: sound_search_api_client.py not found at: " + soundSearchScript.getFullPathName());
        soundRecommendations.clearResults();
        return;
    }
    
    // Generate session ID for this search
    auto sessionId = juce::Uuid().toDashedString().substring(0, 8);
    
    // Get Python's actual temp directory to match Python script behavior
    juce::ChildProcess tempDirProcess;
    juce::StringArray tempDirCmd;
    tempDirCmd.add (pythonExe);
    tempDirCmd.add ("-c");
    tempDirCmd.add ("import tempfile; print(tempfile.gettempdir())");
    
    juce::String pythonTempDir;
    if (tempDirProcess.start (tempDirCmd))
    {
        auto pythonTempOutput = tempDirProcess.readAllProcessOutput().trim();
        if (pythonTempOutput.isNotEmpty())
            pythonTempDir = pythonTempOutput;
    }
    
    // Fallback to JUCE temp dir if Python call failed
    if (pythonTempDir.isEmpty())
        pythonTempDir = juce::File::getSpecialLocation (juce::File::tempDirectory).getFullPathName();
    
    auto outputFile = juce::File(pythonTempDir).getChildFile ("sound_search_" + sessionId + ".json");
    
    // Store output file path for polling
    expectedSoundSearchOutputPath = outputFile.getFullPathName();
    
    // Build command: python sound_search_api_client.py --action search --limit 10 --session-id <id> [--video path] [--text prompt]
    juce::StringArray args;
    args.add (pythonExe);
    args.add ("-X");
    args.add ("utf8");
    args.add (soundSearchScript.getFullPathName());
    args.add ("--action");
    args.add ("search");
    args.add ("--limit");
    args.add (juce::String (processor.getBackendSettings().searchResults));   // "Sounds per search" in the settings
    args.add ("--quiet");  // Suppress progress messages
    args.add ("--session-id");
    args.add (sessionId);
    
    // Add video if available (V2A mode)
    if (videoPath.isNotEmpty() && juce::File(videoPath).existsAsFile())
    {
        args.add ("--video");
        args.add (videoPath);
        
        // Add timeline parameters if video is present
        // These enable video trimming to avoid sending large videos to API
        
        // Add clip bounds if auto-detect is enabled
        if (autoDetectClipBounds && clipStartSeconds >= 0.0f && clipEndSeconds >= 0.0f)
        {
            args.add ("--clip-start-seconds");
            args.add (juce::String (clipStartSeconds));
            args.add ("--clip-end-seconds");
            args.add (juce::String (clipEndSeconds));
            
            juce::Logger::writeToLog ("Sound Search: Using auto-detected clip bounds: " + 
                                     juce::String(clipStartSeconds) + "s - " + juce::String(clipEndSeconds) + "s");
        }
        // Otherwise, use manual video offset + timeline selection
        else if (videoOffset.isNotEmpty() && timelineStart != 0.0f && timelineEnd != 0.0f)
        {
            args.add ("--video-offset");
            args.add (videoOffset);
            args.add ("--timeline-start");
            args.add (juce::String (timelineStart));
            args.add ("--timeline-end");
            args.add (juce::String (timelineEnd));
            
            juce::Logger::writeToLog ("Sound Search: Using manual offset + timeline: offset=" + videoOffset + 
                                     ", timeline=" + juce::String(timelineStart) + "s - " + juce::String(timelineEnd) + "s");
        }
        else
        {
            juce::Logger::writeToLog ("Sound Search: No timeline parameters - using full video (will be downscaled if >2MB)");
        }
    }
    
    // Add text prompt if available
    if (prompt.isNotEmpty())
    {
        args.add ("--text");
        args.add (prompt);
    }
    
    // If neither video nor prompt available, skip search
    if (videoPath.isEmpty() && prompt.isEmpty())
    {
        juce::Logger::writeToLog ("INFO: No video or prompt available for sound search - skipping");
        soundRecommendations.clearResults();
        return;
    }
    
    juce::Logger::writeToLog ("Sound search command: " + args.joinIntoString (" "));
    juce::Logger::writeToLog ("Output file: " + outputFile.getFullPathName());
    
    // Launch subprocess (keep alive until file appears, but no stdout reading)
    soundSearchProcess = std::make_unique<juce::ChildProcess>();
    
    if (!soundSearchProcess->start (args))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start sound search process");
        soundRecommendations.clearResults();
        soundSearchProcess.reset();
        return;
    }
    
    juce::Logger::writeToLog ("Sound search process started (polling output file, non-blocking)");
    
    // Disable button during search
    actionButton.setEnabled (false);
    actionButton.setButtonText ("Searching...");
    
    // Set async state and use main timer for file polling (same as audio generation)
    asyncOperationStartTime = juce::Time::getCurrentTime();
    currentAsyncState = AsyncState::SearchingSounds;
    startTimer (TIMER_INTERVAL_MS);
}

void PtV2AEditor::handleSoundSearchResult (const juce::String& output)
{
    juce::Logger::writeToLog ("=== Sound Search Result ===");
    juce::Logger::writeToLog ("Output length: " + juce::String (output.length()) + " chars");
    
    if (output.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: Sound search returned empty output");
        soundRecommendations.clearResults();
        return;
    }
    
    juce::Logger::writeToLog (output);
    
    // Parse JSON response
    // Expected format:
    // {
    //   "status": "success",
    //   "count": 5,
    //   "results": [
    //     {
    //       "id": 5362,
    //       "description": "footsteps on concrete",
    //       "category": "Footsteps",
    //       "similarity": 0.85,
    //       "local_path": "/tmp/sound_5362.wav",
    //       "filename": "sound_5362.wav"
    //     },
    //     ...
    //   ]
    // }
    
    // CRITICAL: Extract JSON from output (may contain debug messages before/after)
    // The Python script writes debug logs to stderr/stdout, but JUCE reads everything together
    // We need to find the JSON object by looking for the outermost { ... }
    auto jsonStart = output.indexOfChar ('{');
    auto jsonEnd = output.lastIndexOfChar ('}');
    
    if (jsonStart < 0 || jsonEnd < 0 || jsonEnd <= jsonStart)
    {
        juce::Logger::writeToLog ("ERROR: Could not find JSON in output (no {...} found)");
        soundRecommendations.clearResults();
        return;
    }
    
    auto jsonString = output.substring (jsonStart, jsonEnd + 1);
    juce::Logger::writeToLog ("Extracted JSON (" + juce::String (jsonString.length()) + " chars)");
    
    auto json = juce::JSON::parse (jsonString);
    auto* jsonObj = json.getDynamicObject();
    
    if (jsonObj == nullptr)
    {
        juce::Logger::writeToLog ("ERROR: Failed to parse sound search JSON");
        soundRecommendations.clearResults();
        return;
    }
    
    auto status = jsonObj->getProperty ("status").toString();
    
    if (status != "success")
    {
        juce::Logger::writeToLog ("ERROR: Sound search failed - " + status);
        auto message = jsonObj->getProperty ("message").toString();
        juce::Logger::writeToLog ("Message: " + message);
        soundRecommendations.clearResults();
        return;
    }
    
    // Extract results array
    auto* resultsArray = jsonObj->getProperty ("results").getArray();
    
    if (resultsArray == nullptr || resultsArray->isEmpty())
    {
        juce::Logger::writeToLog ("INFO: No sound search results found");
        soundRecommendations.clearResults();
        return;
    }
    
    // Convert JSON results to SoundResult structs
    std::vector<SoundResult> sounds;
    
    for (int i = 0; i < resultsArray->size(); ++i)
    {
        auto* resultObj = (*resultsArray)[i].getDynamicObject();
        if (resultObj == nullptr)
            continue;
        
        SoundResult sound;
        sound.id = resultObj->getProperty ("id");
        sound.description = resultObj->getProperty ("description").toString();
        sound.category = resultObj->getProperty ("category").toString();
        sound.similarity = resultObj->getProperty ("similarity");
        sound.localPath = resultObj->getProperty ("local_path").toString();
        sound.filename = resultObj->getProperty ("filename").toString();
        sound.durationSeconds = (float) (double) resultObj->getProperty ("duration_seconds");
        
        sounds.push_back (sound);
        
        juce::Logger::writeToLog ("Sound " + juce::String (i + 1) + ": " + sound.description + 
                                  " (similarity: " + juce::String (sound.similarity, 3) + ")");
    }
    
    juce::Logger::writeToLog ("✓ Loaded " + juce::String (sounds.size()) + " sound recommendations");
    
    // Update UI with results
    soundRecommendations.setResults (sounds);
    
    // Show toggle button when results are available
    if (!sounds.empty())
    {
        toggleSoundResultsButton.setVisible (true);
        toggleSoundResultsButton.setButtonText ("Show Database Sounds (" + juce::String (sounds.size()) + ")");
        juce::Logger::writeToLog ("Toggle button made visible with " + juce::String (sounds.size()) + " results");
        
        // Auto-show results on first load
        soundRecommendations.setVisible (true);
        resized();
        juce::Logger::writeToLog ("Sound recommendations panel auto-shown");
        
        showStatus ("Found " + juce::String (sounds.size()) + " matching sounds; pick one below to import it.");
    }
}

//==============================================================================
// Toggle Sound Results Handler
//==============================================================================

void PtV2AEditor::handleToggleSoundResults()
{
    bool isCurrentlyVisible = soundRecommendations.isVisible();
    soundRecommendations.setVisible (!isCurrentlyVisible);
    if (isCurrentlyVisible)
        processor.stopSoundPreview();
    resized();
    
    // Update button text based on new state
    if (!isCurrentlyVisible)
    {
        // Now showing
        auto resultsCount = soundRecommendations.hasResults() ? 
            juce::String (" (") + juce::String (soundRecommendations.getResultCount()) + ")" : "";
        toggleSoundResultsButton.setButtonText ("Hide Database Sounds" + resultsCount);
    }
    else
    {
        // Now hiding
        auto resultsCount = soundRecommendations.hasResults() ? 
            juce::String (" (") + juce::String (soundRecommendations.getResultCount()) + ")" : "";
        toggleSoundResultsButton.setButtonText ("Show Database Sounds" + resultsCount);
    }
    
    juce::Logger::writeToLog ("Sound results toggled: " + juce::String (soundRecommendations.isVisible() ? "visible" : "hidden"));
}

//==============================================================================
// Recommend Sounds Button Handler
//==============================================================================

void PtV2AEditor::handleRecommendSoundsButtonClicked()
{
    juce::Logger::writeToLog ("=== Recommend Sounds Button Clicked ===");
    
    if (! tunnelTokenPresent ("searching sounds"))
        return;

    // Get prompt text
    juce::String promptText = prompt.getText();
    
    // Store prompt for use after PTSL completes
    currentPrompt = promptText;
    
    // Disable button during search
    actionButton.setEnabled (false);
    actionButton.setButtonText ("Searching...");
    
    // IMPORTANT: Sound Search always tries to get video from Pro Tools via PTSL first
    // Then falls back to text-only if no video is available
    // This is DIFFERENT from Sound Generation which respects V2A/T2A toggle
    
    juce::Logger::writeToLog ("Starting async PTSL workflow for sound search...");
    juce::Logger::writeToLog ("Will use video if available, otherwise text-only search");

    // Which video clip is under the selection? Text-only search if none.
    startVideoSegmentResolve (ResolveTarget::SoundSearch);
}

//==============================================================================
// Event Handler - Auto Spotting Button Click
//==============================================================================
void PtV2AEditor::handleAutoSpottingButtonClicked()
{
    juce::Logger::writeToLog ("=== Spotting Button Clicked ===");

    auto scriptPath = processor.getAPIClientScript().getParentDirectory().getChildFile ("spotting_client.py");
    if (! scriptPath.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: spotting_client.py not found at: " + scriptPath.getFullPathName());
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Spotting Script Not Found",
            "Could not find spotting_client.py.\n\nExpected location: " + scriptPath.getFullPathName(),
            "OK"
        );
        return;
    }

    startSpotting (false);
}

void PtV2AEditor::handleHybridButtonClicked()
{
    juce::Logger::writeToLog ("=== Hybrid Button Clicked ===");
    auto scriptPath = processor.getAPIClientScript().getParentDirectory().getChildFile ("hybrid_client.py");
    if (! scriptPath.existsAsFile())
    {
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Script Not Found",
                                                "Could not find hybrid_client.py.\n\nExpected location: "
                                                + scriptPath.getFullPathName(), "OK");
        return;
    }
    if (! currentAdapter().isValid())
    {
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "No Hybrid Backend",
                                                "No adapter profile of kind \"hybrid\" is selected. "
                                                "Open Settings to add or pick one.", "OK");
        return;
    }
    startHybrid (false, false);
}

void PtV2AEditor::stopRun()
{
    if (ptslProcess == nullptr)
        return;
    runStopped = true;
    ptslProcess->kill();            // the exit branch of timerCallback reports where it was
}

void PtV2AEditor::startHybrid (bool wholeTrack, bool resume, bool estimate)
{
    auto scriptPath = processor.getAPIClientScript().getParentDirectory().getChildFile ("hybrid_client.py");

    spottingProgressFile = juce::File::getSpecialLocation (juce::File::tempDirectory)
                               .getChildFile ("ai_sound_design_hybrid_" + juce::String (juce::Time::currentTimeMillis()) + ".json");
    spottingProgressFile.deleteFile();
    spottingProgressMtime = juce::Time();

    juce::StringArray args;
    args.add (processor.getPythonExecutable());
    args.add ("-X");
    args.add ("utf8");
    args.add (scriptPath.getFullPathName());
    args.add (wholeTrack ? "--whole-track" : "--from-selection");
    if (resume)
        args.add ("--resume");
    if (estimate)
        args.add ("--estimate");
    args.add ("--progress-file");
    args.add (spottingProgressFile.getFullPathName());
    args.add ("--adapter");
    args.add (currentAdapter().file);
    if (prompt.getText().trim().isNotEmpty())
    {
        args.add ("--prompt");
        args.add (prompt.getText().trim());
    }
    if (negativePromptInput.getText().trim().isNotEmpty())
    {
        args.add ("--negative-prompt");
        args.add (negativePromptInput.getText().trim());
    }
    args.add ("--seed");
    args.add (juce::String (seedInput.getText().trim().isEmpty() ? -1 : seedInput.getText().trim().getIntValue()));
    if (useMemoryLocationsToggle.getToggleState() && useMemoryLocationsToggle.isEnabled())
    {
        args.add ("--use-memory-locations");
        if (! autoSpotToggle.getToggleState())
            args.add ("--no-auto-spot");
    }
    if (useDatabaseSoundsToggle.getToggleState() && useDatabaseSoundsToggle.isEnabled())
    {
        args.add ("--use-database");
        if (keepGeneratedToggle.getToggleState())
            args.add ("--keep-generated");
        if (! ambienceHandlesToggle.getToggleState())
            args.add ("--no-handles");
    }
    if (detectScenesToggle.getToggleState())
        args.add ("--scenes");

    juce::Logger::writeToLog ("Hybrid command: " + args.joinIntoString (" "));

    ptslProcess = std::make_unique<juce::ChildProcess>();
    if (! ptslProcess->start (args))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start hybrid_client.py");
        ptslProcess.reset();
        currentAsyncState = AsyncState::Idle;
        resetSpottingUi();
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Failed to Start Script",
                                                "Could not start hybrid_client.py. Please check the log file.", "OK");
        return;
    }

    currentAsyncState = estimate ? AsyncState::HybridEstimate : AsyncState::HybridGeneration;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    lastProgressTime = asyncOperationStartTime;
    staleDialogOpen = false;
    runStopped = false;
    actionButton.setEnabled (false);
    hybridWholeTrackButton.setEnabled (false);
    actionButton.setButtonText (estimate ? "Counting clips..." : "Generating...");
    progressValue = -1.0;
    progressLabel.setText (estimate ? "Reading the video track..." : wholeTrack ? "Reading the video track..."
                                                                                : "Reading selection...",
                           juce::dontSendNotification);
    progressBar.setVisible (true);
    progressLabel.setVisible (true);
    startTimer (TIMER_INTERVAL_MS);
}

void PtV2AEditor::startSpotting (bool wholeTrack)
{
    auto scriptPath = processor.getAPIClientScript().getParentDirectory().getChildFile ("spotting_client.py");

    spottingProgressFile = juce::File::getSpecialLocation (juce::File::tempDirectory)
                               .getChildFile ("ai_sound_design_spotting_" + juce::String (juce::Time::currentTimeMillis()) + ".json");
    spottingProgressFile.deleteFile();
    spottingProgressMtime = juce::Time();

    // python -X utf8 spotting_client.py --from-selection|--whole-track --progress-file <json>
    juce::StringArray args;
    args.add (processor.getPythonExecutable());
    args.add ("-X");
    args.add ("utf8");
    args.add (scriptPath.getFullPathName());
    args.add (wholeTrack ? "--whole-track" : "--from-selection");
    if (detectScenesToggle.getToggleState())
        args.add ("--scenes");
    args.add ("--progress-file");
    args.add (spottingProgressFile.getFullPathName());

    juce::Logger::writeToLog ("Spotting command: " + args.joinIntoString (" "));

    ptslProcess = std::make_unique<juce::ChildProcess>();
    if (! ptslProcess->start (args))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start spotting_client.py");
        ptslProcess.reset();
        currentAsyncState = AsyncState::Idle;
        resetSpottingUi();

        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Failed to Start Script",
            "Could not start spotting_client.py. Please check the log file.",
            "OK"
        );
        return;
    }

    currentAsyncState = AsyncState::SpottingAnalysis;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    lastProgressTime = asyncOperationStartTime;
    staleDialogOpen = false;
    runStopped = false;
    actionButton.setEnabled (false);
    spotWholeTrackButton.setEnabled (false);
    actionButton.setButtonText ("Spotting...");
    progressValue = -1.0;   // no measurable progress yet: busy animation
    progressLabel.setText ("Reading selection...", juce::dontSendNotification);
    progressBar.setVisible (true);
    progressLabel.setVisible (true);
    startTimer (TIMER_INTERVAL_MS);
}

void PtV2AEditor::updateSpottingProgress()
{
    if (! spottingProgressFile.existsAsFile())
        return;

    auto mtime = spottingProgressFile.getLastModificationTime();
    if (mtime == spottingProgressMtime)
        return;
    spottingProgressMtime = mtime;

    auto doc = juce::JSON::parse (spottingProgressFile.loadFileAsString());
    if (! doc.isObject())
        return;                                   // caught the file half-written; next tick

    int current = (int) doc.getProperty ("current", 0);
    int total = (int) doc.getProperty ("total", 0);
    juce::String clip = doc.getProperty ("clip", "").toString();
    juce::String stage = doc.getProperty ("stage", "").toString();
    juce::String detail = doc.getProperty ("detail", "").toString();
    bool working = stage == "cutting" || stage == "spotting" || stage == "generating";

    // Within the current clip, the backend may say how far it is (model calls done)
    const juce::var fractionVar = doc.getProperty ("fraction", juce::var());
    const bool hasFraction = working && (fractionVar.isDouble() || fractionVar.isInt());
    const double fraction = hasFraction ? juce::jlimit (0.0, 1.0, (double) fractionVar) : 0.0;

    // The script is alive, so the timeout window starts afresh; the elapsed seconds on
    // the button keep counting from the real start.
    lastProgressTime = juce::Time::getCurrentTime();

    // Bar: finished clips plus the backend's share of the current one; full when the script
    // says it is done; busy animation only while a single clip's backend reports nothing.
    const bool done = (bool) doc.getProperty ("done", false);
    progressValue = done ? 1.0
                  : total > 0 && (total > 1 || hasFraction || ! working)
                        ? juce::jlimit (0.0, 1.0, (current - (working ? 1.0 : 0.0) + fraction) / total)
                        : -1.0;
    juce::String stageText = stage;
    if (hasFraction)
        stageText += (detail.isNotEmpty() ? ", " + detail : juce::String())
                     + ", " + juce::String (juce::roundToInt (fraction * 100.0)) + "%";
    else if (detail.isNotEmpty())
        stageText += ", " + detail;
    const juce::var etaVar = doc.getProperty ("eta_seconds", juce::var());
    if ((etaVar.isDouble() || etaVar.isInt()) && (double) etaVar > 0)
    {
        const int etaMin = juce::jmax (1, juce::roundToInt ((double) etaVar / 60.0));
        stageText += etaMin >= 90 ? "; about " + juce::String (etaMin / 60.0, 1) + " h left"
                                  : "; about " + juce::String (etaMin) + " min left";
    }
    progressLabel.setText (stage == "placing" && clip.isNotEmpty()
                               ? "Placing " + clip + "  (" + stageText + ")"
                           : total > 0 && current > 0 && clip.isNotEmpty()
                               ? "Clip " + juce::String (current) + " of " + juce::String (total) + ": " + clip + "  (" + stageText + ")"
                               : stageText,
                           juce::dontSendNotification);
}

void PtV2AEditor::resetSpottingUi()
{
    actionButton.setEnabled (true);
    actionButton.setButtonText (idleActionButtonText());
    spotWholeTrackButton.setEnabled (true);
    hybridWholeTrackButton.setEnabled (true);
    progressBar.setVisible (false);
    progressLabel.setVisible (false);
    spottingProgressFile.deleteFile();
    spottingProgressFile.withFileExtension ("log").deleteFile();
    spottingProgressFile.withFileExtension ("result.json").deleteFile();
}

