# BBC Sound Archive — Database Dump

This directory holds the PostgreSQL database dump for the BBC Sound Archive.

The dump contains all sound metadata and pre-computed X-CLIP embeddings (~100–400 MB).  
**It is not stored in the repository** — download it separately and place it here.

---

## Download

Set `DB_DUMP_URL` in your `.env` file and `setup.sh` will download it automatically:

```bash
# .env
DB_DUMP_URL=https://example.com/bbc_sounds.dump
```

Or download manually and place the file here:
```
db-dump/bbc_sounds.dump
```

---

## Creating a New Dump

If you have a running PostgreSQL container with data, create a dump with:

```bash
# Data-only dump (schema is managed by db-init/01-init.sql)
docker exec -t gen-postgres \
    pg_dump -U bbc_user --data-only --no-owner -Fc bbc_sounds \
    > db-dump/bbc_sounds.dump
```

---

## What's Included

- All BBC sound effect metadata (title, category, duration, file path)
- Pre-computed X-CLIP embeddings for audio + video similarity search
- `file_exists` flags reflecting available sound files

**Note:** The actual BBC audio `.wav` files are **not** included.  
Set `BBC_SOUNDS_DIR` in `.env` to point to your local sound archive.  
The sound search API works without the files — only audio playback requires them.
