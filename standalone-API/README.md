# MMAudio Standalone API

## Quick Start

### 1. Install Dependencies

```bash
cd /path/to/protools-aax/standalone-API
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start the API Server

```bash
python main.py
```

The API will be available at `http://localhost:8000`

### 3. Test the API

```bash
# Check if API is running
curl http://localhost:8000/

# List available models
curl http://localhost:8000/models

# Generate audio from video
curl -X POST "http://localhost:8000/generate" \
  -F "video=@/path/to/video.mp4" \
  -F "prompt=waves crashing on the beach" \
  -F "seed=42" \
  --output generated_audio.wav
```

## API Endpoints

### `GET /`

Health check endpoint

### `GET /models`

List available MMAudio models and currently loaded models

### `POST /cache/stats`

View Cache stats (RAM, VRAM, ...)

### `POST /generate`

Generate audio from video

### `GET /cache/stats`

Detailed cache statistics and memory usage

### `POST /cache/clear`

Clear video cache (preserve models)

### `POST /cache/clear-all`

Full cache reset including models

**Parameters:**

- `video` (file): Video file to process
- `prompt` (string): Text description of desired audio
- `negative_prompt` (string, optional): What to avoid in audio
- `seed` (int, default=42): Random seed for reproducible results
- `duration` (float, optional): Duration in seconds (auto-detected if not provided)
- `model_name` (string, default="large_44k_v2"): MMAudio model to use
- `num_steps` (int, default=25): Number of diffusion steps
- `cfg_strength` (float, default=4.5): Classifier-free guidance strength

**Returns:** flac audio file

## Configuration

Edit the `MMAUDIO_PATH` variable in `main.py` to point to your MMAudio installation:

```python
MMAUDIO_PATH = Path("/path/to/your/MMAudio")
```

## Example Client Code

```python
import requests

# Generate audio from video
with open("video.mp4", "rb") as f:
    response = requests.post(
        "http://localhost:8000/generate",
        files={"video": f},
        data={
            "prompt": "ocean waves and seagulls",
            "negative_prompt": "music, voices",
            "seed": 123,
            "duration": 8.0
        }
    )

# Save generated audio
with open("output.wav", "wb") as f:
    f.write(response.content)

print(f"Generation time: {response.headers.get('X-Generation-Time')}s")
```

## Development

The API is structured for easy extension:

- `main.py` - Main API server
- `requirements.txt` - Python dependencies
- `cache/` - Model and video cache directory (auto-created)
