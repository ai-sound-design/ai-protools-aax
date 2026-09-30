#include "PluginProcessor.h"
#include <algorithm>
#include "PluginEditor.h"

//==============================================================================
// Static constant definitions
//==============================================================================
const juce::String PtV2AProcessor::DEFAULT_NEGATIVE_PROMPT = "voices, music";
const juce::String PtV2AProcessor::DEFAULT_API_URL = "http://localhost:8000";

//==============================================================================
// Static member initialization
//==============================================================================
std::unique_ptr<juce::FileLogger> PtV2AProcessor::fileLogger = nullptr;

//==============================================================================
// Constructor
//==============================================================================
PtV2AProcessor::PtV2AProcessor()
: AudioProcessor (BusesProperties()
                    .withInput  ("Input",  juce::AudioChannelSet::stereo(), true)
                    .withOutput ("Output", juce::AudioChannelSet::stereo(), true))
{
    // Initialize file logger on first plugin instance, unless the user turned
    // log saving off in the settings ("save_logs" in config.json).
    if (getBackendSettings().saveLogs)
        initializeLogger();
    
    // TASK 7: Initialize audio format manager for preview playback
    // Register basic formats (WAV, AIFF, FLAC, MP3)
    formatManager.registerBasicFormats();
}

void PtV2AProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    // TASK 7: Prepare preview transport for playback
    lastSampleRate.store (sampleRate);
    previewTransport.prepareToPlay (samplesPerBlock, sampleRate);
    
    // Allocate preview mix buffer (stereo)
    previewMixBuffer.setSize (2, samplesPerBlock);
}
void PtV2AProcessor::releaseResources()
{
    // TASK 7: Release preview transport resources
    previewTransport.releaseResources();
}

bool PtV2AProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    // Require same channel count on in/out and allow mono or stereo
    const auto& in  = layouts.getMainInputChannelSet();
    const auto& out = layouts.getMainOutputChannelSet();
    if (in != out) return false;
    return in == juce::AudioChannelSet::mono() || in == juce::AudioChannelSet::stereo();
}

void PtV2AProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& /*midi*/)
{
    // Pass-through: do not modify audio from input
    // (Plugin does not process real-time audio)
    
    processBlockCalls.fetch_add (1, std::memory_order_relaxed);

    // TASK 7: Mix preview audio if active
    if (previewTransport.isPlaying())
    {
        // Ensure preview buffer matches block size
        if (previewMixBuffer.getNumSamples() != buffer.getNumSamples())
            previewMixBuffer.setSize (2, buffer.getNumSamples(), false, false, true);
        
        previewMixBuffer.clear();
        
        // Get preview audio from transport
        juce::AudioSourceChannelInfo channelInfo (&previewMixBuffer, 0, buffer.getNumSamples());
        previewTransport.getNextAudioBlock (channelInfo);
        
        // Mix preview into output buffer (additive mixing)
        for (int channel = 0; channel < juce::jmin (buffer.getNumChannels(), previewMixBuffer.getNumChannels()); ++channel)
        {
            buffer.addFrom (channel, 0, previewMixBuffer, channel, 0, buffer.getNumSamples(), 0.7f);  // 70% preview volume
        }
    }
}

juce::AudioProcessorEditor* PtV2AProcessor::createEditor()
{
    return new PtV2AEditor (*this);
}

void PtV2AProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    // minimal: store nothing yet
    juce::MemoryOutputStream (destData, true).writeString ("{}");
}

void PtV2AProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    juce::ignoreUnused (data, sizeInBytes);
}

//==============================================================================
// MMAudio API Integration Implementation
//==============================================================================

juce::String PtV2AProcessor::getPythonExecutable()
{
    // Use embedded Python bundled with the plugin
    // This makes the plugin completely self-contained with all dependencies
    
    // Get plugin binary location
    auto pluginFile = juce::File::getSpecialLocation (juce::File::currentExecutableFile);
    auto pluginDir = pluginFile.getParentDirectory(); // This is x64/ directory
    
    // Go up to Contents/ directory, then find Resources/
    // Structure: <Plugin>.aaxplugin/Contents/x64/<Plugin>.aaxplugin (binary)
    //                                    /Resources/python/python.exe
    auto contentsDir = pluginDir.getParentDirectory(); // Go from x64/ to Contents/
    
    juce::Logger::writeToLog ("=== Python Executable Search ===");
    juce::Logger::writeToLog ("Plugin binary directory: " + pluginDir.getFullPathName());
    juce::Logger::writeToLog ("Plugin Contents directory: " + contentsDir.getFullPathName());
    
    // Platform-specific Python executable name and location
#if JUCE_WINDOWS
    // Windows: python.exe in Contents/Resources/python/
    auto embeddedPythonExe = contentsDir.getChildFile("Resources")
                                        .getChildFile("python")
                                        .getChildFile("python.exe");
#elif JUCE_MAC
    // macOS: python3 or python in Contents/Resources/python/ or Contents/Resources/python/bin/
    auto embeddedPythonExe = contentsDir.getChildFile("Resources")
                                        .getChildFile("python")
                                        .getChildFile("python3");
    
    // If python3 not found, try python
    if (!embeddedPythonExe.existsAsFile())
        embeddedPythonExe = contentsDir.getChildFile("Resources")
                                       .getChildFile("python")
                                       .getChildFile("python");
    
    // Some Python distributions put binary in bin/ subdirectory
    if (!embeddedPythonExe.existsAsFile())
        embeddedPythonExe = contentsDir.getChildFile("Resources")
                                       .getChildFile("python")
                                       .getChildFile("bin")
                                       .getChildFile("python3");
#else
    // Linux: python3 in Contents/Resources/python/
    auto embeddedPythonExe = contentsDir.getChildFile("Resources")
                                        .getChildFile("python")
                                        .getChildFile("python3");
#endif
    
    juce::Logger::writeToLog ("Checking embedded Python: " + embeddedPythonExe.getFullPathName());
    
    if (embeddedPythonExe.existsAsFile())
    {
        juce::Logger::writeToLog ("✓ Using embedded Python from plugin Resources");
        juce::Logger::writeToLog ("Python path: " + embeddedPythonExe.getFullPathName());
        return embeddedPythonExe.getFullPathName();
    }
    
#if JUCE_MAC
    // Try alternative Mac Python locations (bin/python3, bin/python)
    auto altPython1 = contentsDir.getChildFile("Resources")
                                  .getChildFile("python")
                                  .getChildFile("bin")
                                  .getChildFile("python3");
    if (altPython1.existsAsFile())
    {
        juce::Logger::writeToLog ("✓ Using embedded Python from Resources/python/bin/python3");
        return altPython1.getFullPathName();
    }
    
    auto altPython2 = contentsDir.getChildFile("Resources")
                                  .getChildFile("python")
                                  .getChildFile("bin")
                                  .getChildFile("python");
    if (altPython2.existsAsFile())
    {
        juce::Logger::writeToLog ("✓ Using embedded Python from Resources/python/bin/python");
        return altPython2.getFullPathName();
    }
#endif
    
    juce::Logger::writeToLog ("⚠ Embedded Python not found!");
    juce::Logger::writeToLog ("Expected at: " + embeddedPythonExe.getFullPathName());
    juce::Logger::writeToLog ("Make sure Resources/python/ is copied to the plugin bundle");
    juce::Logger::writeToLog ("⚠ Falling back to system Python");
    
    // Fallback: Try system Python (will likely fail without dependencies)
#if JUCE_WINDOWS
    juce::Logger::writeToLog ("Using system Python: python.exe");
    return "python.exe";
#else
    juce::Logger::writeToLog ("Using system Python: python3");
    return "python3";
#endif
}

juce::File PtV2AProcessor::getAPIClientScript()
{
    // For embedded Python: Script is bundled in plugin Resources/python/Scripts/
    // This makes the plugin self-contained and portable
    
    // Get plugin binary location
    auto pluginFile = juce::File::getSpecialLocation (juce::File::currentExecutableFile);
    auto pluginDir = pluginFile.getParentDirectory(); // This is x64/ directory
    
    // Go up to Contents/ directory
    auto contentsDir = pluginDir.getParentDirectory(); // Go from x64/ to Contents/
    
    juce::Logger::writeToLog ("=== API Client Script Search ===");
    
    // Try embedded script first (production/installed builds)
    // Structure: <Plugin>.aaxplugin/Contents/Resources/python/Scripts/standalone_api_client.py
    auto embeddedScript = contentsDir.getChildFile("Resources")
                                     .getChildFile("python")
                                     .getChildFile("Scripts")
                                     .getChildFile("standalone_api_client.py");
    
    juce::Logger::writeToLog ("Checking embedded script: " + embeddedScript.getFullPathName());
    
    if (embeddedScript.existsAsFile())
    {
        juce::Logger::writeToLog ("✓ Using embedded script from plugin Resources");
        juce::Logger::writeToLog ("Script path: " + embeddedScript.getFullPathName());
        return embeddedScript;
    }
    
    juce::Logger::writeToLog ("⚠ Embedded script not found, trying external paths (development fallback)");
    
    // Fallback: External companion directory (for development builds)
    juce::File thesisRoot;
    
#if JUCE_WINDOWS
    // Windows AAX build structure:
    // From: build/pt_v2a_artefacts/Debug/AAX/pt_v2a.aaxplugin/Contents/x64/pt_v2a.aaxplugin
    // To:   protools-aax/companion/standalone_api_client.py
    
    auto candidate1 = pluginDir.getParentDirectory()      // x64
                                .getParentDirectory()      // Contents
                                .getParentDirectory()      // pt_v2a.aaxplugin
                                .getParentDirectory()      // AAX
                                .getParentDirectory()      // Debug
                                .getParentDirectory()      // pt_v2a_artefacts
                                .getParentDirectory()      // build
                                .getParentDirectory();     // protools-aax
    
    auto candidate2 = pluginDir.getParentDirectory()      // Contents
                                .getParentDirectory()      // pt_v2a.aaxplugin
                                .getParentDirectory()      // AAX
                                .getParentDirectory()      // Debug
                                .getParentDirectory()      // pt_v2a_artefacts
                                .getParentDirectory()      // build
                                .getParentDirectory();     // protools-aax
    
    if (candidate1.getChildFile("companion").exists())
        thesisRoot = candidate1;
    else if (candidate2.getChildFile("companion").exists())
        thesisRoot = candidate2;
    else
        thesisRoot = candidate1;  // Fallback
        
#elif JUCE_MAC
    // macOS AAX build structure
    thesisRoot = pluginDir.getParentDirectory()  // Contents
                          .getParentDirectory()  // pt_v2a.aaxplugin
                          .getParentDirectory()  // Debug
                          .getParentDirectory()  // build
                          .getParentDirectory()  // MacOSX
                          .getParentDirectory()  // Builds
                          .getParentDirectory()  // aax-plugin
                          .getParentDirectory(); // protools-aax
#else
    // Linux fallback
    thesisRoot = pluginDir.getParentDirectory()
                          .getParentDirectory()
                          .getParentDirectory()
                          .getParentDirectory();
#endif
    
    juce::Logger::writeToLog ("Thesis root candidate: " + thesisRoot.getFullPathName());
    
    auto scriptPath = thesisRoot.getChildFile ("companion")
                                 .getChildFile ("standalone_api_client.py");
    
    if (scriptPath.existsAsFile())
    {
        juce::Logger::writeToLog ("✓ Found API client script (external/development): " + scriptPath.getFullPathName());
        return scriptPath;
    }
    
    juce::Logger::writeToLog ("Script not found at: " + scriptPath.getFullPathName());
    
    // Last resort: Try relative to current working directory
    auto cwdScript = juce::File::getCurrentWorkingDirectory()
                         .getChildFile ("companion")
                         .getChildFile ("standalone_api_client.py");
    
    if (cwdScript.existsAsFile())
    {
        juce::Logger::writeToLog ("✓ Found API client script in CWD: " + cwdScript.getFullPathName());
        return cwdScript;
    }
    
    juce::Logger::writeToLog ("Script not found at CWD: " + cwdScript.getFullPathName());
    
    // Development fallback: Try parent directories (works cross-platform)
    // This helps when running from build directories during development
    auto devCompanionDir = pluginDir.getParentDirectory()  // up from x64/ or MacOS/
                                    .getParentDirectory()  // up from Contents/
                                    .getParentDirectory()  // up from .aaxplugin/
                                    .getParentDirectory()  // up from AAX/
                                    .getParentDirectory()  // up from pt_v2a_artefacts/
                                    .getParentDirectory()  // up from build/
                                    .getChildFile("companion")
                                    .getChildFile("standalone_api_client.py");
    
    juce::Logger::writeToLog ("Checking development path: " + devCompanionDir.getFullPathName());
    if (devCompanionDir.existsAsFile())
    {
        juce::Logger::writeToLog ("✓ Found API client script in development tree");
        return devCompanionDir;
    }
    
    juce::Logger::writeToLog ("❌ ERROR: API client script not found in any location!");
    juce::Logger::writeToLog ("Current working directory: " + juce::File::getCurrentWorkingDirectory().getFullPathName());
    return juce::File();
}

//==============================================================================
// Adapter profiles
//==============================================================================

juce::File PtV2AProcessor::getAdapterDir()
{
    return getUserDataDir().getChildFile ("adapters");
}

std::vector<PtV2AProcessor::AdapterProfile> PtV2AProcessor::getAdapterProfiles()
{
    auto dir = getAdapterDir();
    if (dir.getNumberOfChildFiles (juce::File::findFiles, "*.json") == 0)
    {
        // First use: let the companion write the default profiles (single source of truth).
        auto script = getAPIClientScript();
        if (script.existsAsFile())
        {
            juce::ChildProcess seed;
            juce::StringArray cmd { getPythonExecutable(), "-X", "utf8", script.getFullPathName(),
                                    "--action", "ensure_adapters" };
            if (seed.start (cmd))
                seed.waitForProcessToFinish (20000);
            juce::Logger::writeToLog ("Adapter profiles created in " + dir.getFullPathName());
        }
    }

    std::vector<AdapterProfile> profiles;
    for (const auto& entry : juce::RangedDirectoryIterator (dir, false, "*.json"))
    {
        auto json = juce::JSON::parse (entry.getFile().loadFileAsString());
        auto* obj = json.getDynamicObject();
        if (obj == nullptr)
            continue;
        AdapterProfile p;
        p.file = entry.getFile().getFileName();
        p.name = obj->getProperty ("name").toString();
        p.kind = obj->getProperty ("kind").toString();
        p.baseUrl = obj->getProperty ("base_url").toString();
        p.tunnelUrl = obj->getProperty ("base_url_tunnel").toString();
        p.health = obj->hasProperty ("health") ? obj->getProperty ("health").toString() : juce::String ("/health");
        p.protocol = obj->getProperty ("protocol").toString();
        if (auto* arr = obj->getProperty ("supports").getArray())
            for (const auto& v : *arr)
                p.supports.add (v.toString());
        if (auto* dur = obj->getProperty ("duration").getDynamicObject())
        {
            p.minDuration = (double) dur->getProperty ("min");
            p.maxDuration = (double) dur->getProperty ("max");
            p.defaultDuration = dur->hasProperty ("default") ? (double) dur->getProperty ("default")
                                                              : (p.minDuration + p.maxDuration) / 2.0;
            if (p.minDuration <= 0.0 || p.maxDuration < p.minDuration)     // nonsense: fall back
            {
                p.minDuration = 4.0; p.maxDuration = 12.0; p.defaultDuration = 8.0;
            }
        }
        if (auto* match = obj->getProperty ("match").getDynamicObject())
        {
            p.piecesPer10s = juce::jlimit (1, 20, (int) match->getProperty ("pieces_per_10s"));
            p.layers = juce::jlimit (1, 10, (int) match->getProperty ("layers"));
            if (match->hasProperty ("min_similarity"))
                p.minSimilarity = juce::jlimit (0.0, 1.0, (double) match->getProperty ("min_similarity"));
            if (match->hasProperty ("ambience_handle_seconds"))
                p.ambienceHandleSeconds = juce::jlimit (0.0, 120.0, (double) match->getProperty ("ambience_handle_seconds"));
            if (match->hasProperty ("tracks_per_scene"))
                p.tracksPerScene = juce::jlimit (1, 64, (int) match->getProperty ("tracks_per_scene"));
            if (match->hasProperty ("fade_preset"))
                p.fadePreset = match->getProperty ("fade_preset").toString().trim();
            if (match->hasProperty ("fade_seconds"))
                p.fadeSeconds = juce::jlimit (0.0, 30.0, (double) match->getProperty ("fade_seconds"));
        }
        if (p.name.isEmpty() || ! (p.kind == "generation" || p.kind == "search" || p.kind == "spotting" || p.kind == "hybrid"))
            continue;
        profiles.push_back (std::move (p));
    }
    std::sort (profiles.begin(), profiles.end(), [] (const AdapterProfile& a, const AdapterProfile& b)
    {
        return a.kind != b.kind ? a.kind < b.kind : a.name.compareIgnoreCase (b.name) < 0;
    });
    return profiles;
}

PtV2AProcessor::AdapterProfile PtV2AProcessor::getSelectedAdapter (const juce::String& kind)
{
    auto profiles = getAdapterProfiles();
    auto settings = getBackendSettings();
    auto wanted = settings.adapters.find (kind);

    AdapterProfile fallback;
    for (const auto& p : profiles)
    {
        if (p.kind != kind)
            continue;
        if (wanted != settings.adapters.end() && p.file == wanted->second)
            return p;
        // Nothing chosen yet: the shipped default first, else the first of its kind.
        const bool shipped = p.file == "mmaudio.json" || p.file == "sound_search.json" || p.file == "spotting.json"
                          || p.file == "hybrid.json";
        if (! fallback.isValid() || shipped)
            fallback = p;
    }
    return fallback;
}

void PtV2AProcessor::setSelectedAdapter (const juce::String& kind, const juce::String& file)
{
    auto settings = getBackendSettings();
    if (settings.adapters[kind] == file)
        return;
    settings.adapters[kind] = file;
    saveBackendSettings (settings);
    juce::Logger::writeToLog ("Adapter for " + kind + ": " + file);
}

bool PtV2AProcessor::saveAdapterUrl (const juce::String& file, const juce::String& url, bool tunnel)
{
    auto target = getAdapterDir().getChildFile (file);
    auto json = juce::JSON::parse (target.loadFileAsString());
    auto* obj = json.getDynamicObject();
    if (obj == nullptr)
        return false;
    obj->setProperty (tunnel ? "base_url_tunnel" : "base_url", url.trim());
    return target.replaceWithText (juce::JSON::toString (json, false));
}

bool PtV2AProcessor::saveAdapterDuration (const juce::String& file, double minSeconds, double maxSeconds, double defaultSeconds)
{
    auto target = getAdapterDir().getChildFile (file);
    auto json = juce::JSON::parse (target.loadFileAsString());
    auto* obj = json.getDynamicObject();
    if (obj == nullptr)
        return false;
    auto* block = new juce::DynamicObject();
    block->setProperty ("min", minSeconds);
    block->setProperty ("max", maxSeconds);
    block->setProperty ("default", defaultSeconds);
    obj->setProperty ("duration", juce::var (block));
    return target.replaceWithText (juce::JSON::toString (json, false));
}

bool PtV2AProcessor::saveAdapterMatch (const juce::String& file, int piecesPer10s, int layers, double minSimilarity,
                                       double ambienceHandleSeconds, int tracksPerScene, const juce::String& fadePreset,
                                       double fadeSeconds)
{
    auto target = getAdapterDir().getChildFile (file);
    auto json = juce::JSON::parse (target.loadFileAsString());
    auto* obj = json.getDynamicObject();
    if (obj == nullptr)
        return false;
    auto* block = obj->getProperty ("match").getDynamicObject();
    if (block == nullptr)
    {
        block = new juce::DynamicObject();
        obj->setProperty ("match", juce::var (block));
    }
    block->setProperty ("pieces_per_10s", piecesPer10s);
    block->setProperty ("layers", layers);
    block->setProperty ("min_similarity", minSimilarity);
    block->setProperty ("ambience_handle_seconds", ambienceHandleSeconds);
    block->setProperty ("tracks_per_scene", tracksPerScene);
    block->setProperty ("fade_preset", fadePreset);
    block->setProperty ("fade_seconds", fadeSeconds);
    return target.replaceWithText (juce::JSON::toString (json, false));
}

juce::String PtV2AProcessor::getConfiguredAPIUrl (const juce::String& service)
{
    // Legacy service keys map onto the selected adapter of that kind.
    static const std::map<juce::String, juce::String> kinds {
        { "mmaudio", "generation" },
        { "sound_search", "search" }, { "spotting", "spotting" }, { "hybrid", "hybrid" } };

    if (auto kind = kinds.find (service); kind != kinds.end())
    {
        auto adapter = getSelectedAdapter (kind->second);
        if (adapter.isValid())
        {
            auto url = adapter.activeUrl (getBackendSettings().useTunnel);
            juce::Logger::writeToLog ("Backend URL for " + service + " (" + adapter.name + "): " + url);
            return url;
        }
    }
    auto url = getBackendSettings().activeUrl (service);
    juce::Logger::writeToLog ("Backend URL for " + service + ": " + url);
    return url;
}

bool PtV2AProcessor::isAPIAvailable (const juce::String& apiUrl)
{
    // Tunnelled requests carry the access token; the Python side makes those.
    if (getBackendSettings().useTunnel)
    {
        juce::Logger::writeToLog ("Tunnel enabled, skipping C++ health check (Python handles auth)");
        return true;
    }

    // Any backend that answers its health endpoint counts; no product names are checked.
    juce::URL healthCheck (apiUrl.trimCharactersAtEnd ("/") + "/health");
    int statusCode = 0;
    
    juce::Logger::writeToLog ("Checking local API: " + apiUrl);
    
    auto inputStream = healthCheck.createInputStream (
        juce::URL::InputStreamOptions (juce::URL::ParameterHandling::inAddress)
            .withConnectionTimeoutMs (3000)
            .withNumRedirectsToFollow (0)
            .withStatusCode (&statusCode)
    );
    
    if (inputStream != nullptr && statusCode >= 200 && statusCode < 300)
    {
        inputStream->readEntireStreamAsString();
        juce::Logger::writeToLog ("✓ Local API available");
        return true;
    }
    
    juce::Logger::writeToLog ("✗ Local API not available (status: " + juce::String (statusCode) + ")");
    return false;
}

juce::String PtV2AProcessor::generateAudioFromVideo (
    const juce::File& videoFile,
    const juce::String& prompt,
    const juce::String& negativePrompt,
    int seed,
    const juce::String& videoClipOffset,
    float timelineInSeconds,
    float timelineOutSeconds,
    bool autoDetectClipBounds,
    float clipStartSeconds,
    float clipEndSeconds,
    bool fullPrecision,
    juce::String* errorMessage)
{
    const auto adapter = getSelectedAdapter ("generation");
    juce::Logger::writeToLog ("=== Generation Started ===");
    juce::Logger::writeToLog ("Backend: " + (adapter.isValid() ? adapter.name + " (" + adapter.file + ")"
                                                              : juce::String ("none selected")));
    juce::Logger::writeToLog ("Video: " + videoFile.getFullPathName());
    juce::Logger::writeToLog ("Prompt: " + prompt);
    juce::Logger::writeToLog ("Negative Prompt: " + negativePrompt);
    juce::Logger::writeToLog ("Seed: " + juce::String (seed));
    
    // Validate inputs
    if (!videoFile.existsAsFile())
    {
        juce::String error = "Video file does not exist: " + videoFile.getFullPathName();
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    
    // Get Python executable
    auto pythonExe = getPythonExecutable();
    
    // The selected adapter profile describes the backend; without one there is
    // nothing to talk to.
    if (! adapter.isValid())
    {
        juce::String error = "No generation backend selected. Open Settings and pick or add an adapter profile.";
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    auto scriptFile = getAPIClientScript();

    if (!scriptFile.existsAsFile())
    {
        juce::String error = "API client script not found: " + scriptFile.getFullPathName();
        
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    
    // Get script directory (for working directory)
    juce::File scriptDir = scriptFile.getParentDirectory();
    juce::String scriptPath = scriptDir.getFullPathName();
    
    juce::Logger::writeToLog ("Script directory: " + scriptPath);
    
    // Build command line arguments using StringArray for clean direct execution
    juce::StringArray commandArray;
    
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");  // Force UTF-8 mode
    commandArray.add (scriptFile.getFullPathName());
    
    commandArray.add ("--video");
    commandArray.add (videoFile.getFullPathName());
    
    if (prompt.isNotEmpty())
    {
        commandArray.add ("--prompt");
        commandArray.add (prompt);
    }
    
    if (negativePrompt.isNotEmpty())
    {
        commandArray.add ("--negative-prompt");
        commandArray.add (negativePrompt);
    }
    
    commandArray.add ("--seed");
    commandArray.add (juce::String (seed));
    
    // The profile tells the script where the backend is and how to build the request
    commandArray.add ("--adapter");
    commandArray.add (adapter.file);
    
    // WORKFLOW 1: Manual offset WITH clip bounds (trimmed clip + manual offset)
    // Priority: Manual offset > Clip bounds > Auto-detect
    if (videoClipOffset.isNotEmpty() && clipStartSeconds >= 0.0f)
    {
        // Special case: Manual offset on trimmed clip
        // Need BOTH clip bounds (where clip starts in source) AND manual offset (timeline position)
        // Python will calculate: source_start = clip_source_start + (timeline_start - clip_timeline_start)
        commandArray.add ("--video-offset");
        commandArray.add (videoClipOffset);
        commandArray.add ("--timeline-start");
        commandArray.add (juce::String (timelineInSeconds));
        commandArray.add ("--timeline-end");
        commandArray.add (juce::String (timelineOutSeconds));
        commandArray.add ("--clip-start-seconds");
        commandArray.add (juce::String (clipStartSeconds, 3));
        commandArray.add ("--clip-end-seconds");
        commandArray.add (juce::String (clipEndSeconds, 3));
        juce::Logger::writeToLog ("Manual Offset (trimmed clip): " + videoClipOffset);
        juce::Logger::writeToLog ("Clip Bounds: " + juce::String (clipStartSeconds, 3) + "s - " + juce::String (clipEndSeconds, 3) + "s");
        juce::Logger::writeToLog ("Timeline: " + juce::String (timelineInSeconds) + "s - " + juce::String (timelineOutSeconds) + "s");
    }
    // WORKFLOW 2: Clip bounds only (auto-detect, trimmed clip, no manual offset)
    else if (clipStartSeconds >= 0.0f && clipEndSeconds >= 0.0f)
    {
        commandArray.add ("--clip-start-seconds");
        commandArray.add (juce::String (clipStartSeconds, 3));
        commandArray.add ("--clip-end-seconds");
        commandArray.add (juce::String (clipEndSeconds, 3));
        juce::Logger::writeToLog ("Clip Bounds (seconds): " + juce::String (clipStartSeconds, 3) + " - " + juce::String (clipEndSeconds, 3));
    }
    // WORKFLOW 3: Manual offset WITHOUT clip bounds (untrimmed clip + manual offset)
    else if (videoClipOffset.isNotEmpty())
    {
        commandArray.add ("--video-offset");
        commandArray.add (videoClipOffset);
        juce::Logger::writeToLog ("Video Clip Offset: " + videoClipOffset);
        
        // Also pass timeline selection times (in seconds) for trimming calculation
        commandArray.add ("--timeline-start");
        commandArray.add (juce::String (timelineInSeconds));
        commandArray.add ("--timeline-end");
        commandArray.add (juce::String (timelineOutSeconds));
        juce::Logger::writeToLog ("Timeline Selection (seconds): " + juce::String (timelineInSeconds) + " - " + juce::String (timelineOutSeconds));
    }
    // WORKFLOW 3 (LEGACY): Auto-detect in background (unsafe from plugin, causes deadlock)
    else if (autoDetectClipBounds)
    {
        commandArray.add ("--auto-detect-clip-bounds");
        juce::Logger::writeToLog ("WARNING: Auto-detect clip boundaries in background (may cause deadlock from plugin!)");
    }
    
    // Generate output directory path (filename will be generated server-side with prompt snippet)
    auto tempDir = juce::File::getSpecialLocation (juce::File::tempDirectory);
    auto outputsDir = tempDir.getChildFile ("pt_v2a_outputs");
    outputsDir.createDirectory();
    
    // NOTE: We no longer generate a specific filename here
    // The server will generate a descriptive name: {prompt_snippet}_{seed}_{model}_{timestamp}.wav
    // Python client will save using the server-provided filename
    // We pass --output with the directory path (client will use this as base for server-generated filename)
    
    commandArray.add ("--output-format");
    commandArray.add ("wav");  // Pro Tools compatible
    
    commandArray.add ("--output");
    commandArray.add (outputsDir.getFullPathName());  // Explicit output directory
    
    juce::ignoreUnused (fullPrecision);   // precision is the backend's business; kept for the call sites
    
    // NOTE: No --import-to-protools flag - plugin will handle PTSL import async!
    // NOTE: Removed --quiet for debugging - we want to see Python output!
    // commandArray.add ("--quiet");  // Minimal output for parsing
    
    juce::Logger::writeToLog ("Starting audio generation (background process)...");
    juce::Logger::writeToLog ("Output directory: " + outputsDir.getFullPathName());
    juce::Logger::writeToLog ("Server will generate filename with prompt snippet");
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // The process runs in the background; the editor polls the output directory for
    // the WAV and, through getGenerationProcess(), notices when the script exits
    // without one (backend crashed, request refused) instead of waiting for the timeout.
    generationProcess = std::make_unique<juce::ChildProcess>();
    
    if (!generationProcess->start (commandArray))
    {
        generationProcess.reset();
        juce::String error = "Failed to start Python process";
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    
    juce::Logger::writeToLog ("✓ Python process started (background)");
    
    // NOTE: Server generates filename with prompt snippet, so we can't predict the exact name
    // Instead, we return the output directory path
    // The Editor will poll for the NEWEST .wav file in this directory
    juce::Logger::writeToLog ("Output directory: " + outputsDir.getFullPathName());
    juce::Logger::writeToLog ("Editor will poll for newest WAV file in directory...");
    
    if (errorMessage != nullptr)
        *errorMessage = "";  // Clear any previous error
    
    // Return the output directory path (Editor will find the newest file there)
    return outputsDir.getFullPathName();
}

//==============================================================================
// T2A Audio Generation (text-only, no video)
//==============================================================================

juce::String PtV2AProcessor::generateAudioTextOnly (
    const juce::String& prompt,
    float duration,
    const juce::String& negativePrompt,
    int seed,
    juce::String* errorMessage)
{
    juce::Logger::writeToLog ("=== T2A Generation Started (text-only) ===");

    juce::Logger::writeToLog ("Duration: " + juce::String (duration, 1) + "s");
    juce::Logger::writeToLog ("Prompt: " + prompt);
    juce::Logger::writeToLog ("Negative Prompt: " + negativePrompt);
    juce::Logger::writeToLog ("Seed: " + juce::String (seed));
    
    // Validate inputs against what the selected backend accepts
    if (const auto limits = getSelectedAdapter ("generation"); limits.isValid() && ! limits.acceptsDuration (duration))
    {
        juce::String error = limits.name + " generates " + limits.durationRange() + ", got: " + juce::String (duration, 1) + "s";
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    
    // Get Python executable and script
    auto pythonExe = getPythonExecutable();
    auto scriptFile = getAPIClientScript();  // Uses standalone_api_client.py (supports T2A)
    
    if (!scriptFile.existsAsFile())
    {
        juce::String error = "API client script not found: " + scriptFile.getFullPathName();
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    
    juce::File scriptDir = scriptFile.getParentDirectory();
    juce::Logger::writeToLog ("Script directory: " + scriptDir.getFullPathName());
    
    // Build command line arguments (NO --video parameter for T2A)
    juce::StringArray commandArray;
    
    commandArray.add (pythonExe);
    commandArray.add ("-X");
    commandArray.add ("utf8");
    commandArray.add (scriptFile.getFullPathName());
    
    // T2A mode: Specify action explicitly
    commandArray.add ("--action");
    commandArray.add ("t2a");
    
    // T2A mode: NO --video parameter, but ADD --duration
    commandArray.add ("--duration");
    commandArray.add (juce::String (duration, 1));
    
    if (prompt.isNotEmpty())
    {
        commandArray.add ("--prompt");
        commandArray.add (prompt);
    }
    
    if (negativePrompt.isNotEmpty())
    {
        commandArray.add ("--negative-prompt");
        commandArray.add (negativePrompt);
    }
    
    commandArray.add ("--seed");
    commandArray.add (juce::String (seed));
    
    // The selected adapter profile tells the script where the backend is
    const auto adapter = getSelectedAdapter ("generation");
    if (! adapter.isValid())
    {
        juce::String error = "No generation backend selected. Open Settings and pick or add an adapter profile.";
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    commandArray.add ("--adapter");
    commandArray.add (adapter.file);
    juce::Logger::writeToLog ("Using adapter profile: " + adapter.file + " (" + adapter.name + ")");
    
    // Output settings
    auto tempDir = juce::File::getSpecialLocation (juce::File::tempDirectory);
    auto outputsDir = tempDir.getChildFile ("pt_v2a_outputs");
    outputsDir.createDirectory();
    
    commandArray.add ("--output-format");
    commandArray.add ("wav");
    
    commandArray.add ("--output");
    commandArray.add (outputsDir.getFullPathName());  // Explicit output directory
    
    commandArray.add ("--verbose");  // Enable verbose output for debugging
    
    juce::Logger::writeToLog ("Starting T2A audio generation (background process)...");
    juce::Logger::writeToLog ("Output directory: " + outputsDir.getFullPathName());
    juce::Logger::writeToLog ("Command: " + commandArray.joinIntoString (" "));
    
    // Start background process
    auto* backgroundProcess = new juce::ChildProcess();
    
    if (!backgroundProcess->start (commandArray))
    {
        delete backgroundProcess;
        juce::String error = "Failed to start Python process for T2A generation";
        juce::Logger::writeToLog ("ERROR: " + error);
        if (errorMessage != nullptr)
            *errorMessage = error;
        return {};
    }
    
    juce::Logger::writeToLog ("✓ T2A process started successfully");
    
    // Intentionally leak process (runs independently)
    // Editor will poll for output file
    
    if (errorMessage != nullptr)
        *errorMessage = "";
    
    // Return output directory path
    return outputsDir.getFullPathName();
}

//==============================================================================
// Logging Implementation
//==============================================================================

bool PtV2AProcessor::initializeLogger()
{
    // Only initialize once (singleton pattern)
    if (fileLogger != nullptr)
        return true;
    
    // Same folder as config.json (see getUserDataDir)
    auto logDir = getUserDataDir();

    // Ensure directory exists
    if (!logDir.exists())
    {
        auto result = logDir.createDirectory();
        if (result.failed())
        {
            // Can't create directory - logging will fail (use console as fallback)
            std::cerr << "Failed to create log directory: " << result.getErrorMessage() << std::endl;
            return false;
        }
    }
    
    // Clean up old rotated logs (industry standard: keep last 30 days)
    // This prevents unlimited log file accumulation over time
    // JUCE's FileLogger creates .log.1, .log.2, etc. when rotating
    auto now = juce::Time::getCurrentTime();
    int deletedCount = 0;
    
    for (auto logFile : logDir.findChildFiles (juce::File::findFiles, false, "*.log*"))
    {
        // Calculate file age in days
        auto fileAge = now - logFile.getCreationTime();
        
        // Delete logs older than 30 days (industry standard)
        if (fileAge.inDays() > 30)
        {
            if (logFile.deleteFile())
                deletedCount++;
        }
    }
    
    if (deletedCount > 0)
        std::cout << "Cleaned up " << deletedCount << " old log files" << std::endl;
    
    auto logFile = logDir.getChildFile (juce::String (kPluginName) + ".log");

    // Create FileLogger instance
    // Parameters: logFile, welcomeMessage, maxInitialFileSizeBytes
    fileLogger = std::make_unique<juce::FileLogger> (
        logFile,
        juce::String (kPluginName) + " Plugin Log",
1024 * 1024 * 5  // 5 MB max log file size (then rotates)
    );
    
    // Set as default logger for all juce::Logger::writeToLog() calls
    juce::Logger::setCurrentLogger (fileLogger.get());
    
    // Write startup message
    juce::Logger::writeToLog ("===========================================");
    juce::Logger::writeToLog (juce::String (kPluginName) + " Plugin Started");
    juce::Logger::writeToLog ("Log file: " + logFile.getFullPathName());
    juce::Logger::writeToLog ("Timestamp: " + juce::Time::getCurrentTime().toString (true, true));
    juce::Logger::writeToLog ("===========================================");
    
    return true;
}

void PtV2AProcessor::updateTrackProperties (const TrackProperties& properties)
{
    if (properties.name.has_value())
    {
        const juce::ScopedLock sl (hostTrackNameLock);
        hostTrackName = *properties.name;
    }
}

juce::String PtV2AProcessor::getHostTrackName() const
{
    const juce::ScopedLock sl (hostTrackNameLock);
    return hostTrackName;
}

void PtV2AProcessor::setLoggingEnabled (bool enabled)
{
    if (enabled)
    {
        initializeLogger();
        return;
    }
    if (fileLogger == nullptr)
        return;
    juce::Logger::writeToLog ("Log saving turned off in the settings; no further lines are written.");
    juce::Logger::setCurrentLogger (nullptr);   // writeToLog() then goes to the debugger only
    fileLogger.reset();
}

juce::File PtV2AProcessor::getLogFile()
{
    if (fileLogger == nullptr)
        return juce::File();
    
    // Get log file path from logger
    return fileLogger->getLogFile();
}

//==============================================================================
// Phase 3B: Timeline Selection & Video Trimming Implementation
//==============================================================================

bool PtV2AProcessor::isFFmpegAvailable()
{
    juce::Logger::writeToLog ("=== Checking FFmpeg Availability ===");
    
    auto pythonExe = getPythonExecutable();
    auto scriptFile = getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: API client script not found: " + scriptFile.getFullPathName());
        return false;
    }
    
    // Build command: python standalone_api_client.py --action check_ffmpeg
    juce::String command = "\"" + pythonExe + "\" ";
    command += "\"" + scriptFile.getFullPathName() + "\" ";
    command += "--action check_ffmpeg";
    
    juce::Logger::writeToLog ("Executing FFmpeg check command...");
    juce::Logger::writeToLog ("Command: " + command);
    
    // Create child process
    juce::ChildProcess process;
    
    if (!process.start (command))
    {
        juce::Logger::writeToLog ("ERROR: Failed to start Python process");
        return false;
    }
    
    // Wait for completion (should be fast, <1 second)
    if (!process.waitForProcessToFinish (5000))  // 5 second timeout
    {
        juce::Logger::writeToLog ("ERROR: FFmpeg check timed out");
        process.kill();
        return false;
    }
    
    // Read output
    auto output = process.readAllProcessOutput().trim();
    juce::Logger::writeToLog ("Python output: " + output);
    
    // Parse JSON response
    auto json = juce::JSON::parse (output);
    if (auto* obj = json.getDynamicObject())
    {
        bool available = obj->getProperty ("available");
        auto version = obj->getProperty ("version").toString();
        auto source = obj->getProperty ("source").toString();
        auto error = obj->getProperty ("error").toString();
        
        if (available)
        {
            juce::Logger::writeToLog ("=== FFmpeg Check SUCCESS ===");
            juce::Logger::writeToLog ("Version: " + version);
            juce::Logger::writeToLog ("Source: " + source);
            return true;
        }
        else
        {
            juce::Logger::writeToLog ("=== FFmpeg Check FAILED ===");
            juce::Logger::writeToLog ("ERROR: " + error);
            return false;
        }
    }
    
    juce::Logger::writeToLog ("ERROR: Failed to parse FFmpeg check response");
    juce::Logger::writeToLog ("Raw output was: " + output);
    return false;
}

PtV2AProcessor::VideoSelectionInfo PtV2AProcessor::getVideoSelectionInfo()
{
    VideoSelectionInfo result;
    result.success = false;
    
    juce::Logger::writeToLog ("=== Getting Video Timeline Selection ===");
    
    auto pythonExe = getPythonExecutable();
    auto scriptFile = getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        result.errorMessage = "API client script not found";
        juce::Logger::writeToLog ("ERROR: " + result.errorMessage);
        return result;
    }
    
    // Get script directory (for working directory)
    juce::File scriptDir = scriptFile.getParentDirectory();
    juce::String scriptPath = scriptDir.getFullPathName();
    
    // Create log file for Python stderr output (separate from stdout)
    auto logDir = getUserDataDir();
    auto pythonLogFile = logDir.getChildFile ("python_stderr.log");
    juce::String pythonLogPath = pythonLogFile.getFullPathName();
    
    juce::Logger::writeToLog ("Python stderr will be logged to: " + pythonLogPath);
    
    // Build command: Direct Python call with -X utf8 flag (NO cmd.exe needed!)
    // Python's -X utf8 flag forces UTF-8 mode without environment variables
    juce::StringArray commandArray;
    commandArray.add (pythonExe);
    commandArray.add ("-X");           // Python option prefix
    commandArray.add ("utf8");         // Force UTF-8 mode (Python 3.7+)
    commandArray.add (scriptFile.getFullPathName());
    commandArray.add ("--action");
    commandArray.add ("get_video_selection");
    
    juce::Logger::writeToLog ("Executing timeline selection command...");
    juce::Logger::writeToLog ("Python: " + pythonExe);
    juce::Logger::writeToLog ("Args: " + commandArray.joinIntoString (" "));
    
    // Create child process
    juce::ChildProcess process;
    
    // Start process directly with array (NO shell wrapper!)
    // JUCE will capture stdout/stderr automatically
    if (!process.start (commandArray))
    {
        result.errorMessage = "Failed to start Python process";
        juce::Logger::writeToLog ("ERROR: " + result.errorMessage);
        return result;
    }
    
    juce::Logger::writeToLog ("Python process started, waiting for completion...");
    
    // CRITICAL: Wait for process to finish FIRST, then read output!
    // Reading output while process is running can cause deadlock with PTSL
    if (!process.waitForProcessToFinish (5000))  // 5 second timeout
    {
        result.errorMessage = "Timeline selection read timed out";
        juce::Logger::writeToLog ("ERROR: " + result.errorMessage);
        juce::Logger::writeToLog ("Make sure:");
        juce::Logger::writeToLog ("1. Pro Tools is running");
        juce::Logger::writeToLog ("2. You have a timeline selection (In/Out points)");
        juce::Logger::writeToLog ("3. PTSL is enabled in Pro Tools preferences");
        process.kill();
        return result;
    }
    
    juce::Logger::writeToLog ("Process finished, reading output...");
    
    // NOW read output after process has completed
    juce::String output = process.readAllProcessOutput();
    
    // Log output to file for debugging AND display
    if (output.isNotEmpty())
    {
        if (fileLogger != nullptr)                  // log saving is on
            pythonLogFile.replaceWithText (output);
        juce::Logger::writeToLog ("Python output captured:");
        juce::Logger::writeToLog (output);
    }
    else
    {
        result.errorMessage = "No output from Python script";
        juce::Logger::writeToLog ("ERROR: " + result.errorMessage);
        return result;
    }
    
    // Extract JSON from output (might have debug lines before/after)
    // Look for lines starting with { (JSON response)
    auto lines = juce::StringArray::fromLines (output);
    juce::String jsonOutput;
    for (const auto& line : lines)
    {
        if (line.trimStart().startsWith ("{"))
        {
            jsonOutput = line.trim();
            break;  // Found JSON response
        }
    }
    
    if (jsonOutput.isEmpty())
    {
        result.errorMessage = "No JSON response found in output";
        juce::Logger::writeToLog ("ERROR: " + result.errorMessage);
        juce::Logger::writeToLog ("Full output was: " + output);
        return result;
    }
    
    juce::Logger::writeToLog ("Extracted JSON: " + jsonOutput);
    output = jsonOutput;  // Use extracted JSON for parsing
    
    // Parse JSON response
    auto json = juce::JSON::parse (output);
    if (auto* obj = json.getDynamicObject())
    {
        result.success = obj->getProperty ("success");
        result.inTime = obj->getProperty ("in_time").toString();
        result.outTime = obj->getProperty ("out_time").toString();
        result.durationSeconds = (float) (double) obj->getProperty ("duration_seconds");
        result.inSeconds = (float) (double) obj->getProperty ("in_seconds");
        result.outSeconds = (float) (double) obj->getProperty ("out_seconds");
        result.fps = (float) (double) obj->getProperty ("fps");
        result.errorMessage = obj->getProperty ("error").toString();
        
        if (result.success)
        {
            juce::Logger::writeToLog ("=== Timeline Selection SUCCESS ===");
            juce::Logger::writeToLog ("Timeline: " + result.inTime + " - " + result.outTime);
            juce::Logger::writeToLog ("Duration: " + juce::String (result.durationSeconds, 2) + "s");
            juce::Logger::writeToLog ("FPS: " + juce::String (result.fps, 2));
        }
        else
        {
            juce::Logger::writeToLog ("=== Timeline Selection FAILED ===");
            juce::Logger::writeToLog ("ERROR: " + result.errorMessage);
            juce::Logger::writeToLog ("Make sure:");
            juce::Logger::writeToLog ("1. Pro Tools is running");
            juce::Logger::writeToLog ("2. You have a timeline selection (In/Out points)");
            juce::Logger::writeToLog ("3. PTSL is enabled in Pro Tools preferences");
        }
        
        return result;
    }
    
    result.errorMessage = "Failed to parse timeline selection response";
    juce::Logger::writeToLog ("ERROR: " + result.errorMessage);
    juce::Logger::writeToLog ("Raw output was: " + output);
    return result;
}

juce::String PtV2AProcessor::getVideoFileFromProTools(juce::String* errorMessage)
{
    juce::Logger::writeToLog ("=== Getting Video File from Pro Tools ===");
    
    auto pythonExe = getPythonExecutable();
    auto scriptFile = getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::String errorMsg = "API client script not found";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return juce::String();
    }
    
    // Use get_video_info action (same as V2A workflow - faster and more reliable)
    juce::String command = "\"" + pythonExe + "\" ";
    command += "\"" + scriptFile.getFullPathName() + "\" ";
    command += "--action get_video_info";
    
    juce::Logger::writeToLog ("Executing video file lookup command...");
    juce::Logger::writeToLog ("Command: " + command);
    
    // Create child process
    juce::ChildProcess process;
    
    if (!process.start (command))
    {
        juce::String errorMsg = "Failed to start Python process";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return juce::String();
    }
    
    juce::Logger::writeToLog ("Process started, waiting for completion...");
    
    // Wait for completion (first PTSL connection can be slow - 20s timeout)
    if (!process.waitForProcessToFinish (20000))  // 20 second timeout
    {
        juce::String errorMsg = "Video file lookup timed out after 20s";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        juce::Logger::writeToLog ("PTSL may be slow to connect on first call");
        process.kill();
        if (errorMessage != nullptr)
            *errorMessage = errorMsg + " (PTSL connection may be slow)";
        return juce::String();
    }
    
    int exitCode = process.getExitCode();
    juce::Logger::writeToLog ("Process completed with exit code: " + juce::String (exitCode));
    
    // Read output
    auto output = process.readAllProcessOutput().trim();
    juce::Logger::writeToLog ("Python output length: " + juce::String (output.length()) + " chars");
    
    if (output.length() > 1000)
    {
        juce::Logger::writeToLog ("Python output (first 1000 chars): " + output.substring (0, 1000));
    }
    else if (!output.isEmpty())
    {
        juce::Logger::writeToLog ("Python output: " + output);
    }
    else
    {
        juce::Logger::writeToLog ("WARNING: Empty output from Python process");
    }
    
    // Parse JSON response (get_video_info returns combined timeline + video data)
    auto json = juce::JSON::parse (output);
    if (auto* obj = json.getDynamicObject())
    {
        bool success = obj->getProperty ("success");
        auto videoPath = obj->getProperty ("video_path").toString();
        auto errorFromJson = obj->getProperty ("error").toString();
        
        if (success && videoPath.isNotEmpty())
        {
            juce::Logger::writeToLog ("=== Video File Lookup SUCCESS ===");
            juce::Logger::writeToLog ("Video path: " + videoPath);
            if (errorMessage != nullptr)
                *errorMessage = "";
            return videoPath;
        }
        else
        {
            juce::Logger::writeToLog ("=== Video File Lookup FAILED ===");
            juce::Logger::writeToLog ("ERROR: " + errorFromJson);
            if (errorMessage != nullptr)
                *errorMessage = errorFromJson;
            return juce::String();
        }
    }
    
    juce::String errorMsg = "Failed to parse video file response";
    juce::Logger::writeToLog ("ERROR: " + errorMsg);
    juce::Logger::writeToLog ("Raw output was: " + output);
    if (errorMessage != nullptr)
        *errorMessage = errorMsg;
    return juce::String();
}

juce::String PtV2AProcessor::trimVideoSegment(
    const juce::String& videoPath,
    float startSeconds,
    float endSeconds,
    juce::String* errorMessage)
{
    juce::Logger::writeToLog ("=== Trimming Video Segment ===");
    juce::Logger::writeToLog ("Video: " + videoPath);
    juce::Logger::writeToLog ("Range: " + juce::String (startSeconds, 2) + "s - " + juce::String (endSeconds, 2) + "s");
    
    auto pythonExe = getPythonExecutable();
    auto scriptFile = getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::String errorMsg = "API client script not found";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return juce::String();
    }
    
    // Build command: python standalone_api_client.py --action trim_video 
    //                --video "path" --start-time X --end-time Y
    juce::String command = "\"" + pythonExe + "\" ";
    command += "\"" + scriptFile.getFullPathName() + "\" ";
    command += "--action trim_video ";
    command += "--video \"" + videoPath + "\" ";
    command += "--start-time " + juce::String (startSeconds) + " ";
    command += "--end-time " + juce::String (endSeconds);
    
    juce::Logger::writeToLog ("Executing video trim command...");
    juce::Logger::writeToLog ("Command: " + command);
    
    // Create child process
    juce::ChildProcess process;
    
    if (!process.start (command))
    {
        juce::String errorMsg = "Failed to start Python process";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return juce::String();
    }
    
    // Wait for completion (FFmpeg trimming can take 1-3 seconds)
    if (!process.waitForProcessToFinish (60000))  // 60 second timeout
    {
        juce::String errorMsg = "Video trimming timed out";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        process.kill();
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return juce::String();
    }
    
    // Read output
    auto output = process.readAllProcessOutput().trim();
    juce::Logger::writeToLog ("Python output: " + output);
    
    // Parse JSON response
    auto json = juce::JSON::parse (output);
    if (auto* obj = json.getDynamicObject())
    {
        bool success = obj->getProperty ("success");
        auto outputPath = obj->getProperty ("output_path").toString();
        auto errorFromJson = obj->getProperty ("error").toString();
        
        if (success && outputPath.isNotEmpty())
        {
            juce::Logger::writeToLog ("=== Video Trim SUCCESS ===");
            juce::Logger::writeToLog ("Output path: " + outputPath);
            if (errorMessage != nullptr)
                *errorMessage = "";
            return outputPath;
        }
        else
        {
            juce::Logger::writeToLog ("=== Video Trim FAILED ===");
            juce::Logger::writeToLog ("ERROR: " + errorFromJson);
            if (errorMessage != nullptr)
                *errorMessage = errorFromJson;
            return juce::String();
        }
    }
    
    juce::String errorMsg = "Failed to parse video trimming response";
    juce::Logger::writeToLog ("ERROR: " + errorMsg);
    juce::Logger::writeToLog ("Raw output was: " + output);
    if (errorMessage != nullptr)
        *errorMessage = errorMsg;
    return juce::String();
}

float PtV2AProcessor::getVideoDuration(
    const juce::String& videoPath,
    juce::String* errorMessage)
{
    juce::Logger::writeToLog ("=== Getting Video Duration ===");
    juce::Logger::writeToLog ("Video: " + videoPath);
    
    auto pythonExe = getPythonExecutable();
    auto scriptFile = getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::String errorMsg = "API client script not found";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return -1.0f;
    }
    
    // Build command: python standalone_api_client.py --action get_duration --video "path"
    juce::String command = "\"" + pythonExe + "\" ";
    command += "\"" + scriptFile.getFullPathName() + "\" ";
    command += "--action get_duration ";
    command += "--video \"" + videoPath + "\"";
    
    juce::Logger::writeToLog ("Executing duration check command...");
    juce::Logger::writeToLog ("Command: " + command);
    
    // Create child process
    juce::ChildProcess process;
    
    if (!process.start (command))
    {
        juce::String errorMsg = "Failed to start Python process";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return -1.0f;
    }
    
    // Wait for completion (should be fast, <2 seconds)
    if (!process.waitForProcessToFinish (10000))  // 10 second timeout
    {
        juce::String errorMsg = "Duration check timed out";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        process.kill();
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return -1.0f;
    }
    
    // Read output
    auto output = process.readAllProcessOutput().trim();
    juce::Logger::writeToLog ("Python output: " + output);
    
    // Parse JSON response
    auto json = juce::JSON::parse (output);
    if (auto* obj = json.getDynamicObject())
    {
        bool success = obj->getProperty ("success");
        double duration = (double) obj->getProperty ("duration");
        auto errorFromJson = obj->getProperty ("error").toString();
        
        if (success && duration > 0.0)
        {
            juce::Logger::writeToLog ("=== Duration Check SUCCESS ===");
            juce::Logger::writeToLog ("Duration: " + juce::String (duration, 2) + "s");
            if (errorMessage != nullptr)
                *errorMessage = "";
            return (float) duration;
        }
        else
        {
            juce::Logger::writeToLog ("=== Duration Check FAILED ===");
            juce::Logger::writeToLog ("ERROR: " + errorFromJson);
            if (errorMessage != nullptr)
                *errorMessage = errorFromJson;
            return -1.0f;
        }
    }
    
    juce::String errorMsg = "Failed to parse duration check response";
    juce::Logger::writeToLog ("ERROR: " + errorMsg);
    juce::Logger::writeToLog ("Raw output was: " + output);
    if (errorMessage != nullptr)
        *errorMessage = errorMsg;
    return -1.0f;
}

bool PtV2AProcessor::validateVideoDuration(
    float durationSeconds,
    float maxDuration,
    juce::String* errorMessage)
{
    juce::Logger::writeToLog ("=== Validating Video Duration ===");
    juce::Logger::writeToLog ("Duration: " + juce::String (durationSeconds, 2) + "s (max: " + 
         juce::String (maxDuration, 2) + "s)");
    
    auto pythonExe = getPythonExecutable();
    auto scriptFile = getAPIClientScript();
    
    if (!scriptFile.existsAsFile())
    {
        juce::String errorMsg = "API client script not found";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return false;
    }
    
    // Build command: python standalone_api_client.py --action validate_duration 
    //                --duration X --max-duration Y
    juce::String command = "\"" + pythonExe + "\" ";
    command += "\"" + scriptFile.getFullPathName() + "\" ";
    command += "--action validate_duration ";
    command += "--duration " + juce::String (durationSeconds) + " ";
    command += "--max-duration " + juce::String (maxDuration);
    
    juce::Logger::writeToLog ("Executing duration validation command...");
    juce::Logger::writeToLog ("Command: " + command);
    
    // Create child process
    juce::ChildProcess process;
    
    if (!process.start (command))
    {
        juce::String errorMsg = "Failed to start Python process";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return false;
    }
    
    // Wait for completion (should be instant)
    if (!process.waitForProcessToFinish (5000))  // 5 second timeout
    {
        juce::String errorMsg = "Duration validation timed out";
        juce::Logger::writeToLog ("ERROR: " + errorMsg);
        process.kill();
        if (errorMessage != nullptr)
            *errorMessage = errorMsg;
        return false;
    }
    
    // Read output
    auto output = process.readAllProcessOutput().trim();
    juce::Logger::writeToLog ("Python output: " + output);
    
    // Parse JSON response
    auto json = juce::JSON::parse (output);
    if (auto* obj = json.getDynamicObject())
    {
        bool valid = obj->getProperty ("valid");
        auto errorFromJson = obj->getProperty ("error").toString();
        
        if (valid)
        {
            juce::Logger::writeToLog ("=== Duration Validation SUCCESS ===");
            juce::Logger::writeToLog ("Duration is valid");
            if (errorMessage != nullptr)
                *errorMessage = "";
            return true;
        }
        else
        {
            juce::Logger::writeToLog ("=== Duration Validation FAILED ===");
            juce::Logger::writeToLog ("ERROR: " + errorFromJson);
            if (errorMessage != nullptr)
                *errorMessage = errorFromJson;
            return false;
        }
    }
    
    juce::String errorMsg = "Failed to parse duration validation response";
    juce::Logger::writeToLog ("ERROR: " + errorMsg);
    juce::Logger::writeToLog ("Raw output was: " + output);
    if (errorMessage != nullptr)
        *errorMessage = errorMsg;
    return false;
}

//==============================================================================
// Cloudflare Access Credential Management Implementation
//==============================================================================

const std::vector<PtV2AProcessor::BackendService>& PtV2AProcessor::backendServices()
{
    static const std::vector<BackendService> services {
        { "mmaudio",      "MMAudio (generation)",            "http://localhost:8000" },

        { "sound_search", "Sound search (BBC archive)",      "http://localhost:8002" },
        { "spotting",     "Spotting",                        "http://localhost:8003" },
    };
    return services;
}

juce::String PtV2AProcessor::BackendSettings::activeUrl (const juce::String& serviceKey) const
{
    if (useTunnel)
    {
        auto it = tunnelUrls.find (serviceKey);
        if (it != tunnelUrls.end() && it->second.isNotEmpty())
            return it->second;
    }
    auto it = directUrls.find (serviceKey);
    if (it != directUrls.end() && it->second.isNotEmpty())
        return it->second;
    for (const auto& service : backendServices())
        if (service.key == serviceKey)
            return service.defaultDirectUrl;
    return DEFAULT_API_URL;
}

juce::File PtV2AProcessor::getUserDataDir()
{
    // Windows: %APPDATA%\AI Sound Design   macOS: ~/Library/AI Sound Design
    // (JUCE's userApplicationDataDirectory is ~/Library on macOS, not
    // ~/Library/Application Support). companion/api/config.py resolves the same
    // folder, so plugin and scripts read one config.json.
    auto appData = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory);
    auto dir = appData.getChildFile (kUserDataDirName);

    if (! dir.exists())
    {
        dir.createDirectory();
        // First run after the rename: carry the old settings over.
        auto legacy = appData.getChildFile ("PTV2A").getChildFile ("config.json");
        if (legacy.existsAsFile())
            legacy.copyFileTo (dir.getChildFile ("config.json"));
    }
    return dir;
}

juce::File PtV2AProcessor::getConfigFilePath()
{
    return getUserDataDir().getChildFile ("config.json");
}

PtV2AProcessor::BackendSettings PtV2AProcessor::getBackendSettings()
{
    BackendSettings settings;
    for (const auto& service : backendServices())
        settings.directUrls[service.key] = service.defaultDirectUrl;

    auto configFile = getConfigFilePath();
    if (! configFile.existsAsFile())
    {
        saveBackendSettings (settings);  // write the defaults so the Python side finds a file too
        return settings;
    }

    auto json = juce::JSON::parse (configFile.loadFileAsString());
    auto* root = json.getDynamicObject();
    if (root == nullptr)
    {
        juce::Logger::writeToLog ("config.json could not be parsed, using defaults: " + configFile.getFullPathName());
        return settings;
    }

    settings.useTunnel = (bool) root->getProperty ("use_cloudflared");
    if (root->hasProperty ("save_logs"))
        settings.saveLogs = (bool) root->getProperty ("save_logs");
    if (root->hasProperty ("search_results"))
        settings.searchResults = juce::jlimit (1, 200, (int) root->getProperty ("search_results"));
    if (auto* adapters = root->getProperty ("adapters").getDynamicObject())
        for (const auto& entry : adapters->getProperties())
            settings.adapters[entry.name.toString()] = entry.value.toString();
    settings.clientId = root->getProperty ("cf_access_client_id").toString();
    settings.clientSecret = root->getProperty ("cf_access_client_secret").toString();

    if (auto* services = root->getProperty ("services").getDynamicObject())
    {
        for (const auto& entry : services->getProperties())
        {
            if (auto* service = entry.value.getDynamicObject())
            {
                const auto key = entry.name.toString();
                auto direct = service->getProperty ("api_url_direct").toString();
                if (direct.isNotEmpty())
                    settings.directUrls[key] = direct;
                settings.tunnelUrls[key] = service->getProperty ("api_url_cloudflared").toString();
            }
        }
    }
    return settings;
}

bool PtV2AProcessor::saveBackendSettings (const BackendSettings& settings)
{
    auto configFile = getConfigFilePath();

    // Start from the file on disk so keys this dialog does not know survive.
    juce::var json;
    if (configFile.existsAsFile())
        json = juce::JSON::parse (configFile.loadFileAsString());
    if (json.getDynamicObject() == nullptr)
        json = juce::var (new juce::DynamicObject());
    auto* root = json.getDynamicObject();

    root->setProperty ("use_cloudflared", settings.useTunnel);
    root->setProperty ("save_logs", settings.saveLogs);
    root->setProperty ("search_results", settings.searchResults);
    {
        juce::var adaptersVar (new juce::DynamicObject());
        for (const auto& kv : settings.adapters)
            adaptersVar.getDynamicObject()->setProperty (kv.first, kv.second);
        root->setProperty ("adapters", adaptersVar);
    }
    root->setProperty ("cf_access_client_id", settings.clientId);
    root->setProperty ("cf_access_client_secret", settings.clientSecret);

    juce::var servicesVar = root->getProperty ("services");
    if (servicesVar.getDynamicObject() == nullptr)
        servicesVar = juce::var (new juce::DynamicObject());
    auto* services = servicesVar.getDynamicObject();

    auto allKeys = std::vector<juce::String>();
    for (const auto& service : backendServices())
        allKeys.push_back (service.key);
    for (const auto& kv : settings.directUrls)
        if (std::find (allKeys.begin(), allKeys.end(), kv.first) == allKeys.end())
            allKeys.push_back (kv.first);

    for (const auto& key : allKeys)
    {
        juce::var serviceVar = services->getProperty (key);
        if (serviceVar.getDynamicObject() == nullptr)
            serviceVar = juce::var (new juce::DynamicObject());
        auto* service = serviceVar.getDynamicObject();

        auto direct = settings.directUrls.find (key);
        auto tunnel = settings.tunnelUrls.find (key);
        service->setProperty ("api_url_direct", direct != settings.directUrls.end() ? direct->second : juce::String());
        service->setProperty ("api_url_cloudflared", tunnel != settings.tunnelUrls.end() ? tunnel->second : juce::String());
        services->setProperty (key, serviceVar);
    }
    root->setProperty ("services", servicesVar);

    const bool ok = configFile.replaceWithText (juce::JSON::toString (json, false, 2));
    juce::Logger::writeToLog (ok ? "Settings saved to " + configFile.getFullPathName()
                                 : "Failed to write " + configFile.getFullPathName());
    return ok;
}

//==============================================================================
// Sound Preview System Implementation (TASK 7)
//==============================================================================

bool PtV2AProcessor::startSoundPreview (const juce::String& audioPath)
{
    juce::Logger::writeToLog ("=== Starting Sound Preview ===");
    juce::Logger::writeToLog ("Audio file: " + audioPath);
    
    // Stop any existing preview
    stopSoundPreview();
    
    // Check if file exists
    juce::File audioFile (audioPath);
    if (!audioFile.existsAsFile())
    {
        juce::Logger::writeToLog ("ERROR: Audio file not found: " + audioPath);
        return false;
    }
    
    // Create reader for audio file
    auto* reader = formatManager.createReaderFor (audioFile);
    if (reader == nullptr)
    {
        juce::Logger::writeToLog ("ERROR: Failed to create audio reader for: " + audioPath);
        return false;
    }
    
    // Create reader source (takes ownership of reader)
    previewSource = std::make_unique<juce::AudioFormatReaderSource> (reader, true);
    
    // Connect to transport
    previewTransport.setSource (previewSource.get(), 0, nullptr, reader->sampleRate);
    
    // Start playback
    previewTransport.start();
    
    juce::Logger::writeToLog ("✓ Sound preview started");
    juce::Logger::writeToLog ("   Sample rate: " + juce::String (reader->sampleRate) + " Hz");
    juce::Logger::writeToLog ("   Channels: " + juce::String (reader->numChannels));
    juce::Logger::writeToLog ("   Length: " + juce::String (reader->lengthInSamples / reader->sampleRate, 2) + "s");
    
    return true;
}

void PtV2AProcessor::stopSoundPreview()
{
    if (previewTransport.isPlaying())
    {
        juce::Logger::writeToLog ("Stopping sound preview");
        previewTransport.stop();
    }
    
    // Release resources
    previewTransport.setSource (nullptr);
    previewSource.reset();
}

bool PtV2AProcessor::isSoundPreviewPlaying() const
{
    return previewTransport.isPlaying();
}

//==============================================================================
// Plugin Instance Creation
//==============================================================================

// This creates new instances of the plugin
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new PtV2AProcessor();
}
