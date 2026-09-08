#!/bin/bash
# ==============================================================================
# setup.sh — Script for protools-aax
#
# Usage:
#   bash setup.sh --generation-only   — Generation APIs only (MMAudio + HunyuanVideo-Foley)
#   bash setup.sh                     — Full stack (+ Sound Search API, PostgreSQL, Cloudflared)
#
# Generation-only steps (always run):
#   1. Create directory structure in parent directory
#   2. Clone MMAudio and HunyuanVideo-Foley repositories
#   3. Build the Docker image (generation-api)
#   4. Create 'mmaudio' and 'hyvf' conda environments inside the container
#   5. Download HunyuanVideo-Foley weights inside the container (~20 GB)
#
# Full stack additional steps (default, skipped with --generation-only):
#   6. Copy .env.example → .env (if .env doesn't exist)
#   7. Build the sound-search-api Docker image
#   8. Check cloudflared credentials (warns if missing)
#   9. Check BBC sounds directory (warns if missing)
#  10. Start PostgreSQL, download DB dump if needed, restore it
#
# After this completes:
#   Generation only:  docker compose -f docker-compose.generation.yml up -d
#   Full stack:       docker compose -f docker-compose.full.yml up -d
# ==============================================================================

set -e

# Parse arguments
FULL_STACK=true
for arg in "$@"; do
    case "$arg" in
        --generation-only) FULL_STACK=false ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
if [ "$FULL_STACK" = true ]; then
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            protools-aax — Full Stack Setup                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
else
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║      protools-aax — Generation Backend Setup               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "   Tip: run without --generation-only to set up the complete stack"
fi
echo ""
echo "  Repo:        $SCRIPT_DIR"
echo "  Parent dir:  $PARENT_DIR"
echo ""

# ==============================================================================
# STEP 1: Create directory structure
# ==============================================================================
echo "── Step 1: Creating directory structure"
mkdir -p "$PARENT_DIR/model-tests/repos"
mkdir -p "$PARENT_DIR/model-tests/models"
mkdir -p "$PARENT_DIR/conda-envs"
echo "   ✓ Directories ready"

# ==============================================================================
# STEP 2: Clone model repositories
# ==============================================================================
echo ""
echo "── Step 2: Cloning model repositories"

if [ -d "$PARENT_DIR/model-tests/repos/MMAudio/.git" ]; then
    echo "   ✓ MMAudio already cloned — skipping"
else
    echo "   Cloning MMAudio..."
    git clone https://github.com/hkchengrex/MMAudio.git \
        "$PARENT_DIR/model-tests/repos/MMAudio"
    echo "   ✓ MMAudio cloned"
fi

if [ -d "$PARENT_DIR/model-tests/repos/HunyuanVideo-Foley/.git" ]; then
    echo "   ✓ HunyuanVideo-Foley already cloned — skipping"
else
    echo "   Cloning HunyuanVideo-Foley..."
    git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley.git \
        "$PARENT_DIR/model-tests/repos/HunyuanVideo-Foley"
    echo "   ✓ HunyuanVideo-Foley cloned"
fi

# ==============================================================================
# STEP 3: Build generation-api Docker image
# ==============================================================================
echo ""
echo "── Step 3: Building Docker image (generation-api)"
cd "$SCRIPT_DIR"
docker compose -f docker-compose.generation.yml build
echo "   ✓ Docker image built"

# ==============================================================================
# STEP 4: Create conda environments inside the container
# ==============================================================================
echo ""
echo "── Step 4: Creating conda environments (this may take a few minutes)"

if [ -d "$PARENT_DIR/conda-envs/mmaudio" ]; then
    echo "   ✓ 'mmaudio' conda env already exists — skipping"
else
    echo "   Creating 'mmaudio' environment (Python 3.11 + PyTorch cu124)..."
    docker compose -f docker-compose.generation.yml run --rm mmaudio-api /bin/bash -c "
        set -e
        source /opt/miniforge/etc/profile.d/conda.sh
        mamba create -n mmaudio python=3.11 -y
        conda run -n mmaudio pip install \
            torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/cu124
        conda run -n mmaudio pip install -e /workspace/model-tests/repos/MMAudio
        conda run -n mmaudio pip install \
            -r /workspace/protools-aax/standalone-API/requirements.txt
        echo 'mmaudio environment OK'
    "
    echo "   ✓ 'mmaudio' environment created"
fi

if [ -d "$PARENT_DIR/conda-envs/hyvf" ]; then
    echo "   ✓ 'hyvf' conda env already exists — skipping"
else
    echo "   Creating 'hyvf' environment (Python 3.10 + PyTorch cu124)..."
    docker compose -f docker-compose.generation.yml run --rm hunyuanvideo-foley-api /bin/bash -c "
        set -e
        source /opt/miniforge/etc/profile.d/conda.sh
        mamba create -n hyvf python=3.10 -y
        conda run -n hyvf pip install \
            torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/cu124
        conda run -n hyvf pip install -e /workspace/model-tests/repos/HunyuanVideo-Foley
        conda run -n hyvf pip install \
            -r /workspace/protools-aax/hunyuanvideo-foley-API/requirements.txt
        echo 'hyvf environment OK'
    "
    echo "   ✓ 'hyvf' environment created"
fi

# ==============================================================================
# STEP 5: Download HunyuanVideo-Foley weights inside the container
# ==============================================================================
echo ""
echo "── Step 5: Checking HunyuanVideo-Foley model weights"

HYVF_WEIGHTS_DIR="$PARENT_DIR/model-tests/models/HunyuanVideo-Foley"
if [ -d "$HYVF_WEIGHTS_DIR" ] && [ -n "$(ls -A "$HYVF_WEIGHTS_DIR" 2>/dev/null)" ]; then
    echo "   ✓ HunyuanVideo-Foley weights already present — skipping"
else
    echo "   Downloading HunyuanVideo-Foley weights (~20 GB)..."
    echo "   (This may take a while depending on your connection)"
    docker compose -f docker-compose.generation.yml run --rm hunyuanvideo-foley-api /bin/bash -c "
        set -e
        source /opt/miniforge/etc/profile.d/conda.sh
        conda run -n hyvf pip install -q huggingface_hub
        conda run -n hyvf huggingface-cli download tencent/HunyuanVideo-Foley \
            --local-dir /workspace/model-tests/models/HunyuanVideo-Foley
        echo 'weights download OK'
    "
    echo "   ✓ Weights downloaded to $HYVF_WEIGHTS_DIR"
fi

echo "   ℹ  MMAudio weights auto-download on first API call (~4 GB)"

# ==============================================================================
# Cleanup generation setup containers
# ==============================================================================
echo ""
echo "── Cleanup: Removing generation setup containers"
docker rm -f gen-mmaudio-api gen-hyvf-api 2>/dev/null || true
echo "   ✓ Done"

# ==============================================================================
# ── FULL STACK STEPS (--full only) ──────────────────────────────────────────
# ==============================================================================
if [ "$FULL_STACK" = false ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    ✅ Setup complete!                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  Start the generation APIs:"
    echo "    docker compose -f docker-compose.generation.yml up -d"
    echo ""
    exit 0
fi

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "   Full Stack Setup"
echo "══════════════════════════════════════════════════════════════"

# ==============================================================================
# STEP 6: Copy .env if it doesn't exist
# ==============================================================================
echo ""
echo "── Step 6: Environment configuration"
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "   ✓ .env already exists — skipping"
else
    # Copy .env.example → .env, auto-uncommenting the required fields
    # so the user just replaces placeholder values (no '#' to remove)
    sed 's/^# TUNNEL_TOKEN=/TUNNEL_TOKEN=/' "$SCRIPT_DIR/.env.example" | \
        sed 's/^# DB_DUMP_URL=/DB_DUMP_URL=/' > "$SCRIPT_DIR/.env"
    echo "   ✓ Created .env from .env.example"
    echo ""
    echo "   ┌─────────────────────────────────────────────────────────────────┐"
    echo "   │  ⚠️  REQUIRED: edit .env before the stack will work             │"
    echo "   │                                                                 │"
    echo "   │  TUNNEL_TOKEN  — Cloudflare tunnel token                        │"
    echo "   │    Get it: Zero Trust → Networks → Tunnels                      │"
    echo "   │            → your tunnel → Configure → Token (copy it)          │"
    echo "   │    Set it:  TUNNEL_TOKEN=eyJ...                                 │"
    echo "   │                                                                 │"
    echo "   │  DB_DUMP_URL   — URL to the BBC Sound Archive database dump     │"
    echo "   │    Get it: from the project maintainer (Google Drive or direct) │"
    echo "   │    Set it:  DB_DUMP_URL=https://drive.google.com/file/d/...     │"
    echo "   │                                                                 │"
    echo "   │  BBC_SOUNDS_DIR (optional) — path to BBC .wav files             │"
    echo "   │    Default: ../BBCSoundDownloader/sounds                        │"
    echo "   └─────────────────────────────────────────────────────────────────┘"
    echo ""
    read -rp "   Press Enter to open .env in nano, or Ctrl+C to edit manually... "
    nano "$SCRIPT_DIR/.env"
fi

# Source .env for subsequent steps (strip comments and empty lines)
set -a
source <(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^[[:space:]]*$') 2>/dev/null || true
set +a

# ==============================================================================
# STEP 7: Build sound-search-api Docker image
# ==============================================================================
echo ""
echo "── Step 7: Building sound-search-api Docker image"
docker compose -f docker-compose.full.yml build sound-search-api
echo "   ✓ sound-search-api image built"

# ==============================================================================
# STEP 8: Check cloudflared credentials
# ==============================================================================
echo ""
echo "── Step 8: Checking cloudflared credentials"
CF_JSON=$(ls "$SCRIPT_DIR/cloudflared/"*.json 2>/dev/null | head -1)
if [ -n "${TUNNEL_TOKEN}" ]; then
    echo "   ✓ TUNNEL_TOKEN set — will use token-based auth"
elif [ -n "$CF_JSON" ] && [ -f "$SCRIPT_DIR/cloudflared/config.yml" ]; then
    echo "   ✓ Credentials file found: $(basename "$CF_JSON")"
    echo "   ✓ config.yml present"
else
    echo ""
    echo "   ⚠️  No cloudflared credentials found. Tunnel will not start."
    echo ""
    echo "   Option A — Token-based (recommended for new deployments):"
    echo "     1. Go to: Cloudflare Zero Trust → Access → Tunnels"
    echo "     2. Create/select a tunnel and copy its token"
    echo "     3. Add to .env:  TUNNEL_TOKEN=<your-token>"
    echo ""
    echo "   Option B — Credentials file (existing deployments):"
    echo "     1. Copy cloudflared/config.yml.example → cloudflared/config.yml"
    echo "     2. Edit with your tunnel name and UUID"
    echo "     3. Place <uuid>.json in cloudflared/"
    echo "     4. Run: cloudflared tunnel login  (saves cert.pem)"
    echo ""
fi

# ==============================================================================
# STEP 9: Check BBC sounds directory
# ==============================================================================
echo ""
echo "── Step 9: Checking BBC sounds directory"
BBC_DIR="${BBC_SOUNDS_DIR:-$PARENT_DIR/BBCSoundDownloader/sounds}"
if [ -d "$BBC_DIR" ] && [ -n "$(ls -A "$BBC_DIR" 2>/dev/null)" ]; then
    SOUND_COUNT=$(find "$BBC_DIR" -name "*.wav" 2>/dev/null | wc -l | tr -d ' ')
    echo "   ✓ BBC sounds found: $SOUND_COUNT .wav files"
    echo "     Path: $BBC_DIR"
else
    echo "   ⚠️  BBC sounds not found at: $BBC_DIR"
    echo "   Sound search queries will work but return no audio files."
    echo "   Set BBC_SOUNDS_DIR in .env if your sounds are elsewhere."
fi

# ==============================================================================
# STEP 10: PostgreSQL — start, download dump (if needed), restore
# ==============================================================================
echo ""
echo "── Step 10: Database setup (PostgreSQL + BBC Sound Archive)"

DB_DUMP="$SCRIPT_DIR/db-dump/bbc_sounds.dump"
mkdir -p "$SCRIPT_DIR/db-dump"

# Download dump if URL is set and file not present
if [ -f "$DB_DUMP" ]; then
    echo "   ✓ Database dump already at db-dump/bbc_sounds.dump"
elif [ -n "${DB_DUMP_URL}" ]; then
    echo "   Downloading database dump..."
    # Handle Google Drive URLs — two-step cookie-based download to bypass virus-scan
    if echo "${DB_DUMP_URL}" | grep -q "drive.google.com"; then
        GDRIVE_ID=$(echo "${DB_DUMP_URL}" | sed 's|.*/file/d/\([^/?]*\).*|\1|; s|.*[?&]id=\([^&]*\).*|\1|')
        GDRIVE_COOKIES=$(mktemp)
        echo "   (Google Drive detected — two-step download with virus-scan bypass)"
        # Step 1: seed session cookies
        curl -sc "$GDRIVE_COOKIES" \
            "https://drive.google.com/uc?id=${GDRIVE_ID}&export=download" \
            -o /dev/null 2>/dev/null
        # Step 2: actual download with cookies + confirm=t
        curl -Lb "$GDRIVE_COOKIES" --progress-bar \
            "https://drive.google.com/uc?id=${GDRIVE_ID}&export=download&confirm=t" \
            -o "$DB_DUMP"
        rm -f "$GDRIVE_COOKIES"
    else
        curl -L --progress-bar -o "$DB_DUMP" "${DB_DUMP_URL}"
    fi
    # Validate: reject HTML pages / empty files
    FILE_SIZE=$(stat -c%s "$DB_DUMP" 2>/dev/null || echo 0)
    if [ "$FILE_SIZE" -lt 100000 ]; then
        echo "   ✗ Download failed or returned HTML (${FILE_SIZE} bytes)."
        echo "   Ensure the Google Drive file is shared 'Anyone with the link → Viewer'."
        rm -f "$DB_DUMP"
        exit 1
    fi
    echo "   ✓ Download complete"
else
    echo "   ℹ  No database dump found (set DB_DUMP_URL in .env to auto-download)"
    echo "   PostgreSQL will start with an empty database."
fi

# Start postgres
cd "$SCRIPT_DIR"
echo "   Starting postgres..."
docker compose -f docker-compose.full.yml up -d postgres

# Wait for postgres to be healthy
echo -n "   Waiting for postgres..."
ATTEMPTS=0
until docker compose -f docker-compose.full.yml exec -T postgres \
        pg_isready -U bbc_user -d bbc_sounds &>/dev/null; do
    echo -n "."
    sleep 2
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ "$ATTEMPTS" -gt 30 ]; then
        echo " timed out!"
        echo "   ⚠️  Check logs: docker compose -f docker-compose.full.yml logs postgres"
        break
    fi
done
echo " ✓"

# Restore dump if available and DB is empty
if [ -f "$DB_DUMP" ]; then
    # Check if DB already has data
    SOUND_COUNT=$(docker compose -f docker-compose.full.yml exec -T postgres \
        psql -U bbc_user -d bbc_sounds -t -c "SELECT COUNT(*) FROM bbc_sounds;" \
        2>/dev/null | tr -d '[:space:]') || SOUND_COUNT="0"

    if [ "${SOUND_COUNT:-0}" -gt 0 ] 2>/dev/null; then
        echo "   ✓ Database already populated (${SOUND_COUNT} sounds) — skipping restore"
    else
        echo "   Restoring BBC Sound Archive (this may take a few minutes)..."
        POSTGRES_CID=$(docker compose -f docker-compose.full.yml ps -q postgres)
        docker cp "$DB_DUMP" "${POSTGRES_CID}:/tmp/bbc_sounds.dump"
        docker compose -f docker-compose.full.yml exec -T postgres \
            pg_restore -U bbc_user -d bbc_sounds --data-only --no-owner /tmp/bbc_sounds.dump
        docker compose -f docker-compose.full.yml exec -T postgres \
            rm /tmp/bbc_sounds.dump
        FINAL_COUNT=$(docker compose -f docker-compose.full.yml exec -T postgres \
            psql -U bbc_user -d bbc_sounds -t -c "SELECT COUNT(*) FROM bbc_sounds;" \
            2>/dev/null | tr -d '[:space:]') || FINAL_COUNT="?"
        echo "   ✓ Database restored (${FINAL_COUNT} sounds)"

        # Build IVFFlat vector indexes now that the table is populated.
        # Building on empty data produces meaningless cluster centroids, so we
        # do this AFTER the restore rather than in the db-init SQL.
        echo "   Building vector indexes (IVFFlat)..."
        docker compose -f docker-compose.full.yml exec -T postgres \
            psql -U bbc_user -d bbc_sounds -c "
                CREATE INDEX IF NOT EXISTS idx_text_emb
                    ON bbc_sounds USING ivfflat (text_embedding vector_cosine_ops)
                    WITH (lists = 100);
                CREATE INDEX IF NOT EXISTS idx_text_emb_large
                    ON bbc_sounds USING ivfflat (text_embedding_large vector_cosine_ops)
                    WITH (lists = 100);
            "
        echo "   ✓ Vector indexes built"
    fi
fi

# Stop postgres (will restart cleanly with 'up -d')
docker compose -f docker-compose.full.yml stop postgres

# ==============================================================================
# Done
# ==============================================================================
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ Full setup complete!                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Start the full stack:"
echo "    docker compose -f docker-compose.full.yml up -d"
echo ""
echo "  Health checks:"
echo "    curl http://localhost:8000/health   # MMAudio"
echo "    curl http://localhost:8001/health   # HunyuanVideo-Foley"
echo "    curl http://localhost:8002/health   # Sound Search"
echo ""
echo "  View logs:"
echo "    docker compose -f docker-compose.full.yml logs -f"
echo ""
echo "  Need to create a DB dump from your current data?"
echo "    docker exec gen-postgres \\"
echo "        pg_dump -U bbc_user --data-only --no-owner -Fc bbc_sounds \\"
echo "        > db-dump/bbc_sounds.dump"
echo "  Note: do NOT add -t (pseudo-TTY) — it corrupts binary (-Fc) output."
echo ""
