"""
Video validation utilities

Provides:
- Video duration validation
- Video file format validation
"""

from pathlib import Path
from typing import Dict

# Supported video formats for Pro Tools integration
SUPPORTED_VIDEO_FORMATS = {
    # Common container formats
    '.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm', '.flv', '.wmv', '.f4v',
    # Professional / broadcast
    '.mxf', '.m2ts', '.mts', '.ts',
    # MPEG legacy
    '.mpg', '.mpeg',
    # Optical media
    '.vob',
    # Open / mobile
    '.ogv', '.3gp', '.3g2',
}


def validate_video_duration(
    duration_seconds: float,
    max_duration: float = 12.0,
    min_duration: float = 4.0
) -> Dict[str, any]:
    """
    Validate video duration against minimum and maximum allowed duration.
    
    MMAudio was trained on 8-second clips, so we enforce a 4-12 second
    range to ensure good results.
    
    Args:
        duration_seconds (float): Video duration in seconds
        max_duration (float): Maximum allowed duration (default: 12.0s)
        min_duration (float): Minimum allowed duration (default: 4.0s)
    
    Returns:
        dict: {
            'valid': bool,
            'duration': float,
            'min_duration': float,
            'max_duration': float,
            'error': str or None
        }
    
    Example:
        >>> result = validate_video_duration(8.5)
        >>> if result['valid']:
        >>>     print("Duration OK")
        >>> else:
        >>>     print(f"Invalid: {result['error']}")
    
    Note:
        Based on MMAudio training data (8s clips), we enforce strict
        4-12s range. NO fallback to full video - this is intentional
        to ensure quality results.
    """
    if duration_seconds <= 0:
        return {
            'valid': False,
            'duration': duration_seconds,
            'min_duration': min_duration,
            'max_duration': max_duration,
            'error': f'Invalid duration: {duration_seconds:.2f}s (must be positive)'
        }
    
    if duration_seconds < min_duration:
        return {
            'valid': False,
            'duration': duration_seconds,
            'min_duration': min_duration,
            'max_duration': max_duration,
            'error': f'Duration {duration_seconds:.2f}s is below minimum {min_duration:.2f}s'
        }
    
    if duration_seconds > max_duration:
        return {
            'valid': False,
            'duration': duration_seconds,
            'min_duration': min_duration,
            'max_duration': max_duration,
            'error': f'Duration {duration_seconds:.2f}s exceeds maximum {max_duration:.2f}s'
        }
    
    return {
        'valid': True,
        'duration': duration_seconds,
        'min_duration': min_duration,
        'max_duration': max_duration,
        'error': None
    }


def validate_video_file(video_path: str) -> Path:
    """
    Validate video file exists and has supported format.
    
    Args:
        video_path (str): Path to video file
    
    Returns:
        Path: Validated path object
    
    Raises:
        FileNotFoundError: If video file doesn't exist
        ValueError: If path is not a file or format not supported
    
    Example:
        >>> try:
        >>>     path = validate_video_file("video.mp4")
        >>>     print(f"Valid video: {path}")
        >>> except (FileNotFoundError, ValueError) as e:
        >>>     print(f"Invalid: {e}")
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    if not video_path.is_file():
        raise ValueError(f"Path is not a file: {video_path}")
    
    if video_path.suffix.lower() not in SUPPORTED_VIDEO_FORMATS:
        supported = ', '.join(sorted(SUPPORTED_VIDEO_FORMATS))
        raise ValueError(
            f"Unsupported video format '{video_path.suffix}'. "
            f"Supported formats: {supported}"
        )
    
    return video_path
