#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_basics/juce_gui_basics.h>
#include <vector>

/**
 * @struct SoundResult
 * @brief Represents a single sound search result from BBC Sound Archive
 */
struct SoundResult
{
    int id;
    juce::String description;
    juce::String category;
    float similarity;
    juce::String localPath;
    juce::String filename;
};

/**
 * @class SoundRecommendationsComponent
 * @brief UI component for displaying and interacting with BBC Sound Search results
 * 
 * Features:
 *   - Displays current sound name from search results
 *   - Navigation: Previous/Next buttons to browse results
 *   - Download: Fetch sound file to enable import
 *   - Import: Add selected sound to Pro Tools timeline
 * 
 * Layout (Option 3 - Centered, Focus on Actions):
 *   ┌─────────────────────────────────────┐
 *   │ 🎵 Database Recommendations [1/5]  │
 *   │  ┌───────────────────────────────┐  │        
 *   │  │ footsteps_concrete            │  │                                         
 *   │  └───────────────────────────────┘  │
 *   │ [◀ Prev]   [⬇ Download]   [Next ▶]  │
 *   │              [↓ Import]             │
 *   └─────────────────────────────────────┘
 */
class SoundRecommendationsComponent : public juce::Component
{
public:
    //==============================================================================
    // Construction / Destruction
    //==============================================================================
    
    SoundRecommendationsComponent();
    ~SoundRecommendationsComponent() override = default;

    //==============================================================================
    // JUCE Component Lifecycle
    //==============================================================================
    
    void paint (juce::Graphics& g) override;
    void resized() override;

    //==============================================================================
    // Public Interface
    //==============================================================================
    
    /**
     * Set the search results to display
     * @param results Vector of sound results from search API
     */
    void setResults (const std::vector<SoundResult>& results);
    
    /**
     * Clear all results and hide component
     */
    void clearResults();
    
    /**
     * Get the currently selected sound result
     * @return Pointer to current sound, nullptr if no results
     */
    const SoundResult* getCurrentSound() const;
    
    /**
     * Check if component has results
     * @return True if results available
     */
    bool hasResults() const { return !soundResults.empty(); }
    
    /**
     * Get number of results
     * @return Total result count
     */
    int getResultCount() const { return static_cast<int>(soundResults.size()); }
    
    /**
     * Get current result index (0-based)
     * @return Current index
     */
    int getCurrentIndex() const { return currentIndex; }

    //==============================================================================
    // Callbacks
    //==============================================================================
    
    /**
     * Callback triggered when user clicks Download button
     * Signature: void onDownload(const SoundResult& sound)
     */
    std::function<void(const SoundResult&)> onDownload;
    
    /**
     * Callback triggered when user clicks Import button
     * Signature: void onImport(const SoundResult& sound)
     */
    std::function<void(const SoundResult&)> onImport;
    
    /**
     * Mark a sound as downloaded (enables import button)
     * @param soundId The ID of the downloaded sound
     * @param localPath Path to the downloaded file
     */
    void markSoundAsDownloaded(int soundId, const juce::String& localPath);
    
    /**
     * Mark a sound as currently downloading (shows "Downloading..." state)
     * @param soundId The ID of the sound being downloaded
     */
    void markSoundAsDownloading(int soundId);
    
    /**
     * Clear downloading state (on error/timeout, allows retry)
     * @param soundId The ID of the sound that failed to download
     */
    void clearDownloadingState(int soundId);

private:
    //==============================================================================
    // Member Variables
    //==============================================================================
    
    /** All search results */
    std::vector<SoundResult> soundResults;
    
    /** Current result index (0-based) */
    int currentIndex = 0;
    
    /** Track which sounds have been downloaded: sound_id -> local_path */
    std::map<int, juce::String> downloadedSounds;
    
    /** Track which sounds are currently downloading */
    std::set<int> downloadingSounds;

    //==============================================================================
    // GUI Components
    //==============================================================================
    
    /** Header label showing count and index */
    juce::Label headerLabel;
    
    /** Display box for current sound name */
    juce::Label soundNameLabel;
    
    /** Navigation: Previous button */
    juce::TextButton prevButton { juce::CharPointer_UTF8 ("\xe2\x97\x80 Prev") };  // ◀ Prev
    
    /** Navigation: Next button */
    juce::TextButton nextButton { juce::CharPointer_UTF8 ("Next \xe2\x96\xb6") };  // Next ▶
    
    /** Action: Download button */
    juce::TextButton downloadButton { juce::CharPointer_UTF8 ("\xe2\xac\x87 Download") };  // ⬇ Download
    
    /** Action: Import button */
    juce::TextButton importButton { juce::CharPointer_UTF8 ("\xe2\x86\x93 Import") };  // ↓ Import

    //==============================================================================
    // Event Handlers
    //==============================================================================
    
    void handlePrevClicked();
    void handleNextClicked();
    void handleDownloadClicked();
    void handleImportClicked();
    
    /**
     * Update UI to reflect current sound
     */
    void updateDisplay();

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SoundRecommendationsComponent)
};
