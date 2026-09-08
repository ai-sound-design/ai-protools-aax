"""
CLI utilities for Pro Tools V2A integration.

This package contains shared CLI action handlers used by both
MMAudio and HunyuanVideo-Foley API clients.
"""

from .actions import (
    action_check_ffmpeg,
    action_get_video_info,
    action_get_duration,
    action_import_audio,
)

__all__ = [
    'action_check_ffmpeg',
    'action_get_video_info',
    'action_get_duration',
    'action_import_audio',
]