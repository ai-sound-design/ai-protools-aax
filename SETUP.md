# Setup Guide — Generation Backends

This guide explains how to set up the two AI audio generation APIs on a new machine:

| API | Model | Port |
|-----|-------|------|
| MMAudio | [MMAudio](https://github.com/hkchengrex/MMAudio) | 8000 |
| HunyuanVideo-Foley | [HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley) | 8001 |

Both APIs accept a video file (and optional text prompt) and return generated audio.

---

## Prerequisites

Make sure the following are installed on the host machine before running setup:

| Requirement | Install guide |
|-------------|--------------|
| **NVIDIA GPU** (≥16 GB VRAM recommended) | — |
| **NVIDIA drivers** (≥535) | https://www.nvidia.com/drivers |
| **Docker** + **Docker Compose** (v2+) | https://docs.docker.com/engine/install |
| **NVIDIA Container Toolkit** | https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html |
| **git** | `apt install git` |

Verify Docker can see your GPU:
```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

---

## Directory Structure

The setup script will create the following layout relative to where `protools-aax/` lives:

```

<parent>/
├── protools-aax/               ← this repository
│   ├── Dockerfile
│   ├── docker-compose.generation.yml
│   ├── setup.sh
│   ├── standalone-API/          ← MMAudio FastAPI server
│   ├── hunyuanvideo-foley-API/  ← HunyuanVideo-Foley FastAPI server
│   └── shared/                  ← shared config
│
├── model-tests/
│   ├── repos/
│   │   ├── MMAudio/             ← cloned by setup.sh
│   │   └── HunyuanVideo-Foley/  ← cloned by setup.sh
│   └── models/
│       └── HunyuanVideo-Foley/  ← weights downloaded by setup.sh (~20 GB)
│
└── conda-envs/
    ├── mmaudio/                 ← Python env created by setup.sh
    └── hyvf/                    ← Python env created by setup.sh
```

Inside the Docker containers, `<parent>/` is mounted as `/workspace`.

---

## Quick Start

Clone the repository and run the setup script:

```bash
# 1. Clone this repo into any directory
git clone https://github.com/ai-sound-design/ai-protools-aax.git protools-aax
cd protools-aax

# 2. Run the automated setup
bash setup.sh          # Full stack (generation + sound search + DB + tunnel)
# or:
bash setup.sh --generation-only   # Generation APIs only (MMAudio + HYVF)
```

```bash
# 3. Start the services
docker compose -f docker-compose.full.yml up -d          # Full stack
# or:
docker compose -f docker-compose.generation.yml up -d    # Generation only
```

That's it. The APIs will start automatically.

---

## What setup.sh Does

**Always (steps 1–5):**

| Step | What happens |
|------|-------------|
| 1 | Creates `../model-tests/repos/`, `../model-tests/models/`, `../conda-envs/` |
| 2 | Clones MMAudio and HunyuanVideo-Foley repos |
| 3 | Builds the Docker image (`generation-api:latest`) |
| 4 | Creates `mmaudio` conda env (Python 3.11 + PyTorch + MMAudio) |
| 4 | Creates `hyvf` conda env (Python 3.10 + PyTorch + HunyuanVideo-Foley) |
| 5 | Downloads HunyuanVideo-Foley weights **inside the container** (~20 GB) |

**Full stack only (default, skip with `--generation-only`):**

| Step | What happens |
|------|-------------|
| 6 | Creates `.env` from `.env.example` if not present |
| 7 | Builds `sound-search-api:latest` Docker image |
| 8 | Checks cloudflared credentials — prints setup instructions if missing |
| 9 | Checks BBC sounds directory — warns if not found |
| 10 | Starts PostgreSQL, downloads DB dump (if `DB_DUMP_URL` is set), restores data |

No host-side `huggingface-cli` required — `setup.sh` installs and uses it inside the container.  
MMAudio weights (~4 GB) are downloaded automatically on the first API call.

---

## Verifying the Setup

After `docker compose ... up -d`, check both APIs are running:

```bash
curl http://localhost:8000/health   # MMAudio
curl http://localhost:8001/health   # HunyuanVideo-Foley
```

Expected response:
```json
{"status": "ok", "service": "MMAudio Standalone API", "device": "cuda", "version": "1.0.0"}
```

---

## Useful Commands

**Generation APIs only:**
```bash
docker compose -f docker-compose.generation.yml up -d        # Start
docker compose -f docker-compose.generation.yml down         # Stop
docker compose -f docker-compose.generation.yml logs -f      # Logs
docker compose -f docker-compose.generation.yml build        # Rebuild image
```

**Full stack:**
```bash
docker compose -f docker-compose.full.yml up -d        # Start all services
docker compose -f docker-compose.full.yml down         # Stop all
docker compose -f docker-compose.full.yml logs -f      # All logs
docker compose -f docker-compose.full.yml logs -f sound-search-api  # One service
```

**Shells:**
```bash
docker exec -it gen-mmaudio-api /bin/bash
docker exec -it gen-hyvf-api /bin/bash
docker exec -it gen-sound-search-api /bin/bash
docker exec -it gen-postgres psql -U bbc_user -d bbc_sounds
```

---

## Configuration

All settings can be overridden via environment variables. Edit `docker-compose.generation.yml`
and uncomment/add the relevant `environment:` entries:

| Variable | Default | Description |
|----------|---------|-------------|
| `MMAUDIO_PATH` | `/workspace/model-tests/repos/MMAudio` | Path to MMAudio repo inside container |
| `HYVF_PATH` | `/workspace/model-tests/repos/HunyuanVideo-Foley` | Path to HYVF repo inside container |
| `HYVF_WEIGHTS_PATH` | `/workspace/model-tests/models/HunyuanVideo-Foley` | Path to HYVF weights inside container |
| `FORCE_DEVICE` | `auto` | Force `cuda`, `cpu`, or `mps` |
| `FORCE_DTYPE` | `bfloat16` | Precision: `float32`, `bfloat16`, `float16` |
| `VIDEO_CACHE_MAX_GB` | `32` | Max RAM for video cache |
| `API_PORT` | `8000` / `8001` | Port the server listens on |

Full list: see [`CONFIGURATION.md`](./CONFIGURATION.md) and [`shared/config.py`](./shared/config.py).

---

## Troubleshooting

**"could not select device driver nvidia"**  
→ NVIDIA Container Toolkit is not installed or not configured for Docker.  
→ Follow: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

**"conda activate mmaudio: command not found"**  
→ The conda environment wasn't created. Re-run `bash setup.sh` — it will skip steps already done and retry the env creation.

**"No module named 'mmaudio'"**  
→ The MMAudio repo wasn't installed into the conda env. Inside the container:
```bash
conda run -n mmaudio pip install -e /workspace/model-tests/repos/MMAudio
```

**"No module named 'hunyuanvideo_foley'"**  
→ Same issue for HYVF:
```bash
conda run -n hyvf pip install -e /workspace/model-tests/repos/HunyuanVideo-Foley
```

**API returns 500 on first request (MMAudio)**  
→ MMAudio downloads its weights on the first call. This can take a few minutes. Check logs:
```bash
docker compose -f docker-compose.generation.yml logs -f mmaudio-api
```

**HunyuanVideo-Foley weights not found**  
→ Re-run `bash setup.sh` — step 5 will detect missing weights and download them.  
→ Or download manually inside the container:
```bash
docker exec -it gen-hyvf-api /bin/bash -c "
  source /opt/miniforge/etc/profile.d/conda.sh &&
  conda run -n hyvf pip install -q huggingface_hub &&
  conda run -n hyvf huggingface-cli download tencent/HunyuanVideo-Foley \
    --local-dir /workspace/model-tests/models/HunyuanVideo-Foley
"
```

---

## Full Stack — Additional Setup

### Cloudflared Tunnel

The stack uses a **dashboard-managed tunnel** with a connector token — no local credential files needed.

#### Step 1 — Create a tunnel (or migrate an existing one)

**New deployment:**
1. Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → Networks → Tunnels → **Create a tunnel**
2. Choose **Cloudflared**, give it a name (e.g. `my-thesis-apis`)
3. Under **Public Hostnames**, add your three services:
   | Subdomain | Domain | Service |
   |-----------|--------|---------|
   | `mmaudio` | your domain | `http://mmaudio-api:8000` |
   | `hyvf` | your domain | `http://hunyuanvideo-foley-api:8001` |
   | `sounds` | your domain | `http://sound-search-api:8002` |
4. On the **Install connector** page, copy the token (the `eyJ...` string at the end of the `docker run` command)

**Existing locally-managed tunnel** (created with `cloudflared tunnel create`):
1. Go to **Networks → Tunnels** → select your tunnel → **Migrate**
2. Confirm the migration — ingress rules are preserved, management moves to the dashboard
3. After migration, click **Configure → Set up a connector → Refresh token** to get a valid post-migration token

> ⚠️ Locally-managed tunnels use `cert.pem` + `UUID.json` and do **not** have a `TUNNEL_TOKEN`. You must migrate before the token approach works.

#### Step 2 — Add to `.env`

```bash
TUNNEL_TOKEN=eyJhIjoiNDU...the single-line token from the dashboard...
```

`setup.sh` (step 8) will check that the token is set and warn if it's missing.

> **Note:** `--protocol http2` is set in the compose command to force TCP/HTTP2 instead of QUIC/UDP. This avoids Docker container UDP buffer size limitations (QUIC requires ~7 MB, containers typically only get ~400 KB).

---

### BBC Sound Files

Point the stack at your local BBC sound archive:

```bash
# .env
BBC_SOUNDS_DIR=/absolute/path/to/your/bbc/sounds
```

Default (if not set): `../BBCSoundDownloader/sounds/` relative to `protools-aax/`.

The **sound search API works without sound files** — all embedding-based search runs from the database. Sound files are only needed for audio playback.

---

### Database (BBC Sound Archive)

**For new deployments — use a pre-built dump:**

1. Get the database dump URL (ask the project maintainer) and add to `.env`:
   ```bash
   # Direct link (GitHub Releases, etc.):
   DB_DUMP_URL=https://example.com/bbc_sounds.dump

   # Google Drive sharing link (paste as-is — setup.sh handles conversion):
   DB_DUMP_URL=https://drive.google.com/file/d/1ABC.../view?usp=sharing
   ```
2. Re-run `setup.sh` (step 10 will download and restore it automatically)

Or download manually and place at `db-dump/bbc_sounds.dump` — `setup.sh` will detect it and restore.

> **Google Drive note:** Share the file as "Anyone with the link → Viewer". `setup.sh` automatically extracts the file ID and uses the direct download endpoint, bypassing the virus-scan confirmation page.

**For maintainers — create a new dump from your running DB:**

```bash
docker exec -t gen-postgres \
    pg_dump -U bbc_user --data-only --no-owner -Fc bbc_sounds \
    > db-dump/bbc_sounds.dump
```

Upload to Google Drive (or GitHub Releases) and share the URL via `DB_DUMP_URL` in `.env`.

---

## Notes

- The conda environments (`mmaudio`, `hyvf`) are stored on the **host** in `../conda-envs/` and mounted into the container. This means they persist across Docker image rebuilds — you only need to create them once.
- If you update the `requirements.txt` files, re-run the pip install steps inside the container (no need to recreate the whole env).
- The APIs share the same Docker image (`generation-api:latest`) but run in separate containers with separate conda environments.
