"""
Shared configuration for MMAudio and HunyuanVideo-Foley APIs.

Environment Variables:
    # API Server Configuration
    API_HOST: Host to bind the API server (default: "0.0.0.0")
    API_PORT: Port for the API server (default: 8000 for MMAudio, 8001 for HunyuanVideo-Foley)
    LOG_LEVEL: Logging level (default: "info")
    
    # Cache Configuration
    VIDEO_CACHE_MAX_GB: Maximum size of video cache in GB (default: 32)
    VIDEO_CACHE_TTL_MIN: Time-to-live for cached videos in minutes (default: 60)
    VIDEO_FRAME_CHECK: Enable frame count checking (default: "false")
    
    # Device Configuration
    FORCE_DEVICE: Force specific device ("cuda", "mps", "cpu", default: auto-detect)
    FORCE_DTYPE: Force specific dtype ("float32", "bfloat16", "float16", default: "bfloat16")
    
    # Model Paths
    MMAUDIO_PATH: Path to MMAudio repository (default: "/workspace/model-tests/repos/MMAudio")
    HYVF_PATH: Path to HunyuanVideo-Foley repository (default: "/workspace/model-tests/repos/HunyuanVideo-Foley")
    HYVF_WEIGHTS_PATH: Path to HunyuanVideo-Foley weights (default: "/workspace/model-tests/models/HunyuanVideo-Foley")
    
    # Performance
    ALLOW_TF32: Allow TF32 acceleration for matmul and cudnn (default: "true")
    ENABLE_TRACEMALLOC: Enable memory profiling (default: "true")
"""

import os
from pathlib import Path
from typing import Literal

# ========== API SERVER CONFIGURATION ==========
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))  # Override with 8001 for HunyuanVideo-Foley
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

# ========== CACHE CONFIGURATION ==========
VIDEO_CACHE_MAX_GB = float(os.getenv("VIDEO_CACHE_MAX_GB", "32"))  # 32GB default max size
VIDEO_CACHE_TTL_MIN = int(os.getenv("VIDEO_CACHE_TTL_MIN", "60"))  # 60 minutes default TTL
VIDEO_FRAME_CHECK = os.getenv("VIDEO_FRAME_CHECK", "false").strip().lower() in ("1", "true", "yes", "on")

# ========== DEVICE CONFIGURATION ==========
FORCE_DEVICE: Literal["cuda", "mps", "cpu", "auto"] | None = os.getenv("FORCE_DEVICE", "auto")  # type: ignore
FORCE_DTYPE: Literal["float32", "bfloat16", "float16", "auto"] | None = os.getenv("FORCE_DTYPE", "bfloat16")  # type: ignore

# ========== MODEL PATHS ==========
MMAUDIO_PATH = Path(os.getenv("MMAUDIO_PATH", "/workspace/model-tests/repos/MMAudio"))
HYVF_PATH = Path(os.getenv("HYVF_PATH", "/workspace/model-tests/repos/HunyuanVideo-Foley"))
HYVF_WEIGHTS_PATH = Path(os.getenv("HYVF_WEIGHTS_PATH", "/workspace/model-tests/models/HunyuanVideo-Foley"))

# ========== PERFORMANCE CONFIGURATION ==========
ALLOW_TF32 = os.getenv("ALLOW_TF32", "true").strip().lower() in ("1", "true", "yes", "on")
ENABLE_TRACEMALLOC = os.getenv("ENABLE_TRACEMALLOC", "true").strip().lower() in ("1", "true", "yes", "on")

# ========== LOGGING CONFIGURATION ==========
LOG_BUFFER_SIZE = int(os.getenv("LOG_BUFFER_SIZE", "500"))  # Keep last N log entries

# ========== VALIDATION ==========
def validate_config():
    """Validate configuration values"""
    errors = []
    
    if VIDEO_CACHE_MAX_GB < 0:
        errors.append(f"VIDEO_CACHE_MAX_GB must be >= 0, got {VIDEO_CACHE_MAX_GB}")
    
    if VIDEO_CACHE_TTL_MIN < 0:
        errors.append(f"VIDEO_CACHE_TTL_MIN must be >= 0, got {VIDEO_CACHE_TTL_MIN}")
    
    if API_PORT < 1 or API_PORT > 65535:
        errors.append(f"API_PORT must be between 1-65535, got {API_PORT}")
    
    if FORCE_DEVICE not in ("cuda", "mps", "cpu", "auto", None):
        errors.append(f"FORCE_DEVICE must be 'cuda', 'mps', 'cpu', or 'auto', got {FORCE_DEVICE}")
    
    if FORCE_DTYPE not in ("float32", "bfloat16", "float16", "auto", None):
        errors.append(f"FORCE_DTYPE must be 'float32', 'bfloat16', 'float16', or 'auto', got {FORCE_DTYPE}")
    
    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(errors))

# Auto-validate on import
validate_config()
