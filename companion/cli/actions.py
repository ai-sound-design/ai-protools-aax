"""
Shared CLI actions for Pro Tools V2A integration.

This module contains action handlers used by both MMAudio and HunyuanVideo-Foley
API clients. Each action returns a JSON-serializable result dict.

Functions accept a log_debug_func parameter for flexible logging integration.
"""

import json
import sys
from typing import Callable, Optional, Dict, Any

from video import check_ffmpeg_available, get_video_duration
from ptsl_integration import (
    get_video_timeline_selection,
    get_video_file_from_protools,
    import_audio_to_pro_tools,
)


def action_check_ffmpeg(log_debug_func: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Check FFmpeg availability.
    
    Args:
        log_debug_func: Optional logging function for debug output
        
    Returns:
        dict with 'available' (bool) and optional 'error' (str)
    """
    if log_debug_func:
        log_debug_func("=== DEBUG: check_ffmpeg action START ===")
    
    result = check_ffmpeg_available()
    
    if log_debug_func:
        log_debug_func(f"=== DEBUG: FFmpeg available: {result['available']} ===")
    
    return result


def action_get_video_info(log_debug_func: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Get timeline selection AND video file in one PTSL call (faster!).
    
    Args:
        log_debug_func: Optional logging function for debug output
        
    Returns:
        dict with timeline selection info and video file path
    """
    if log_debug_func:
        log_debug_func("=== DEBUG: get_video_info action START ===")
    
    # Get timeline selection
    selection = get_video_timeline_selection()
    
    if log_debug_func:
        log_debug_func(f"=== DEBUG: Timeline selection: {selection['success']} ===")
    
    if not selection['success']:
        # Return error from timeline selection
        return selection
    
    # Get video file path, passing timeline selection for validation
    video_file = get_video_file_from_protools(
        timeline_in_seconds=selection.get('in_seconds'),
        timeline_out_seconds=selection.get('out_seconds')
    )
    
    if log_debug_func:
        log_debug_func(f"=== DEBUG: Video file lookup: {video_file['success']} ===")
    
    # Combine results into single response
    combined_result = {
        'success': selection['success'] and video_file['success'],
        # Timeline selection fields
        'in_time': selection.get('in_time'),
        'out_time': selection.get('out_time'),
        'in_seconds': selection.get('in_seconds'),
        'out_seconds': selection.get('out_seconds'),
        'duration_seconds': selection.get('duration_seconds'),
        'fps': selection.get('fps'),
        # Video file fields
        'video_path': video_file.get('video_path'),
        'video_files': video_file.get('video_files', []),
        'video_count': video_file.get('video_count', 0),
        # Error from whichever failed (if any)
        'error': video_file.get('error') if not video_file['success'] else selection.get('error')
    }
    
    if log_debug_func:
        log_debug_func("=== DEBUG: Combined result ready ===")
    
    return combined_result


def action_get_duration(video_path: str, log_debug_func: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Get video file duration using FFprobe.
    
    Args:
        video_path: Path to video file
        log_debug_func: Optional logging function for debug output
        
    Returns:
        dict with 'success' (bool), 'duration' (float), and optional 'error' (str)
    """
    if log_debug_func:
        log_debug_func("=== DEBUG: get_duration action START ===")
        log_debug_func(f"Video path: {video_path}")
    
    if not video_path:
        error_response = {
            'success': False,
            'error': 'video_path argument required for get_duration action'
        }
        if log_debug_func:
            log_debug_func(f"ERROR: {error_response['error']}")
        return error_response
    
    if log_debug_func:
        log_debug_func("Calling get_video_duration()...")
    
    result = get_video_duration(video_path)
    
    if log_debug_func:
        log_debug_func(f"Result: {result}")
    
    return result


def action_import_audio(
    audio_path: str,
    timecode: Optional[str] = None,
    log_debug_func: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Import audio file to Pro Tools timeline.
    
    Args:
        audio_path: Path to audio file to import
        timecode: Optional timecode position for import (e.g., "00:00:07:00")
        log_debug_func: Optional logging function for debug output
        
    Returns:
        dict with 'success' (bool), 'audio_path' (str), and optional 'error' (str)
    """
    if log_debug_func:
        log_debug_func("=== DEBUG: import_audio action START ===")
    
    if not audio_path:
        error_result = {
            'success': False,
            'error': 'audio_path argument required for import_audio action'
        }
        if log_debug_func:
            log_debug_func(f"ERROR: {error_result['error']}")
        return error_result
    
    if log_debug_func:
        log_debug_func(f"Audio path: {audio_path}")
        if timecode:
            log_debug_func(f"Import timecode: {timecode}")
        else:
            log_debug_func("Import timecode: Not specified (will use session start)")
    
    # Import to Pro Tools timeline
    try:
        success = import_audio_to_pro_tools(
            audio_path=audio_path,
            timecode=timecode
        )
        
        result = {
            'success': success,
            'audio_path': audio_path
        }
        
        if not success:
            result['error'] = 'Failed to import audio to Pro Tools'
        
        if log_debug_func:
            log_debug_func(f"=== DEBUG: Import result: {success} ===")
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        
        if log_debug_func:
            log_debug_func(f"ERROR: Import exception: {error_msg}")
        
        error_result = {
            'success': False,
            'error': error_msg
        }
        
        return error_result