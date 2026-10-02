#pragma once

#include <juce_gui_basics/juce_gui_basics.h>
#include <functional>
#include <map>
#include <set>
#include <vector>

/**
 * One result of the sound-archive search.
 */
struct SoundResult
{
    int id = 0;
    juce::String description;
    juce::String category;
    float similarity = 0.0f;
    float durationSeconds = 0.0f;
    float offsetSeconds = -1.0f;   ///< a search by sound: where in the recording the match lies (-1: whole file)
    float lengthSeconds = 0.0f;    ///< ...and how long that stretch is (the query's length)
    juce::String localPath;///< set once the file has been downloaded
    juce::String filename;
};

/**
 * The search results as a list: every row shows one sound with a preview button
 * (streams the file from the backend, plays through this plugin's output) and an
 * Import button (downloads first if needed, then places the sound at the selection).
 *
 *   Database Recommendations (10)
 *   ┌────────────────────────────────────────────────────────────┐
 *   │ ▶  Burmese cat meowing            Animals   82 %  [Import] │
 *   │ ▶  Cat hisses and growls          Animals   79 %  [Import] │
 *   │ …                                                          │
 *   └────────────────────────────────────────────────────────────┘
 */
class SoundRecommendationsComponent : public juce::Component,
                                      private juce::ListBoxModel,
                                      private juce::Timer
{
public:
    SoundRecommendationsComponent();
    ~SoundRecommendationsComponent() override;

    void paint (juce::Graphics& g) override;
    void resized() override;

    void setResults (const std::vector<SoundResult>& results);
    void clearResults();

    bool hasResults() const noexcept          { return ! soundResults.empty(); }
    int getResultCount() const noexcept       { return (int) soundResults.size(); }
    int getCurrentIndex() const noexcept      { return listBox.getSelectedRow(); }
    const SoundResult* getCurrentSound() const;

    /** Preferred height for `rows` visible rows. */
    static int heightForRows (int rows) noexcept { return headerHeight + rows * rowHeight + 2 * border; }

    //==========================================================================
    // Callbacks the editor provides
    std::function<void (const SoundResult&)> onDownload;                 ///< legacy, no longer used by the UI
    std::function<void (const SoundResult&)> onImport;                   ///< download if needed, then import
    std::function<void (const SoundResult&, bool start)> onPreview;      ///< start = true: play, false: stop
    std::function<bool()> isPreviewPlaying;                              ///< polled while a preview runs

    //==========================================================================
    // State updates from the editor
    void markSoundAsDownloaded (int soundId, const juce::String& localPath);
    void markSoundAsDownloading (int soundId);
    void clearDownloadingState (int soundId);
    void setPreviewLoading (int soundId);     ///< preview file is being fetched
    void setPreviewing (int soundId);         ///< -1 = nothing plays

private:
    static constexpr int headerHeight = 26;
    static constexpr int rowHeight = 28;
    static constexpr int border = 6;

    // ListBoxModel
    int getNumRows() override { return getResultCount(); }
    void paintListBoxItem (int row, juce::Graphics& g, int width, int height, bool selected) override;
    juce::Component* refreshComponentForRow (int row, bool selected, juce::Component* existing) override;
    void listBoxItemDoubleClicked (int row, const juce::MouseEvent&) override;

    void timerCallback() override;
    void refreshRows();

    struct Row;   // one line of the list: play button, text, import button
    friend struct Row;

    void playClicked (int row);
    void importClicked (int row);

    std::vector<SoundResult> soundResults;
    std::map<int, juce::String> downloadedSounds;
    std::set<int> downloadingSounds;
    int previewingId = -1;
    int loadingPreviewId = -1;

    juce::Label headerLabel;
    juce::ListBox listBox;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SoundRecommendationsComponent)
};
