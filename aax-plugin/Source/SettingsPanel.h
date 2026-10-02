#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "PluginProcessor.h"

/**
 * Settings dialog, one tab per mode: Spotting, Generation, Recommendation, Hybrid, then
 * Plugin (its own options, and the tunnel as its advanced part).
 *
 * A mode's tab lists the adapter profiles of its kind (one JSON file per backend):
 * name, address, a Test button that probes <address><health> off the message thread,
 * and the options the profile carries (a hybrid backend's library match). Editing the
 * address writes it back into the profile file. The lengths a generation backend
 * accepts are not edited here: the backend reports them in its health answer, the
 * profile's "duration" block is only the fallback for a backend that says nothing.
 * The footer opens the profiles folder and reloads it.
 */
class SettingsPanel : public juce::Component
{
public:
    SettingsPanel (PtV2AProcessor& processor, std::function<void()> onSaved);
    ~SettingsPanel() override;

    void paint (juce::Graphics& g) override;
    void resized() override;

    static constexpr int preferredWidth = 760;
    static constexpr int rowHeight = 28;
    static constexpr int optionRowHeight = 24;

private:
    struct AdapterRow
    {
        AdapterProfile profile;
        juce::Label name;
        juce::TextEditor url;
        juce::TextButton test { "Test" };
        juce::Label status;
        // Hybrid profiles only: the library match, one option per line (label, field, short hint)
        juce::TextEditor pieces, layers, minSimilarity, handleSeconds, tracksPerScene, fadePreset, fadeSeconds;
        juce::ComboBox fadePlace;            ///< where the fade runs: outside the event (1) or inside it (2)
        struct Option { juce::Label label, hint; juce::Component* field; int fieldWidth; };
        std::vector<std::unique_ptr<Option>> options;
        bool hasMatch() const { return profile.isValid() && profile.kind == "hybrid"; }
    };

    /** One tab. Its content is laid out by `layout` (given the width, returns the height
        used) and scrolls when it is taller than the page. */
    struct Page : public juce::Component
    {
        Page();
        void resized() override;
        juce::Viewport viewport;
        juce::Component content;
        std::function<int (int width)> layout;
        int contentHeight = 0;
    };

    /** A mode's tab: its profiles. */
    struct BackendPage
    {
        juce::String kind;                   ///< "spotting", "generation", "search", "hybrid"
        Page page;
        juce::Label hint;                    ///< what this kind of backend does
        std::vector<std::unique_ptr<AdapterRow>> rows;
    };

    void buildTabs();
    void buildRows (BackendPage& backend);
    int layoutBackendPage (BackendPage& backend, int width);
    int layoutPluginPage (int width);
    void loadFromSettings();
    void applyTunnelMode();
    void testAdapter (AdapterRow& row);
    void save();
    void close();
    void fitToContent();
    static void setUpNumberEditor (juce::TextEditor& editor, double value);

    PtV2AProcessor& processor;
    PtV2AProcessor::BackendSettings settings;
    std::function<void()> onSaved;

    juce::TabbedComponent tabs { juce::TabbedButtonBar::TabsAtTop };
    std::vector<std::unique_ptr<BackendPage>> backends;
    Page pluginPage;

    // Footer: the profiles folder, Cancel and Save
    juce::TextButton openFolderButton { "Open Adapter Folder..." };
    juce::TextButton reloadButton { "Reload" };
    juce::Label folderHint;
    juce::TextButton saveButton { "Save" };
    juce::TextButton cancelButton { "Cancel" };

    // Plugin tab
    juce::Label searchCountLabel { {}, "Sounds per search" };
    juce::ComboBox searchCount;
    juce::Label searchCountHint;
    juce::ToggleButton logToggle { "Save a log file (for troubleshooting)" };
    juce::Label logHint;

    // Plugin tab, advanced part: the tunnel
    juce::Label advancedHeading { {}, "Advanced: tunnel or proxy" };
    juce::ToggleButton tunnelToggle { "Reach the backends through a tunnel or proxy (Cloudflare Access, Pangolin, ...)" };
    /** Up to two headers sent with every request while the tunnel is on: name and value each. */
    juce::Label headerLabel[2] { { {}, "Header 1" }, { {}, "Header 2" } };
    juce::TextEditor headerName[2];
    juce::TextEditor headerValue[2];
    juce::Label tunnelHint;
    void maskSecretValues();                 ///< a value whose header name says secret/token/key/password is shown as dots

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SettingsPanel)
};
