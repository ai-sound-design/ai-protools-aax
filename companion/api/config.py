"""
Configuration constants and helpers for the MMAudio + HunyuanVideo-Foley clients.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

# Paths - use user config directory (matches C++ PluginProcessor path)
if os.name == 'nt':  # Windows
    _USER_CONFIG_DIR = Path(os.environ.get('APPDATA', '')) / 'PTV2A'
else:  # macOS
    # macOS: JUCE's userApplicationDataDirectory returns ~/Library/ (not ~/Library/Application Support/)
    _USER_CONFIG_DIR = Path.home() / 'Library' / 'PTV2A'

_USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_CONFIG_PATH = _USER_CONFIG_DIR / "config.json"

# =============================================================================
# Shared Settings (Both MMAudio and HunyuanVideo-Foley)
# =============================================================================
# API Configuration defaults
DEFAULT_API_URL = "http://localhost:8000"

# Config defaults (overridden by config.json in the user config directory, see _CONFIG_PATH)
CONFIG_DEFAULTS: Dict[str, Any] = {
    "use_cloudflared": False,
    "services": {
        "mmaudio": {
            "api_url_direct": "http://localhost:8000",
            "api_url_cloudflared": "https://mmaudio.example.com",
        },
        "hunyuan": {
            "api_url_direct": "http://localhost:8001",
            "api_url_cloudflared": "https://hyvf.example.com",
        },
        "sound_search": {
            "api_url_direct": "http://localhost:8002",
            "api_url_cloudflared": "https://sounds.example.com",
        },
    },
    "cf_access_client_id": "",
    "cf_access_client_secret": "",
}

_config_cache: Dict[str, Any] | None = None


def _load_config() -> Dict[str, Any]:
    """Load config.json, falling back to defaults. Creates default config on first run."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    cfg = CONFIG_DEFAULTS.copy()
    
    # Create default config file on first run
    if not _CONFIG_PATH.exists():
        try:
            _CONFIG_PATH.write_text(json.dumps(CONFIG_DEFAULTS, indent=2))
        except Exception:
            pass  # If we can't write, we'll just use defaults
    
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text())
            if isinstance(data, dict):
                # Merge shallow keys, but keep nested dicts intact
                cfg.update(data)
                for service in ("mmaudio", "hunyuan", "sound_search"):
                    svc_defaults = CONFIG_DEFAULTS["services"][service]
                    cfg["services"].setdefault(service, svc_defaults.copy())
                    cfg["services"][service] = {
                        **svc_defaults,
                        **cfg["services"].get(service, {}),
                    }
        except json.JSONDecodeError:
            pass

    _config_cache = cfg
    return cfg


def reload_config() -> None:
    global _config_cache
    _config_cache = None


def get_config() -> Dict[str, Any]:
    return _load_config().copy()


def use_cloudflared() -> bool:
    cfg = _load_config()
    return bool(cfg.get("use_cloudflared"))


def get_service_urls(service: str) -> Dict[str, str]:
    cfg = _load_config()
    services = cfg.get("services", {})
    return services.get(service, {})


def get_api_url(service: str) -> str:
    service_cfg = get_service_urls(service)
    if use_cloudflared():
        return service_cfg.get("api_url_cloudflared") or service_cfg.get("api_url_direct") or ""
    return service_cfg.get("api_url_direct") or ""


def get_cf_headers() -> Dict[str, str]:
    """Return Cloudflare Access headers (only when enabled)."""
    if not use_cloudflared():
        return {}
    cfg = _load_config()
    client_id = cfg.get("cf_access_client_id")
    client_secret = cfg.get("cf_access_client_secret")
    if client_id and client_secret:
        return {
            "CF-Access-Client-Id": client_id,
            "CF-Access-Client-Secret": client_secret,
        }
    return {}


# Supported video formats for Pro Tools integration
SUPPORTED_VIDEO_FORMATS = {
    # Common container formats
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".webm",
    ".flv",
    ".wmv",
    ".f4v",
    # Professional / broadcast
    ".mxf",
    ".m2ts",
    ".mts",
    ".ts",
    # MPEG legacy
    ".mpg",
    ".mpeg",
    # Optical media
    ".vob",
    # Open / mobile
    ".ogv",
    ".3gp",
    ".3g2",
}

# Common generation parameters
DEFAULT_NEGATIVE_PROMPT = "voices, music, melody, singing, speech,interference"
DEFAULT_SEED = 42

# Output configuration
DEFAULT_OUTPUT_FORMAT = "wav"  # "wav" or "flac"
DEFAULT_TIMEOUT = 300  # seconds

# Video preprocessing
VIDEO_DOWNSCALE_THRESHOLD_MB = 2.0  # Downscale videos larger than this (MB) to 480p for faster upload

# FFmpeg encoding settings
FFMPEG_CRF_QUALITY = 25        # CRF quality (0-51, lower=better, 25=very good)
FFMPEG_PRESET = "ultrafast"    # Encoding speed preset (ultrafast/veryfast/fast/medium)
FFMPEG_TARGET_HEIGHT = 480     # Downscale target height in pixels (480p)

# =============================================================================
# MMAudio-Specific Settings (16kHz output, port 8000)
# =============================================================================

MMAUDIO_DEFAULT_API_URL = "http://localhost:8000"
MMAUDIO_DEFAULT_NUM_STEPS = 25
MMAUDIO_DEFAULT_CFG_STRENGTH = 4.5
MMAUDIO_DEFAULT_MODEL = "large_44k_v2"

# =============================================================================
# HunyuanVideo-Foley-Specific Settings (48kHz output, port 8001)
# =============================================================================

HYVF_DEFAULT_API_URL = "http://localhost:8001"
HYVF_DEFAULT_NUM_STEPS = 50
HYVF_DEFAULT_CFG_STRENGTH = 4.5
HYVF_DEFAULT_MODEL_SIZE = "xxl"  # "xl" or "xxl"
