#include "SettingsPanel.h"
#include <cmath>

namespace
{
    constexpr int rowHeight = SettingsPanel::rowHeight;
    constexpr int lengthRowHeight = SettingsPanel::lengthRowHeight;
    constexpr int gap = 8;
    constexpr int margin = 16;
    constexpr int nameWidth = 230;
    constexpr int testWidth = 60;
    constexpr int statusWidth = 120;

    /** GET <url> with a short timeout. Runs on a background thread. */
    bool probeHealth (const juce::String& fullUrl, const juce::String& extraHeaders, juce::String& detail)
    {
        if (fullUrl.trim().isEmpty())
        {
            detail = "no URL";
            return false;
        }

        juce::URL url (fullUrl.trim());
        int status = 0;
        auto options = juce::URL::InputStreamOptions (juce::URL::ParameterHandling::inAddress)
                           .withConnectionTimeoutMs (4000)
                           .withExtraHeaders (extraHeaders)
                           .withStatusCode (&status);

        auto stream = url.createInputStream (options);
        if (stream == nullptr)
        {
            detail = "unreachable";
            return false;
        }
        stream->readEntireStreamAsString();  // drain; some servers need the body read
        detail = "HTTP " + juce::String (status);
        return status >= 200 && status < 300;
    }
}

SettingsPanel::SettingsPanel (PtV2AProcessor& p, std::function<void()> savedCallback)
    : processor (p), onSaved (std::move (savedCallback))
{
    intro.setText ("Backends are described by adapter profiles, one JSON file each. Every profile in the "
                   "folder appears here and in the Backend list of its mode. Add a file to add a backend.",
                   juce::dontSendNotification);
    intro.setFont (juce::Font (13.0f));
    intro.setJustificationType (juce::Justification::topLeft);
    intro.setColour (juce::Label::textColourId, juce::Colours::lightgrey);
    addAndMakeVisible (intro);

    openFolderButton.onClick = [this]
    {
        auto dir = PtV2AProcessor::getAdapterDir();
        dir.createDirectory();
        dir.revealToUser();
    };
    reloadButton.onClick = [this]
    {
        rebuildRows();
        applyTunnelMode();
        setSize (preferredWidth, preferredHeight());
        if (auto* dialog = findParentComponentOfClass<juce::DialogWindow>())
            dialog->setContentComponentSize (preferredWidth, preferredHeight());
    };
    folderHint.setFont (juce::Font (12.0f));
    folderHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    folderHint.setText (PtV2AProcessor::getAdapterDir().getFullPathName(), juce::dontSendNotification);
    addAndMakeVisible (openFolderButton);
    addAndMakeVisible (reloadButton);
    addAndMakeVisible (folderHint);

    tunnelToggle.onClick = [this]
    {
        settings.useTunnel = tunnelToggle.getToggleState();
        applyTunnelMode();
    };
    addAndMakeVisible (tunnelToggle);

    clientId.setMultiLine (false);
    clientSecret.setMultiLine (false);
    clientSecret.setPasswordCharacter ((juce::juce_wchar) 0x2022);
    clientIdLabel.setFont (juce::Font (14.0f));
    clientSecretLabel.setFont (juce::Font (14.0f));
    tunnelHint.setText ("Cloudflare Access service token, sent as CF-Access-Client-Id / -Secret. "
                        "With the tunnel on, the rows above edit each profile's tunnel address.",
                        juce::dontSendNotification);
    tunnelHint.setFont (juce::Font (12.0f));
    tunnelHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    addAndMakeVisible (clientIdLabel);
    addAndMakeVisible (clientSecretLabel);
    addAndMakeVisible (clientId);
    addAndMakeVisible (clientSecret);
    addAndMakeVisible (tunnelHint);

    searchCountLabel.setFont (juce::Font (14.0f));
    for (int n : { 5, 10, 15, 20, 30, 50, 100 })
        searchCount.addItem (juce::String (n), n);          // item id = value
    searchCountHint.setText ("How many archive sounds a recommendation search returns; the list scrolls.",
                             juce::dontSendNotification);
    searchCountHint.setFont (juce::Font (12.0f));
    searchCountHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    addAndMakeVisible (searchCountLabel);
    addAndMakeVisible (searchCount);
    addAndMakeVisible (searchCountHint);

    logHint.setText ("Written to " + PtV2AProcessor::getUserDataDir().getFullPathName()
                     + ". Off: nothing is written to disk and Open Log is unavailable.",
                     juce::dontSendNotification);
    logHint.setFont (juce::Font (12.0f));
    logHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    addAndMakeVisible (logToggle);
    addAndMakeVisible (logHint);

    saveButton.onClick = [this] { save(); };
    cancelButton.onClick = [this] { close(); };
    addAndMakeVisible (saveButton);
    addAndMakeVisible (cancelButton);

    loadFromSettings();
    setSize (preferredWidth, preferredHeight());
}

SettingsPanel::~SettingsPanel() = default;

int SettingsPanel::preferredHeight() const
{
    int rowsHeight = 0;
    for (const auto& row : rows)
        rowsHeight += rowHeight + gap + (row->hasSubRow() ? lengthRowHeight + gap : 0);
    rowsHeight = juce::jmax (rowHeight + gap, rowsHeight);
    return 2 * margin + 44 + gap + rowsHeight + rowHeight + 20 + 3 * gap      // intro, rows, folder buttons + hint
         + rowHeight + gap + 2 * (rowHeight + gap) + 20 + 2 * gap             // tunnel toggle, id, secret, hint
         + rowHeight + 20 + gap + rowHeight + 20 + 2 * gap                    // search count, log toggle
         + rowHeight + gap;                                                   // buttons
}

void SettingsPanel::setUpNumberEditor (juce::TextEditor& editor, double value)
{
    editor.setMultiLine (false);
    editor.setReturnKeyStartsNewLine (false);
    editor.setInputRestrictions (6, "0123456789.");
    editor.setJustification (juce::Justification::centred);
    editor.setText (juce::String (value, value == std::floor (value) ? 0 : 1), false);
}

void SettingsPanel::rebuildRows()
{
    rows.clear();
    for (const auto& profile : processor.getAdapterProfiles())
    {
        auto row = std::make_unique<AdapterRow>();
        row->profile = profile;
        row->name.setText (profile.name + "  (" + profile.kind + ")", juce::dontSendNotification);
        row->name.setFont (juce::Font (14.0f));
        row->name.setTooltip (profile.file);
        row->url.setMultiLine (false);
        row->url.setReturnKeyStartsNewLine (false);
        row->status.setFont (juce::Font (13.0f));
        row->status.setJustificationType (juce::Justification::centredLeft);

        auto* raw = row.get();
        row->test.onClick = [this, raw] { testAdapter (*raw); };

        addAndMakeVisible (row->name);
        addAndMakeVisible (row->url);
        addAndMakeVisible (row->test);
        addAndMakeVisible (row->status);
        if (row->hasLengths())
        {
            for (auto* label : { &row->lengthLabel, &row->maxLabel, &row->defaultLabel })
            {
                label->setFont (juce::Font (13.0f));
                label->setJustificationType (juce::Justification::centredRight);
                addAndMakeVisible (*label);
            }
            setUpNumberEditor (row->minLength, profile.minDuration);
            setUpNumberEditor (row->maxLength, profile.maxDuration);
            setUpNumberEditor (row->defaultLength, profile.defaultDuration);
            row->lengthLabel.setTooltip ("Lengths this backend generates. The plugin offers whole seconds "
                                         "between min and max for text-to-audio and skips clips outside them.");
            for (auto* editor : { &row->minLength, &row->maxLength, &row->defaultLength })
                addAndMakeVisible (*editor);
        }
        if (row->hasMatch())
        {
            for (auto* label : { &row->piecesLabel, &row->layersLabel, &row->similarityLabel })
            {
                label->setFont (juce::Font (13.0f));
                label->setJustificationType (juce::Justification::centredRight);
                addAndMakeVisible (*label);
            }
            setUpNumberEditor (row->pieces, profile.piecesPer10s);
            setUpNumberEditor (row->layers, profile.layers);
            setUpNumberEditor (row->minSimilarity, profile.minSimilarity);
            row->minSimilarity.setText (juce::String (profile.minSimilarity, 2), false);
            row->pieces.setInputRestrictions (2, "0123456789");
            row->layers.setInputRestrictions (2, "0123456789");
            row->minSimilarity.setInputRestrictions (4, "0123456789.");
            row->piecesLabel.setTooltip ("Use database sounds: at most this many library pieces per ten seconds "
                                         "of a generated sound; a recording that fits the whole sound is kept whole "
                                         "(1 = never cut). Max db tracks: how many tracks of library sounds one event "
                                         "may get; a further track is added only where another recording still fits, "
                                         "so 1 keeps everything on one track. Min similarity (0-1): pieces below it "
                                         "are not placed, so a sound without a convincing match keeps its generated version.");
            addAndMakeVisible (row->pieces);
            addAndMakeVisible (row->layers);
            addAndMakeVisible (row->minSimilarity);
        }
        rows.push_back (std::move (row));
    }
    if (rows.empty())
    {
        auto row = std::make_unique<AdapterRow>();
        row->name.setText ("No adapter profiles found in the folder below.", juce::dontSendNotification);
        row->name.setFont (juce::Font (14.0f));
        row->url.setVisible (false);
        row->test.setVisible (false);
        addAndMakeVisible (row->name);
        rows.push_back (std::move (row));
    }
    resized();
}

void SettingsPanel::loadFromSettings()
{
    settings = processor.getBackendSettings();
    rebuildRows();
    tunnelToggle.setToggleState (settings.useTunnel, juce::dontSendNotification);
    logToggle.setToggleState (settings.saveLogs, juce::dontSendNotification);
    if (searchCount.indexOfItemId (settings.searchResults) < 0)
        searchCount.addItem (juce::String (settings.searchResults), settings.searchResults);
    searchCount.setSelectedId (settings.searchResults, juce::dontSendNotification);
    clientId.setText (settings.clientId, false);
    clientSecret.setText (settings.clientSecret, false);
    applyTunnelMode();
}

void SettingsPanel::applyTunnelMode()
{
    const bool tunnel = settings.useTunnel;
    for (auto& row : rows)
    {
        if (! row->profile.isValid())
            continue;
        row->url.setText (tunnel ? row->profile.tunnelUrl : row->profile.baseUrl, false);
        row->url.setTextToShowWhenEmpty (tunnel ? "https://<service>.<your-domain>" : "http://localhost:8000",
                                         juce::Colours::grey);
        row->status.setText ({}, juce::dontSendNotification);
    }
    for (auto* c : { (juce::Component*) &clientIdLabel, (juce::Component*) &clientSecretLabel,
                     (juce::Component*) &clientId, (juce::Component*) &clientSecret,
                     (juce::Component*) &tunnelHint })
        c->setEnabled (tunnel);
}

void SettingsPanel::testAdapter (AdapterRow& row)
{
    const auto url = row.url.getText().trim().trimCharactersAtEnd ("/") + row.profile.health;
    juce::String headers;
    if (tunnelToggle.getToggleState())
        headers = "CF-Access-Client-Id: " + clientId.getText().trim() + "\r\n"
                  "CF-Access-Client-Secret: " + clientSecret.getText().trim() + "\r\n";

    row.status.setText ("testing...", juce::dontSendNotification);
    row.status.setColour (juce::Label::textColourId, juce::Colours::lightgrey);
    row.test.setEnabled (false);

    // The probe blocks for up to the timeout; keep it off Pro Tools' message thread.
    juce::Component::SafePointer<SettingsPanel> safeThis (this);
    AdapterRow* target = &row;
    juce::Thread::launch ([safeThis, target, url, headers]
    {
        juce::String detail;
        const bool ok = probeHealth (url, headers, detail);
        juce::MessageManager::callAsync ([safeThis, target, ok, detail]
        {
            if (safeThis == nullptr)
                return;
            // The row still belongs to this panel as long as the panel is alive.
            target->status.setText (ok ? "reachable (" + detail + ")" : "failed: " + detail,
                                    juce::dontSendNotification);
            target->status.setColour (juce::Label::textColourId,
                                      ok ? juce::Colours::lightgreen : juce::Colours::orange);
            target->test.setEnabled (true);
        });
    });
}

void SettingsPanel::save()
{
    settings.useTunnel = tunnelToggle.getToggleState();
    settings.clientId = clientId.getText().trim();
    settings.clientSecret = clientSecret.getText().trim();
    settings.saveLogs = logToggle.getToggleState();
    if (searchCount.getSelectedId() > 0)
        settings.searchResults = searchCount.getSelectedId();

    if (! processor.saveBackendSettings (settings))
    {
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Save Failed",
                                                "Could not write " + processor.getConfigFilePath().getFullPathName(),
                                                "OK");
        return;
    }

    // Addresses and length limits live in the profile files; only what changed is written.
    for (auto& row : rows)
    {
        if (! row->profile.isValid())
            continue;
        const auto current = settings.useTunnel ? row->profile.tunnelUrl : row->profile.baseUrl;
        const auto edited = row->url.getText().trim();
        if (edited != current && ! processor.saveAdapterUrl (row->profile.file, edited, settings.useTunnel))
            juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Save Failed",
                                                    "Could not update the adapter profile " + row->profile.file, "OK");

        if (row->hasLengths())
        {
            const double lo = row->minLength.getText().getDoubleValue();
            const double hi = row->maxLength.getText().getDoubleValue();
            double preset = row->defaultLength.getText().getDoubleValue();
            const bool changed = lo != row->profile.minDuration || hi != row->profile.maxDuration
                              || preset != row->profile.defaultDuration;
            if (! changed)
                continue;
            if (lo <= 0.0 || hi < lo)
            {
                juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Length Limits",
                                                        row->profile.name + ": min must be above 0 and max at least min. "
                                                        "The limits were left unchanged.", "OK");
                continue;
            }
            preset = juce::jlimit (lo, hi, preset > 0.0 ? preset : (lo + hi) / 2.0);
            if (! processor.saveAdapterDuration (row->profile.file, lo, hi, preset))
                juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Save Failed",
                                                        "Could not update the adapter profile " + row->profile.file, "OK");
        }
        if (row->hasMatch())
        {
            const int pieces = juce::jlimit (1, 20, row->pieces.getText().getIntValue());
            const int layers = juce::jlimit (1, 10, row->layers.getText().getIntValue());
            const double similarity = juce::jlimit (0.0, 1.0, row->minSimilarity.getText().getDoubleValue());
            if (pieces == row->profile.piecesPer10s && layers == row->profile.layers
                && std::abs (similarity - row->profile.minSimilarity) < 0.001)
                continue;
            if (! processor.saveAdapterMatch (row->profile.file, pieces, layers, similarity))
                juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Save Failed",
                                                        "Could not update the adapter profile " + row->profile.file, "OK");
        }
    }

    PtV2AProcessor::setLoggingEnabled (settings.saveLogs);
    if (onSaved)
        onSaved();
    close();
}

void SettingsPanel::close()
{
    if (auto* dialog = findParentComponentOfClass<juce::DialogWindow>())
        dialog->exitModalState (0);
}

void SettingsPanel::paint (juce::Graphics& g)
{
    g.fillAll (getLookAndFeel().findColour (juce::ResizableWindow::backgroundColourId));

    // Dividers above the advanced section and above the plugin options
    g.setColour (juce::Colours::grey.withAlpha (0.4f));
    g.drawHorizontalLine (tunnelToggle.getY() - gap, (float) margin, (float) (getWidth() - margin));
    g.drawHorizontalLine (searchCountLabel.getY() - gap, (float) margin, (float) (getWidth() - margin));
}

void SettingsPanel::resized()
{
    auto area = getLocalBounds().reduced (margin);

    intro.setBounds (area.removeFromTop (44));
    area.removeFromTop (gap);

    for (auto& row : rows)
    {
        auto line = area.removeFromTop (rowHeight);
        if (! row->profile.isValid())
        {
            row->name.setBounds (line);
        }
        else
        {
            row->name.setBounds (line.removeFromLeft (nameWidth));
            row->status.setBounds (line.removeFromRight (statusWidth));
            line.removeFromRight (gap);
            row->test.setBounds (line.removeFromRight (testWidth));
            line.removeFromRight (gap);
            row->url.setBounds (line);
        }
        area.removeFromTop (gap);
        if (row->hasLengths())
        {
            auto sub = area.removeFromTop (lengthRowHeight).withTrimmedLeft (nameWidth);
            row->lengthLabel.setBounds (sub.removeFromLeft (96));
            sub.removeFromLeft (gap);
            row->minLength.setBounds (sub.removeFromLeft (52));
            row->maxLabel.setBounds (sub.removeFromLeft (40));
            sub.removeFromLeft (gap);
            row->maxLength.setBounds (sub.removeFromLeft (52));
            row->defaultLabel.setBounds (sub.removeFromLeft (60));
            sub.removeFromLeft (gap);
            row->defaultLength.setBounds (sub.removeFromLeft (52));
            area.removeFromTop (gap);
        }
        if (row->hasMatch())
        {
            auto sub = area.removeFromTop (lengthRowHeight).withTrimmedLeft (nameWidth);
            row->piecesLabel.setBounds (sub.removeFromLeft (110));
            sub.removeFromLeft (gap);
            row->pieces.setBounds (sub.removeFromLeft (44));
            row->layersLabel.setBounds (sub.removeFromLeft (92));
            sub.removeFromLeft (gap);
            row->layers.setBounds (sub.removeFromLeft (36));
            row->similarityLabel.setBounds (sub.removeFromLeft (96));
            sub.removeFromLeft (gap);
            row->minSimilarity.setBounds (sub.removeFromLeft (48));
            area.removeFromTop (gap);
        }
    }

    auto folderLine = area.removeFromTop (rowHeight);
    openFolderButton.setBounds (folderLine.removeFromLeft (170));
    folderLine.removeFromLeft (gap);
    reloadButton.setBounds (folderLine.removeFromLeft (80));
    folderHint.setBounds (area.removeFromTop (20));
    area.removeFromTop (2 * gap);

    tunnelToggle.setBounds (area.removeFromTop (rowHeight));
    area.removeFromTop (gap);

    auto idLine = area.removeFromTop (rowHeight);
    clientIdLabel.setBounds (idLine.removeFromLeft (nameWidth));
    clientId.setBounds (idLine);
    area.removeFromTop (gap);

    auto secretLine = area.removeFromTop (rowHeight);
    clientSecretLabel.setBounds (secretLine.removeFromLeft (nameWidth));
    clientSecret.setBounds (secretLine);
    area.removeFromTop (4);
    tunnelHint.setBounds (area.removeFromTop (20).withTrimmedLeft (nameWidth));

    area.removeFromTop (2 * gap);
    auto countLine = area.removeFromTop (rowHeight);
    searchCountLabel.setBounds (countLine.removeFromLeft (nameWidth));
    searchCount.setBounds (countLine.removeFromLeft (90));
    searchCountHint.setBounds (area.removeFromTop (20).withTrimmedLeft (nameWidth));

    area.removeFromTop (gap);
    logToggle.setBounds (area.removeFromTop (rowHeight));
    logHint.setBounds (area.removeFromTop (20).withTrimmedLeft (24));

    auto buttons = area.removeFromBottom (rowHeight);
    saveButton.setBounds (buttons.removeFromRight (100));
    buttons.removeFromRight (gap);
    cancelButton.setBounds (buttons.removeFromRight (100));
}
