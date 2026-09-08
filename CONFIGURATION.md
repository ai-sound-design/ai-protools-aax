# Configuration Guide

## Overview

Both APIs (MMAudio and HunyuanVideo-Foley) now use a **shared configuration system** via `shared/config.py`. This ensures consistency and simplifies deployment.

## Configuration Methods

### 1. Environment Variables (Recommended)

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
nano .env
```

### 2. Docker Environment

Add to your `docker-compose.yml`:

```yaml
services:
  mmaudio-api:
    environment:
      - API_PORT=8000
      - VIDEO_CACHE_MAX_GB=32
      - VIDEO_CACHE_TTL_MIN=60
      - FORCE_DEVICE=cuda
      - FORCE_DTYPE=bfloat16
```

### 3. System Environment

```bash
export VIDEO_CACHE_MAX_GB=64
export VIDEO_CACHE_TTL_MIN=120
python standalone-API/main.py
```

## Configuration Options

### API Server

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `0.0.0.0` | Host to bind the API server |
| `API_PORT` | `8000` (MMAudio)<br>`8001` (HunyuanVideo-Foley) | Port for the API server |
| `LOG_LEVEL` | `info` | Logging level (debug, info, warning, error) |

### Cache System

| Variable | Default | Description |
|----------|---------|-------------|
| `VIDEO_CACHE_MAX_GB` | `32` | Maximum size of video cache in GB |
| `VIDEO_CACHE_TTL_MIN` | `60` | Time-to-live for cached videos (minutes) |
| `VIDEO_FRAME_CHECK` | `false` | Enable frame validation (has performance impact) |

### Device & Precision

| Variable | Default | Description |
|----------|---------|-------------|
| `FORCE_DEVICE` | `auto` | Force device: `cuda`, `mps`, `cpu`, or `auto` |
| `FORCE_DTYPE` | `bfloat16` | Force dtype: `float32`, `bfloat16`, `float16`, or `auto` |

### Model Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `MMAUDIO_PATH` | `/workspace/model-tests/repos/MMAudio` | Path to MMAudio repository |
| `HYVF_PATH` | `/workspace/model-tests/repos/HunyuanVideo-Foley` | Path to HunyuanVideo-Foley repository |
| `HYVF_WEIGHTS_PATH` | `/workspace/model-tests/models/HunyuanVideo-Foley` | Path to HunyuanVideo-Foley weights |

### Performance

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOW_TF32` | `true` | Allow TF32 acceleration (NVIDIA Ampere+) |
| `ENABLE_TRACEMALLOC` | `true` | Enable memory profiling |
| `LOG_BUFFER_SIZE` | `500` | Number of log entries to keep in memory |

## Examples

### High-Memory Server

```bash
export VIDEO_CACHE_MAX_GB=128
export VIDEO_CACHE_TTL_MIN=180
```

### CPU-Only Testing

```bash
export FORCE_DEVICE=cpu
export FORCE_DTYPE=float32
```

### Production Deployment

```bash
export VIDEO_CACHE_MAX_GB=64
export VIDEO_CACHE_TTL_MIN=120
export LOG_LEVEL=warning
export ENABLE_TRACEMALLOC=false
```

### Development/Debugging

```bash
export VIDEO_FRAME_CHECK=true
export LOG_LEVEL=debug
export ENABLE_TRACEMALLOC=true
```

## Docker Compose Example

```yaml
version: '3.8'

services:
  mmaudio-api:
    build: ./standalone-API
    environment:
      - API_PORT=8000
      - VIDEO_CACHE_MAX_GB=32
      - VIDEO_CACHE_TTL_MIN=60
      - FORCE_DEVICE=cuda
      - LOG_LEVEL=info
    ports:
      - "8000:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  hunyuanvideo-foley-api:
    build: ./hunyuanvideo-foley-API
    environment:
      - API_PORT=8001
      - VIDEO_CACHE_MAX_GB=32
      - VIDEO_CACHE_TTL_MIN=60
      - FORCE_DEVICE=cuda
      - LOG_LEVEL=info
    ports:
      - "8001:8001"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## Validation

The configuration is automatically validated on import. Invalid values will raise a `ValueError` with details.

## Migration from Old Configuration

**Old (hardcoded in main.py):**
```python
VIDEO_CACHE_MAX_GB = 32
device = 'cuda'
```

**New (environment variables):**
```bash
export VIDEO_CACHE_MAX_GB=32
export FORCE_DEVICE=cuda
```

All configurations are now centralized in `shared/config.py` and can be overridden via environment variables.
