"""
MMAudio API client for video-to-audio generation

Provides HTTP client functions for interacting with the MMAudio standalone API.
"""

import os
import time
import tempfile
from pathlib import Path
from typing import Optional

import requests

from .config import (
    MMAUDIO_DEFAULT_API_URL,
    MMAUDIO_DEFAULT_MODEL,
    MMAUDIO_DEFAULT_NUM_STEPS,
    MMAUDIO_DEFAULT_CFG_STRENGTH,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_TIMEOUT,
    get_api_url,
    get_cf_headers,
)

# Backwards compatibility aliases
DEFAULT_API_URL = MMAUDIO_DEFAULT_API_URL
DEFAULT_MODEL = MMAUDIO_DEFAULT_MODEL
DEFAULT_NUM_STEPS = MMAUDIO_DEFAULT_NUM_STEPS
DEFAULT_CFG_STRENGTH = MMAUDIO_DEFAULT_CFG_STRENGTH


def check_api_health(api_url: str = DEFAULT_API_URL, quiet: bool = False) -> bool:
    """
    Check if the API server is reachable.
    
    Args:
        api_url (str): API server URL
        quiet (bool): Suppress error messages
    
    Returns:
        bool: True if API is reachable, False otherwise
    
    Example:
        >>> if check_api_health():
        >>>     print("API is online!")
    """
    try:
        url = api_url or get_api_url()
        response = requests.get(url, timeout=10, headers=get_cf_headers())
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"❌ API not reachable: {e}")
        return False


def get_available_models(api_url: str = DEFAULT_API_URL, quiet: bool = False) -> Optional[dict]:
    """
    Get available models from the API.
    
    Args:
        api_url (str): API server URL
        quiet (bool): Suppress error messages
    
    Returns:
        dict or None: Model information if successful, None otherwise
    
    Example:
        >>> models = get_available_models()
        >>> if models:
        >>>     print(f"Available: {models['available_models']}")
        >>>     print(f"Loaded: {models['loaded_models']}")
    """
    try:
        url = api_url or get_api_url()
        response = requests.get(
            f"{url}/models",
            timeout=10,
            headers=get_cf_headers(),
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"❌ Failed to get models: {e}")
        return None


def generate_audio(
    api_url: str,
    video_path: Optional[str],  # Optional for T2A mode
    prompt: str,
    negative_prompt: str,
    seed: int,
    model_name: str = DEFAULT_MODEL,
    duration: Optional[float] = None,  # Required for T2A, auto-detected for V2A
    num_steps: int = DEFAULT_NUM_STEPS,
    cfg_strength: float = DEFAULT_CFG_STRENGTH,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    output_path: Optional[str] = None,
    use_temp: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    quiet: bool = False,
    verbose: bool = False,
    full_precision: bool = False
) -> Optional[str]:
    """
    Generate audio from video (V2A) or text only (T2A) using the MMAudio Standalone API.
    
    Args:
        api_url (str): API server URL
        video_path (str): Path to input video file
        prompt (str): Text prompt describing desired audio
        negative_prompt (str): Negative prompt to avoid certain sounds
        seed (int): Random seed for reproducibility
        model_name (str): Model variant to use (default: "large_44k_v2")
        duration (float, optional): Duration in seconds (default: auto-detect)
        num_steps (int): Number of generation steps (default: 25)
        cfg_strength (float): CFG strength for prompt guidance (default: 4.5)
        output_format (str): "flac" or "wav" (default: "wav" for Pro Tools)
        output_path (str, optional): Custom output path
        use_temp (bool): Use system temp directory for output
        timeout (int): Request timeout in seconds (default: 300)
        quiet (bool): Minimal output
        verbose (bool): Detailed output
    
    Returns:
        str or None: Path to generated audio file if successful, None otherwise
    
    Examples:
        # V2A (Video-to-Audio)
        >>> audio_path = generate_audio(
        >>>     api_url="http://localhost:8000",
        >>>     video_path="video.mp4",
        >>>     prompt="ocean waves",
        >>>     negative_prompt="voices, music",
        >>>     seed=42
        >>> )
        
        # T2A (Text-to-Audio)
        >>> audio_path = generate_audio(
        >>>     api_url="http://localhost:8000",
        >>>     video_path=None,  # No video for T2A
        >>>     prompt="thunder and rain",
        >>>     negative_prompt="voices, music",
        >>>     seed=42,
        >>>     duration=8.0  # Required for T2A
        >>> )
    """
    
    # Determine mode: T2A (text-only) or V2A (video-to-audio)
    is_t2a_mode = video_path is None
    
    # T2A mode validation
    if is_t2a_mode:
        if duration is None:
            # Default duration for T2A: 8 seconds (standard from MMAudio demo.py)
            duration = 8.0
            if not quiet:
                print(f"ℹ️  T2A mode: Using default duration of {duration}s")
        
        if duration < 4 or duration > 12:
            if not quiet:
                print(f"❌ Invalid duration for T2A: {duration}s (must be 1-30s)")
            return None
    else:
        # V2A mode validation
        if not os.path.exists(video_path):
            if not quiet:
                print(f"❌ Video file not found: {video_path}")
            return None
    
    if not quiet:
        print(f"\n🚀 Sending request to API...")
        if is_t2a_mode:
            print(f"   Mode: T2A (Text-to-Audio)")
            print(f"   Duration: {duration}s")
        else:
            print(f"   Mode: V2A (Video-to-Audio)")
            print(f"   Video: {Path(video_path).name}")
            print(f"   Duration: {'auto-detect' if duration is None else f'{duration}s'}")
        print(f"   Model: {model_name}")
        if verbose:
            print(f"   Prompt: '{prompt}'")
            print(f"   Negative Prompt: '{negative_prompt}'")
            print(f"   Seed: {seed}")
            print(f"   Steps: {num_steps}")
            print(f"   CFG Strength: {cfg_strength}")
            print(f"   Output Format: {output_format}")
    
    # Prepare request data
    data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": seed,
        "model_name": model_name,
        "num_steps": num_steps,
        "cfg_strength": cfg_strength,
        "output_format": output_format,
        "full_precision": full_precision
    }
    
    if duration is not None:
        data["duration"] = duration
    
    start_time = time.time()
    
    headers = get_cf_headers()
    try:
        url = api_url or get_api_url()
        
        if not quiet:
            print("⏳ Processing... (this may take a minute)")
        
        if is_t2a_mode:
            # T2A mode: No file upload, just form data
            response = requests.post(
                f"{url}/generate",
                headers=headers,
                data=data,
                timeout=timeout
            )
        else:
            # V2A mode: Upload video file
            with open(video_path, 'rb') as video_file:
                files = {"video": (Path(video_path).name, video_file, "video/mp4")}
                response = requests.post(
                    f"{url}/generate",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=timeout
                )
        
        response.raise_for_status()
        
        total_time = time.time() - start_time
        
        # Get metadata from headers
        generation_time = response.headers.get('X-Generation-Time', 'unknown')
        actual_duration = response.headers.get('X-Duration', 'unknown')
        used_seed = response.headers.get('X-Seed', seed)
        output_format_used = response.headers.get('X-Output-Format', output_format)
        generation_mode = response.headers.get('X-Mode', 'V2A' if not is_t2a_mode else 'T2A')
        
        # Extract server-generated filename from Content-Disposition header
        # FastAPI FileResponse includes: Content-Disposition: attachment; filename="..."
        server_filename = None
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            # Parse filename from Content-Disposition header
            import re
            match = re.search(r'filename="?([^"]+)"?', content_disposition)
            if match:
                server_filename = match.group(1)
        
        if not quiet:
            print(f"\n✅ Audio generated successfully!")
            print(f"   Mode: {generation_mode}")
            print(f"   Total time: {total_time:.2f}s")
            print(f"   Generation time: {generation_time}s")
            print(f"   Duration: {actual_duration}s")
            print(f"   Seed used: {used_seed}")
            print(f"   Format: {output_format_used}")
            if server_filename:
                print(f"   Filename: {server_filename}")
        
        # Determine output path
        if output_path:
            output_path_obj = Path(output_path)
            
            # Check if output_path is a directory or file path
            if output_path_obj.is_dir() or (not output_path_obj.exists() and not output_path_obj.suffix):
                # It's a directory (or looks like one) - append server filename
                output_dir = output_path_obj
                output_dir.mkdir(parents=True, exist_ok=True)
                
                if server_filename:
                    final_output_path = output_dir / server_filename
                else:
                    timestamp = int(time.time())
                    file_ext = output_format.lower()
                    output_filename = f"generated_audio_{timestamp}_{seed}.{file_ext}"
                    final_output_path = output_dir / output_filename
            else:
                # It's a file path - use as-is
                final_output_path = output_path_obj
                # Ensure output directory exists
                final_output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Auto-generate output path, using server-provided filename if available
            if use_temp:
                output_dir = Path(tempfile.gettempdir()) / "pt_v2a_outputs"
                output_dir.mkdir(exist_ok=True, parents=True)
            else:
                output_dir = Path("./standalone-API_outputs")
                output_dir.mkdir(exist_ok=True)
            
            # Use server-generated filename if available, otherwise fallback to timestamp-based
            if server_filename:
                output_filename = server_filename
            else:
                timestamp = int(time.time())
                file_ext = output_format.lower()
                output_filename = f"generated_audio_{timestamp}_{seed}.{file_ext}"
            
            final_output_path = output_dir / output_filename

        # Save audio file
        with open(final_output_path, 'wb') as f:
            f.write(response.content)
        
        # Always return absolute path (important for Pro Tools plugin integration)
        absolute_path = final_output_path.absolute()
        
        if not quiet:
            print(f"📁 Audio saved as: {absolute_path}")
            print(f"📊 File size: {len(response.content) / 1024:.1f} KB")
        
        return str(absolute_path)
        
    except requests.exceptions.Timeout:
        if not quiet:
            print("❌ Request timed out. The server might be overloaded.")
        return None
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"❌ Request failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   Server response: {e.response.text}")
        return None
    except Exception as e:
        if not quiet:
            print(f"❌ Unexpected error: {e}")
        return None
