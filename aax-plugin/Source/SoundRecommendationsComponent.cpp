#include "SoundRecommendationsComponent.h"

//==============================================================================
struct SoundRecommendationsComponent::Row : public juce::Component
{
    Row (SoundRecommendationsComponent& o) : owner (o)
    {
        play.onClick = [this] { owner.playClicked (rowIndex); };
        import.onClick = [this] { owner.importClicked (rowIndex); };
        text.setJustificationType (juce::Justification::centredLeft);
        text.setFont (juce::Font (13.0f));
        text.setInterceptsMouseClicks (false, false);
        meta.setJustificationType (juce::Justification::centredRight);
        meta.setFont (juce::Font (12.0f));
        meta.setColour (juce::Label::textColourId, juce::Colours::grey);
        meta.setInterceptsMouseClicks (false, false);
        addAndMakeVisible (play);
        addAndMakeVisible (text);
        addAndMakeVisible (meta);
        addAndMakeVisible (import);
    }

    void update (int index, const SoundResult& sound)
    {
        rowIndex = index;
        text.setText (sound.description, juce::dontSendNotification);
        juce::String info = sound.category;
        if (sound.durationSeconds > 0.0f)
        {
            int secs = juce::roundToInt (sound.durationSeconds);
            info += (info.isEmpty() ? "" : "   ") + juce::String (secs / 60) + ":" + juce::String (secs % 60).paddedLeft ('0', 2);
        }
        if (sound.similarity > 0.0f)
            info += (info.isEmpty() ? "" : "   ") + juce::String (juce::roundToInt (sound.similarity * 100.0f)) + " %";
        meta.setText (info, juce::dontSendNotification);

        const bool previewing = owner.previewingId == sound.id;
        const bool loading = owner.loadingPreviewId == sound.id;
        play.setButtonText (previewing ? juce::String (juce::CharPointer_UTF8 ("\xe2\x96\xa0"))     // ■
                          : loading    ? juce::String ("...")
                                       : juce::String (juce::CharPointer_UTF8 ("\xe2\x96\xb6")));   // ▶
        play.setEnabled (! loading);
        play.setTooltip (previewing ? "Stop preview" : "Preview this sound");

        const bool downloading = owner.downloadingSounds.count (sound.id) > 0;
        const bool downloaded = owner.downloadedSounds.count (sound.id) > 0;
        import.setButtonText (downloading ? "Loading..." : downloaded ? "Import" : "Import");
        import.setEnabled (! downloading);
        import.setTooltip (downloaded ? "Place this sound at the selection"
                                      : "Download this sound and place it at the selection");
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (4, 3);
        play.setBounds (r.removeFromLeft (30));
        r.removeFromLeft (8);
        import.setBounds (r.removeFromRight (74));
        r.removeFromRight (8);
        meta.setBounds (r.removeFromRight (170));
        text.setBounds (r);
    }

    SoundRecommendationsComponent& owner;
    int rowIndex = 0;
    juce::TextButton play, import;
    juce::Label text, meta;
};

//==============================================================================
SoundRecommendationsComponent::SoundRecommendationsComponent()
{
    headerLabel.setJustificationType (juce::Justification::centredLeft);
    headerLabel.setFont (juce::Font (14.0f, juce::Font::bold));
    addAndMakeVisible (headerLabel);

    listBox.setModel (this);
    listBox.setRowHeight (rowHeight);
    listBox.setMultipleSelectionEnabled (false);
    listBox.setColour (juce::ListBox::backgroundColourId, juce::Colour (0xff232323));
    listBox.setColour (juce::ListBox::outlineColourId, juce::Colours::grey);
    listBox.setOutlineThickness (1);
    addAndMakeVisible (listBox);

    clearResults();
    setVisible (false);
}

SoundRecommendationsComponent::~SoundRecommendationsComponent()
{
    stopTimer();
    listBox.setModel (nullptr);
}

void SoundRecommendationsComponent::paint (juce::Graphics& g)
{
    g.fillAll (getLookAndFeel().findColour (juce::ResizableWindow::backgroundColourId).darker (0.3f));
    g.setColour (juce::Colours::grey);
    g.drawRect (getLocalBounds(), 1);
}

void SoundRecommendationsComponent::resized()
{
    auto area = getLocalBounds().reduced (border);
    headerLabel.setBounds (area.removeFromTop (headerHeight));
    listBox.setBounds (area);
}

//==============================================================================
void SoundRecommendationsComponent::setResults (const std::vector<SoundResult>& results)
{
    if (previewingId != -1 && onPreview)
        onPreview (SoundResult { previewingId }, false);
    previewingId = -1;
    loadingPreviewId = -1;
    stopTimer();

    soundResults = results;
    downloadedSounds.clear();
    downloadingSounds.clear();
    for (const auto& sound : soundResults)
        if (sound.localPath.isNotEmpty())
            downloadedSounds[sound.id] = sound.localPath;

    headerLabel.setText ("Database Recommendations (" + juce::String (soundResults.size()) + ")"
                         + (soundResults.empty() ? "" : juce::String ("   ") + juce::String (juce::CharPointer_UTF8 ("\xe2\x96\xb6"))
                                                        + " preview, Import places the sound at the selection"),
                         juce::dontSendNotification);
    listBox.updateContent();
    listBox.deselectAllRows();
    listBox.repaint();
    setVisible (! soundResults.empty());
}

void SoundRecommendationsComponent::clearResults()
{
    setResults ({});
}

const SoundResult* SoundRecommendationsComponent::getCurrentSound() const
{
    int row = listBox.getSelectedRow();
    if (row < 0 || row >= getResultCount())
        return nullptr;
    return &soundResults[(size_t) row];
}

//==============================================================================
void SoundRecommendationsComponent::paintListBoxItem (int row, juce::Graphics& g, int width, int height, bool selected)
{
    if (selected)
        g.fillAll (juce::Colour (0xff2f5f9f).withAlpha (0.45f));
    else if (row % 2 == 1)
        g.fillAll (juce::Colours::white.withAlpha (0.03f));
    g.setColour (juce::Colours::white.withAlpha (0.08f));
    g.drawHorizontalLine (height - 1, 0.0f, (float) width);
}

juce::Component* SoundRecommendationsComponent::refreshComponentForRow (int row, bool, juce::Component* existing)
{
    if (row < 0 || row >= getResultCount())
    {
        delete existing;
        return nullptr;
    }
    auto* line = dynamic_cast<Row*> (existing);
    if (line == nullptr)
    {
        delete existing;
        line = new Row (*this);
    }
    line->update (row, soundResults[(size_t) row]);
    return line;
}

void SoundRecommendationsComponent::listBoxItemDoubleClicked (int row, const juce::MouseEvent&)
{
    playClicked (row);
}

void SoundRecommendationsComponent::refreshRows()
{
    listBox.repaint();
    for (int row = 0; row < getResultCount(); ++row)
        if (auto* line = dynamic_cast<Row*> (listBox.getComponentForRowNumber (row)))
            line->update (row, soundResults[(size_t) row]);
}

//==============================================================================
void SoundRecommendationsComponent::playClicked (int row)
{
    if (row < 0 || row >= getResultCount() || ! onPreview)
        return;
    const auto& sound = soundResults[(size_t) row];
    listBox.selectRow (row);

    if (previewingId == sound.id)
    {
        onPreview (sound, false);
        setPreviewing (-1);
        return;
    }
    onPreview (sound, true);
}

void SoundRecommendationsComponent::importClicked (int row)
{
    if (row < 0 || row >= getResultCount() || ! onImport)
        return;
    listBox.selectRow (row);
    auto sound = soundResults[(size_t) row];
    auto it = downloadedSounds.find (sound.id);
    if (it != downloadedSounds.end())
        sound.localPath = it->second;
    juce::Logger::writeToLog ("[SoundRec] Import: ID=" + juce::String (sound.id) + ", " + sound.description);
    onImport (sound);
}

//==============================================================================
void SoundRecommendationsComponent::markSoundAsDownloaded (int soundId, const juce::String& localPath)
{
    downloadedSounds[soundId] = localPath;
    downloadingSounds.erase (soundId);
    for (auto& sound : soundResults)
        if (sound.id == soundId)
            sound.localPath = localPath;
    refreshRows();
}

void SoundRecommendationsComponent::markSoundAsDownloading (int soundId)
{
    downloadingSounds.insert (soundId);
    refreshRows();
}

void SoundRecommendationsComponent::clearDownloadingState (int soundId)
{
    downloadingSounds.erase (soundId);
    refreshRows();
}

void SoundRecommendationsComponent::setPreviewLoading (int soundId)
{
    loadingPreviewId = soundId;
    refreshRows();
}

void SoundRecommendationsComponent::setPreviewing (int soundId)
{
    loadingPreviewId = -1;
    previewingId = soundId;
    if (previewingId != -1)
        startTimer (200);      // notice when the file has played to its end
    else
        stopTimer();
    refreshRows();
}

void SoundRecommendationsComponent::timerCallback()
{
    if (previewingId != -1 && isPreviewPlaying && ! isPreviewPlaying())
        setPreviewing (-1);
}
