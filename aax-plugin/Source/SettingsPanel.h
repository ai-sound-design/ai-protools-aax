#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "PluginProcessor.h"

/**
 * Settings dialog: the adapter profiles (one JSON file per backend), how to reach
 * them, and a few plugin-wide options.
 *
 * Every profile in the adapters folder gets a row: name, kind, its address and a
 * Test button that probes <address><health> off the message thread. Editing the
 * address writes it back into the profile file. "Advanced" switches to the
 * Cloudflare Access tunnel: the rows then edit each profile's tunnel address and
 * the service token becomes editable.
 */
class SettingsPanel : public juce::Component
{
public:
    SettingsPanel (PtV2AProcessor& processor, std::function<void()> onSaved);
    ~SettingsPanel() override;

    void paint (juce::Graphics& g) override;
    void resized() override;

    static constexpr int preferredWidth = 660;
    static constexpr int rowHeight = 28;
    static constexpr int lengthRowHeight = 24;

private:
    struct AdapterRow
    {
        AdapterProfile profile;
        juce::Label name;
        juce::TextEditor url;
        juce::TextButton test { "Test" };
        juce::Label status;
        // Generation profiles only: the lengths the backend accepts, in seconds
        juce::Label lengthLabel { {}, "Length (s): min" };
        juce::TextEditor minLength, maxLength, defaultLength;
        juce::Label maxLabel { {}, "max" }, defaultLabel { {}, "default" };
        bool hasLengths() const { return profile.isValid() && profile.kind == "generation"; }
        // Hybrid profiles only: how finely a generated sound may be stitched from library pieces
        juce::Label piecesLabel { {}, "Pieces per 10 s" };
        juce::TextEditor pieces, layers, minSimilarity, handleSeconds, tracksPerScene, fadePreset, fadeSeconds;
        juce::Label layersLabel { {}, "max db tracks" }, similarityLabel { {}, "min similarity" };
        juce::Label handleLabel { {}, "Ambience handles (s)" }, tracksLabel { {}, "tracks per scene" };
        juce::Label fadeLabel { {}, "Fade preset" }, fadeSecondsLabel { {}, "fade (s)" };
        bool hasMatch() const { return profile.isValid() && profile.kind == "hybrid"; }
        bool hasSubRow() const { return hasLengths() || hasMatch(); }
    };

    int preferredHeight() const;
    void rebuildRows();
    void loadFromSettings();
    void applyTunnelMode();
    void testAdapter (AdapterRow& row);
    void save();
    void close();
    static void setUpNumberEditor (juce::TextEditor& editor, double value);

    PtV2AProcessor& processor;
    PtV2AProcessor::BackendSettings settings;
    std::function<void()> onSaved;

    juce::Label intro;
    std::vector<std::unique_ptr<AdapterRow>> rows;
    juce::TextButton openFolderButton { "Open Adapter Folder..." };
    juce::TextButton reloadButton { "Reload" };
    juce::Label folderHint;

    juce::ToggleButton tunnelToggle { "Advanced: reach the backends through a Cloudflare Access tunnel" };
    juce::Label clientIdLabel { {}, "Client ID" };
    juce::Label clientSecretLabel { {}, "Client secret" };
    juce::TextEditor clientId;
    juce::TextEditor clientSecret;
    juce::Label tunnelHint;

    juce::Label searchCountLabel { {}, "Sounds per search" };
    juce::ComboBox searchCount;
    juce::Label searchCountHint;

    juce::ToggleButton logToggle { "Save a log file (for troubleshooting)" };
    juce::Label logHint;

    juce::TextButton saveButton { "Save" };
    juce::TextButton cancelButton { "Cancel" };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SettingsPanel)
};
