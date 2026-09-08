"""
HunyuanVideo-Foley API client for video-to-audio generation

Provides HTTP client functions for interacting with the HunyuanVideo-Foley standalone API.
Analogous to api/client.py but adapted for HunyuanVideo-Foley specific parameters.
"""

import os
import time
import tempfile
from pathlib import Path
from typing import Optional

import requests

from .config import (
    HYVF_DEFAULT_API_URL,
    HYVF_DEFAULT_MODEL_SIZE,
    HYVF_DEFAULT_NUM_STEPS,
    HYVF_DEFAULT_CFG_STRENGTH,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_TIMEOUT,
    get_cf_headers,
    get_api_url,
)


def check_api_health(api_url: str = None, quiet: bool = False) -> bool:
    """
    Check if the HunyuanVideo-Foley API server is reachable.
    
    Args:
        api_url (str): API server URL (default: from config.json)
        quiet (bool): Suppress error messages
    
    Returns:
        bool: True if API is reachable, False otherwise
    
    Example:
        >>> if check_api_health():
        >>>     print("HunyuanVideo-Foley API is online!")
    """
    try:
        url = api_url or get_api_url("hunyuan")
        response = requests.get(f"{url}/", timeout=10, headers=get_cf_headers())
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"❌ API not reachable: {e}")
        return False


def get_available_models(api_url: str = None, quiet: bool = False) -> Optional[dict]:
    """
    Get available models from the HunyuanVideo-Foley API.
    
    Args:
        api_url (str): API server URL (default: from config.json)
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
        url = api_url or get_api_url("hunyuan")
        response = requests.get(f"{url}/models", timeout=10, headers=get_cf_headers())
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"❌ Failed to get models: {e}")
        return None


def generate_audio(
    api_url: str,
    video_path: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
    model_size: str = HYVF_DEFAULT_MODEL_SIZE,
    duration: Optional[float] = None,
    num_steps: int = HYVF_DEFAULT_NUM_STEPS,
    cfg_strength: float = HYVF_DEFAULT_CFG_STRENGTH,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    full_precision: bool = False,  # Use float32 instead of float16
    output_path: Optional[str] = None,
    use_temp: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    quiet: bool = False,
    verbose: bool = False
) -> Optional[str]:
    """
    Generate audio from video using the HunyuanVideo-Foley Standalone API.
    
    Args:
        api_url (str): API server URL (default: http://localhost:8001)
        video_path (str): Path to input video file
        prompt (str): Text prompt describing desired Foley audio
        negative_prompt (str): Negative prompt to avoid certain sounds
        seed (int): Random seed for reproducibility
        model_size (str): "xl" (faster, 8-12GB VRAM) or "xxl" (higher quality, 16-20GB VRAM)
        duration (float, optional): Duration in seconds (default: auto-detect)
        num_steps (int): Number of generation steps (default: 50)
        cfg_strength (float): CFG strength for prompt guidance (default: 4.5)
        output_format (str): "wav" or "flac" (default: "wav" for Pro Tools)
        full_precision (bool): Use float32 instead of bfloat16 (default: False)
                              NOTE: Effect is minimal - model is hardcoded to bfloat16→float32.
                              Only affects feature/latent precision. ~10-20% more VRAM.
        output_path (str, optional): Custom output path
        use_temp (bool): Use system temp directory for output
        timeout (int): Request timeout in seconds (default: 300)
        quiet (bool): Minimal output
        verbose (bool): Detailed output
    
    Returns:
        str or None: Path to generated audio file if successful, None otherwise
    
    Example:
        >>> audio_path = generate_audio(
        >>>     api_url="http://localhost:8001",
        >>>     video_path="video.mp4",
        >>>     prompt="footsteps on gravel",
        >>>     negative_prompt="voices, music",
        >>>     seed=42,
        >>>     model_size="xxl"
        >>> )
        >>> if audio_path:
        >>>     print(f"Generated 48kHz audio: {audio_path}")
    """
    
    if not os.path.exists(video_path):
        if not quiet:
            print(f"❌ Video file not found: {video_path}")
        return None
    
    if not quiet:
        print(f"\n🚀 Sending request to HunyuanVideo-Foley API...")
        print(f"   Video: {Path(video_path).name}")
        print(f"   Model Size: {model_size.upper()}")
        print(f"   Duration: {'auto-detect' if duration is None else f'{duration}s'}")
        print(f"   Precision: {'float32 (full)' if full_precision else 'bfloat16 (default)'}")
        if verbose:
            print(f"   Prompt: '{prompt}'")
            print(f"   Negative Prompt: '{negative_prompt}'")
            print(f"   Seed: {seed}")
            print(f"   Steps: {num_steps}")
            print(f"   CFG Strength: {cfg_strength}")
            print(f"   Output Format: {output_format}")
    
    # Prepare request data (HunyuanVideo-Foley specific parameters)
    data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": seed,
        "model_size": model_size,  # HunyuanVideo-Foley uses model_size instead of model_name
        "num_steps": num_steps,
        "cfg_strength": cfg_strength,
        "output_format": output_format,
        "full_precision": str(full_precision).lower()  # Convert bool to string for form data
    }
    
    if duration is not None:
        data["duration"] = duration
    
    start_time = time.time()
    
    try:
        with open(video_path, 'rb') as video_file:
            files = {"video": (Path(video_path).name, video_file, "video/mp4")}
            
            if not quiet:
                print("⏳ Processing... (this may take a minute)")
            
            # Debug: Print CF-Access headers
            cf_headers = get_cf_headers()
            if cf_headers:
                print(f"=== DEBUG: Sending CF-Access headers to {api_url}/generate ===")
                for key in cf_headers:
                    value = cf_headers[key]
                    if 'Secret' in key:
                        value = value[:10] + "..."
                    print(f"  {key}: {value}")
            
            response = requests.post(
                f"{api_url}/generate",
                files=files,
                data=data,
                timeout=timeout,
                headers=cf_headers
            )
            
            # Debug: Check if we got HTML instead of audio
            content_type = response.headers.get('Content-Type', '')
            if 'html' in content_type.lower():
                print(f"=== ERROR: Received HTML instead of audio! ===")
                print(f"  Status Code: {response.status_code}")
                print(f"  Content-Type: {content_type}")
                print(f"  Content preview: {response.text[:500]}")
            
            response.raise_for_status()
        
        total_time = time.time() - start_time
        
        # Get metadata from headers
        generation_time = response.headers.get('X-Generation-Time', 'unknown')
        actual_duration = response.headers.get('X-Duration', 'unknown')
        used_seed = response.headers.get('X-Seed', seed)
        output_format_used = response.headers.get('X-Output-Format', output_format)
        sample_rate = response.headers.get('X-Sample-Rate', '48000')
        
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
            print(f"   Total time: {total_time:.2f}s")
            print(f"   Generation time: {generation_time}s")
            print(f"   Video duration: {actual_duration}s")
            print(f"   Seed used: {used_seed}")
            print(f"   Format: {output_format_used}")
            print(f"   Sample Rate: {sample_rate} Hz (professional Foley standard)")
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
                    output_filename = f"hyvf_{model_size}_{timestamp}_{seed}.{file_ext}"
                    final_output_path = output_dir / output_filename
            else:
                # It's a file path - use as-is
                final_output_path = output_path_obj
                # Ensure output directory exists
                final_output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Auto-generate output filename with correct extension
            if use_temp:
                output_dir = Path(tempfile.gettempdir()) / "pt_v2a_outputs"
                output_dir.mkdir(exist_ok=True, parents=True)
            else:
                output_dir = Path("./hunyuanvideo-foley-outputs")
                output_dir.mkdir(exist_ok=True)
            
            # Use server-generated filename if available, otherwise fallback to old format
            if server_filename:
                output_filename = server_filename
            else:
                timestamp = int(time.time())
                file_ext = output_format.lower()
                output_filename = f"hyvf_{model_size}_{timestamp}_{seed}.{file_ext}"
            
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
