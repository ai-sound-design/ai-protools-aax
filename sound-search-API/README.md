# BBC Sound Search API

X-CLIP based video/text to sound retrieval service for BBC Sound Archive.

## Features

- **Video Search**: Upload video clips to find matching BBC sound effects
- **Text Search**: Search by text description
- **Vector Similarity**: Uses X-CLIP embeddings for semantic matching
- **PostgreSQL Backend**: Fast vector search with pgvector extension

## API Endpoints

### `POST /search/sounds`
Search for sounds by video or text.

**Parameters:**
- `video` (file, optional): Video file to search with
- `text` (string, optional): Text query
- `limit` (int, default=10): Maximum results to return
- `threshold` (float, default=0.0): Minimum similarity score (0-1)

**Example:**
```bash
# Text search
curl -X POST http://localhost:8002/search/sounds \
  -F "text=footsteps on gravel" \
  -F "limit=10"

# Video search
curl -X POST http://localhost:8002/search/sounds \
  -F "video=@myvideo.mp4" \
  -F "limit=10"
```

### `GET /sounds/{id}`
Get metadata for a specific sound.

### `GET /sounds/{id}/download`
Download the audio file.

### `GET /sounds/{id}/preview`
Stream a preview (first 5 seconds).

### `GET /stats`
Get database statistics.

### `GET /categories`
List available sound categories.

### `GET /health`
Health check endpoint.

## Environment Variables

- `DATABASE_URL`: PostgreSQL connection URL (default: `postgresql://bbc_user:change_me@postgres:5432/bbc_sounds`)
- `BBC_SOUNDS_PATH`: Path to BBC sound files (default: `/sounds`)
- `XCLIP_MODEL`: X-CLIP model name (default: `microsoft/xclip-base-patch32`)

## Setup

1. Ensure PostgreSQL with pgvector is running
2. Generate text embeddings: `python ../companion/generate_embeddings.py`
3. Build and run:
```bash
docker-compose up -d sound-search-api
```

## Dependencies

- PyTorch 2.5+
- Transformers (Hugging Face)
- FastAPI
- PostgreSQL with pgvector
- PyAV for video processing
