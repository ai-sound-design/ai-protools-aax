#include "SettingsPanel.h"
#include <cmath>

namespace
{
    constexpr int rowHeight = SettingsPanel::rowHeight;
    constexpr int optionRowHeight = SettingsPanel::optionRowHeight;
    constexpr int gap = 8;
    constexpr int margin = 16;
    constexpr int nameWidth = 180;
    constexpr int urlWidth = 290;
    constexpr int testWidth = 60;
    constexpr int tabBarHeight = 30;
    constexpr int pageMinHeight = 150;      // the tallest tab sets the page height, between these
    constexpr int pageMaxHeight = 400;      // beyond it the tab scrolls

    /** GET <url> with a short timeout; `body` receives the answer. Runs on a background thread. */
    bool probeHealth (const juce::String& fullUrl, const juce::String& extraHeaders, juce::String& detail, juce::String& body)
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
        body = stream->readEntireStreamAsString();
        detail = "HTTP " + juce::String (status);
        return status >= 200 && status < 300;
    }

    const char* hintFor (const juce::String& kind)
    {
        if (kind == "spotting")   return "Spotting backends look at the video and say what sounds when. The active one is chosen in the plugin's Backend list.";
        if (kind == "generation") return "Generation backends make a sound from a video or a prompt. The lengths each one accepts come from its health answer (Test shows them).";
        if (kind == "search")     return "Recommendation backends search a sound archive; one profile per archive. The active one is chosen in the plugin's Backend list.";
        return "Hybrid backends run the whole chain: scenes, spotting, generation and, where a library recording fits, its pieces instead.";
    }

    const char* tabTitleFor (const juce::String& kind)
    {
        if (kind == "spotting")   return "Spotting";
        if (kind == "generation") return "Generation";
        if (kind == "search")     return "Recommendation";
        return "Hybrid";
    }
}

//==============================================================================
SettingsPanel::Page::Page()
{
    viewport.setViewedComponent (&content, false);
    viewport.setScrollBarsShown (true, false);
    addAndMakeVisible (viewport);
}

void SettingsPanel::Page::resized()
{
    viewport.setBounds (getLocalBounds());
    // Twice: the scrollbar that a tall content needs takes some width
    for (int pass = 0; pass < 2; ++pass)
    {
        const int width = viewport.getMaximumVisibleWidth();
        if (layout)
            contentHeight = layout (width);
        content.setSize (width, juce::jmax (contentHeight, viewport.getMaximumVisibleHeight()));
    }
}

//==============================================================================
SettingsPanel::SettingsPanel (PtV2AProcessor& p, std::function<void()> savedCallback)
    : processor (p), onSaved (std::move (savedCallback))
{
    tabs.setTabBarDepth (tabBarHeight);
    tabs.setOutline (0);
    addAndMakeVisible (tabs);

    // Sounds per search (shown on the Recommendation tab, below its profiles)
    searchCountLabel.setFont (juce::Font (14.0f));
    for (int n : { 5, 10, 15, 20, 30, 50, 100 })
        searchCount.addItem (juce::String (n), n);          // item id = value
    searchCountHint.setText ("How many archive sounds a recommendation search returns; the list scrolls.",
                             juce::dontSendNotification);
    searchCountHint.setFont (juce::Font (12.0f));
    searchCountHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    logHint.setText ("Written to " + PtV2AProcessor::getUserDataDir().getFullPathName()
                     + ". Off: nothing is written to disk and Open Log is unavailable.",
                     juce::dontSendNotification);
    logHint.setFont (juce::Font (12.0f));
    logHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    // Plugin tab
    pluginPage.content.addAndMakeVisible (logToggle);
    pluginPage.content.addAndMakeVisible (logHint);
    pluginPage.layout = [this] (int width) { return layoutPluginPage (width); };

    // Plugin tab, advanced part: the tunnel
    advancedHeading.setFont (juce::Font (14.0f, juce::Font::bold));
    pluginPage.content.addAndMakeVisible (advancedHeading);
    tunnelToggle.onClick = [this]
    {
        settings.useTunnel = tunnelToggle.getToggleState();
        applyTunnelMode();
    };
    pluginPage.content.addAndMakeVisible (tunnelToggle);
    const char* const exampleNames[2] = { "CF-Access-Client-Id", "CF-Access-Client-Secret" };
    for (int i = 0; i < 2; ++i)
    {
        headerLabel[i].setFont (juce::Font (14.0f));
        headerName[i].setMultiLine (false);
        headerName[i].setTextToShowWhenEmpty (juce::String ("header name, e.g. ") + exampleNames[i], juce::Colours::grey);
        headerName[i].onTextChange = [this] { maskSecretValues(); };
        headerValue[i].setMultiLine (false);
        headerValue[i].setTextToShowWhenEmpty ("value", juce::Colours::grey);
        pluginPage.content.addAndMakeVisible (headerLabel[i]);
        pluginPage.content.addAndMakeVisible (headerName[i]);
        pluginPage.content.addAndMakeVisible (headerValue[i]);
    }
    tunnelHint.setText ("Sent with every request while the tunnel is on. Cloudflare Access: a service token as "
                        "CF-Access-Client-Id and CF-Access-Client-Secret; Pangolin or another proxy: its access-token "
                        "header. With the tunnel on, the mode tabs edit each profile's tunnel address.",
                        juce::dontSendNotification);
    tunnelHint.setFont (juce::Font (12.0f));
    tunnelHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    tunnelHint.setJustificationType (juce::Justification::topLeft);
    pluginPage.content.addAndMakeVisible (tunnelHint);
    openFolderButton.onClick = [this]
    {
        auto dir = PtV2AProcessor::getAdapterDir();
        dir.createDirectory();
        dir.revealToUser();
    };
    reloadButton.onClick = [this]
    {
        buildTabs();
        applyTunnelMode();
        fitToContent();
    };
    folderHint.setFont (juce::Font (12.0f));
    folderHint.setColour (juce::Label::textColourId, juce::Colours::grey);
    folderHint.setText ("Profiles: " + PtV2AProcessor::getAdapterDir().getFullPathName(), juce::dontSendNotification);
    addAndMakeVisible (openFolderButton);
    addAndMakeVisible (reloadButton);
    addAndMakeVisible (folderHint);
    saveButton.onClick = [this] { save(); };
    cancelButton.onClick = [this] { close(); };
    addAndMakeVisible (saveButton);
    addAndMakeVisible (cancelButton);

    loadFromSettings();
    fitToContent();
}

SettingsPanel::~SettingsPanel() = default;

void SettingsPanel::setUpNumberEditor (juce::TextEditor& editor, double value)
{
    editor.setMultiLine (false);
    editor.setReturnKeyStartsNewLine (false);
    editor.setInputRestrictions (6, "0123456789.");
    editor.setJustification (juce::Justification::centred);
    editor.setText (juce::String (value, value == std::floor (value) ? 0 : 1), false);
}

//==============================================================================
void SettingsPanel::buildTabs()
{
    const int current = juce::jmax (0, tabs.getCurrentTabIndex());
    tabs.clearTabs();
    backends.clear();

    const auto background = getLookAndFeel().findColour (juce::ResizableWindow::backgroundColourId);
    for (auto* kind : { "spotting", "generation", "search", "hybrid" })
    {
        auto backend = std::make_unique<BackendPage>();
        backend->kind = kind;
        backend->hint.setText (hintFor (kind), juce::dontSendNotification);
        backend->hint.setFont (juce::Font (12.0f));
        backend->hint.setColour (juce::Label::textColourId, juce::Colours::grey);
        backend->hint.setJustificationType (juce::Justification::topLeft);
        backend->page.content.addAndMakeVisible (backend->hint);
        buildRows (*backend);
        if (backend->kind == "search")
            for (auto* c : { (juce::Component*) &searchCountLabel, (juce::Component*) &searchCount,
                             (juce::Component*) &searchCountHint })
                backend->page.content.addAndMakeVisible (c);
        auto* raw = backend.get();
        backend->page.layout = [this, raw] (int width) { return layoutBackendPage (*raw, width); };
        tabs.addTab (tabTitleFor (kind), background, &backend->page, false);
        backends.push_back (std::move (backend));
    }
    tabs.addTab ("Plugin", background, &pluginPage, false);
    tabs.setCurrentTabIndex (juce::jmin (current, tabs.getNumTabs() - 1), juce::dontSendNotification);
}

void SettingsPanel::buildRows (BackendPage& backend)
{
    backend.rows.clear();
    for (const auto& profile : processor.getAdapterProfiles())
    {
        if (profile.kind != backend.kind)
            continue;
        auto row = std::make_unique<AdapterRow>();
        row->profile = profile;
        row->name.setText (profile.name, juce::dontSendNotification);
        row->name.setFont (juce::Font (14.0f));
        row->name.setTooltip (profile.file);
        row->url.setMultiLine (false);
        row->url.setReturnKeyStartsNewLine (false);
        row->status.setFont (juce::Font (13.0f));
        row->status.setJustificationType (juce::Justification::centredLeft);
        row->status.setMinimumHorizontalScale (0.8f);

        auto* raw = row.get();
        row->test.onClick = [this, raw] { testAdapter (*raw); };

        auto& content = backend.page.content;
        content.addAndMakeVisible (row->name);
        content.addAndMakeVisible (row->url);
        content.addAndMakeVisible (row->test);
        content.addAndMakeVisible (row->status);
        if (row->hasMatch())
        {
            setUpNumberEditor (row->pieces, profile.piecesPer10s);
            setUpNumberEditor (row->layers, profile.layers);
            setUpNumberEditor (row->minSimilarity, profile.minSimilarity);
            row->minSimilarity.setText (juce::String (profile.minSimilarity, 2), false);
            setUpNumberEditor (row->handleSeconds, profile.ambienceHandleSeconds);
            setUpNumberEditor (row->tracksPerScene, profile.tracksPerScene);
            row->tracksPerScene.setInputRestrictions (2, "0123456789");
            row->pieces.setInputRestrictions (2, "0123456789");
            row->layers.setInputRestrictions (2, "0123456789");
            row->minSimilarity.setInputRestrictions (4, "0123456789.");
            row->handleSeconds.setInputRestrictions (3, "0123456789");
            row->fadePreset.setText (profile.fadePreset, false);
            row->fadePreset.setFont (juce::Font (13.0f));
            setUpNumberEditor (row->fadeSeconds, profile.fadeSeconds);
            row->fadeSeconds.setInputRestrictions (4, "0123456789.");
            row->fadePlace.addItem ("outside the event", 1);
            row->fadePlace.addItem ("inside the event", 2);
            row->fadePlace.setSelectedId (profile.fadeInside ? 2 : 1, juce::dontSendNotification);

            struct Spec { const char* label; juce::Component* field; int width; const char* hint; const char* tooltip; };
            const Spec specs[] = {
                { "Pieces per 10 s", &row->pieces, 48, "0 = automatic, 1 = never cut",
                  "At most this many library pieces per ten seconds of a generated sound. 1 keeps every "
                  "recording whole; 0 lets the backend decide: separate onsets such as steps or barks get a "
                  "piece each, a steady bed stays whole, guided by the spotting's word on the event." },
                { "Max db tracks", &row->layers, 48, "library tracks one event may get",
                  "A further track is added only where another recording still fits, so 1 keeps everything "
                  "on one track." },
                { "Min similarity", &row->minSimilarity, 48, "0-1; below it the generated sound stays",
                  "Pieces less similar than this are not placed, so a sound without a convincing match keeps "
                  "its generated version." },
                { "Ambience handles (s)", &row->handleSeconds, 48, "recording kept before and after an ambience",
                  "An ambience piece keeps this many seconds of its recording before and after the event in "
                  "its file; the clip is trimmed to the event, so the handles can be pulled out with the Trim "
                  "tool. The Hybrid switch \"Keep ambience handles\" turns this off for one run (hard cut)." },
                { "Tracks per scene", &row->tracksPerScene, 48, "tracks the sounds of one scene share",
                  "The sounds of one scene share at most this many tracks (about eight is usual). Sounds that "
                  "do not overlap in time share a track; further library layers are only placed where a track "
                  "within the budget is free. Sounds that have to be placed open more tracks if that many overlap." },
                { "Fade preset", &row->fadePreset, 160, "Pro Tools batch-fades preset for ambience clips",
                  "Auto fade: the Pro Tools batch-fades preset (a range across a clip's edges, Edit > Fades > "
                  "Create..., tick create new fade ins and outs, Save Settings As... under this name) that gives "
                  "an ambience clip its fade-in and fade-out. A preset Pro Tools does not know leaves the clip "
                  "without fades." },
                { "Fade (s)", &row->fadeSeconds, 48, "the fade's length, as in the preset",
                  "Auto fade: how long the fade-in and fade-out are. Outside the event, the clip keeps this much "
                  "of its handle beyond the event on each side for the fade to run over. Give the preset's "
                  "fade-in and fade-out the same length." },
                { "Fade place", &row->fadePlace, 160, "outside: full level at the edges; inside: as at a cut",
                  "Auto fade: outside the event, the clip reaches beyond the event by the fade length and is at "
                  "full level at the event's edges (the fade lies in the handle). Inside, the clip ends exactly "
                  "at the event and the fade runs within it, as an ambience starts at a scene cut." },
            };
            row->options.reserve (std::size (specs));
            for (const auto& spec : specs)
            {
                row->options.push_back (std::make_unique<AdapterRow::Option>());
                auto& option = *row->options.back();
                option.field = spec.field;
                option.fieldWidth = spec.width;
                option.label.setText (spec.label, juce::dontSendNotification);
                option.label.setFont (juce::Font (13.0f));
                option.label.setTooltip (spec.tooltip);
                option.hint.setText (spec.hint, juce::dontSendNotification);
                option.hint.setFont (juce::Font (12.0f));
                option.hint.setColour (juce::Label::textColourId, juce::Colours::grey);
                option.hint.setMinimumHorizontalScale (0.8f);
                if (auto* client = dynamic_cast<juce::SettableTooltipClient*> (spec.field))
                    client->setTooltip (spec.tooltip);
            }
            for (auto& option : row->options)
            {
                content.addAndMakeVisible (option->label);
                content.addAndMakeVisible (*option->field);
                content.addAndMakeVisible (option->hint);
            }
        }
        backend.rows.push_back (std::move (row));
    }
    if (backend.rows.empty())
    {
        auto row = std::make_unique<AdapterRow>();
        row->name.setText ("No " + juce::String (tabTitleFor (backend.kind)).toLowerCase()
                           + " profile in the folder. Add a JSON file with \"kind\": \"" + backend.kind + "\" and Reload.",
                           juce::dontSendNotification);
        row->name.setFont (juce::Font (14.0f));
        backend.page.content.addAndMakeVisible (row->name);
        backend.rows.push_back (std::move (row));
    }
}

//==============================================================================
int SettingsPanel::layoutBackendPage (BackendPage& backend, int width)
{
    auto area = juce::Rectangle<int> (0, 0, width, 10000).reduced (margin, gap);
    backend.hint.setBounds (area.removeFromTop (34));
    area.removeFromTop (gap);

    for (auto& row : backend.rows)
    {
        auto line = area.removeFromTop (rowHeight);
        if (! row->profile.isValid())
        {
            row->name.setBounds (line);
            area.removeFromTop (gap);
            continue;
        }
        row->name.setBounds (line.removeFromLeft (nameWidth));
        row->url.setBounds (line.removeFromLeft (urlWidth));
        line.removeFromLeft (gap);
        row->test.setBounds (line.removeFromLeft (testWidth));
        line.removeFromLeft (gap);
        row->status.setBounds (line);
        area.removeFromTop (gap);

        // Options as a form under the address: label | field | hint, one line each
        for (auto& option : row->options)
        {
            auto line = area.removeFromTop (optionRowHeight).withTrimmedLeft (nameWidth);
            option->label.setBounds (line.removeFromLeft (150));
            line.removeFromLeft (gap);
            option->field->setBounds (line.removeFromLeft (option->fieldWidth));
            line.removeFromLeft (gap);
            option->hint.setBounds (line);
            area.removeFromTop (4);
        }
        if (! row->options.empty())
            area.removeFromTop (gap);
    }
    if (backend.kind == "search")
    {
        area.removeFromTop (gap);
        auto countLine = area.removeFromTop (rowHeight);
        searchCountLabel.setBounds (countLine.removeFromLeft (nameWidth));
        searchCount.setBounds (countLine.removeFromLeft (90));
        searchCountHint.setBounds (area.removeFromTop (20).withTrimmedLeft (nameWidth));
    }
    return area.getY() + gap;
}

int SettingsPanel::layoutPluginPage (int width)
{
    auto area = juce::Rectangle<int> (0, 0, width, 10000).reduced (margin, gap);
    logToggle.setBounds (area.removeFromTop (rowHeight));
    logHint.setBounds (area.removeFromTop (20).withTrimmedLeft (24));
    area.removeFromTop (3 * gap);

    advancedHeading.setBounds (area.removeFromTop (22));
    area.removeFromTop (gap);
    tunnelToggle.setBounds (area.removeFromTop (rowHeight));
    area.removeFromTop (gap);
    for (int i = 0; i < 2; ++i)
    {
        auto line = area.removeFromTop (rowHeight).withTrimmedLeft (24);
        headerLabel[i].setBounds (line.removeFromLeft (70));
        headerName[i].setBounds (line.removeFromLeft (200));
        line.removeFromLeft (gap);
        headerValue[i].setBounds (line);
        area.removeFromTop (i == 0 ? gap : 4);
    }
    tunnelHint.setBounds (area.removeFromTop (48).withTrimmedLeft (24 + 70));
    return area.getY() + gap;
}

void SettingsPanel::fitToContent()
{
    // The tallest tab sets the page height, within limits; taller content scrolls
    const int width = preferredWidth;
    int tallest = pageMinHeight;
    for (auto& backend : backends)
        tallest = juce::jmax (tallest, layoutBackendPage (*backend, width));
    tallest = juce::jmax (tallest, layoutPluginPage (width));
    const int pageHeight = juce::jmin (pageMaxHeight, tallest);
    const int height = margin + tabBarHeight + pageHeight + gap + 20 + gap + rowHeight + margin;
    setSize (width, height);
    if (auto* dialog = findParentComponentOfClass<juce::DialogWindow>())
        dialog->setContentComponentSize (width, height);
}

//==============================================================================
void SettingsPanel::loadFromSettings()
{
    settings = processor.getBackendSettings();
    buildTabs();
    tunnelToggle.setToggleState (settings.useTunnel, juce::dontSendNotification);
    logToggle.setToggleState (settings.saveLogs, juce::dontSendNotification);
    if (searchCount.indexOfItemId (settings.searchResults) < 0)
        searchCount.addItem (juce::String (settings.searchResults), settings.searchResults);
    searchCount.setSelectedId (settings.searchResults, juce::dontSendNotification);
    for (int i = 0; i < 2; ++i)
    {
        headerName[i].setText (settings.tunnelHeaderNames[i], false);
        headerValue[i].setText (settings.tunnelHeaderValues[i], false);
    }
    maskSecretValues();
    applyTunnelMode();
}

void SettingsPanel::maskSecretValues()
{
    for (int i = 0; i < 2; ++i)
    {
        const auto name = headerName[i].getText().toLowerCase();
        const bool secret = name.contains ("secret") || name.contains ("token") || name.contains ("key")
                            || name.contains ("password") || name.contains ("authorization");
        const auto text = headerValue[i].getText();
        headerValue[i].setPasswordCharacter (secret ? (juce::juce_wchar) 0x2022 : 0);
        headerValue[i].setText (text, false);
    }
}

void SettingsPanel::applyTunnelMode()
{
    const bool tunnel = settings.useTunnel;
    for (auto& backend : backends)
        for (auto& row : backend->rows)
        {
            if (! row->profile.isValid())
                continue;
            row->url.setText (tunnel ? row->profile.tunnelUrl : row->profile.baseUrl, false);
            row->url.setTextToShowWhenEmpty (tunnel ? "https://<service>.<your-domain>" : "http://localhost:8000",
                                             juce::Colours::grey);
            row->status.setText ({}, juce::dontSendNotification);
        }
    for (auto* c : { (juce::Component*) &headerLabel[0], (juce::Component*) &headerLabel[1],
                     (juce::Component*) &headerName[0], (juce::Component*) &headerName[1],
                     (juce::Component*) &headerValue[0], (juce::Component*) &headerValue[1],
                     (juce::Component*) &tunnelHint })
        c->setEnabled (tunnel);
}

void SettingsPanel::testAdapter (AdapterRow& row)
{
    const auto url = row.url.getText().trim().trimCharactersAtEnd ("/") + row.profile.health;
    juce::String headers;
    if (tunnelToggle.getToggleState())
        for (int i = 0; i < 2; ++i)
            if (headerName[i].getText().trim().isNotEmpty() && headerValue[i].getText().trim().isNotEmpty())
                headers += headerName[i].getText().trim() + ": " + headerValue[i].getText().trim() + "\r\n";

    row.status.setText ("testing...", juce::dontSendNotification);
    row.status.setColour (juce::Label::textColourId, juce::Colours::lightgrey);
    row.test.setEnabled (false);

    // The probe blocks for up to the timeout; keep it off Pro Tools' message thread.
    juce::Component::SafePointer<SettingsPanel> safeThis (this);
    AdapterRow* target = &row;
    const bool generation = row.profile.kind == "generation";
    const auto file = row.profile.file;
    juce::Thread::launch ([safeThis, target, url, headers, generation, file]
    {
        juce::String detail, body;
        const bool ok = probeHealth (url, headers, detail, body);
        // A generation backend's health names the lengths it accepts; show them and keep them
        double lo = 0.0, hi = 0.0;
        if (ok && generation)
            PtV2AProcessor::parseDurationLimits (body, lo, hi);
        juce::MessageManager::callAsync ([safeThis, target, ok, detail, lo, hi, file]
        {
            if (safeThis == nullptr)
                return;
            // The row still belongs to this panel as long as the panel is alive.
            juce::String text = ok ? "reachable (" + detail + ")" : "failed: " + detail;
            if (ok && hi > 0.0)
            {
                safeThis->processor.setReportedDurationLimits (file, lo, hi);
                text = "reachable, " + juce::String (lo, 0) + "-" + juce::String (hi, 0) + " s";
            }
            target->status.setText (text, juce::dontSendNotification);
            target->status.setColour (juce::Label::textColourId,
                                      ok ? juce::Colours::lightgreen : juce::Colours::orange);
            target->test.setEnabled (true);
        });
    });
}

void SettingsPanel::save()
{
    settings.useTunnel = tunnelToggle.getToggleState();
    settings.tunnelHeaderNames.clear();
    settings.tunnelHeaderValues.clear();
    for (int i = 0; i < 2; ++i)
    {
        settings.tunnelHeaderNames.add (headerName[i].getText().trim());
        settings.tunnelHeaderValues.add (headerValue[i].getText().trim());
    }
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

    // Addresses and match settings live in the profile files; only what changed is written.
    for (auto& backend : backends)
        for (auto& row : backend->rows)
        {
            if (! row->profile.isValid())
                continue;
            const auto current = settings.useTunnel ? row->profile.tunnelUrl : row->profile.baseUrl;
            const auto edited = row->url.getText().trim();
            if (edited != current && ! processor.saveAdapterUrl (row->profile.file, edited, settings.useTunnel))
                juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Save Failed",
                                                        "Could not update the adapter profile " + row->profile.file, "OK");

            if (row->hasMatch())
            {
                const int pieces = juce::jlimit (0, 20, row->pieces.getText().getIntValue());   // 0: automatic
                const int layers = juce::jlimit (1, 10, row->layers.getText().getIntValue());
                const double similarity = juce::jlimit (0.0, 1.0, row->minSimilarity.getText().getDoubleValue());
                const double handles = juce::jlimit (0.0, 120.0, row->handleSeconds.getText().getDoubleValue());
                const int tracks = juce::jlimit (1, 64, row->tracksPerScene.getText().getIntValue());
                const juce::String preset = row->fadePreset.getText().trim();
                const double fadeSecs = juce::jlimit (0.0, 30.0, row->fadeSeconds.getText().getDoubleValue());
                const bool fadeInside = row->fadePlace.getSelectedId() == 2;
                if (pieces == row->profile.piecesPer10s && layers == row->profile.layers
                    && std::abs (similarity - row->profile.minSimilarity) < 0.001
                    && std::abs (handles - row->profile.ambienceHandleSeconds) < 0.001
                    && tracks == row->profile.tracksPerScene && preset == row->profile.fadePreset
                    && std::abs (fadeSecs - row->profile.fadeSeconds) < 0.001 && fadeInside == row->profile.fadeInside)
                    continue;
                if (! processor.saveAdapterMatch (row->profile.file, pieces, layers, similarity, handles, tracks, preset,
                                                  fadeSecs, fadeInside))
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

//==============================================================================
void SettingsPanel::paint (juce::Graphics& g)
{
    g.fillAll (getLookAndFeel().findColour (juce::ResizableWindow::backgroundColourId));
    // A frame around the page below the tab bar, and a divider above the footer
    g.setColour (juce::Colours::grey.withAlpha (0.4f));
    auto frame = tabs.getBounds().withTrimmedTop (tabBarHeight);
    g.drawRect (frame);
    g.drawHorizontalLine (folderHint.getY() - gap / 2, (float) margin, (float) (getWidth() - margin));
}

void SettingsPanel::resized()
{
    auto area = getLocalBounds().reduced (margin);

    auto buttons = area.removeFromBottom (rowHeight);
    saveButton.setBounds (buttons.removeFromRight (100));
    buttons.removeFromRight (gap);
    cancelButton.setBounds (buttons.removeFromRight (100));
    openFolderButton.setBounds (buttons.removeFromLeft (170));
    buttons.removeFromLeft (gap);
    reloadButton.setBounds (buttons.removeFromLeft (80));
    area.removeFromBottom (gap);
    folderHint.setBounds (area.removeFromBottom (20));
    area.removeFromBottom (gap);

    tabs.setBounds (area);
}
