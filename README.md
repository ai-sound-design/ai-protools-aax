# ai-protools-aax

Research prototype for AI-assisted sound design in film post-production (anonymized for peer review).
The system combines AI-based audio generation, semantic sound recommendation, and spotting assistance in a Pro Tools-native AAX plugin workflow.

## Paper Version

The exact state of this repository at the time of paper submission is preserved and will not change:

- Branch: [`paper-submission`](https://github.com/ai-sound-design/ai-protools-aax/tree/paper-submission)
- Tag: [`v1-paper-submission`](https://github.com/ai-sound-design/ai-protools-aax/releases/tag/v1-paper-submission)

The `main` branch continues to be developed. In particular, the design implications derived from the paper will be implemented here, so `main` may differ from the version described in the paper.
GitHub's auto-generated source archives do not include the Git submodules in `external/`; use `git clone --recurse-submodules` instead.

## Demo

### 1. Sound Generation
https://github.com/user-attachments/assets/cbe2bbf0-ac58-4ff3-87b1-0d0e45d20e33

### 2. Sound Recommendation
https://github.com/user-attachments/assets/05d01e95-872f-4549-a6ed-f4d72c6ab3d3

### 3. Spotting Support
https://github.com/user-attachments/assets/4fcb9db9-5133-450c-b541-a01176fe2abb

## What This Project Does

The project enables four AI support workflows inside Pro Tools. The user marks a time range on any track; the plugin finds the video clips beneath it and handles each clip on its own.

1. **Spotting:** Sends the selected video range to a vision-language backend and places a memory location for every sound event it detects, with start and end timecode, plus one marker per clip boundary. *Spot Selection* works on the selection, *Spot Entire Track...* on the whole video track. *Detect scenes* first groups the clips into scenes (one place, one continuous stretch of time) and adds one memory location per scene, which the Hybrid mode uses; *Detect sound events* can be limited to kinds of sound (ambience, foley, SFX, music, dialogue), which the model is told and other events are dropped.
2. **Sound Generation:** Generates sound for the selected range from the video and an optional text prompt (or from the prompt alone, T2A; the sound is as long as the marked range (*Auto* in the Duration list) unless a fixed length is picked) and places the result on the plugin's track at the clip's position. The seed field defaults to -1, a fresh random seed per run; the seed that was used is part of the file and clip name, so a result can be repeated.
3. **Sound Recommendation:** Retrieves candidate sounds from a searchable library based on video, text, or both, with preview and import onto the plugin's track.
4. **Hybrid:** Asks the backend for the individual sound events in the selected range and gets one generated sound per event back, placed at the event's position. The sounds of a scene share at most the *tracks per scene* set in Settings (default 8, the usual guideline): sounds that do not overlap in time share a track, the tracks are named after the scene (`Living room, day 1 (db)`, `… 2 (gen)`) and every clip after its event or recording. Further library layers are only placed where a track within the budget is free.
   - *Use existing memory locations*: the memory locations inside the range are used as they are, event markers (a spotting run, or markers set by hand) as the events and "Scene n: …" markers as the scenes; a clip without events is spotted by the backend first (the events it finds are written into the session as memory locations), scenes without markers are detected. With the switch off, the backend spots and detects everything itself.
   - *Use database sounds*: the backend also finds library recordings that sound like each generated sound, by audio embedding and located to the second inside long recordings, and places them instead of the generated sound, on the scene's `(db)` tracks (the generated one stays only where nothing matched). *Keep generated sounds* places it too, on the scene's `(gen)` tracks. A generated sound is searched whole first and only cut into pieces where a cut improves the match, up to the *pieces per 10 s* set in Settings; *max db tracks* allows further tracks with other recordings where they still fit, and *min similarity* leaves weak matches out.
   - *Keep ambience handles*: an ambience piece keeps the seconds set in Settings (*Ambience handles*, default 10) of its recording before and after the event in its file, and the clip is trimmed to the event, so the handles can be pulled out with the Trim tool when a correction is needed; off cuts the piece to the event. A handle that would begin before the session start is cut there. *Auto fade* keeps *fade (s)* of the handle (Settings, default 1) outside the event on each side and gives the clip Pro Tools' own fade-in and fade-out over that stretch, so the sound is at full level at the event's edges; the fades come from a batch-fades preset (*Fade preset* in Settings, default "AI Sound Design"; create it once: select a range across a clip's edges, Edit > Fades > Create…, tick *Create new fade ins* and *Create new fade outs*, set their lengths to the same value, then *Save Settings As…* into the root settings folder) and are editable like any fade; off leaves the fades to you.
   - Scenes: a hybrid run always works per scene, from the session's scene markers (a spotting run with *Detect scenes*, corrected by hand if needed) or, where there are none, detected by the backend (one place, one continuous stretch of time), named and written into the session as memory locations.
   - *Run on entire track…*: the whole film. The plugin first counts the clips and shows a rough duration (hours for a feature), then runs scene by scene. The action button becomes *Stop*; what was placed stays, and a stopped or crashed run can be continued later, because the companion keeps a journal of every backend answer and every placed clip. There is no time limit: the companion writes a heartbeat into its progress file, and only when that stops for five minutes does the plugin ask whether to keep waiting. An ambience event longer than the generation model's maximum gets its library recording in the event's length.

The modes sit in one switch: Spotting, Sound Recommendation and Sound Generation in a column, and Hybrid, which combines the three, beside them; hovering a mode explains it. A mode is greyed out, with the reason in its tooltip, when its kind of backend has no adapter profile or does not answer, and the database switch when the hybrid backend reports no audio index. Long runs show a progress bar with the clip count and, where the backend reports it, the progress inside the clip ("step 2 of 3: frames 9-16 of 18", "sound 3 of 6: cat footsteps").

## Repository Structure

```text
protools-aax/
├── aax-plugin/                     # JUCE AAX plugin project, installers, build scripts
├── companion/                      # Python helpers bundled with the plugin: Pro Tools (PTSL)
│                                   # integration, backend clients, adapter profiles, video cutting
├── cloudflared/                    # Reaching a backend through a Cloudflare Access tunnel
└── external/                       # Third-party code as Git submodules (JUCE, py-ptsl)
```

The backend services (generation, search, spotting) live in the separate
[ai-services repository](https://github.com/ai-sound-design/ai-services).

## Architecture at a Glance

1. User marks a time range in Pro Tools, on any track (+ optional text input in the plugin). The plugin looks up the video clips beneath that range; each clip is handled on its own, so a range spanning several clips yields one result per clip at its own position.
2. AAX plugin calls Python helper scripts bundled in plugin resources.
3. Helper scripts communicate with one or more backend APIs.
4. Generated audio or search results are returned.
5. Plugin inserts or references results in the Pro Tools session.

## System Overview

The system is a plugin and a backend of HTTP services (generation, search, spotting, hybrid). This repository holds the plugin; the backend used during the research project was hosted on a university server and is not available anymore, but a portable, self-contained version of it is published in the [ai-services repository](https://github.com/ai-sound-design/ai-services), and any other service that fulfils the same contract works as well (see [Connecting the Plugin to Your Backend](#connecting-the-plugin-to-your-backend)).

- AAX plugin
  - JUCE-based AAX plugin for Pro Tools
  - Handles timeline interaction, user actions, and API calls
  - Embeds a Python runtime and the companion scripts

- Companion tooling
  - Python modules for Pro Tools integration (PTSL), the backend clients, adapter profiles, the CLI and video preprocessing

- Backend services (separate repository)
  - Generation: video-conditioned audio generation (MMAudio as the reference)
  - Search: retrieval over indexed sound libraries by video or text (X-CLIP + pgvector) and by sound (CLAP audio embeddings of 10 s windows, located to the second)
  - Spotting: sound events with timecodes from a vision-language model
  - Hybrid: one generated sound per event, optionally matched with library recordings

## Setup

1. **Backend.** The plugin needs its backend services (generation, search, spotting, and hybrid for one sound per event). A complete, ready-to-run example is the [ai-services repository](https://github.com/ai-sound-design/ai-services): one `docker compose up` on a machine with an NVIDIA GPU, plus the contract each service must fulfil if you want to write your own.
2. **Plugin.** Build it and set up its embedded Python runtime:
   - [`aax-plugin/README.md`](aax-plugin/README.md): embedded Python runtime for the plugin; see also [`aax-plugin/EMBEDDED_PYTHON_SETUP.md`](aax-plugin/EMBEDDED_PYTHON_SETUP.md) and [`aax-plugin/MAC_BUILD_GUIDE.md`](aax-plugin/MAC_BUILD_GUIDE.md)
   - Signing: the Pro Tools Developer Build loads the unsigned plugin; the regular Pro Tools only loads plugins signed with PACE's `wraptool`. [`aax-plugin/sign_aax_windows.ps1`](aax-plugin/sign_aax_windows.ps1) and [`aax-plugin/sign_aax_mac.sh`](aax-plugin/sign_aax_mac.sh) do that after each build; they need the PACE Code Signing For AAX SDK, the "PACE Tools" licence on a plugged-in iLok and your iLok account and wrap-configuration GUID in `ILOK_ACCOUNT` and `PACE_WCGUID` (details in the Mac build guide, [Step 3](aax-plugin/MAC_BUILD_GUIDE.md#step-3-sign-plugin-with-pace)).
   - Installer (Windows): [`aax-plugin/build_installer_windows.ps1`](aax-plugin/build_installer_windows.ps1) packs the signed bundle into one setup `.exe` (Inno Setup 6, `winget install JRSoftware.InnoSetup`) that installs the plugin into Pro Tools' plug-in folder on any machine, replacing an older version; the Mac counterpart is [`aax-plugin/create_installer_mac.sh`](aax-plugin/create_installer_mac.sh). Without an installer, copy the bundle into `C:\Program Files\Common Files\Avid\Audio\Plug-Ins` (Windows) or `/Library/Application Support/Avid/Audio/Plug-Ins` (macOS) with Pro Tools closed.
3. **Connect them.** With the backend on the same machine nothing needs configuring; otherwise see [Connecting the Plugin to Your Backend](#connecting-the-plugin-to-your-backend) and, for a backend behind Cloudflare Access, [`cloudflared/documentation.md`](cloudflared/documentation.md).

## Connecting the Plugin to Your Backend

The plugin is not tied to a particular model. It knows four kinds of service (generation, search, spotting, hybrid) and, for each kind, an **adapter profile**: one JSON file per backend in

- Windows: `%APPDATA%\AI Sound Design\adapters\`
- macOS: `~/Library/AI Sound Design/adapters/`

Every profile in that folder appears in the plugin's **Backend** list of its mode and in the **Settings** dialog, with a Test button, an *Open Adapter Folder* button and the profile's editable settings: the lengths a generation backend accepts, and for a hybrid backend the pieces per 10 s, the maximum number of database tracks and the minimum similarity. On first use the folder is filled with profiles for the reference stack on `localhost`: MMAudio (port 8000), HunyuanVideo-Foley (8001), sound search (8002), spotting (8003) and hybrid (8004); a shipped default that still carries its default name learns new capabilities of a newer plugin on start, without touching its address.

A generation profile describes where the service runs and how the request is built, so a new model is a new file, not a new plugin build:

```json
{
  "name": "MMAudio (local)",
  "kind": "generation",
  "base_url": "http://localhost:8000",
  "base_url_tunnel": "",
  "health": "/health",
  "request": {
    "endpoint": "/generate",
    "video_field": "video",
    "fields": { "prompt": "{prompt}", "negative_prompt": "{negative_prompt}",
                "seed": "{seed}", "duration": "{duration?}", "model_name": "large_44k_v2" }
  },
  "response": { "kind": "audio_file" },
  "supports": ["negative_prompt", "seed", "duration", "text_only"],
  "duration": { "min": 4, "max": 12, "default": 8 }
}
```

Field values are templates (`{prompt}`, `{negative_prompt}`, `{seed}`, `{duration}`; a trailing `?` makes the field optional; a seed of -1 in the plugin is replaced by a random one before sending), the answer is either the audio itself or JSON naming where to fetch it, `supports` decides which parameter rows the plugin enables, and `duration` states the lengths in seconds the backend accepts: the plugin offers them in its T2A list below *Auto* (the marked range, raised to the minimum when it is shorter, refused when it is longer) and skips clips outside them. Search and spotting profiles carry the address; their request shape is the plugin's own. A search profile may add constant fields, which is how the backend's sound libraries become entries in the Backend list, one profile per library:

```json
{ "name": "My recordings", "kind": "search", "base_url": "http://localhost:8002",
  "health": "/health", "protocol": "ai-sound-design-search-v1",
  "request": { "fields": { "library": "mine" } } }
```

A hybrid profile lists `memory_locations` in `supports` when the backend accepts the events the plugin found in the session and `database_match` when it can answer library recordings for each generated sound; its `match` block holds the settings the plugin edits in Settings and sends along:

```json
{ "name": "Hybrid (local)", "kind": "hybrid", "base_url": "http://localhost:8004",
  "health": "/health", "protocol": "ai-sound-design-hybrid-v1",
  "request": { "endpoint": "/hybrid", "video_field": "video",
               "fields": { "prompt": "{prompt?}", "negative_prompt": "{negative_prompt?}", "seed": "{seed}" } },
  "response": { "kind": "json", "sounds_field": "sounds", "audio_url_field": "audio_url" },
  "supports": ["negative_prompt", "seed", "memory_locations", "database_match"],
  "match": { "pieces_per_10s": 3, "min_piece_seconds": 2, "layers": 1, "text_weight": 0.0, "min_similarity": 0.5,
             "ambience_handle_seconds": 10, "tracks_per_scene": 8, "fade_preset": "AI Sound Design", "fade_seconds": 1 } }
```

While a spotting or hybrid run waits for its backend, the companion polls the backend's optional progress endpoint (`/spot/progress/{job_id}`, `/hybrid/progress/{job_id}`) and the plugin shows the fraction and text it reports; a backend without one gets a busy bar.

The format is documented in [`companion/api/adapters.py`](companion/api/adapters.py); the backend, its services and how to index sound libraries live in the separate [ai-services repository](https://github.com/ai-sound-design/ai-services).

The selected profile per kind, the Cloudflare Access credentials and a few plugin options live in the shared `config.json` next to the folder. With `use_cloudflared` on, each profile's `base_url_tunnel` is used instead of `base_url`; see [`cloudflared/documentation.md`](cloudflared/documentation.md) for the tunnel setup. The companion CLI tools accept `--adapter <file>` and `--api-url` to override the configuration for a single call.

## Status

This repository contains a research prototype developed in the context of a research project.
It is not intended as a production-ready tool.

## Upstream Models & Repositories

- MMAudio (video-conditioned audio generation): [github.com/hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio)
- HunyuanVideo-Foley: [github.com/Tencent-Hunyuan/HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley)
- X-CLIP (retrieval by video or text): [huggingface.co/microsoft/xclip-base-patch32](https://huggingface.co/microsoft/xclip-base-patch32)
- CLAP (retrieval by sound): [huggingface.co/laion/clap-htsat-fused](https://huggingface.co/laion/clap-htsat-fused)
- Gemma 4 via Ollama (spotting): [ollama.com/library/gemma4](https://ollama.com/library/gemma4)

## License

The code in this repository is licensed under the [MIT License](LICENSE).
Third-party components are **not** covered by it and keep their own terms:

| Component | Terms | Included here |
|-----------|-------|---------------|
| [JUCE 8](https://juce.com/legal/juce-8-licence/) (`external/JUCE`) | AGPLv3 or commercial JUCE licence | Git submodule |
| AAX SDK (Avid) | Proprietary, requires an Avid developer account | No, obtained separately |
| [py-ptsl](https://github.com/iluvcapra/py-ptsl) (`external/py-ptsl`) | BSD-3-Clause | Git submodule |
| [MMAudio](https://github.com/hkchengrex/MMAudio) | MIT | No, used by the backend |
| [HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley) | Tencent Hunyuan Community License | No, optional backend model |
| [X-CLIP](https://huggingface.co/microsoft/xclip-base-patch32) | MIT | No, downloaded at runtime |
| [CLAP](https://huggingface.co/laion/clap-htsat-fused) | Apache-2.0 | No, used by the backend |
| Gemma 4 via [Ollama](https://ollama.com) | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | No, used by the backend |

Note that the plugin links against JUCE: distributing a compiled plugin binary requires complying with the AGPLv3 or holding a commercial JUCE licence. The MIT license above applies to this repository's own source code only.

## Data

This project integrates with the **BBC Sound Effects Archive** for research-only search/retrieval. **No BBC audio or metadata are included in this repository**. Users must obtain any BBC content under the BBC's licensing terms:

- Archive: https://sound-effects.bbcrewind.co.uk/
- License: https://sound-effects.bbcrewind.co.uk/licensing

## Author

Anonymized for peer review.
