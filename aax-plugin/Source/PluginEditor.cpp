#include "PluginEditor.h"
#include "PluginProcessor.h"

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
    
    audioGenModeButton.setRadioGroupId (1000);  // Separate group from V2A/T2A
    audioGenModeButton.setToggleState (true, juce::dontSendNotification);  // Default: Audio Generation
    audioGenModeButton.onClick = [this] { handleWorkflowModeChange(); };
    contentComponent.addAndMakeVisible (audioGenModeButton);
    
    soundRecModeButton.setRadioGroupId (1000);  // Same group as Audio Generation
    soundRecModeButton.onClick = [this] { handleWorkflowModeChange(); };
    contentComponent.addAndMakeVisible (soundRecModeButton);
    
    autoSpottingModeButton.setRadioGroupId (1000);  // Same group as other modes
    autoSpottingModeButton.onClick = [this] { handleWorkflowModeChange(); };
    contentComponent.addAndMakeVisible (autoSpottingModeButton);
    
    // Configure Auto Spotting info label
    autoSpottingInfoLabel.setJustificationType (juce::Justification::centredLeft);
    autoSpottingInfoLabel.setVisible (false);  // Initially hidden (only visible in Auto Spotting mode)
    contentComponent.addAndMakeVisible (autoSpottingInfoLabel);

    // Configure unified action button (changes based on workflow mode)
    actionButton.onClick = [this]
    {
        if (currentWorkflowMode == WorkflowMode::AudioGeneration)
            handleRenderButtonClicked();
        else if (currentWorkflowMode == WorkflowMode::SoundRecommendation)
            handleRecommendSoundsButtonClicked();
        else if (currentWorkflowMode == WorkflowMode::AutoSpotting)
            handleAutoSpottingButtonClicked();
    };
    contentComponent.addAndMakeVisible (actionButton);
    
    // Configure open log button with click handler
    openLogButton.onClick = [this]
    {
        handleOpenLogButtonClicked();
    };
    contentComponent.addAndMakeVisible (openLogButton);

    // Configure settings button with click handler
    settingsButton.onClick = [this] { showCredentialDialog(); };
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
    contentComponent.addAndMakeVisible (soundRecommendations);

    // First-launch check: show dialog if credentials are missing
    if (processor.getCloudflareClientSecret().isEmpty())
    {
    // Delay dialog to avoid showing during plugin initialization
    juce::Timer::callAfterDelay (500, [this]
    {
        showCredentialDialog();
    });
}
    
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
    seedInput.setTextToShowWhenEmpty ("42", juce::Colours::grey);
    seedInput.setText ("42");  // Set default value
    contentComponent.addAndMakeVisible (seedInput);
    
    // Configure generation mode radio buttons (V2A vs T2A)
    v2aModeButton.setRadioGroupId (1001);
    v2aModeButton.setToggleState (true, juce::dontSendNotification);  // Default: V2A mode
    v2aModeButton.onClick = [this] { handleGenerationModeChange(); };
    contentComponent.addAndMakeVisible (v2aModeButton);
    
    t2aModeButton.setRadioGroupId (1001);
    t2aModeButton.onClick = [this] { handleGenerationModeChange(); };
    contentComponent.addAndMakeVisible (t2aModeButton);
    
    // Configure duration dropdown (for T2A mode)
    durationLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (durationLabel);
    
    durationComboBox.addItem ("4s", 1);
    durationComboBox.addItem ("5s", 2);
    durationComboBox.addItem ("6s", 3);
    durationComboBox.addItem ("7s", 4);
    durationComboBox.addItem ("8s", 5);
    durationComboBox.addItem ("9s", 6);
    durationComboBox.addItem ("10s", 7);
    durationComboBox.addItem ("11s", 8);
    durationComboBox.addItem ("12s", 9);
    durationComboBox.setSelectedId (5, juce::dontSendNotification);  // Default: 8s
    durationComboBox.setEnabled (false);  // Initially disabled (V2A mode)
    contentComponent.addAndMakeVisible (durationComboBox);
    
    // Configure high precision mode toggle (deprecated TODO remove in future)
    // highPrecisionModeToggle.setToggleState (false, juce::dontSendNotification);  // Default: off (bfloat16)
    // addAndMakeVisible (highPrecisionModeToggle);
    
    // Configure model selection labels
    modelLabel.setJustificationType (juce::Justification::centredLeft);
    contentComponent.addAndMakeVisible (modelLabel);
    
    // Configure model ComboBox with integrated sizes
    modelProviderComboBox.addItem ("MMAudio", 1);
    modelProviderComboBox.addItem ("HunyuanVideo-Foley (XL)", 2);
    modelProviderComboBox.addItem ("HunyuanVideo-Foley (XXL)", 3);
    modelProviderComboBox.setSelectedId (1, juce::dontSendNotification);  // Default: MMAudio
    contentComponent.addAndMakeVisible (modelProviderComboBox);
    
    // Configure toggle button for sound recommendations
    toggleSoundResultsButton.onClick = [this] { handleToggleSoundResults(); };
    toggleSoundResultsButton.setVisible (false);  // Initially hidden until results available
    contentComponent.addAndMakeVisible (toggleSoundResultsButton);
    
    // Initial UI state based on default workflow mode
    handleWorkflowModeChange();
    
    // Update API credential status warning
    updateAPICredentialStatus();
    
    // Sound recommendations initially hidden
    soundRecommendations.setVisible (false);
    
    // Set fixed window size (not resizable in Pro Tools)
    // Pro Tools plugins typically have fixed UI layouts
    setResizable (true, true);
    setResizeLimits (400, 400, 1200, 1200);  // min/max width/height
    setSize (750, 600);  // Width x Height in pixels (increased for model selection row)
}

//==============================================================================
// Event Handler - Render Button Click
//==============================================================================
void PtV2AEditor::handleRenderButtonClicked()
{
    juce::Logger::writeToLog ("=== Render Button Clicked ===");
    juce::Logger::writeToLog ("Prompt: " + prompt.getText());
    juce::Logger::writeToLog ("Mode: " + juce::String (isT2AMode ? "T2A" : "V2A"));
    
    // Check if credentials are saved
    if (processor.getCloudflareClientSecret().isEmpty())
    {
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Error: No API Connection",
            "Please save the correct API credentials under API Settings before rendering audio.\n\n"
            "Click 'API Settings' at the bottom right to configure your credentials.",
            "OK"
        );
        return;
    }
    
    // T2A mode validation and workflow
    if (isT2AMode)
    {
        // Validate model selection
        if (modelProviderComboBox.getSelectedId() != 1)  // Not MMAudio
        {
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon,
                "Invalid Model Selection",
                "T2A mode only supports MMAudio.\n\n"
                "HunyuanVideo-Foley requires video input (V2A mode).",
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
    int providerSelectedId = modelProviderComboBox.getSelectedId();
    juce::String serviceName = (providerSelectedId == 2) ? "hunyuan" : "mmaudio";
    juce::String providerDisplayName = (providerSelectedId == 2) ? "HunyuanVideo-Foley" : "MMAudio";
    
    juce::String apiUrl = processor.getConfiguredAPIUrl (serviceName);
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
        actionButton.setButtonText ("Render Audio");
        return;
    }
    
    //==========================================================================
    // Step 2: Start async timeline selection read (non-blocking!)
    //==========================================================================
    actionButton.setButtonText ("Reading Selection...");
    actionButton.setEnabled (false);
    
    // Start async PTSL process - timer will handle the rest!
    // The workflow continues in handleTimelineSelectionResult() after PTSL finishes
    startTimelineSelectionRead();
}

//==============================================================================
// Event Handler - Open Log Button Click
//==============================================================================
void PtV2AEditor::handleOpenLogButtonClicked()
{
    juce::Logger::writeToLog ("=== Open Log Button Clicked ===");
    
    // Get log file path from processor
    auto logFile = PtV2AProcessor::getLogFile();
    
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
        actionButton.setButtonText ("Render Audio");
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
    
    // Calculate content height (sum of all components + spacing + margins)
    int contentHeight = 24 +  // Top margin
                        28 +  // Mode row
                        20 +  // Spacing
                        28 +  // Prompt row (or Auto Spotting info label - same space)
                        20 +  // Spacing
                        28 +  // Negative prompt row
                        20 +  // Spacing
                        28 +  // Seed row
                        20 +  // Spacing
                        28 +  // Model row
                        60 +  // Spacing before buttons
                        28 +  // Button row
                        15 +  // Spacing
                        28 +  // Toggle button row
                        10 +  // Spacing
                        140 + // Sound recommendations component
                        10 +  // Spacing
                        28 +  // Settings button row
                        24;   // Bottom margin
    
    // Set content component size (width matches viewport for horizontal scroll, calculated height)
    int minContentWidth = 700;  // Minimum width to ensure all content fits
    int actualWidth = juce::jmax (getWidth(), minContentWidth);
    contentComponent.setSize (actualWidth, contentHeight);
    
    // Layout components within contentComponent with 24px margin around edges
    auto r = contentComponent.getLocalBounds().reduced (24);
    
    // Mode selection row at the top - use proportional layout with even spacing
    auto modeRow = r.removeFromTop (28);
    modeLabel.setBounds (modeRow.removeFromLeft (65));
    modeRow.removeFromLeft (10);
    int availableWidth = modeRow.getWidth();
    int buttonGap = 15;
    int buttonWidth = (availableWidth - 2 * buttonGap) / 3;  // Even width for all three buttons
    audioGenModeButton.setBounds (modeRow.removeFromLeft (buttonWidth));
    modeRow.removeFromLeft (buttonGap);
    soundRecModeButton.setBounds (modeRow.removeFromLeft (buttonWidth));
    modeRow.removeFromLeft (buttonGap);
    autoSpottingModeButton.setBounds (modeRow.removeFromLeft (buttonWidth));
    
    // 20px spacing after mode selection
    r.removeFromTop (20);
    
    // Prompt text input OR Auto Spotting info label (share same space)
    auto promptRow = r.removeFromTop (28);
    
    // Auto Spotting info label (positioned where prompt is, only visible in Auto Spotting mode)
    auto autoSpottingInfoRow = promptRow;
    autoSpottingInfoRow.removeFromLeft (65);  // Skip label area to align with prompt field
    autoSpottingInfoRow.removeFromLeft (10);  // Skip spacing
    autoSpottingInfoLabel.setBounds (autoSpottingInfoRow);
    
    // Prompt text input: full width, 28px height
    promptLabel.setBounds (promptRow.removeFromLeft (65));
    promptRow.removeFromLeft (10);    
    prompt.setBounds (promptRow);

    // 20px spacing between components
    r.removeFromTop (20);
 
    // Negative prompt row: Label + Input field
    auto negativePromptRow = r.removeFromTop (28);
    negativePromptLabel.setBounds (negativePromptRow.removeFromLeft (65));
    negativePromptRow.removeFromLeft (10);
    negativePromptInput.setBounds (negativePromptRow);

    // 20px spacing before next row
    r.removeFromTop (20);
    
    // Seed and generation mode row: Label + Input + Radio Buttons + Duration - responsive layout
    auto seedRow = r.removeFromTop (28);
    seedLabel.setBounds (seedRow.removeFromLeft (65));
    seedRow.removeFromLeft (10);
    
    // Fixed width for seed input
    seedInput.setBounds (seedRow.removeFromLeft (120));
    seedRow.removeFromLeft (20);
    
    // Calculate remaining space for V2A/T2A buttons and duration
    int remainingWidth = seedRow.getWidth();
    int v2aWidth = juce::jmin (140, remainingWidth * 3 / 10);  // Roughly 30% or 140px
    int t2aWidth = juce::jmin (130, remainingWidth * 3 / 10);  // Roughly 30% or 130px
    
    // Radio buttons for V2A/T2A mode
    v2aModeButton.setBounds (seedRow.removeFromLeft (v2aWidth));
    seedRow.removeFromLeft (10);
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
    
    // 20px spacing before model selection
    r.removeFromTop (20);
    
    // Model selection row: Label + Model ComboBox (with integrated sizes)
    auto modelRow = r.removeFromTop (28);
    modelLabel.setBounds (modelRow.removeFromLeft (65));
    modelRow.removeFromLeft (10);
    modelProviderComboBox.setBounds (modelRow.removeFromLeft (230));
    // highPrecisionModeToggle.setBounds (modelRow); // (deprecated TODO remove in future)


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

    // 60px spacing before buttons section
    r.removeFromTop (60);

    // Main action button - centered
    auto buttonRow = r.removeFromTop (28);
    const int actionW = 160;
    buttonRow.removeFromLeft ((buttonRow.getWidth() - actionW) / 2);  // Center
    actionButton.setBounds (buttonRow.removeFromLeft (actionW));

    // Toggle button for sound recommendations - centered below render button
    r.removeFromTop (15);  // Spacing
    auto toggleButtonRow = r.removeFromTop (28);
    toggleButtonRow.removeFromLeft ((toggleButtonRow.getWidth() - 200) / 2);  // Center
    toggleSoundResultsButton.setBounds (toggleButtonRow.removeFromLeft (200));
    
    // Sound recommendations component - shown when toggle is active
    r.removeFromTop (10);  // Spacing
    auto soundRecommendationsArea = r.removeFromTop (140);  // Fixed height for component
    soundRecommendations.setBounds (soundRecommendationsArea);

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

void PtV2AEditor::startTimelineSelectionRead()
{
    juce::Logger::writeToLog ("=== Starting Async Timeline Selection Read ===");
    
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
        actionButton.setButtonText ("Render Audio");
        return;
    }
    
    // Build command: Direct Python call with -X utf8 flag
    // Use get_video_info to get BOTH timeline selection AND video path in one call
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("get_video_info");
    
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
        actionButton.setButtonText ("Render Audio");
        ptslProcess.reset();
        return;
    }
    
    // Record start time for timeout detection
    asyncOperationStartTime = juce::Time::getCurrentTime();
    
    // IMPORTANT: Only set state if not already set by caller
    // Sound Search pre-sets ReadingTimelineForSoundSearch before calling this function
    if (currentAsyncState == AsyncState::Idle)
        currentAsyncState = AsyncState::ReadingTimeline;
    
    // Start timer to poll process status every 100ms
    startTimer (TIMER_INTERVAL_MS);
    
    juce::Logger::writeToLog ("Timeline selection started, timer polling every " + 
                              juce::String (TIMER_INTERVAL_MS) + "ms");
}

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
        actionButton.setButtonText ("Render Audio");
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
        actionButton.setButtonText ("Render Audio");
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
                actionButton.setButtonText ("Render Audio");
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
        
        case AsyncState::ReadingTimelineForSoundSearch:
        {
            // Same as ReadingTimeline but triggers sound search instead of audio generation
            if (!ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Recommend Sounds");
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
                    "Timeline selection timed out for sound search.\n\n"
                    "Please check PTSL connection.",
                    "OK"
                );
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Recommend Sounds");
                return;
            }
            
            // Check if process is still running
            if (ptslProcess->isRunning())
            {
                return;  // Keep waiting
            }
            
            // Process finished - read output
            juce::Logger::writeToLog ("Timeline selection for sound search finished after " + 
                                      juce::String (elapsed.inMilliseconds()) + "ms");
            
            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            
            // Parse JSON to get video path
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
            
            juce::String videoPath;
            float durationSeconds = 0.0f;
            if (jsonOutput.isNotEmpty())
            {
                auto json = juce::JSON::parse (jsonOutput);
                if (auto* obj = json.getDynamicObject())
                {
                    bool success = obj->getProperty ("success");
                    if (success)
                    {
                        videoPath = obj->getProperty ("video_path").toString();
                        juce::Logger::writeToLog ("Video path from PTSL: " + videoPath);
                        
                        // Get selection duration
                        durationSeconds = obj->getProperty ("duration_seconds");
                        juce::Logger::writeToLog ("Selection duration: " + juce::String (durationSeconds, 2) + "s");
                        
                        // Store timeline position for sound import (same as V2A/T2A)
                        juce::String inTime = obj->getProperty ("in_time").toString();
                        if (inTime.isNotEmpty())
                        {
                            timelineInTime = inTime;
                            juce::Logger::writeToLog ("Stored timeline in-time for sound import: " + timelineInTime);
                        }
                    }
                    else
                    {
                        juce::String error = obj->getProperty ("error").toString();
                        bool noSelection = error.contains ("No clips selected");
                        
                        if (noSelection)
                        {
                            juce::Logger::writeToLog ("No video selected - using text-only search");
                        }
                        else
                        {
                            juce::Logger::writeToLog ("PTSL error: " + error);
                            juce::AlertWindow::showMessageBoxAsync (
                                juce::MessageBoxIconType::WarningIcon,
                                "Video Error",
                                error,
                                "OK"
                            );
                            actionButton.setEnabled (true);
                            actionButton.setButtonText ("Recommend Sounds");
                            return;
                        }
                    }
                }
            }
            
            // Validate video duration if video is available (4-12 seconds for optimal X-CLIP processing)
            if (videoPath.isNotEmpty() && durationSeconds > 0.0f)
            {
                if (durationSeconds < 4.0f)
                {
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::WarningIcon,
                        "Selection Too Short",
                        juce::String::formatted (
                            "Timeline selection is only %.2f seconds.\n\n"
                            "Sound Search requires video clips between 4-12 seconds.\n\n"
                            "Please select a longer video clip.",
                            durationSeconds
                        ),
                        "OK"
                    );
                    
                    actionButton.setEnabled (true);
                    actionButton.setButtonText ("Recommend Sounds");
                    return;
                }
                
                if (durationSeconds > 12.0f)
                {
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::WarningIcon,
                        "Selection Too Long",
                        juce::String::formatted (
                            "Timeline selection is %.2f seconds.\n\n"
                            "Sound Search requires video clips between 4-12 seconds.\n\n"
                            "Please:\n"
                            "1. Select a shorter video clip\n"
                            "2. Cut your current clip into segments of 4-12 seconds each",
                            durationSeconds
                        ),
                        "OK"
                    );
                    
                    actionButton.setEnabled (true);
                    actionButton.setButtonText ("Recommend Sounds");
                    return;
                }
                
                juce::Logger::writeToLog ("Video duration valid for sound search: " + juce::String (durationSeconds, 2) + "s");
            }
            
            // Validate: need at least video OR text
            if (videoPath.isEmpty() && currentPrompt.isEmpty())
            {
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "No Input",
                    "No video or text prompt available for sound search.",
                    "OK"
                );
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Recommend Sounds");
                return;
            }
            
            // If video is available, read clip bounds first (same workflow as Audio Generation)
            if (videoPath.isNotEmpty())
            {
                juce::Logger::writeToLog ("Starting clip bounds read for sound search...");
                // Store video path for use after clip bounds read
                currentVideoPath = videoPath;
                currentAsyncState = AsyncState::ReadingClipBoundsForSoundSearch;
                asyncOperationStartTime = juce::Time::getCurrentTime();
                startTimer (TIMER_INTERVAL_MS);
                startClipBoundsRead (videoPath);
                return;
            }
            
            // Text-only search (no video) - trigger immediately with no clip bounds
            juce::Logger::writeToLog ("Text-only search - no clip bounds needed");
            triggerSoundSearch (
                "",                              // No video
                currentPrompt,
                "",                              // Video offset
                0.0f,                            // Timeline start
                0.0f,                            // Timeline end
                -1.0f,                           // No clip start
                -1.0f,                           // No clip end
                false                            // No auto-detect
            );
            
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
        
        case AsyncState::ReadingClipBounds:
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
                juce::Logger::writeToLog ("ERROR: Clip bounds read timed out after " + 
                                          juce::String (PTSL_TIMEOUT_MS) + "ms");
                
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                
                juce::Logger::writeToLog ("Clip bounds read timed out - aborting");
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Render Audio");
                return;
            }
            
            // Check if process is still running
            if (ptslProcess->isRunning())
            {
                // Still running - keep waiting (non-blocking)
                return;
            }
            
            // Process finished! Read output
            juce::Logger::writeToLog ("Clip bounds read finished after " + 
                                      juce::String (elapsed.inMilliseconds()) + "ms");
            
            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            
            // Pass output to handler for parsing
            handleClipBoundsResult (output);
            break;
        }
        
        case AsyncState::ReadingClipBoundsForSoundSearch:
        {
            // Same as ReadingClipBounds but for Sound Search workflow
            if (!ptslProcess)
            {
                stopTimer();
                currentAsyncState = AsyncState::Idle;
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Recommend Sounds");
                return;
            }
            
            // Check for timeout
            if (elapsed.inMilliseconds() > PTSL_TIMEOUT_MS)
            {
                juce::Logger::writeToLog ("ERROR: Clip bounds read for sound search timed out after " + 
                                          juce::String (PTSL_TIMEOUT_MS) + "ms");
                
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Recommend Sounds");
                return;
            }
            
            // Check if process is still running
            if (ptslProcess->isRunning())
            {
                return;  // Keep waiting
            }
            
            // Process finished! Read output
            juce::Logger::writeToLog ("Clip bounds read for sound search finished after " + 
                                      juce::String (elapsed.inMilliseconds()) + "ms");
            
            auto output = ptslProcess->readAllProcessOutput();
            ptslProcess.reset();
            stopTimer();
            currentAsyncState = AsyncState::Idle;
            
            // Pass output to handler for parsing (Sound Search variant)
            handleClipBoundsForSoundSearchResult (output);
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
        
        case AsyncState::AutoSpottingAnalysis:
        {
            // Poll Auto Spotting wizard process (fake progress based on time, avoid stdout reading during PTSL ops)
            // Timeout: 45 seconds (11s fake delays + 34s safety buffer for Python script)
            if (elapsed.inMilliseconds() > 45000)
            {
                juce::Logger::writeToLog ("ERROR: Auto Spotting wizard timed out after 45s");
                
                stopTimer();
                
                if (ptslProcess)
                {
                    ptslProcess->kill();
                    ptslProcess.reset();
                }
                
                currentAsyncState = AsyncState::Idle;
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Auto Spotting Timeout",
                    "Auto Spotting analysis timed out after 45 seconds.\n\n"
                    "Please check Pro Tools connection and try again.",
                    "OK"
                );
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Analyze & Spot Markers");
                return;
            }
            
            // Update button text based on elapsed time (fake progress to avoid stdout polling during PTSL)
            int elapsedSeconds = elapsed.inMilliseconds() / 1000;
            if (elapsedSeconds < 3)
            {
                actionButton.setButtonText ("Analyzing video...");
            }
            else if (elapsedSeconds < 7)
            {
                actionButton.setButtonText ("Detecting audio cues...");
            }
            else if (elapsedSeconds < 11)
            {
                actionButton.setButtonText ("Creating markers...");
            }
            else
            {
                actionButton.setButtonText ("Finalizing...");
                
                // Start Python process after 11s fake delay (only once)
                if (!ptslProcess)
                {
                    juce::Logger::writeToLog ("=== Starting Python Script (after 11s fake delay) ===");
                    
                    auto scriptFile = processor.getAPIClientScript();
                    auto companionDir = scriptFile.getParentDirectory();
                    auto scriptPath = companionDir.getChildFile ("auto_spotting_wizard.py");
                    
                    juce::String pythonExe = processor.getPythonExecutable();
                    
                    juce::Logger::writeToLog ("Python executable: " + pythonExe);
                    juce::Logger::writeToLog ("Script path: " + scriptPath.getFullPathName());
                    
                    // Build command: python.exe auto_spotting_wizard.py
                    juce::StringArray args;
                    args.add (pythonExe);  // First arg: Python interpreter
                    args.add (scriptPath.getFullPathName());  // Second arg: Script to run
                    
                    juce::Logger::writeToLog ("Full command: " + args.joinIntoString (" "));
                    
                    ptslProcess = std::make_unique<juce::ChildProcess>();
                    
                    if (!ptslProcess->start (args))
                    {
                        juce::Logger::writeToLog ("ERROR: Failed to start Python process");
                        
                        stopTimer();
                        ptslProcess.reset();
                        currentAsyncState = AsyncState::Idle;
                        
                        actionButton.setEnabled (true);
                        actionButton.setButtonText ("Analyze & Spot Markers");
                        
                        juce::AlertWindow::showMessageBoxAsync (
                            juce::MessageBoxIconType::WarningIcon,
                            "Failed to Start Script",
                            "Could not start Auto Spotting wizard script.\n\n"
                            "Please check the log file for details.",
                            "OK"
                        );
                        
                        return;
                    }
                    
                    juce::Logger::writeToLog ("Python process started successfully");
                }
            }
            
            // If process hasn't been started yet (< 11s), keep waiting
            if (!ptslProcess)
            {
                return;  // Keep polling until 11s mark
            }
            
            // Check if process is still running (don't read stdout to avoid PTSL interference)
            if (ptslProcess->isRunning())
            {
                return;  // Keep polling
            }
            
            // Process finished - check exit code and capture any error output
            int exitCode = ptslProcess->getExitCode();
            
            // Try to read stderr for error messages
            juce::String errorOutput;
            if (ptslProcess)
            {
                char buffer[4096];
                int bytesRead = ptslProcess->readProcessOutput (buffer, sizeof(buffer) - 1);
                if (bytesRead > 0)
                {
                    buffer[bytesRead] = '\0';
                    errorOutput = juce::String (buffer);
                    juce::Logger::writeToLog ("=== Python Script Output ===");
                    juce::Logger::writeToLog (errorOutput);
                    juce::Logger::writeToLog ("=== End Output ===");
                }
            }
            
            juce::Logger::writeToLog ("Auto Spotting wizard completed after " + 
                                      juce::String (elapsed.inSeconds(), 1) + "s with exit code " + 
                                      juce::String (exitCode));
            
            stopTimer();
            ptslProcess.reset();
            currentAsyncState = AsyncState::Idle;
            
            actionButton.setEnabled (true);
            actionButton.setButtonText ("Analyze & Spot Markers");
            
            // Show result based on exit code
            if (exitCode == 0)
            {
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::InfoIcon,
                    "Auto Spotting Complete",
                    "Analysis complete! Memory locations have been placed at detected audio events.\n\n"
                    "Check the timeline ruler to see the automatically generated markers.",
                    "OK"
                );
            }
            else
            {
                // Parse error output to detect specific issues
                bool duplicateMarkers = errorOutput.contains ("already used") || 
                                       errorOutput.contains ("InvalidParameter") ||
                                       (exitCode == 1 && errorOutput.contains ("created\": 0"));
                
                if (duplicateMarkers)
                {
                    // User-friendly message for duplicate markers (common in user study)
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::WarningIcon,
                        "Memory Locations Already Exist",
                        "Auto Spotting could not create markers because they already exist.\n\n"
                        "To run Auto Spotting again:\n"
                        "1. Delete all existing memory locations in Pro Tools\n"
                        "2. Click 'Analyze & Spot Markers' again\n\n"
                        "Note: This is a prototype limitation - real implementation would handle duplicates automatically.",
                        "OK"
                    );
                }
                else
                {
                    // Generic error message for other failures
                    juce::String errorMsg = "Auto Spotting wizard encountered an error.\n\n"
                                            "Please check the log file for details and ensure:\n"
                                            "- Pro Tools session is open\n"
                                            "- PTSL server is running\n"
                                            "- Memory locations are configured in the script";
                    
                    if (errorOutput.isNotEmpty())
                    {
                        errorMsg += "\n\nError details:\n" + errorOutput.substring (0, 200);
                    }
                    
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::WarningIcon,
                        "Auto Spotting Failed",
                        errorMsg,
                        "OK"
                    );
                }
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
            if (elapsed.inMilliseconds() > PTSL_TIMEOUT_MS)
            {
                juce::Logger::writeToLog ("ERROR: Audio import timed out after " + 
                                          juce::String (PTSL_TIMEOUT_MS) + "ms");
                
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Import Timeout",
                    "Audio import to Pro Tools timed out.\n\n"
                    "The audio file was generated successfully but could not be imported.\n"
                    "You can manually import it from the temp directory.",
                    "OK"
                );
                
                actionButton.setEnabled (true);
                actionButton.setButtonText ("Render Audio");
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
            if (elapsed.inMilliseconds() > PTSL_TIMEOUT_MS)
            {
                juce::Logger::writeToLog ("ERROR: Sound import timed out after " + 
                                          juce::String (PTSL_TIMEOUT_MS) + "ms");
                
                stopTimer();
                ptslProcess->kill();
                ptslProcess.reset();
                currentAsyncState = AsyncState::Idle;
                
                juce::AlertWindow::showMessageBoxAsync (
                    juce::MessageBoxIconType::WarningIcon,
                    "Sound Import Timeout",
                    "Sound import to Pro Tools timed out.\n\n"
                    "The import process did not complete within 60 seconds.",
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
        actionButton.setButtonText ("Render Audio");
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
        actionButton.setButtonText ("Render Audio");
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
                "1. Select a video clip in Pro Tools (use Selector Tool)\n"
                "2. Make sure the clip is 4-12 seconds long\n"
                "3. Pro Tools must be running with PTSL enabled",
                "OK"
            );
            
            actionButton.setEnabled (true);
            actionButton.setButtonText ("Render Audio");
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
        
        //======================================================================
        // V2A MODE: Continue with video processing
        //======================================================================
        juce::Logger::writeToLog ("=== V2A Mode: Processing video clip ===");
        
        // Validate duration: 4-12 seconds
        if (durationSeconds < 4.0f)
        {
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon,
                "Selection Too Short",
                juce::String::formatted (
                    "Timeline selection is only %.2f seconds.\n\n"
                    "V2A requires clip selections between 4-12 seconds.\n\n"
                    "Please select a longer video clip\n",
                    durationSeconds
                ),
                "OK"
            );
            
            actionButton.setEnabled (true);
            actionButton.setButtonText ("Render Audio");
            return;
        }
        
        if (durationSeconds > 12.0f)
        {
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon,
                "Selection Too Long",
                juce::String::formatted (
                    "Timeline selection is %.2f seconds.\n\n"
                    "V2A requires clip selections between 4-12 seconds.\n\n"
                    "Please:\n"
                    "1. Select a shorter video clip\n"
                    "2. Cut your current clip into segments of 4-12 seconds each",
                    durationSeconds
                ),
                "OK"
            );
            
            actionButton.setEnabled (true);
            actionButton.setButtonText ("Render Audio");
            return;
        }
        
        // Duration is valid! Continue with workflow...
        juce::Logger::writeToLog ("Selection duration valid: " + 
                                  juce::String (durationSeconds, 2) + "s");
        
        //======================================================================
        // Step 3: Video file path (already retrieved in combined action!)
        //======================================================================
        // NOTE: We already have videoPath from the combined get_video_info action
        // No need for separate getVideoFileFromProTools() call (avoids second timeout!)
        
        if (videoPath.isEmpty())
        {
            juce::Logger::writeToLog ("ERROR: No video path in combined result");
            
            juce::AlertWindow::showMessageBoxAsync (
                juce::MessageBoxIconType::WarningIcon,
                "No Video Found",
                "Could not find video file in Pro Tools session:\n\n" +
                errorMessage + "\n\n"
                "Make sure:\n"
                "1. Your Pro Tools session has a video track\n"
                "2. Video file is imported to the session",
                "OK"
            );
            
            actionButton.setEnabled (true);
            actionButton.setButtonText ("Render Audio");
            currentAsyncState = AsyncState::Idle;
            return;
        }
        
        juce::Logger::writeToLog ("Video file: " + videoPath);
        
        //======================================================================
        // Step 3.5: Check if clip is trimmed (compare clip duration vs source duration)
        //======================================================================
        // COMMENTED OUT: FFprobe check causes timeout on large videos (419MB takes >5s)
        // Solution: ALWAYS read clip bounds via PTSL (works for trimmed AND untrimmed clips)
        /*
        // Get source video duration via FFprobe
        float sourceVideoDuration = getSourceVideoDuration (videoPath);
        
        if (sourceVideoDuration > 0.0f)
        {
            juce::Logger::writeToLog ("Source video duration: " + juce::String (sourceVideoDuration, 2) + "s");
            juce::Logger::writeToLog ("Clip duration: " + juce::String (durationSeconds, 2) + "s");
            
            // Check if clip is trimmed (with 0.5s tolerance for rounding)
            if (durationSeconds < (sourceVideoDuration - 0.5f))
            {
                juce::Logger::writeToLog ("→ Clip is TRIMMED (shorter than source)");
                clipIsTrimmed = true;
            }
            else
            {
                juce::Logger::writeToLog ("→ Clip uses FULL source video");
                clipIsTrimmed = false;
            }
        }
        else
        {
            juce::Logger::writeToLog ("WARNING: Could not determine source video duration, assuming not trimmed");
            clipIsTrimmed = false;
        }
        */
        
        //======================================================================
        // Step 4: ALWAYS read clip bounds (works for trimmed AND untrimmed clips)
        //======================================================================
        // Clip bounds from PTSL work for all cases:
        // - Trimmed clip: Returns actual source position (e.g. 20-27s)
        // - Untrimmed clip: Returns full video (e.g. 0-60s)
        // This is faster and more reliable than FFprobe check
        
        juce::Logger::writeToLog ("Reading clip bounds from Pro Tools (works for all clip types)...");
        
        actionButton.setButtonText ("Reading Clip Bounds...");
        
        // Store video and prompt for later use (after clip bounds are read)
        currentVideoPath = videoPath;
        currentPrompt = prompt.getText();
        
        // Start async clip bounds reading
        // The timer will continue running, and handleClipBoundsResult() will proceed to generation
        currentAsyncState = AsyncState::ReadingClipBounds;
        startClipBoundsRead (videoPath);
        return;  // Exit here, will continue in handleClipBoundsResult()
        
        //======================================================================
        // Step 5: Start async audio generation (NO PTSL import yet!)
        //======================================================================
        actionButton.setButtonText ("Generating Audio...");
        juce::Logger::writeToLog ("Starting async audio generation...");
        juce::Logger::writeToLog ("Selected clip: " + inTime + " - " + outTime);
        juce::Logger::writeToLog ("Duration: " + juce::String (durationSeconds, 2) + "s");
        juce::Logger::writeToLog ("Video file: " + videoPath);
        juce::Logger::writeToLog ("Prompt: " + prompt.getText());
        
        // Start async audio generation (will poll for output file)
        startAudioGeneration (videoPath, prompt.getText());
        
        // Log generation start (no modal popup to avoid freezing)
        juce::Logger::writeToLog ("✅ Audio generation process started");
        juce::Logger::writeToLog ("    Selection: " + inTime + " - " + outTime);
        juce::Logger::writeToLog ("    Duration: " + juce::String (durationSeconds, 1) + "s");
        juce::Logger::writeToLog ("    Plugin will poll for completion and auto-import");
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
        actionButton.setButtonText ("Render Audio");
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
    int seed = seedText.isEmpty() ? 42 : seedText.getIntValue();  // Default seed = 42
    
    // bool useHighPrecision = highPrecisionModeToggle.getToggleState(); // (deprecated TODO remove in future)
    
    // Read model selection from UI (1=MMAudio, 2=HunyuanVideo-Foley XL, 3=HunyuanVideo-Foley XXL)
    int selectedId = modelProviderComboBox.getSelectedId();
    PtV2AProcessor::ModelProvider modelProvider;
    juce::String modelSize;
    
    if (selectedId == 1) {
        modelProvider = PtV2AProcessor::ModelProvider::MMAudio;
        modelSize = "Large";
    } else if (selectedId == 2) {
        modelProvider = PtV2AProcessor::ModelProvider::HunyuanVideoFoley;
        modelSize = "XL";
    } else {
        modelProvider = PtV2AProcessor::ModelProvider::HunyuanVideoFoley;
        modelSize = "XXL";
    }
    
    juce::String providerName = (modelProvider == PtV2AProcessor::ModelProvider::MMAudio) ? "MMAudio" : "HunyuanVideo-Foley";
    juce::Logger::writeToLog ("Model selection: " + providerName + " / " + modelSize);
    juce::Logger::writeToLog ("Advanced params: negative_prompt=\"" + negativePrompt + "\", seed=" + juce::String(seed) + ", full_precision=" + "false");
    
    // Call processor to start generation (returns immediately with expected output path)
    juce::String errorMessage;
    expectedAudioOutputPath = processor.generateAudioFromVideo (
        juce::File (videoPath),
        promptText,
        negativePrompt,  // User-controlled negative prompt
        seed,            // User-controlled seed
        modelProvider,   // NEW: Selected model provider (MMAudio / HunyuanVideo-Foley)
        modelSize,       // NEW: Selected model size
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
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Generation Failed",
            "Failed to start audio generation:\n\n" + errorMessage,
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Render Audio");
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
    int seed = seedText.isEmpty() ? 42 : seedText.getIntValue();
    
    // T2A only supports MMAudio with Large model size
    PtV2AProcessor::ModelProvider modelProvider = PtV2AProcessor::ModelProvider::MMAudio;
    juce::String modelSize = "Large";
    
    juce::Logger::writeToLog ("Model: MMAudio / " + modelSize);
    juce::Logger::writeToLog ("Advanced params: negative_prompt=\"" + negativePrompt + "\", seed=" + juce::String(seed));
    
    // Call processor to start T2A generation (no video, just text + duration)
    juce::String errorMessage;
    expectedAudioOutputPath = processor.generateAudioTextOnly (
        promptText,
        duration,
        negativePrompt,
        seed,
        modelSize,
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
        actionButton.setButtonText ("Render Audio");
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
// Clip Bounds Reading (Async Phase 1 of Auto-Trim Workflow)
//==============================================================================

void PtV2AEditor::startClipBoundsRead (const juce::String& videoPath)
{
    // Phase 1: Read clip boundaries asynchronously via PTSL
    // This is SAFE because it doesn't block the main thread
    // Once complete, handleClipBoundsResult() will store bounds and proceed to generation
    
    juce::Logger::writeToLog ("=== Starting Async Clip Bounds Read ===");
    juce::Logger::writeToLog ("Video: " + videoPath);
    
    // Store video path for later use in Phase 2
    currentVideoPath = videoPath;
    
    // Get Python executable and script
    juce::String pythonExe = processor.getPythonExecutable();
    juce::File scriptFile = processor.getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: API client script not found");
        juce::Logger::writeToLog ("Clip bounds read aborted - script not found");
        return;
    }
    
    // Build command: python -X utf8 standalone_api_client.py --action get_clip_bounds
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("get_clip_bounds");
    
    juce::String command = commandArray.joinIntoString (" ");
    juce::Logger::writeToLog ("Command: " + command);
    
    // Start async process
    ptslProcess = std::make_unique<juce::ChildProcess>();
    if (!ptslProcess->start (commandArray))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start clip bounds process");
        juce::Logger::writeToLog ("Clip bounds read aborted");
        ptslProcess.reset();
        return;
    }
    
    // State should already be set by caller (ReadingClipBounds or ReadingClipBoundsForSoundSearch)
    // Reset timer for this operation
    asyncOperationStartTime = juce::Time::getCurrentTime();
    juce::Logger::writeToLog ("Reading clip boundaries... (async)");
    
    // Timer should already be running from timeline selection
    // If not (called standalone), start it
    if (!isTimerRunning())
        startTimer (TIMER_INTERVAL_MS);
    
    juce::Logger::writeToLog ("Clip bounds read started (async)");
}

void PtV2AEditor::handleClipBoundsResult (const juce::String& output)
{
    // Phase 1 complete: Parse JSON output with clip boundaries
    juce::Logger::writeToLog ("=== Handling Clip Bounds Result ===");
    juce::Logger::writeToLog ("Output: " + output);
    
    // Extract JSON from output (last JSON line)
    auto lines = juce::StringArray::fromLines (output);
    juce::String jsonOutput;
    for (const auto& line : lines)
    {
        if (line.trimStart().startsWith ("{"))
        {
            jsonOutput = line.trim();
        }
    }
    
    if (jsonOutput.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: No JSON in clip bounds output");
        juce::Logger::writeToLog ("Failed to parse clip bounds - aborting");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Parse JSON: {"success": true, "start_seconds": 5.005, "end_seconds": 10.844, ...}
    auto jsonResult = juce::JSON::parse (jsonOutput);
    if (jsonResult.isVoid())
    {
        juce::Logger::writeToLog ("ERROR: Failed to parse clip bounds JSON");
        juce::Logger::writeToLog ("Invalid clip bounds response - aborting");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    bool success = jsonResult.getProperty ("success", false);
    if (!success)
    {
        juce::String error = jsonResult.getProperty ("error", "Unknown error");
        juce::Logger::writeToLog ("ERROR: Clip bounds read failed: " + error);
        juce::Logger::writeToLog ("Aborting clip bounds read");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Extract clip boundaries
    clipStartSeconds = (float) jsonResult.getProperty ("start_seconds", -1.0);
    clipEndSeconds = (float) jsonResult.getProperty ("end_seconds", -1.0);
    
    juce::Logger::writeToLog ("✅ Clip bounds read successfully");
    juce::Logger::writeToLog ("  Start: " + juce::String (clipStartSeconds, 3) + "s");
    juce::Logger::writeToLog ("  End: " + juce::String (clipEndSeconds, 3) + "s");
    
    if (clipStartSeconds < 0.0f || clipEndSeconds < 0.0f)
    {
        juce::Logger::writeToLog ("ERROR: Invalid clip bounds");
        juce::Logger::writeToLog ("Clip boundaries are invalid - aborting");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Phase 1 complete! Now proceed to Phase 2: Background generation with clip bounds
    currentAsyncState = AsyncState::Idle;  // Reset before starting generation
    juce::Logger::writeToLog ("Proceeding to audio generation with clip bounds");
    
    // Start audio generation (will use clipStartSeconds and clipEndSeconds)
    startAudioGeneration (currentVideoPath, currentPrompt); 
    actionButton.setButtonText ("Generating Audio...");
}

//==============================================================================
// Handle Clip Bounds Result (Sound Search Variant)
//==============================================================================

void PtV2AEditor::handleClipBoundsForSoundSearchResult (const juce::String& output)
{
    // Parse JSON output with clip boundaries for Sound Search workflow
    juce::Logger::writeToLog ("=== Handling Clip Bounds Result (Sound Search) ===");
    juce::Logger::writeToLog ("Output: " + output);
    
    // Extract JSON from output (last JSON line)
    auto lines = juce::StringArray::fromLines (output);
    juce::String jsonOutput;
    for (const auto& line : lines)
    {
        if (line.trimStart().startsWith ("{"))
        {
            jsonOutput = line.trim();
        }
    }
    
    if (jsonOutput.isEmpty())
    {
        juce::Logger::writeToLog ("ERROR: No JSON in clip bounds output");
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Recommend Sounds");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Parse JSON
    auto jsonResult = juce::JSON::parse (jsonOutput);
    if (jsonResult.isVoid())
    {
        juce::Logger::writeToLog ("ERROR: Failed to parse clip bounds JSON");
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Recommend Sounds");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    bool success = jsonResult.getProperty ("success", false);
    if (!success)
    {
        juce::String error = jsonResult.getProperty ("error", "Unknown error");
        juce::Logger::writeToLog ("ERROR: Clip bounds read failed: " + error);
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Recommend Sounds");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Extract clip boundaries
    float clipStart = (float) jsonResult.getProperty ("start_seconds", -1.0);
    float clipEnd = (float) jsonResult.getProperty ("end_seconds", -1.0);
    
    juce::Logger::writeToLog ("✅ Clip bounds read successfully for sound search");
    juce::Logger::writeToLog ("  Start: " + juce::String (clipStart, 3) + "s");
    juce::Logger::writeToLog ("  End: " + juce::String (clipEnd, 3) + "s");
    
    if (clipStart < 0.0f || clipEnd < 0.0f)
    {
        juce::Logger::writeToLog ("ERROR: Invalid clip bounds");
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Recommend Sounds");
        currentAsyncState = AsyncState::Idle;
        return;
    }
    
    // Trigger sound search with clip bounds
    currentAsyncState = AsyncState::Idle;  // Reset before starting search
    juce::Logger::writeToLog ("Proceeding to sound search with clip bounds");
    
    triggerSoundSearch (
        currentVideoPath,
        currentPrompt,
        "",              // Video offset
        0.0f,            // Timeline start (not used)
        0.0f,            // Timeline end (not used)
        clipStart,       // Clip start from PTSL
        clipEnd,         // Clip end from PTSL
        true             // Auto-detect enabled
    );
}

//==============================================================================
// Source Video Duration Check
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
        
        stopTimer();
        currentAsyncState = AsyncState::Idle;
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Generation Timeout",
            "Audio generation timed out after 2 minutes.\n\n"
            "This might indicate:\n"
            "- API server is not responding\n"
            "- Network connection issues\n"
            "- Video is too complex to process\n\n"
            "Check the log file for details.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Render Audio");
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
        
        // Sound search now triggered manually via "Recommend Sounds" button
        
        startAudioImport (newestWavFile.getFullPathName());
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
        actionButton.setButtonText ("Render Audio");
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
    
    juce::Logger::writeToLog ("Starting PTSL import process...");
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // Create and start process
    ptslProcess = std::make_unique<juce::ChildProcess>();
    
    if (!ptslProcess->start (commandArray))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start PTSL import process");
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Import Error",
            "Failed to start audio import process.\n\n"
            "Audio was generated successfully at:\n" + audioPath + "\n\n"
            "You can manually import it to Pro Tools.",
            "OK"
        );
        
        actionButton.setEnabled (true);
        actionButton.setButtonText ("Render Audio");
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
    
    if (success)
    {
        juce::Logger::writeToLog ("✓ Audio successfully imported to Pro Tools timeline!");
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::InfoIcon,
            "Success!",
            "Audio generated and imported to Pro Tools timeline!\n\n"
            "-> Generation complete\n"
            "-> Imported to timeline\n\n"
            "Check your Pro Tools session for the new audio track.",
            "OK"
        );
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
    actionButton.setButtonText ("Render Audio");
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
    
    // Model provider handling: HunyuanVideo-Foley not compatible with T2A
    if (isT2AMode)
    {
        // If HunyuanVideo-Foley is selected, switch to MMAudio
        if (modelProviderComboBox.getSelectedId() >= 2)  // HunyuanVideo-Foley (XL or XXL)
        {
            juce::Logger::writeToLog ("T2A mode: Switching from HunyuanVideo-Foley to MMAudio");
            modelProviderComboBox.setSelectedId (1, juce::sendNotification);  // Switch to MMAudio
        }
        
        // T2A mode: Lock model provider to MMAudio only (disable dropdown)
        modelProviderComboBox.setEnabled (false);
        juce::Logger::writeToLog ("T2A mode: Model provider locked to MMAudio");
    }
    else
    {
        // V2A mode: Enable model provider dropdown for user selection
        modelProviderComboBox.setEnabled (true);
        juce::Logger::writeToLog ("V2A mode: Model provider dropdown enabled");
    }
    
    repaint();
}

//==============================================================================
// API Credential Status Update
//==============================================================================
void PtV2AEditor::updateAPICredentialStatus()
{
    // Check if credentials are saved
    bool hasCredentials = !processor.getCloudflareClientSecret().isEmpty();
    
    if (!hasCredentials)
    {
        // No credentials saved at all
        apiWarningLabel.setText (juce::CharPointer_UTF8 ("\xe2\x9a\xa0 API credentials empty"), juce::dontSendNotification);  // ⚠
        apiWarningLabel.setVisible (true);
        juce::Logger::writeToLog ("=== API Credential Status: Missing ===");
    }
    else
    {
        // Credentials exist - test if they're valid (non-blocking check)
        // This makes a real HTTP request, so we do it asynchronously
        juce::String error;
        bool valid = processor.testCloudflareCredentials (
            processor.getCloudflareClientId(),
            processor.getCloudflareClientSecret(),
            &error
        );
        
        if (valid)
        {
            // Valid credentials - hide warning
            apiWarningLabel.setVisible (false);
            juce::Logger::writeToLog ("=== API Credential Status: Valid ===");
        }
        else
        {
            // Invalid credentials - show warning
            apiWarningLabel.setText (juce::CharPointer_UTF8 ("\xe2\x9a\xa0 No API Connection"), juce::dontSendNotification);  // ⚠
            apiWarningLabel.setVisible (true);
            juce::Logger::writeToLog ("=== API Credential Status: Invalid ===");
            juce::Logger::writeToLog ("Error: " + error);
        }
    }
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
    
    bool isAudioGen = (currentWorkflowMode == WorkflowMode::AudioGeneration);
    bool isSoundRec = (currentWorkflowMode == WorkflowMode::SoundRecommendation);
    bool isAutoSpotting = (currentWorkflowMode == WorkflowMode::AutoSpotting);
    
    juce::Logger::writeToLog ("=== Workflow Mode Changed ===");
    juce::String modeName = isAudioGen ? "Audio Generation" : (isSoundRec ? "Sound Recommendation" : "Auto Spotting");
    juce::Logger::writeToLog ("New mode: " + modeName);
    
    // Update action button text and appearance
    if (isAudioGen)
    {
        actionButton.setButtonText ("Render Audio");
    }
    else if (isSoundRec)
    {
        actionButton.setButtonText ("Recommend Sounds");
    }
    else if (isAutoSpotting)
    {
        actionButton.setButtonText ("Analyze & Spot Markers");
    }
    
    // Show/hide fields based on workflow mode
    // Prompt is visible in Audio Gen and Sound Rec, hidden in Auto Spotting
    prompt.setVisible (!isAutoSpotting);
    promptLabel.setVisible (!isAutoSpotting);
    
    // Auto Spotting info label only visible in Auto Spotting mode
    autoSpottingInfoLabel.setVisible (isAutoSpotting);
    
    // Audio Generation specific fields (hidden in Sound Recommendation and Auto Spotting)
    negativePromptInput.setVisible (isAudioGen);
    negativePromptLabel.setVisible (isAudioGen);
    
    seedInput.setVisible (isAudioGen);
    seedLabel.setVisible (isAudioGen);
    
    // V2A/T2A toggle only visible in Audio Generation (not used in Sound Recommendation)
    // Sound Search automatically tries video detection first, then falls back to text-only
    v2aModeButton.setVisible (isAudioGen);
    t2aModeButton.setVisible (isAudioGen);
    
    // Duration and model always visible in Audio Gen (enabled state controlled by V2A/T2A)
    durationComboBox.setVisible (isAudioGen);
    durationLabel.setVisible (isAudioGen);
    
    modelProviderComboBox.setVisible (isAudioGen);
    modelLabel.setVisible (isAudioGen);
    
    repaint();
}

//==============================================================================
// Cloudflare Access Credential Dialog
//==============================================================================
void PtV2AEditor::showCredentialDialog()
{
    // Create AlertWindow on heap for async modal state
    auto* credentialWindow = new juce::AlertWindow (
        "API Access Credentials",
        "Enter your Access Token Secret.\n\n"
        "Do not change the Client ID unless advised to.\n"
        "You can test the API connection before saving.\n",
        juce::MessageBoxIconType::NoIcon
    );
    
    // Pre-fill with current values
    auto currentId = processor.getCloudflareClientId();
    auto currentSecret = processor.getCloudflareClientSecret();
    
    // Client ID: Read-only, pre-filled (user doesn't need to change this)
    credentialWindow->addTextEditor ("clientId", currentId, "Client ID:");
    if (auto* idEditor = credentialWindow->getTextEditor ("clientId"))
    {
        idEditor->setReadOnly (false);
       // idEditor->setColour (juce::TextEditor::backgroundColourId, juce::Colours::lightgrey);
    }
    
    // Client Secret: Editable, this is what user needs to input
    credentialWindow->addTextEditor ("clientSecret", currentSecret, "Client Secret:");
    
    credentialWindow->addButton ("Save", 1, juce::KeyPress (juce::KeyPress::returnKey));
    credentialWindow->addButton ("Test Connection", 2);
    credentialWindow->addButton ("Cancel", 0, juce::KeyPress (juce::KeyPress::escapeKey));
    
    // Use async modal state (non-blocking, Pro Tools safe!)
    credentialWindow->enterModalState (true, juce::ModalCallbackFunction::create (
        [this, credentialWindow] (int result)
        {
            if (result == 2)  // Test Connection
            {
                auto testId = credentialWindow->getTextEditorContents ("clientId");
                auto testSecret = credentialWindow->getTextEditorContents ("clientSecret");
                
                actionButton.setButtonText ("Testing...");
                actionButton.setEnabled (false);
                
                juce::String error;
                bool valid = processor.testCloudflareCredentials (testId, testSecret, &error);
                
                actionButton.setButtonText ("Render Audio");
                actionButton.setEnabled (true);
                
                if (valid)
                {
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::InfoIcon,
                        "Connection Successful",
                        "Credentials are valid! Save them for API Access.",
                        "OK"
                    );
                    
                    // Show dialog again to let user save
                    juce::Timer::callAfterDelay (100, [this] { showCredentialDialog(); });
                }
                else
                {
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::WarningIcon,
                        "Connection Failed",
                        "Could not connect to API.\n\n" + error,
                        "OK"
                    );
                    
                    // Show dialog again
                    juce::Timer::callAfterDelay (100, [this] { showCredentialDialog(); });
                }
            }
            else if (result == 1)  // Save
            {
                auto newId = credentialWindow->getTextEditorContents ("clientId");
                auto newSecret = credentialWindow->getTextEditorContents ("clientSecret");
                
                if (processor.saveCloudflareCredentials (newId, newSecret))
                {
                    // Update credential status after successful save
                    updateAPICredentialStatus();
                    
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::InfoIcon,
                        "Credentials Saved",
                        "API Access credentials saved successfully.",
                        "OK"
                    );
                }
                else
                {
                    juce::AlertWindow::showMessageBoxAsync (
                        juce::MessageBoxIconType::WarningIcon,
                        "Save Failed",
                        "Could not save credentials.\n"
                        "Check file permissions.",
                        "OK"
                    );
                }
            }
            
            // JUCE will delete the window automatically
        }
    ), true);
}
//==============================================================================
// Sound Search Event Handlers
//==============================================================================

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
    
    // Build timeline reading command (get_video_info action)
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("get_video_info");
    
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
    }
    else
    {
        juce::Logger::writeToLog ("No timeline position, importing at session start");
    }
    
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
    args.add ("10");  // TODO: how many?
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
        juce::Logger::writeToLog ("Sound recommendations panel auto-shown");
        
        // Show success message
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::InfoIcon,
            "Sound Search Complete!",
            "Found " + juce::String (sounds.size()) + " matching sounds from BBC Sound Archive.\n\n"
            "-> Search complete\n"
            "-> Results loaded\n\n"
            "Check the Database Recommendations panel below to import sounds.",
            "OK"
        );
    }
}

//==============================================================================
// Toggle Sound Results Handler
//==============================================================================

void PtV2AEditor::handleToggleSoundResults()
{
    bool isCurrentlyVisible = soundRecommendations.isVisible();
    soundRecommendations.setVisible (!isCurrentlyVisible);
    
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
    
    // Check if credentials are saved
    if (processor.getCloudflareClientSecret().isEmpty())
    {
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Error: No API connection",
            "Please save the correct API credentials under API Settings before searching sounds.\n\n"
            "Click 'API Settings' at the bottom right to configure your credentials.",
            "OK"
        );
        return;
    }
    
    // Get prompt text
    juce::String promptText = prompt.getText();
    
    // Store prompt for use after PTSL completes
    currentPrompt = promptText;
    
    // Disable button during search
    actionButton.setEnabled (false);
    actionButton.setButtonText ("Searching...");
    
    // IMPORTANT: Sound Search always tries to get video from Pro Tools via PTSL first
    // Then falls back to text-only if no video is available
    // This is DIFFERENT from Audio Generation which respects V2A/T2A toggle
    
    juce::Logger::writeToLog ("Starting async PTSL workflow for sound search...");
    juce::Logger::writeToLog ("Will use video if available, otherwise text-only search");
    
    // Start PTSL timeline selection read (non-blocking)
    currentAsyncState = AsyncState::ReadingTimelineForSoundSearch;
    startTimer (TIMER_INTERVAL_MS);
    startTimelineSelectionRead();
}

//==============================================================================
// Event Handler - Auto Spotting Button Click
//==============================================================================
void PtV2AEditor::handleAutoSpottingButtonClicked()
{
    juce::Logger::writeToLog ("=== Auto Spotting Button Clicked ===");
    juce::Logger::writeToLog ("Starting Auto Spotting wizard (Wizard of Oz prototype)...");
    
    // Validate script exists before starting fake delays
    auto scriptFile = processor.getAPIClientScript();
    auto companionDir = scriptFile.getParentDirectory();
    auto scriptPath = companionDir.getChildFile ("auto_spotting_wizard.py");
    
    if (!scriptPath.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: auto_spotting_wizard.py not found at: " + scriptPath.getFullPathName());
        
        juce::AlertWindow::showMessageBoxAsync (
            juce::MessageBoxIconType::WarningIcon,
            "Error: Auto Spotting Script Not Found",
            "Could not find auto_spotting_wizard.py script.\n\n"
            "Expected location: " + scriptPath.getFullPathName(),
            "OK"
        );
        
        return;
    }
    
    // Start timer for fake progress (Python script will be started after 11s in timerCallback)
    actionButton.setEnabled (false);
    actionButton.setButtonText ("Analyzing video...");
    
    currentAsyncState = AsyncState::AutoSpottingAnalysis;
    asyncOperationStartTime = juce::Time::getCurrentTime();
    startTimer (TIMER_INTERVAL_MS);
    
    juce::Logger::writeToLog ("Auto Spotting timer started (11s fake delay before marker creation)");
}

