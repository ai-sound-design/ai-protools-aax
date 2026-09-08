"""
FFmpeg operations for video processing

Provides:
- FFmpeg availability detection (imageio-ffmpeg or system)
- Video segment trimming with fast copy codec
- Video duration detection using FFprobe
"""

import os
import subprocess
import shutil
import tempfile
import json
import time
from pathlib import Path
from typing import Dict, Optional


def check_ffmpeg_available() -> Dict[str, any]:
    """
    Check if FFmpeg is available via imageio-ffmpeg package.
    
    Uses imageio-ffmpeg which provides cross-platform FFmpeg binaries.
    Falls back to system PATH if imageio-ffmpeg is not installed.
    
    Returns:
        dict: {
            'available': bool,
            'version': str or None,
            'path': str or None,
            'source': 'imageio-ffmpeg' or 'system',
            'error': str or None
        }
    
    Example:
        >>> result = check_ffmpeg_available()
        >>> if result['available']:
        >>>     print(f"FFmpeg {result['version']} from {result['source']}")
        >>> else:
        >>>     print(f"FFmpeg not available: {result['error']}")
    """
    try:
        # Priority 1: Use imageio-ffmpeg (cross-platform, bundled with pip)
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            source = 'imageio-ffmpeg'
        except ImportError:
            # Priority 2: Fallback to system PATH
            ffmpeg_path = shutil.which('ffmpeg')
            source = 'system'
            
            if not ffmpeg_path:
                return {
                    'available': False,
                    'version': None,
                    'path': None,
                    'source': None,
                    'error': 'FFmpeg not found in system PATH and imageio-ffmpeg not installed'
                }
        
        # Get version info
        result = subprocess.run(
            [ffmpeg_path, '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Extract version from first line (e.g., "ffmpeg version 4.4.2")
            version_line = result.stdout.split('\n')[0]
            version = version_line.split(' ')[2] if len(version_line.split(' ')) > 2 else 'unknown'
            
            return {
                'available': True,
                'version': version,
                'path': ffmpeg_path,
                'source': source,
                'error': None
            }
        else:
            return {
                'available': False,
                'version': None,
                'path': ffmpeg_path,
                'source': source,
                'error': f'FFmpeg found but returned error code {result.returncode}'
            }
            
    except subprocess.TimeoutExpired:
        return {
            'available': False,
            'version': None,
            'path': None,
            'source': None,
            'error': 'FFmpeg check timed out'
        }
    except Exception as e:
        return {
            'available': False,
            'version': None,
            'path': None,
            'source': None,
            'error': f'FFmpeg check error: {str(e)}'
        }


def trim_video_segment(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    output_path: Optional[str] = None
) -> Dict[str, any]:
    """
    Trim video segment using FFmpeg with fast copy codec.
    
    Uses FFmpeg's `-c copy` to avoid re-encoding (fast, no quality loss).
    
    Args:
        video_path (str): Path to source video file
        start_seconds (float): Start time in seconds
        end_seconds (float): End time in seconds
        output_path (str, optional): Output path (auto-generated if None)
    
    Returns:
        dict: {
            'success': bool,
            'output_path': str or None,
            'duration': float,
            'error': str or None
        }
    
    Example:
        >>> result = trim_video_segment(
        >>>     "video.mp4",
        >>>     start_seconds=5.0,
        >>>     end_seconds=10.0
        >>> )
        >>> if result['success']:
        >>>     print(f"Trimmed video: {result['output_path']}")
    
    Note:
        - Uses `-c copy` for fast processing (no re-encoding)
        - Oriented on FFmpeg best practices for video trimming
        - Duration is calculated, not read from output file
    """
    try:
        # Validate input file
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {
                'success': False,
                'output_path': None,
                'duration': None,
                'error': f'Video file not found: {video_path}'
            }
        
        # Check FFmpeg availability and get path
        ffmpeg_check = check_ffmpeg_available()
        if not ffmpeg_check['available']:
            return {
                'success': False,
                'output_path': None,
                'duration': None,
                'error': f'FFmpeg not available: {ffmpeg_check["error"]}'
            }
        
        # Use the FFmpeg path (embedded or system)
        ffmpeg_exe = ffmpeg_check['path']
        
        # Calculate duration
        duration = end_seconds - start_seconds
        
        # Generate output path if not provided
        if output_path is None:
            # Use temp directory for trimmed video
            temp_dir = Path(tempfile.gettempdir()) / "pt_v2a"
            temp_dir.mkdir(exist_ok=True, parents=True)
            
            # Generate unique filename
            timestamp = int(Path(video_path).stat().st_mtime)
            output_path = str(temp_dir / f"trimmed_{timestamp}_{start_seconds}_{end_seconds}.mp4")
        
        # Build FFmpeg command
        # Use embedded/detected FFmpeg path instead of relying on PATH
        # Re-encode for accurate file sizes (not -c copy)
        from api.config import FFMPEG_CRF_QUALITY, FFMPEG_PRESET
        
        cmd = [
            ffmpeg_exe,
            '-y',  # Overwrite output file
            '-ss', str(start_seconds),
            '-to', str(end_seconds),
            '-i', str(video_path),
            '-c:v', 'libx264',      # Re-encode video
            '-preset', FFMPEG_PRESET,  # Fast encoding
            '-crf', str(FFMPEG_CRF_QUALITY),  # Good quality
            '-c:a', 'aac',          # Audio codec
            output_path
        ]
        
        # Execute FFmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout for trimming
        )
        
        if result.returncode != 0:
            return {
                'success': False,
                'output_path': None,
                'duration': None,
                'error': f'FFmpeg trimming failed: {result.stderr}'
            }
        
        # Verify output file exists
        if not Path(output_path).exists():
            return {
                'success': False,
                'output_path': None,
                'duration': None,
                'error': f'FFmpeg completed but output file not found: {output_path}'
            }
        
        return {
            'success': True,
            'output_path': output_path,
            'duration': duration,
            'error': None
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'output_path': None,
            'duration': None,
            'error': 'FFmpeg trimming timed out (60s limit)'
        }
    except Exception as e:
        return {
            'success': False,
            'output_path': None,
            'duration': None,
            'error': f'Trimming error: {str(e)}'
        }


def trim_and_maybe_downscale_video(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    output_path: Optional[str] = None,
    target_height: Optional[int] = None,
    crf: Optional[int] = None,
    preset: Optional[str] = None,
    size_threshold_mb: Optional[float] = None
) -> Dict[str, any]:
    """
    Smart trim: Downscales to 480p if estimated size exceeds threshold.
    
    Combines trimming and optional downscaling in ONE FFmpeg operation for better performance.
    Estimates trimmed file size based on duration ratio and downscales only if necessary.
    
    Logic:
    1. Estimate trimmed file size: original_size × (trim_duration / original_duration)
    2. If estimated size > threshold: Trim + downscale to 480p (ONE operation)
    3. Else: Just trim at original resolution
    
    Note:
        - May upscale videos <480p, but this is acceptable for audio generation
        - MMAudio uses 384×384, HunyuanVideo-Foley uses 256×256/512×512
        - Both models downscale anyway, so upscaling 360p→480p has negligible impact
    
    Args:
        video_path: Input video path
        start_seconds: Trim start time
        end_seconds: Trim end time
        output_path: Output path (auto-generated if None)
        target_height: Downscale target height (default: from config.FFMPEG_TARGET_HEIGHT)
        crf: Quality factor 0-51, lower=better (default: from config.FFMPEG_CRF_QUALITY)
        preset: FFmpeg preset ultrafast/veryfast/fast/medium (default: from config.FFMPEG_PRESET)
        size_threshold_mb: Size threshold to trigger downscaling (default: from config.VIDEO_DOWNSCALE_THRESHOLD_MB)
    
    Returns:
        dict: {
            'success': bool,
            'output_path': str,
            'duration': float,
            'downscaled': bool,
            'original_size_mb': float,
            'estimated_size_mb': float,
            'final_size_mb': float,
            'encoding_time': float,
            'error': str or None
        }
    
    Example:
        >>> result = trim_and_maybe_downscale_video(
        >>>     "large_video.mp4",
        >>>     start_seconds=5.0,
        >>>     end_seconds=10.0
        >>> )
        >>> if result['success']:
        >>>     print(f"Downscaled: {result['downscaled']}")
        >>>     print(f"Final size: {result['final_size_mb']} MB")
    """
    try:
        # Import settings from config if not provided
        from api.config import (
            VIDEO_DOWNSCALE_THRESHOLD_MB,
            FFMPEG_CRF_QUALITY,
            FFMPEG_PRESET,
            FFMPEG_TARGET_HEIGHT
        )
        
        if size_threshold_mb is None:
            size_threshold_mb = VIDEO_DOWNSCALE_THRESHOLD_MB
        if crf is None:
            crf = FFMPEG_CRF_QUALITY
        if preset is None:
            preset = FFMPEG_PRESET
        if target_height is None:
            target_height = FFMPEG_TARGET_HEIGHT
        
        # Validate input
        if not Path(video_path).exists():
            return {'success': False, 'error': f'Video not found: {video_path}'}
        
        # Get FFmpeg
        ffmpeg_check = check_ffmpeg_available()
        if not ffmpeg_check['available']:
            return {'success': False, 'error': f'FFmpeg not available: {ffmpeg_check["error"]}'}
        
        ffmpeg_path = ffmpeg_check['path']
        
        # 1. Get original FPS (to preserve it)
        fps = get_video_fps(video_path, ffmpeg_path)
        
        # 2. Estimate trimmed size based on duration percentage
        original_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
        duration_result = get_video_duration(video_path)
        
        if duration_result['success']:
            original_duration = duration_result['duration']
            trim_duration = end_seconds - start_seconds
            # Simple percentage-based estimation
            duration_percentage = trim_duration / original_duration
            estimated_size_mb = original_size_mb * duration_percentage
        else:
            # Conservative: assume trimmed will be same size
            estimated_size_mb = original_size_mb
        
        # 3. Decide: Downscale or not?
        should_downscale = estimated_size_mb >= size_threshold_mb
        
        # 4. Generate output path
        if output_path is None:
            temp_dir = Path(tempfile.gettempdir()) / "pt_v2a"
            temp_dir.mkdir(exist_ok=True)
            timestamp = int(Path(video_path).stat().st_mtime)
            suffix = "_480p" if should_downscale else ""
            output_path = str(temp_dir / f"trimmed_{timestamp}_{start_seconds}_{end_seconds}{suffix}.mp4")
        
        # 5. Build FFmpeg command (combined trim + optional downscale)
        start_time = time.time()
        
        if should_downscale:
            # Trim + Downscale to 480p in ONE operation
            cmd = [
                str(ffmpeg_path),
                '-y',
                '-an',
                '-ss', str(start_seconds),
                '-to', str(end_seconds),
                '-i', str(video_path),
                '-vf', f'scale=-2:{target_height}',  # Downscale (may upscale if <480p)
                '-c:v', 'libx264',
                '-preset', preset,
                '-crf', str(crf),
                '-r', str(fps),       # EXPLICIT FPS (preserve original!)
                '-c:a', 'aac',
                '-maxrate', '3M',     # Cap bitrate at 3 Mbps (prevents excessively large files)
                '-bufsize', '6M',     # VBV buffer = 2x maxrate (allows headroom for complex scenes)
                output_path
            ]
        else:
            # Just trim (preserve original resolution)
            cmd = [
                str(ffmpeg_path),
                '-y',
                '-an',
                '-ss', str(start_seconds),
                '-to', str(end_seconds),
                '-i', str(video_path),
                '-c:v', 'libx264',
                '-preset', preset,
                '-crf', str(crf),
                '-r', str(fps),       # EXPLICIT FPS (preserve original!)
                '-c:a', 'aac',
                '-maxrate', '3M',     # Cap bitrate at 3 Mbps (prevents excessively large files)
                '-bufsize', '6M',     # VBV buffer = 2x maxrate (allows headroom for complex scenes)
                output_path
            ]
        
        # 6. Execute
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        encoding_time = time.time() - start_time
        
        if result.returncode != 0:
            return {'success': False, 'error': f'FFmpeg failed: {result.stderr}'}
        
        if not Path(output_path).exists():
            return {'success': False, 'error': 'Output file not created'}
        
        final_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        
        return {
            'success': True,
            'output_path': output_path,
            'duration': end_seconds - start_seconds,
            'downscaled': should_downscale,
            'original_size_mb': round(original_size_mb, 2),
            'estimated_size_mb': round(estimated_size_mb, 2),
            'final_size_mb': round(final_size_mb, 2),
            'encoding_time': round(encoding_time, 2),
            'error': None
        }
        
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Encoding timeout (60s)'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_video_duration(video_path: str) -> Dict[str, any]:
    """
    Get video file duration using FFprobe.
    
    Uses FFprobe (part of FFmpeg) to read video metadata.
    
    Args:
        video_path (str): Path to video file
    
    Returns:
        dict: {
            'success': bool,
            'duration': float or None (duration in seconds),
            'error': str or None
        }
    
    Example:
        >>> result = get_video_duration("video.mp4")
        >>> if result['success']:
        >>>     print(f"Video duration: {result['duration']}s")
        >>> else:
        >>>     print(f"Error: {result['error']}")
    
    Note:
        Uses FFprobe's JSON output format for reliable parsing
    """
    try:
        # Validate input file
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {
                'success': False,
                'duration': None,
                'error': f'Video file not found: {video_path}'
            }
        
        # Check FFmpeg availability (FFprobe is part of FFmpeg)
        ffmpeg_check = check_ffmpeg_available()
        if not ffmpeg_check['available']:
            return {
                'success': False,
                'duration': None,
                'error': f'FFmpeg/FFprobe not available: {ffmpeg_check["error"]}'
            }
        
        # Try to find FFprobe (usually in same directory as FFmpeg)
        ffmpeg_path = Path(ffmpeg_check['path'])
        ffprobe_path = ffmpeg_path.parent / ('ffprobe.exe' if ffmpeg_path.suffix == '.exe' else 'ffprobe')
        
        # If ffprobe not found next to ffmpeg, try system PATH
        if not ffprobe_path.exists():
            ffprobe_exe = shutil.which('ffprobe')
            if ffprobe_exe:
                ffprobe_path = Path(ffprobe_exe)
        
        # If FFprobe is available, use it (preferred method)
        if ffprobe_path.exists():
            # Build FFprobe command to get duration
            # -v quiet: suppress warnings
            # -print_format json: output as JSON
            # -show_format: show container/format info (includes duration)
            cmd = [
                str(ffprobe_path),
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(video_path)
            ]
            
            # Execute FFprobe
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10  # 10 second timeout
            )
            
            if result.returncode != 0:
                return {
                    'success': False,
                    'duration': None,
                    'error': f'FFprobe failed: {result.stderr}'
                }
            
            # Parse JSON output
            try:
                data = json.loads(result.stdout)
                duration_str = data.get('format', {}).get('duration')
                
                if duration_str is None:
                    return {
                        'success': False,
                        'duration': None,
                        'error': 'Duration not found in FFprobe output'
                    }
                
                duration = float(duration_str)
                
                return {
                    'success': True,
                    'duration': duration,
                    'error': None
                }
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                return {
                    'success': False,
                    'duration': None,
                    'error': f'Failed to parse FFprobe output: {e}'
                }
        
        # Fallback: Use FFmpeg to get duration (works when FFprobe is not available)
        # FFmpeg prints duration in stderr when analyzing input file
        else:
            cmd = [
                str(ffmpeg_path),
                '-i', str(video_path),
                '-f', 'null',
                '-'
            ]
            
            # Execute FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Parse duration from stderr (FFmpeg prints: "Duration: HH:MM:SS.ms")
            try:
                stderr = result.stderr
                duration_match = None
                for line in stderr.split('\n'):
                    if 'Duration:' in line:
                        # Extract duration string like "00:01:23.45"
                        import re
                        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', line)
                        if match:
                            hours, minutes, seconds, centiseconds = match.groups()
                            duration = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centiseconds) / 100
                            return {
                                'success': True,
                                'duration': duration,
                                'error': None
                            }
                
                return {
                    'success': False,
                    'duration': None,
                    'error': 'Could not extract duration from FFmpeg output'
                }
                
            except (ValueError, AttributeError) as e:
                return {
                    'success': False,
                    'duration': None,
                    'error': f'Failed to parse FFmpeg output: {str(e)}'
                }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'duration': None,
            'error': 'FFprobe timed out (10s limit)'
        }
    except Exception as e:
        return {
            'success': False,
            'duration': None,
            'error': f'Duration check error: {str(e)}'
        }


def get_video_fps(video_path: str, ffmpeg_path: Optional[str] = None) -> float:
    """
    Get video FPS (frames per second) using FFmpeg.
    
    Parses FFmpeg's stderr output to extract framerate information.
    Handles both decimal (30.0 fps) and fractional (30000/1001 fps) formats.
    
    Args:
        video_path: Path to video file
        ffmpeg_path: Path to FFmpeg executable (auto-detected if None)
    
    Returns:
        float: FPS value (defaults to 30.0 if detection fails)
    
    Example:
        >>> fps = get_video_fps("video.mp4")
        >>> print(f"Video FPS: {fps}")
    """
    try:
        # Get FFmpeg path if not provided
        if ffmpeg_path is None:
            ffmpeg_check = check_ffmpeg_available()
            if not ffmpeg_check['available']:
                return 30.0  # Fallback
            ffmpeg_path = ffmpeg_check['path']
        
        # Run FFmpeg to get stream info
        fps_cmd = [
            str(ffmpeg_path),
            '-i', str(video_path),
            '-f', 'null',
            '-'
        ]
        result = subprocess.run(fps_cmd, capture_output=True, text=True, timeout=5)
        
        # Parse FPS from stderr (format: "Stream #0:0: Video: ..., 30 fps" or "29.97 fps")
        import re
        fps_match = re.search(r'(\d+(?:\.\d+)?)\s*fps', result.stderr)
        if fps_match:
            return float(fps_match.group(1))
        
        # Try alternative format: "30000/1001 fps"
        fps_match = re.search(r'(\d+)/(\d+)\s*fps', result.stderr)
        if fps_match:
            num, den = int(fps_match.group(1)), int(fps_match.group(2))
            return num / den
        
        # Default fallback
        return 30.0
        
    except Exception:
        return 30.0  # Fallback if FPS detection fails


def get_video_bitrate(video_path: str) -> Dict[str, any]:
    """
    Get video bitrate using FFprobe.
    
    Args:
        video_path: Path to video file
    
    Returns:
        dict: {
            'success': bool,
            'bitrate_mbps': float,  # Megabits per second
            'duration': float,      # Seconds
            'error': str or None
        }
    
    Example:
        >>> result = get_video_bitrate("video.mp4")
        >>> if result['success']:
        >>>     print(f"Bitrate: {result['bitrate_mbps']:.1f} Mbps")
    """
    try:
        # Get FFprobe path
        try:
            import imageio_ffmpeg
            ffprobe_path = imageio_ffmpeg.get_ffmpeg_exe().replace('ffmpeg', 'ffprobe')
        except ImportError:
            ffprobe_path = shutil.which('ffprobe')
        
        if not ffprobe_path:
            return {
                'success': False,
                'bitrate_mbps': 0,
                'duration': 0,
                'error': 'FFprobe not found'
            }
        
        # FFprobe command to get bitrate and duration
        command = [
            ffprobe_path,
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'format=bit_rate,duration',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            return {
                'success': False,
                'bitrate_mbps': 0,
                'duration': 0,
                'error': f'FFprobe failed: {result.stderr}'
            }
        
        data = json.loads(result.stdout)
        
        # Extract bitrate (in bits per second)
        bitrate_bps = int(data.get('format', {}).get('bit_rate', 0))
        bitrate_mbps = bitrate_bps / 1_000_000  # Convert to Mbps
        
        # Extract duration
        duration = float(data.get('format', {}).get('duration', 0))
        
        return {
            'success': True,
            'bitrate_mbps': round(bitrate_mbps, 2),
            'duration': round(duration, 2),
            'error': None
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'bitrate_mbps': 0,
            'duration': 0,
            'error': 'FFprobe timeout (5s limit)'
        }
    except Exception as e:
        return {
            'success': False,
            'bitrate_mbps': 0,
            'duration': 0,
            'error': str(e)
        }


def downscale_video(
    video_path: str,
    output_path: str = None,
    target_height: Optional[int] = None,
    crf: Optional[int] = None,
    preset: Optional[str] = None
) -> Dict[str, any]:
    """
    Downscale video to target height while preserving FPS and aspect ratio.
    
    Only changes:
    - Resolution height (to 480p or specified)
    - Bitrate (via CRF quality-based encoding)
    
    Preserves:
    - FPS (framerate)
    - Aspect ratio (width calculated automatically)
    - Duration
    
    Args:
        video_path: Input video path
        output_path: Output path (default: temp file)
        target_height: Target height in pixels (default: from config.FFMPEG_TARGET_HEIGHT)
        crf: Quality factor 0-51, lower=better (default: from config.FFMPEG_CRF_QUALITY)
        preset: FFmpeg preset ultrafast/veryfast/fast/medium (default: from config.FFMPEG_PRESET)
    
    Returns:
        dict: {
            'success': bool,
            'output_path': str,
            'original_size_mb': float,
            'downscaled_size_mb': float,
            'compression_ratio': float,
            'encoding_time': float,
            'original_fps': float,
            'error': str or None
        }
    
    Example:
        >>> result = downscale_video("large_video.mov")
        >>> if result['success']:
        >>>     print(f"Compressed {result['compression_ratio']}x smaller")
        >>>     print(f"New file: {result['output_path']}")
    """
    import time
    
    try:
        # Import settings from config if not provided
        from api.config import (
            FFMPEG_CRF_QUALITY,
            FFMPEG_PRESET,
            FFMPEG_TARGET_HEIGHT
        )
        
        if crf is None:
            crf = FFMPEG_CRF_QUALITY
        if preset is None:
            preset = FFMPEG_PRESET
        if target_height is None:
            target_height = FFMPEG_TARGET_HEIGHT
        
        # Get FFmpeg/FFprobe paths
        # Priority: imageio_ffmpeg (embedded in plugin) > system PATH
        ffmpeg_path = None
        ffprobe_path = None
        
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            
            # Try to find ffprobe next to ffmpeg
            ffmpeg_dir = Path(ffmpeg_path).parent
            if os.name == 'nt':  # Windows
                ffprobe_candidate = ffmpeg_dir / 'ffprobe.exe'
            else:  # Linux/Mac
                ffprobe_candidate = ffmpeg_dir / 'ffprobe'
            
            if ffprobe_candidate.exists():
                ffprobe_path = str(ffprobe_candidate)
            else:
                # Fallback to system PATH
                ffprobe_path = shutil.which('ffprobe')
                
        except ImportError:
            # Fallback to system PATH for both
            ffmpeg_path = shutil.which('ffmpeg')
            ffprobe_path = shutil.which('ffprobe')
        
        if not ffmpeg_path:
            return {
                'success': False,
                'error': 'FFmpeg not found (imageio_ffmpeg not installed and not in PATH)'
            }
        
        # Get original FPS (to preserve it)
        fps = get_video_fps(video_path, ffmpeg_path)
        
        # Generate output path if not provided
        if output_path is None:
            temp_dir = Path(tempfile.gettempdir()) / "pt_v2a"
            temp_dir.mkdir(exist_ok=True)
            suffix = Path(video_path).suffix
            output_path = str(temp_dir / f"downscaled_{int(time.time())}{suffix}")
        
        # Original file size
        original_size = Path(video_path).stat().st_size / (1024 * 1024)  # MB
        
        # FFmpeg command: downscale with CRF quality-based encoding + bitrate cap
        command = [
            str(ffmpeg_path),
            '-i', str(video_path),
            '-vf', f'scale=-2:{target_height}',  # -2 = auto-calculate width (even number)
            '-c:v', 'libx264',
            '-crf', str(crf),
            '-preset', preset,
            '-maxrate', '3M',     # Cap bitrate at 3 Mbps (prevents excessively large files)
            '-bufsize', '6M',     # VBV buffer = 2x maxrate (allows headroom for complex scenes)
            '-r', str(fps),       # EXPLICIT FPS (preserve original!)
            '-an',                # Remove audio (not needed for video-to-audio models)
            '-y',
            str(output_path)
        ]
        
        start_time = time.time()
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        encoding_time = time.time() - start_time
        
        if result.returncode != 0:
            return {
                'success': False,
                'error': f'FFmpeg encoding failed: {result.stderr}'
            }
        
        if not Path(output_path).exists():
            return {
                'success': False,
                'error': 'Output file not created'
            }
        
        downscaled_size = Path(output_path).stat().st_size / (1024 * 1024)  # MB
        compression_ratio = original_size / downscaled_size if downscaled_size > 0 else 0
        
        return {
            'success': True,
            'output_path': output_path,
            'original_size_mb': round(original_size, 2),
            'downscaled_size_mb': round(downscaled_size, 2),
            'compression_ratio': round(compression_ratio, 1),
            'encoding_time': round(encoding_time, 2),
            'original_fps': round(fps, 2),
            'error': None
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'Encoding timeout (>30s)'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


