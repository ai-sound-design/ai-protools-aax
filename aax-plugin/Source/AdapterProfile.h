#pragma once
#include <juce_core/juce_core.h>

/**
 * One adapter profile: a JSON file in the user's adapters folder that describes a
 * backend. The plugin knows three kinds of service (generation, search, spotting)
 * and the profile selected for each; nothing model-specific is compiled in.
 * The file format is documented in companion/api/adapters.py.
 */
struct AdapterProfile
{
    juce::String file;        ///< file name inside the adapters folder (the identity)
    juce::String name;        ///< shown in the Backend list and the settings
    juce::String kind;        ///< "generation", "search" or "spotting"
    juce::String baseUrl;
    juce::String tunnelUrl;   ///< used instead of baseUrl when the Cloudflare tunnel is on
    juce::String health;      ///< health path, default "/health"
    juce::String protocol;
    juce::StringArray supports;   ///< generation: "negative_prompt", "seed", "duration", "text_only"

    /// Generation: the lengths the backend accepts, in seconds ("duration": {min, max, default}).
    /// The plugin builds its duration list from these and skips clips outside them.
    double minDuration = 4.0;
    double maxDuration = 12.0;
    double defaultDuration = 8.0;

    /// Hybrid: library match settings ("match": {pieces_per_10s, layers, ...}), sent to the backend
    /// by the companion; the plugin only edits them in Settings.
    int piecesPer10s = 3;
    int layers = 1;
    double minSimilarity = 0.5;   ///< pieces below it are not placed
    double ambienceHandleSeconds = 10.0;   ///< an ambience piece keeps this much of its recording before and after
    int tracksPerScene = 8;                ///< the sounds of a scene share at most this many tracks
    juce::String fadePreset { "AI Sound Design" };   ///< Pro Tools batch-fades preset for the ambience handles
    double fadeSeconds = 1.0;              ///< how much handle a clip keeps outside the event for that fade
    bool fadeInside = false;               ///< the fade runs inside the event instead (the clip ends at the event)

    bool isValid() const noexcept { return file.isNotEmpty(); }
    bool supportsFeature (const juce::String& feature) const { return supports.contains (feature); }
    bool acceptsDuration (double seconds) const noexcept { return seconds >= minDuration && seconds <= maxDuration; }
    juce::String durationRange() const { return juce::String (minDuration, 0) + "-" + juce::String (maxDuration, 0) + " s"; }

    juce::String activeUrl (bool tunnel) const
    {
        return (tunnel && tunnelUrl.isNotEmpty() ? tunnelUrl : baseUrl).trim().trimCharactersAtEnd ("/");
    }
};
