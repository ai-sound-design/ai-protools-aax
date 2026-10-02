"""
BBC Sound Search API client for semantic sound retrieval

Provides HTTP client functions for interacting with the Sound Search standalone API.
Supports video-based and text-based semantic search with X-CLIP embeddings.
"""

import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

from .config import (
    get_config,
    get_cf_headers,
    use_cloudflared,
)

# Import video preprocessing and validation from video module
try:
    # Try relative import first (when called as module)
    from ..video.ffmpeg import downscale_video, get_video_duration
except (ImportError, ValueError):
    try:
        # Fallback: add parent directory to path (when called as script)
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from video.ffmpeg import downscale_video, get_video_duration
    except ImportError:
        downscale_video = None
        get_video_duration = None

# Default settings
DEFAULT_LIMIT = 5
DEFAULT_TEXT_WEIGHT = 0.6
DEFAULT_NUM_FRAMES = 16


def get_sound_search_url() -> str:
    """Base URL of the selected search adapter profile (falls back to the legacy services table)."""
    try:
        from .config import get_api_url
    except ImportError:
        from config import get_api_url  # type: ignore
    return get_api_url("sound_search") or "http://localhost:8002"


def check_api_health(quiet: bool = False) -> bool:
    """
    Check if the Sound Search API server is reachable.
    
    Args:
        quiet: Suppress error messages
    
    Returns:
        True if API is reachable, False otherwise
    """
    try:
        url = get_sound_search_url()
        response = requests.get(f"{url}/health", timeout=10, headers=get_cf_headers())
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"[ERROR] Sound Search API not reachable: {e}")
        return False


def search_sounds(
    video_path: Optional[str] = None,
    text_query: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    text_weight: float = DEFAULT_TEXT_WEIGHT,
    num_frames: int = DEFAULT_NUM_FRAMES,
    quiet: bool = False,
    verbose: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """
    Search for sounds using video and/or text.
    
    Args:
        video_path: Path to video file (optional)
        text_query: Text description (optional)
        limit: Number of results (default: 5)
        text_weight: Weight for text vs video (0-1, default: 0.6)
        num_frames: Number of frames to extract (default: 16)
        quiet: Minimal output
        verbose: Detailed output
        
    Returns:
        List of sound results with id, description, category, similarity, etc.
        None if request fails.
    
    Examples:
        # Video search
        >>> results = search_sounds(video_path="door.mp4", limit=5)
        
        # Text search
        >>> results = search_sounds(text_query="footsteps on pavement", limit=5)
        
        # Hybrid search (video + text)
        >>> results = search_sounds(
        >>>     video_path="door.mp4",
        >>>     text_query="door closing",
        >>>     text_weight=0.6
        >>> )
    """
    if not video_path and not text_query:
        if not quiet:
            print("[ERROR] Must provide either video_path or text_query")
        return None
    
    if video_path and not os.path.exists(video_path):
        if not quiet:
            print(f"[ERROR] Video file not found: {video_path}")
        return None
    
    if not quiet:
        print(f"\n[SEARCH] Searching BBC Sound Archive...")
        if video_path and text_query:
            print(f"   Mode: Hybrid (Video + Text)")
            print(f"   Video: {Path(video_path).name}")
            print(f"   Text: '{text_query}'")
            print(f"   Text Weight: {text_weight}")
        elif video_path:
            print(f"   Mode: Video Search")
            print(f"   Video: {Path(video_path).name}")
        else:
            print(f"   Mode: Text Search")
            print(f"   Query: '{text_query}'")
        print(f"   Limit: {limit}")
        if verbose:
            print(f"   Num Frames: {num_frames}")
    
    # Video preprocessing is now handled in sound_search_api_client.py
    # using trim_and_maybe_downscale_video() for consistency with audio generation
    # No additional preprocessing needed here
    
    try:
        url = f"{get_sound_search_url()}/search/sounds"
        
        data = {
            'limit': limit,
            'text_weight': text_weight,
            'num_frames': num_frames
        }
        # The selected search profile may pin fields, e.g. which library to search.
        try:
            from .adapters import search_request_fields
            data.update(search_request_fields())
        except Exception:
            pass

        if text_query:
            data['text'] = text_query
        
        if video_path:
            # V2A mode: Upload video file (same as audio generation)
            with open(video_path, 'rb') as video_file:
                files = {"video": (Path(video_path).name, video_file, "video/mp4")}
                response = requests.post(
                    url,
                    files=files,
                    data=data,
                    headers=get_cf_headers(),
                    timeout=120
                )
        else:
            # Text-only mode: No file upload
            response = requests.post(
                url,
                data=data,
                headers=get_cf_headers(),
                timeout=120
            )
        
        response.raise_for_status()
        
        result = response.json()
        results = result.get('results', [])
        
        if not quiet:
            print(f"[OK] Found {len(results)} results")
        
        return results
        
    except requests.exceptions.Timeout as e:
        if not quiet:
            print(f"[ERROR] Search request timed out after 60s: {e}")
        # Log to temp file for debugging
        import tempfile
        from .config import logs_enabled
        debug_log = Path(tempfile.gettempdir()) / "sound_search_client_error.log"
        with open(debug_log if logs_enabled() else os.devnull, 'a') as f:
            import datetime
            f.write(f"[{datetime.datetime.now()}] Timeout: {e}\n")
        return None
    except requests.exceptions.ConnectionError as e:
        if not quiet:
            print(f"[ERROR] Connection failed - is the API server running on {get_sound_search_url()}?: {e}")
        # Log to temp file for debugging
        import tempfile
        from .config import logs_enabled
        debug_log = Path(tempfile.gettempdir()) / "sound_search_client_error.log"
        with open(debug_log if logs_enabled() else os.devnull, 'a') as f:
            import datetime
            f.write(f"[{datetime.datetime.now()}] ConnectionError: {e}\n")
        return None
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"[ERROR] Search failed: {e}")
        # Log to temp file for debugging
        import tempfile
        from .config import logs_enabled
        debug_log = Path(tempfile.gettempdir()) / "sound_search_client_error.log"
        with open(debug_log if logs_enabled() else os.devnull, 'a') as f:
            import datetime
            import traceback
            f.write(f"[{datetime.datetime.now()}] RequestException: {e}\n")
            f.write(traceback.format_exc())
        return None



def search_by_sound(
    audio_path: str,
    text_query: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    text_weight: float = 0.0,
    quiet: bool = False,
    envelope_weight: Optional[float] = None,
    only: Optional[List[int]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Library windows that sound like `audio_path` (POST /search/by_audio), each with
    `offset_seconds`/`length_seconds`: the stretch of the recording that matched, in the
    query's length. `text_weight` is the share of `text_query` in the query (0: the sound
    alone). None when the request fails or the backend has no audio index."""
    try:
        url = f"{get_sound_search_url()}/search/by_audio"
        data = {"limit": limit, "text_weight": text_weight, "refine": "true"}
        if envelope_weight is not None:
            # Share of the loudness-envelope similarity when the stretch inside a recording
            # is chosen: a sketch wants nearly all of it, a real sound the backend's default
            data["envelope_weight"] = envelope_weight
        if only:
            data["only"] = ",".join(str(i) for i in only)      # search inside these sounds alone
        try:
            from .adapters import search_request_fields
            data.update({k: v for k, v in search_request_fields().items() if k in ("library", "category")})
        except Exception:
            pass
        if text_query:
            data["text"] = text_query
        with open(audio_path, "rb") as handle:
            files = {"audio": (Path(audio_path).name, handle, "audio/wav")}
            response = requests.post(url, files=files, data=data, headers=get_cf_headers(), timeout=120)
        if response.status_code == 503:
            if not quiet:
                print(f"[ERROR] The search service has no audio index yet: {response.text[:200]}")
            return None
        response.raise_for_status()
        results = response.json().get("results", [])
        if not quiet:
            print(f"[OK] Found {len(results)} results by sound")
        return results
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"[ERROR] Search by sound failed: {e}")
        return None


def download_snippet(
    sound_id: int,
    start_seconds: float,
    length_seconds: float,
    output_dir: Optional[str] = None,
    session_id: Optional[str] = None,
    quiet: bool = False,
) -> Optional[str]:
    """`length_seconds` of the sound from `start_seconds` as a 48 kHz WAV (GET
    /sounds/{id}/snippet): the stretch a search by sound pointed at, ready to place."""
    try:
        url = f"{get_sound_search_url()}/sounds/{sound_id}/snippet"
        response = requests.get(url, params={"start": f"{start_seconds:.3f}", "length": f"{length_seconds:.3f}"},
                                headers=get_cf_headers(), timeout=120)
        response.raise_for_status()
        content_disp = response.headers.get("Content-Disposition", "")
        if "filename=" in content_disp:
            filename = content_disp.split("filename=")[-1].strip('"')
        else:
            filename = f"sound_{sound_id}_{start_seconds:.1f}s.wav"
        if output_dir and os.path.isdir(output_dir):
            target_dir = output_dir
        else:
            target_dir = os.path.join(tempfile.gettempdir(), "sound-search", session_id or "")
        os.makedirs(target_dir, exist_ok=True)
        output_file = os.path.join(target_dir, filename)
        with open(output_file, "wb") as f:
            f.write(response.content)
        return output_file
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"[ERROR] Snippet download failed: {e}")
        return None


def get_sound_info(sound_id: int, quiet: bool = False) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific sound.
    
    Args:
        sound_id: BBC sound ID
        quiet: Suppress error messages
        
    Returns:
        Sound metadata dict with id, description, category, file_path, etc.
        None if request fails.
    """
    try:
        url = f"{get_sound_search_url()}/sounds/{sound_id}"
        response = requests.get(url, headers=get_cf_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"[ERROR] Failed to get sound info: {e}")
        return None


def download_sound(
    sound_id: int,
    output_path: Optional[str] = None,
    session_id: Optional[str] = None,
    quiet: bool = False,
    verbose: bool = False,
) -> Optional[str]:
    """
    Download sound file to specified path or temp directory.
    
    Args:
        sound_id: BBC sound ID
        output_path: Directory or file path to save to (optional)
        session_id: Session ID for organizing temp files (optional)
        quiet: Suppress output messages
        verbose: Show detailed progress
        
    Returns:
        Full path to downloaded file, None if download fails.
        
    Examples:
        # Download to specific path
        >>> path = download_sound(5362, output_path="/tmp/sounds/")
        
        # Download to temp with session ID
        >>> path = download_sound(5362, session_id="abc123")
        # Saved to: /tmp/sound-search/abc123/{filename}.wav
    """
    try:
        url = f"{get_sound_search_url()}/sounds/{sound_id}/download"
        
        if verbose:
            print(f"[DOWNLOAD] Requesting: {url}")
        
        response = requests.get(url, headers=get_cf_headers(), timeout=60)
        response.raise_for_status()
        
        if verbose:
            content_length = response.headers.get('Content-Length', 'unknown')
            print(f"[DOWNLOAD] Received {content_length} bytes")
        
        # Get filename from Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[-1].strip('"')
        else:
            # Fallback: get from sound info
            info = get_sound_info(sound_id, quiet=True) or {}
            name = (info.get('file_path') or (info.get('extra') or {}).get('file_name')
                    or info.get('external_id') or f"sound_{sound_id}.wav")
            filename = os.path.basename(str(name))
        
        # Determine output path
        if output_path:
            if os.path.isdir(output_path):
                output_file = os.path.join(output_path, filename)
            else:
                output_file = output_path
        else:
            # Use temp directory with optional session ID
            if session_id:
                temp_dir = os.path.join(tempfile.gettempdir(), "sound-search", session_id)
            else:
                temp_dir = os.path.join(tempfile.gettempdir(), "sound-search")
            os.makedirs(temp_dir, exist_ok=True)
            output_file = os.path.join(temp_dir, filename)
        
        # Write file
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        if verbose:
            print(f"[DOWNLOAD] Writing to: {output_file}")
        
        with open(output_file, 'wb') as f:
            bytes_written = f.write(response.content)
        
        if verbose:
            print(f"[DOWNLOAD] Wrote {bytes_written} bytes")
        
        if not quiet:
            print(f"[OK] Downloaded: {filename}")
        
        return output_file
        
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"[ERROR] Download failed for sound {sound_id}: {e}")
        return None


def search_and_download(
    video_path: Optional[str] = None,
    text_query: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    text_weight: float = DEFAULT_TEXT_WEIGHT,
    num_frames: int = DEFAULT_NUM_FRAMES,
    output_path: Optional[str] = None,
    session_id: Optional[str] = None,
    quiet: bool = False,
    verbose: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """
    Search for sounds and download them in one call.
    
    This is the main convenience function for plugin integration.
    Performs a search, downloads all results to temp directory,
    and returns enriched results with local file paths.
    
    Args:
        video_path: Path to video file (optional)
        text_query: Text description (optional)
        limit: Number of results (default: 5)
        text_weight: Weight for text vs video (0-1, default: 0.6)
        num_frames: Number of frames to extract (default: 16)
        output_path: Custom output directory (optional, uses /tmp/sound-search/ by default)
        session_id: Session ID for organizing temp files (optional, generates UUID if not provided)
        quiet: Minimal output
        verbose: Detailed output
        
    Returns:
        List of sound dicts with added 'local_path' key for each downloaded file.
        None if search or any download fails.
    
    Example:
        >>> results = search_and_download(
        >>>     video_path="door.mp4",
        >>>     text_query="door closing",
        >>>     session_id="plugin_session_123"
        >>> )
        >>> if results:
        >>>     for sound in results:
        >>>         print(f"{sound['description']}: {sound['local_path']}")
    """
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
    
    # Search for sounds
    results = search_sounds(
        video_path=video_path,
        text_query=text_query,
        limit=limit,
        text_weight=text_weight,
        num_frames=num_frames,
        quiet=quiet,
        verbose=verbose,
    )
    
    if not results:
        return None
    
    # Download all sounds
    if not quiet:
        print(f"\n[DOWNLOAD] Downloading {len(results)} sounds...")
    
    enriched_results = []
    for i, sound in enumerate(results, 1):
        sound_id = sound['id']
        
        if verbose:
            print(f"[DOWNLOAD] Sound {i}/{len(results)}: ID {sound_id}")
        
        local_path = download_sound(
            sound_id=sound_id,
            output_path=output_path,
            session_id=session_id,
            quiet=quiet,
            verbose=verbose,
        )
        
        if local_path:
            # Add local path to result
            sound['local_path'] = local_path
            enriched_results.append(sound)
        else:
            if not quiet:
                print(f"[WARN] Skipping sound {sound_id} (download failed)")
    
    if not quiet:
        print(f"[OK] Downloaded {len(enriched_results)}/{len(results)} sounds")
    
    return enriched_results if enriched_results else None


def cleanup_session(session_id: str, quiet: bool = False) -> bool:
    """
    Clean up temporary files for a specific session.
    
    Args:
        session_id: Session ID to clean up
        quiet: Suppress output messages
        
    Returns:
        True if cleanup successful, False otherwise.
    """
    import shutil
    
    session_dir = os.path.join(tempfile.gettempdir(), "sound-search", session_id)
    
    if not os.path.exists(session_dir):
        return True
    
    try:
        shutil.rmtree(session_dir)
        if not quiet:
            print(f"[OK] Cleaned up session: {session_id}")
        return True
    except Exception as e:
        if not quiet:
            print(f"[WARN] Failed to clean up session {session_id}: {e}")
        return False
