-- BBC Sound Archive Database Initialization
-- Auto-executed by PostgreSQL on first container start
--
-- Schema matches the production database exactly.
-- IVFFlat vector indexes are created by setup.sh AFTER the data dump is
-- restored — building them on an empty table would yield meaningless centroids.

-- Enable pgvector extension for embedding storage and similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Main table ───────────────────────────────────────────────────────────────
CREATE TABLE bbc_sounds (
    id              SERIAL PRIMARY KEY,

    -- Metadata from the BBC Sound Archive CSV
    location        VARCHAR(255) UNIQUE NOT NULL,  -- original filename, e.g. "07067001.wav"
    description     TEXT NOT NULL,                 -- e.g. "Heavy rain on leaves"
    cdname          VARCHAR(255),                  -- CD/category name, e.g. "Weather"
    cdnumber        VARCHAR(50),                   -- e.g. "BBC Sound Effects No.1"
    category        VARCHAR(255),                  -- fine-grained category
    tracknum        INTEGER,                       -- track number on CD

    duration_seconds DOUBLE PRECISION,

    -- File tracking
    file_path       TEXT NOT NULL,                 -- absolute host path to .wav file
    file_exists     BOOLEAN DEFAULT FALSE,

    -- Embeddings (NULL until generated)
    embedding            vector(512),              -- audio embedding (X-CLIP base)
    text_embedding       vector(512),              -- text embedding (X-CLIP base, 512-dim)
    text_embedding_large vector(768),              -- text embedding (X-CLIP large, 768-dim)

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Scalar indexes ────────────────────────────────────────────────────────────
CREATE INDEX idx_bbc_sounds_category    ON bbc_sounds (category);
CREATE INDEX idx_bbc_sounds_file_exists ON bbc_sounds (file_exists);

-- ── Vector indexes ────────────────────────────────────────────────────────────
-- Created by setup.sh AFTER the dump is restored so IVFFlat centroids are
-- computed on real data.  To build manually after populating the table:
--
--   CREATE INDEX idx_text_emb ON bbc_sounds
--       USING ivfflat (text_embedding vector_cosine_ops) WITH (lists = 100);
--   CREATE INDEX idx_text_emb_large ON bbc_sounds
--       USING ivfflat (text_embedding_large vector_cosine_ops) WITH (lists = 100);

-- ── Views ─────────────────────────────────────────────────────────────────────
-- Sounds that exist on disk — used by the sound-search API for all queries
CREATE VIEW available_sounds AS
    SELECT id, location, description, cdname, cdnumber, category, tracknum,
           duration_seconds, file_path, file_exists,
           embedding, created_at, text_embedding, text_embedding_large
    FROM bbc_sounds
    WHERE file_exists = TRUE;

-- Per-category statistics
CREATE VIEW category_stats AS
    SELECT
        cdname,
        COUNT(*)                                            AS total_sounds,
        COUNT(*) FILTER (WHERE file_exists = TRUE)         AS available_sounds,
        SUM(duration_seconds) FILTER (WHERE file_exists = TRUE)
                                                            AS total_duration_seconds,
        AVG(duration_seconds)                               AS avg_duration_seconds
    FROM bbc_sounds
    GROUP BY cdname
    ORDER BY available_sounds DESC;

-- Database-wide statistics (exposed via /stats endpoint)
CREATE VIEW sound_stats AS
    SELECT
        COUNT(*)                                             AS total_sounds,
        COUNT(*) FILTER (WHERE file_exists = TRUE)          AS available_sounds,
        COUNT(*) FILTER (WHERE file_exists = FALSE)         AS missing_sounds,
        SUM(duration_seconds) FILTER (WHERE file_exists = TRUE) / 3600.0
                                                             AS total_hours_available,
        COUNT(DISTINCT cdname)                               AS unique_categories,
        AVG(duration_seconds)                                AS avg_duration_seconds
    FROM bbc_sounds;

-- ── Permissions ───────────────────────────────────────────────────────────────
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO bbc_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO bbc_user;

DO $$
BEGIN
    RAISE NOTICE 'BBC Sound Archive database initialised.';
    RAISE NOTICE 'IVFFlat vector indexes will be created by setup.sh after data restore.';
END $$;
