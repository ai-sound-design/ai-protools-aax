"""
MMAudio API client utilities

Provides:
- API health checking
- Audio generation from video
- Model information retrieval
"""

from .client import generate_audio, check_api_health, get_available_models
from .config import (
    # Config functions
    get_api_url,
    # Shared settings
    SUPPORTED_VIDEO_FORMATS,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_SEED,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_TIMEOUT,
    VIDEO_DOWNSCALE_THRESHOLD_MB,
    # MMAudio-specific
    MMAUDIO_DEFAULT_API_URL,
    MMAUDIO_DEFAULT_NUM_STEPS,
    MMAUDIO_DEFAULT_CFG_STRENGTH,
    MMAUDIO_DEFAULT_MODEL,
    # HunyuanVideo-Foley-specific
    HYVF_DEFAULT_API_URL,
    HYVF_DEFAULT_NUM_STEPS,
    HYVF_DEFAULT_CFG_STRENGTH,
    HYVF_DEFAULT_MODEL_SIZE,
)

# Backwards compatibility alias
DEFAULT_API_URL = MMAUDIO_DEFAULT_API_URL

__all__ = [
    # Client functions
    'generate_audio',
    'check_api_health',
    'get_available_models',
    'get_api_url',
    # Shared settings
    'SUPPORTED_VIDEO_FORMATS',
    'DEFAULT_NEGATIVE_PROMPT',
    'DEFAULT_SEED',
    'DEFAULT_OUTPUT_FORMAT',
    'DEFAULT_TIMEOUT',
    'VIDEO_DOWNSCALE_THRESHOLD_MB',
    # MMAudio-specific settings
    'DEFAULT_API_URL',  # Backwards compatibility
    'MMAUDIO_DEFAULT_API_URL',
    'MMAUDIO_DEFAULT_NUM_STEPS',
    'MMAUDIO_DEFAULT_CFG_STRENGTH',
    'MMAUDIO_DEFAULT_MODEL',
    # HunyuanVideo-Foley-specific settings
    'HYVF_DEFAULT_API_URL',
    'HYVF_DEFAULT_NUM_STEPS',
    'HYVF_DEFAULT_CFG_STRENGTH',
    'HYVF_DEFAULT_MODEL_SIZE',
]
