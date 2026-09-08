"""
PTSL Integration Package
Handles Pro Tools Scripting Library (PTSL) communication via gRPC

Using py-ptsl library for maintained PTSL integration.

Modules:
- ptsl_client: Audio import to Pro Tools
- timeline: Timeline selection and timecode operations
- video: Video file detection from Pro Tools session
"""

# Import from py-ptsl based implementation (now the main version)
from .ptsl_client import import_audio_to_pro_tools
from .timeline import get_video_timeline_selection, timecode_to_seconds
from .video import get_video_file_from_protools

__all__ = [
    'import_audio_to_pro_tools',
    'get_video_timeline_selection',
    'timecode_to_seconds',
    'get_video_file_from_protools',
]
