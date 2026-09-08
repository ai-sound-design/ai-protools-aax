# BBC Sound Archive - Embedding Generation

## Generate X-CLIP Text Embeddings

This script generates text embeddings for all BBC Sound Archive descriptions using X-CLIP.

### Prerequisites

1. PostgreSQL database running with BBC sounds imported
2. `db-tools` conda environment active
3. GPU available (recommended) or CPU

### Installation

```bash
# Activate db-tools environment
conda activate db-tools

# Install additional dependencies
pip install torch torchvision transformers
```

### Usage

```bash
# With GPU (recommended)
python generate_embeddings.py

# With CPU (slower)
DEVICE=cpu python generate_embeddings.py

# Custom model
XCLIP_MODEL=microsoft/xclip-large-patch14 python generate_embeddings.py
```

### What it does

1. Loads X-CLIP text encoder (microsoft/xclip-base-patch32 by default)
2. Fetches all sound descriptions from `available_sounds` view
3. Generates embeddings in batches of 32
4. Updates `text_embedding` column in database
5. Creates vector index for fast similarity search

### Performance

- **GPU**: ~3-4 seconds for all 3,594 sounds
- **CPU**: ~30-60 seconds for all 3,594 sounds
- **Batch size**: 32 descriptions per batch
- **Embedding size**: 512 dimensions

### Output

```
============================================================
BBC Sound Archive - Text Embedding Generation
============================================================

Connecting to database...
✓ Database connected
Fetching sounds from database...
Found 3594 sounds to encode

Loading X-CLIP model: microsoft/xclip-base-patch32
Device: cuda
✓ X-CLIP model loaded
Embedding dimension: 512

Processing in batches of 32...
============================================================
Progress: 32/3594 (0.9%)
Progress: 64/3594 (1.8%)
...
Progress: 3594/3594 (100.0%)
============================================================
✓ Processed 3594 sounds

Creating vector index for fast search...
✓ Vector index created

============================================================
COMPLETED!
============================================================
Total sounds encoded: 3594
Embedding dimension: 512
Time elapsed: 3.2 seconds (0.1 minutes)
Average: 0.00 seconds per sound

✓ Database ready for vector search!
✓ You can now use the sound-search-API
============================================================
```

### Troubleshooting

**ImportError: No module named 'transformers'**
```bash
conda activate db-tools
pip install transformers torch
```

**CUDA out of memory**
```bash
# Reduce batch size
BATCH_SIZE=16 python generate_embeddings.py

# Or use CPU
DEVICE=cpu python generate_embeddings.py
```

**Database connection failed**
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Check connection
psql -h localhost -U bbc_user -d bbc_sounds
```
