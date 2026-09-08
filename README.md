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

### 1. Audio Generation
https://github.com/user-attachments/assets/cbe2bbf0-ac58-4ff3-87b1-0d0e45d20e33

### 2. Sound Recommendation
https://github.com/user-attachments/assets/05d01e95-872f-4549-a6ed-f4d72c6ab3d3

### 3. Spotting Support
https://github.com/user-attachments/assets/4fcb9db9-5133-450c-b541-a01176fe2abb

## What This Project Does

The project enables three AI support workflows inside Pro Tools:

1. **Audio Generation:** Generates sound for a selected scene segment from video and an optional text prompt, then inserts the result into the timeline.
2. **Sound Recommendation:** Retrieves candidate sounds from a searchable library based on video, text, or hybrid queries.
3. **Spotting Support:** Creates marker-based event suggestions to support spotting in predefined study scenes used for prototype evaluation (Wizard-of-Oz).

## Repository Structure

```text
protools-aax/                       # Clone directory (scripts and compose files expect this name)
├── aax-plugin/                     # JUCE AAX plugin project, installers, build scripts
├── companion/                      # Shared Python integration and utility modules
├── standalone-API/                 # MMAudio API service
├── hunyuanvideo-foley-API/         # HunyuanVideo-Foley API service
├── sound-search-API/               # X-CLIP + pgvector retrieval API
├── shared/                         # Shared configuration helpers
├── db-init/                        # Database schema initialization scripts
├── db-dump/                        # Placeholder for the database dump (not stored in Git)
├── cloudflared/                    # Cloudflare Tunnel configuration and documentation
├── external/                       # Third-party code as Git submodules (JUCE, py-ptsl)
├── Dockerfile                      # Base image for the generation APIs
├── docker-compose.generation.yml   # Generation APIs only
├── docker-compose.full.yml         # Full stack: generation + sound search + database + tunnel
├── setup.sh                        # Automated backend setup
├── SETUP.md                        # Backend setup guide
├── CONFIGURATION.md                # Central configuration reference
└── .env.example                    # Environment variable template
```

## Architecture at a Glance

1. User selects a video clip in Pro Tools (+ optional text input in the plugin).
2. AAX plugin calls Python helper scripts bundled in plugin resources.
3. Helper scripts communicate with one or more backend APIs.
4. Generated audio or search results are returned.
5. Plugin inserts or references results in the Pro Tools session.

## System Overview

The repository is split into a plugin layer and multiple backend services.
Note that the backend services were hosted on a university server for the duration of the research project and are not available anymore.
To use the plugin, you have to reproduce or adapt the backend infrastructure (see [Setup](#setup)).

- AAX plugin
  - JUCE-based AAX plugin for Pro Tools
  - Handles timeline interaction, user actions, and API calls
  - Embeds Python runtime and helper scripts for integration workflows

- Companion tooling
  - Shared Python modules for Pro Tools integration, API clients, CLI, and video preprocessing

- AI generation services
  - MMAudio API for video-conditioned audio generation
  - HunyuanVideo-Foley API as an alternative

- Retrieval service
  - Sound Search API (X-CLIP + pgvector/PostgreSQL)
  - Supports text/video similarity search on BBC sound metadata

## Setup

This repository contains multiple backend services and a Pro Tools AAX plugin. Start here:

- [`SETUP.md`](SETUP.md): backend setup via Docker Compose (generation APIs, sound search, database, tunnel)
- [`CONFIGURATION.md`](CONFIGURATION.md): environment variables and configuration reference
- [`aax-plugin/README.md`](aax-plugin/README.md): embedded Python runtime for the plugin; see also [`aax-plugin/EMBEDDED_PYTHON_SETUP.md`](aax-plugin/EMBEDDED_PYTHON_SETUP.md) and [`aax-plugin/MAC_BUILD_GUIDE.md`](aax-plugin/MAC_BUILD_GUIDE.md)
- [`standalone-API/README.md`](standalone-API/README.md): MMAudio API
- [`sound-search-API/README.md`](sound-search-API/README.md): Sound Search API
- [`db-init/README.md`](db-init/README.md) and [`db-dump/README.md`](db-dump/README.md): database schema and data dump
- [`companion/database/README_EMBEDDINGS.md`](companion/database/README_EMBEDDINGS.md): generating X-CLIP embeddings for the sound archive
- [`cloudflared/documentation.md`](cloudflared/documentation.md): tunnel access and companion client configuration

## Connecting the Plugin to Your Backend

By default, the plugin and the companion scripts expect all backend services on `localhost`: MMAudio on port 8000, HunyuanVideo-Foley on port 8001, and Sound Search on port 8002.
To point them at another machine or at a Cloudflare Tunnel, edit the shared configuration file, which is created with these defaults on first run:

- Windows: `%APPDATA%\PTV2A\config.json`
- macOS: `~/Library/PTV2A/config.json`

For each service, `api_url_direct` is used while `use_cloudflared` is `false`, and `api_url_cloudflared` once it is `true`.
Cloudflare Access credentials can be entered via the **API Settings** button in the plugin or written into the same file.
The companion CLI tools accept `--api-url` to override the configured URL for a single call.
See [`companion/api/config.sample.json`](companion/api/config.sample.json) for the full structure and [`cloudflared/documentation.md`](cloudflared/documentation.md) for the tunnel setup.

## Status

This repository contains a research prototype developed in the context of a research project.
It is not intended as a production-ready tool.

## Upstream Models & Repositories

- MMAudio (video-conditioned audio generation): [github.com/hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio)
- HunyuanVideo-Foley: [github.com/Tencent-Hunyuan/HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley)
- X-CLIP (retrieval backbone): [huggingface.co/microsoft/xclip-base-patch32](https://huggingface.co/microsoft/xclip-base-patch32)

## License

The code in this repository is licensed under the [MIT License](LICENSE).
Third-party components are **not** covered by it and keep their own terms:

| Component | Terms | Included here |
|-----------|-------|---------------|
| [JUCE 8](https://juce.com/legal/juce-8-licence/) (`external/JUCE`) | AGPLv3 or commercial JUCE licence | Git submodule |
| AAX SDK (Avid) | Proprietary, requires an Avid developer account | No, obtained separately |
| [py-ptsl](https://github.com/iluvcapra/py-ptsl) (`external/py-ptsl`) | BSD-3-Clause | Git submodule |
| [MMAudio](https://github.com/hkchengrex/MMAudio) | MIT | No, cloned by `setup.sh` |
| [HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley) | Tencent Hunyuan Community License | No, cloned by `setup.sh` |
| [X-CLIP](https://huggingface.co/microsoft/xclip-base-patch32) | MIT | No, downloaded at runtime |

Note that the plugin links against JUCE: distributing a compiled plugin binary requires complying with the AGPLv3 or holding a commercial JUCE licence. The MIT license above applies to this repository's own source code only.

## Data

This project integrates with the **BBC Sound Effects Archive** for research-only search/retrieval. **No BBC audio or metadata are included in this repository**. Users must obtain any BBC content under the BBC's licensing terms:

- Archive: https://sound-effects.bbcrewind.co.uk/
- License: https://sound-effects.bbcrewind.co.uk/licensing

## Author

Anonymized for peer review.
