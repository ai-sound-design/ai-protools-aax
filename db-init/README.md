# BBC Sound Archive Database Initialization

This directory contains SQL scripts that are automatically executed when the PostgreSQL container starts for the first time.

## Files

- `01-init.sql` - Creates database schema, tables, indexes, and views

## Execution Order

Scripts are executed in alphabetical order by PostgreSQL's `docker-entrypoint-initdb.d`.

## Schema Overview

### Table: `bbc_sounds`
Main table storing BBC Sound Archive metadata and embeddings.

**Columns:**
- `id` - Auto-incrementing primary key
- `location` - Unique filename (e.g., "07067001.wav")
- `description` - Sound description from CSV
- `cdname` - Category/CD name
- `duration_seconds` - Duration from CSV
- `file_path` - Relative path to audio file
- `file_exists` - Whether file was found during import
- `audio_embedding` - Audio encoder embeddings (vector)
- `search_vector` - Full-text search (auto-generated)

### Views

- `sound_stats` - Overall database statistics
- `category_stats` - Statistics per category

## After Container Start

1. Import CSV data: `python import_bbc_sounds.py`
2. Generate embeddings: `python generate_embeddings.py`
3. Create vector indexes (uncomment in `01-init.sql`)

## Connection Info

```bash
Host: localhost
Port: 5432
Database: bbc_sounds
User: bbc_user
Password: <set-via-env-or-local-secret>
```

```python
# Python connection
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="bbc_sounds",
    user="bbc_user",
    password="<set-via-env-or-local-secret>"
)
```
