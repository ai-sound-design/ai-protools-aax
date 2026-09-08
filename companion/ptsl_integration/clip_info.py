"""
Automatic video clip detection via PTSL GetClipList.

This module provides functions to automatically detect trimmed video clips
without requiring manual user input for clip offsets.

Workflow:
1. User cuts video clip in Pro Tools (using Blade tool, etc.)
2. User selects the trimmed clip
3. System automatically reads clip boundaries from GetClipList
4. FFmpeg trims exact portion needed from source video file
"""

from typing import Dict, Optional, List
import sys


def frames_to_seconds(frames: int, framerate: float) -> float:
    """
    Convert frame count to seconds.
    
    Args:
        frames: Number of frames
        framerate: Frames per second (e.g. 30, 29.97, 25, 24)
    
    Returns:
        Time in seconds
    
    Example:
        >>> frames_to_seconds(150, 30.0)
        5.0
        >>> frames_to_seconds(150, 29.97)
        5.005005...
    """
    if framerate <= 0:
        raise ValueError(f"Invalid framerate: {framerate}")
    
    return frames / framerate


def get_session_framerate(engine) -> float:
    """
    Get session framerate from Pro Tools.
    
    Args:
        engine: PTSL Engine instance
    
    Returns:
        Framerate as float (e.g. 30.0, 29.97, 25.0, 24.0)
    
    Raises:
        RuntimeError: If framerate cannot be determined
    """
    try:
        from ptsl import PTSL_pb2 as pt
        
        # Get timecode rate enum
        tc_rate = engine.session_timecode_rate()
        
        # Map Pro Tools timecode rates to numeric framerates
        # Use hasattr checks for backward compatibility with older py-ptsl versions
        framerate_map = {}
        
        # Common framerates (likely available in all versions)
        if hasattr(pt, 'STCR_Fps23976'):
            framerate_map[pt.STCR_Fps23976] = 23.976
        if hasattr(pt, 'STCR_Fps24'):
            framerate_map[pt.STCR_Fps24] = 24.0
        if hasattr(pt, 'STCR_Fps25'):
            framerate_map[pt.STCR_Fps25] = 25.0
        if hasattr(pt, 'STCR_Fps2997'):
            framerate_map[pt.STCR_Fps2997] = 29.97
        if hasattr(pt, 'STCR_Fps2997Drop'):
            framerate_map[pt.STCR_Fps2997Drop] = 29.97
        if hasattr(pt, 'STCR_Fps30'):
            framerate_map[pt.STCR_Fps30] = 30.0
        if hasattr(pt, 'STCR_Fps30Drop'):
            framerate_map[pt.STCR_Fps30Drop] = 30.0
        
        # Higher framerates (added in PTSL 2025.06, may not be in older versions)
        if hasattr(pt, 'STCR_Fps4795'):
            framerate_map[pt.STCR_Fps4795] = 47.95
        if hasattr(pt, 'STCR_Fps48'):
            framerate_map[pt.STCR_Fps48] = 48.0
        if hasattr(pt, 'STCR_Fps50'):
            framerate_map[pt.STCR_Fps50] = 50.0
        if hasattr(pt, 'STCR_Fps5994'):
            framerate_map[pt.STCR_Fps5994] = 59.94
        if hasattr(pt, 'STCR_Fps5994Drop'):
            framerate_map[pt.STCR_Fps5994Drop] = 59.94
        if hasattr(pt, 'STCR_Fps60'):
            framerate_map[pt.STCR_Fps60] = 60.0
        if hasattr(pt, 'STCR_Fps60Drop'):
            framerate_map[pt.STCR_Fps60Drop] = 60.0
        if hasattr(pt, 'STCR_Fps100'):
            framerate_map[pt.STCR_Fps100] = 100.0
        if hasattr(pt, 'STCR_Fps120'):
            framerate_map[pt.STCR_Fps120] = 120.0
        
        framerate = framerate_map.get(tc_rate)
        if framerate is None:
            raise RuntimeError(f"Unknown timecode rate: {tc_rate}")
        
        return framerate
    
    except Exception as e:
        raise RuntimeError(f"Failed to get session framerate: {e}")


def get_clip_list(engine) -> List[Dict]:
    """
    Get list of all clips in session via PTSL GetClipList command.
    
    Args:
        engine: PTSL Engine instance
    
    Returns:
        List of clip dictionaries with keys:
        - clip_id: Unique clip identifier
        - clip_full_name: Full clip name
        - clip_type: Clip type (CType_Video, CType_Audio, etc.)
        - file_id: Source file identifier
        - start_point: {position: int, time_type: str} - start in source
        - end_point: {position: int, time_type: str} - end in source
        - sync_point: {position: int, time_type: str} (optional)
    
    Note:
        GetClipList returns clips from the Clips List (bin), not necessarily
        clips on the timeline. Video clips must be imported to the Clips List.
    """
    try:
        response_json = engine.client.run_command(125, {})  # Command 125 = GetClipList
        
        if response_json and 'clip_list' in response_json:
            return response_json['clip_list']
        else:
            return []
    
    except Exception as e:
        print(f"Warning: GetClipList failed: {e}", file=sys.stderr)
        return []


def find_clip_by_file_id(clips: List[Dict], file_id: str) -> Optional[Dict]:
    """
    Find a clip in the clip list by its file_id.
    
    Args:
        clips: List of clip dictionaries from get_clip_list()
        file_id: File ID to search for
    
    Returns:
        Clip dictionary if found, None otherwise
    
    Note:
        If multiple clips reference the same file (e.g. trimmed versions),
        returns the first match. Consider using clip_id for exact matching.
    """
    for clip in clips:
        if clip.get('file_id') == file_id:
            return clip
    return None


def get_clip_trim_info(
    engine,
    file_id: str,
    company_name: str = "Master Thesis",
    app_name: str = "PT V2A Plugin"
) -> Dict[str, any]:
    """
    Get automatic trim information for a video clip.
    
    This function reads the clip boundaries from Pro Tools GetClipList
    and calculates the exact portion to trim, without requiring manual
    user input for clip offsets.
    
    Workflow:
    1. Get session framerate
    2. Get all clips via GetClipList
    3. Find clip matching the file_id
    4. Extract start/end points (in frames)
    5. Convert to seconds
    
    Args:
        engine: PTSL Engine instance
        file_id: File ID of the video clip
        company_name: Company name for PTSL connection
        app_name: Application name for PTSL connection
    
    Returns:
        Dictionary with:
        - success: bool
        - start_seconds: float (start position in source video)
        - end_seconds: float (end position in source video)
        - duration_seconds: float
        - framerate: float
        - clip_name: str
        - error: str (if success=False)
    
    Example:
        >>> result = get_clip_trim_info(engine, "b6bf000f-d8f7-214b-ae6e-6bba1db70de9")
        >>> if result['success']:
        >>>     print(f"Trim from {result['start_seconds']}s to {result['end_seconds']}s")
    """
    try:
        # Get session framerate
        framerate = get_session_framerate(engine)
        print(f"Session framerate: {framerate} fps", file=sys.stderr)
        
        # Get all clips
        clips = get_clip_list(engine)
        print(f"Found {len(clips)} clips in Clips List", file=sys.stderr)
        
        # Find our clip
        clip = find_clip_by_file_id(clips, file_id)
        if not clip:
            return {
                'success': False,
                'error': f'No clip found with file_id={file_id}. Make sure the video clip is imported to the Clips List (not just on timeline).'
            }
        
        # Extract frame positions
        start_point = clip.get('start_point', {})
        end_point = clip.get('end_point', {})
        
        if not start_point or not end_point:
            return {
                'success': False,
                'error': 'Clip missing start_point or end_point data'
            }
        
        # Check time type - we expect frames
        start_time_type = start_point.get('time_type', '')
        end_time_type = end_point.get('time_type', '')
        
        if 'Frame' not in start_time_type or 'Frame' not in end_time_type:
            print(f"Warning: Unexpected time type - start: {start_time_type}, end: {end_time_type}", file=sys.stderr)
        
        # Get frame positions
        start_frame = start_point.get('position', 0)
        end_frame = end_point.get('position', 0)
        
        # Convert to seconds
        start_seconds = frames_to_seconds(start_frame, framerate)
        end_seconds = frames_to_seconds(end_frame, framerate)
        duration_seconds = end_seconds - start_seconds
        
        print(f"Clip '{clip.get('clip_full_name')}': frames {start_frame}-{end_frame} = {start_seconds:.2f}s-{end_seconds:.2f}s ({duration_seconds:.2f}s)", file=sys.stderr)
        
        return {
            'success': True,
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'duration_seconds': duration_seconds,
            'framerate': framerate,
            'clip_name': clip.get('clip_full_name', 'Unknown'),
            'clip_id': clip.get('clip_id', ''),
            'start_frame': start_frame,
            'end_frame': end_frame,
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': f'Failed to get clip trim info: {str(e)}'
        }


def get_clip_info_for_selected_video(engine) -> Optional[Dict]:
    """
    Get clip information for the selected video clip.
    
    Uses the "rename trick" to reliably identify the exact selected clip:
    1. Temporarily rename the selected clip with a unique name
    2. Find it in GetClipList to get all its information
    3. Rename it back to the original name
    4. Return the clip info with frame boundaries
    
    This method is reliable even when multiple clips share the same file_id
    (e.g., when a video is cut into multiple clips like test_video-01, test_video-02).
    
    Args:
        engine: PTSL Engine instance
    
    Returns:
        Dictionary with clip information if found:
        - clip_name: str - Name of the clip
        - clip_id: str - Unique clip identifier
        - file_id: str - Source file identifier  
        - file_path: str - Path to the video file
        - start_frame: int - Start frame in source video
        - end_frame: int - End frame in source video
        - clip_type: str - Clip type (should be 'CType_Video')
        
        Returns None if no video clip found or selected.
    
    Example:
        >>> clip_info = get_clip_info_for_selected_video(engine)
        >>> if clip_info:
        >>>     print(f"Clip: {clip_info['clip_name']}")
        >>>     print(f"Frames: {clip_info['start_frame']}-{clip_info['end_frame']}")
    
    Raises:
        RuntimeError: If clip identification or rename operations fail
    """
    try:
        import uuid
        from ptsl import PTSL_pb2 as pt
        
        print("[CLIP INFO] Identifying selected video clip...", file=sys.stderr)
        
        # Step 1: Get the file_path of the selected clip  
        print("[CLIP INFO] Getting selected clip's file location...", file=sys.stderr)
        
        # Use ClipsList filter to get selected clip
        if hasattr(pt, 'FLTFilter_SelectedClipsClipsList'):
            filter_value = pt.FLTFilter_SelectedClipsClipsList
        else:
            filter_value = pt.SelectedClipsClipsList
        
        file_locations = engine.get_file_location(filters=[filter_value])
        
        if not file_locations:
            print("[CLIP INFO] No clip selected in Clips List", file=sys.stderr)
            return None
        
        # CRITICAL FIX: Filter for VIDEO files only (exclude audio clips)
        # get_file_location() returns ALL selected clips, including audio
        # We need to find the VIDEO clip, not an imported audio clip
        video_location = None
        for loc in file_locations:
            # Check file extension to identify video files
            path_lower = loc.path.lower()
            if path_lower.endswith((
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
            )):
                video_location = loc
                print(f"[CLIP INFO] Found video file: {loc.path}", file=sys.stderr)
                break
        
        if not video_location:
            print("[CLIP INFO] No VIDEO clip selected (only audio clips found)", file=sys.stderr)
            print(f"[CLIP INFO] Selected files: {[loc.path for loc in file_locations]}", file=sys.stderr)
            return None
        
        selected_file_id = video_location.file_id
        file_path = video_location.path
        
        print(f"[CLIP INFO] Selected file: {file_path}", file=sys.stderr)
        print(f"[CLIP INFO] File ID: {selected_file_id}", file=sys.stderr)
        
        # Step 2: Get all clips BEFORE rename (to find original name later)
        print("[CLIP INFO] Getting clip list...", file=sys.stderr)
        response_before = engine.client.run_command(125, {})  # GetClipList
        
        if not response_before or 'clip_list' not in response_before:
            print("[CLIP INFO] Failed to get clip list", file=sys.stderr)
            return None
        
        clips_before = response_before['clip_list']
        
        # Step 3: Rename selected clip to temporary unique name
        # Use full UUID (32 chars) + timestamp to guarantee uniqueness across renders
        import time
        timestamp = int(time.time() * 1000)  # milliseconds
        temp_name = f"__TEMP_SELECTED_{uuid.uuid4().hex}_{timestamp}__"
        print(f"[CLIP INFO] Temporarily renaming selected clip...", file=sys.stderr)
        print(f"[CLIP INFO] Temp name: {temp_name}", file=sys.stderr)
        
        # Use ClipsList location
        if hasattr(pt, 'CLocation_ClipsList'):
            clip_loc = pt.CLocation_ClipsList
        else:
            clip_loc = pt.CL_ClipsList
        
        print(f"[CLIP INFO] Using clip location: {clip_loc}", file=sys.stderr)
        
        engine.rename_selected_clip(
            new_name=temp_name,
            rename_file=False,  # Don't rename the actual file!
            clip_location=clip_loc
        )
        
        print(f"[CLIP INFO] Rename command completed", file=sys.stderr)
        
        # Step 4: Get clip list AFTER rename to find the renamed clip
        print("[CLIP INFO] Finding renamed clip...", file=sys.stderr)
        response_after = engine.client.run_command(125, {})  # GetClipList
        
        if not response_after or 'clip_list' not in response_after:
            print("[CLIP INFO] Failed to get clip list after rename", file=sys.stderr)
            return None
        
        clips_after = response_after['clip_list']
        print(f"[CLIP INFO] Found {len(clips_after)} clips after rename", file=sys.stderr)
        
        # Debug: Print all clip names to see what's there
        for i, clip in enumerate(clips_after):
            clip_name = clip.get('clip_full_name', 'N/A')
            clip_type = clip.get('clip_type', 'N/A')
            print(f"[CLIP INFO] Clip {i+1}: '{clip_name}' (type: {clip_type})", file=sys.stderr)
        
        # Find the clip with temporary name
        selected_clip = None
        original_name = None
        
        for clip in clips_after:
            # CRITICAL: Only look at video clips to avoid finding audio clips with same name
            clip_type = clip.get('clip_type', '')
            # Support both CType_Video (older PT) and ClipType_Video (newer PT)
            if clip_type not in ('CType_Video', 'ClipType_Video'):
                continue
                
            if clip.get('clip_full_name') == temp_name:
                selected_clip = clip
                
                # Find original name by matching clip_id
                for old_clip in clips_before:
                    # CRITICAL: Only look at video clips
                    old_clip_type = old_clip.get('clip_type', '')
                    if old_clip_type not in ('CType_Video', 'ClipType_Video'):
                        continue
                        
                    if old_clip.get('clip_id') == clip.get('clip_id'):
                        original_name = old_clip.get('clip_full_name')
                        break
                
                break
        
        if not selected_clip:
            print("[CLIP INFO] Could not find renamed clip", file=sys.stderr)
            return None
        
        # If we couldn't find original name, try to infer it by removing __TEMP_SELECTED_ prefix
        if not original_name or original_name == temp_name:
            # Look for any clip with same file_id that doesn't have temp name
            for old_clip in clips_before:
                # CRITICAL: Only look at video clips
                old_clip_type = old_clip.get('clip_type', '')
                if old_clip_type not in ('CType_Video', 'ClipType_Video'):
                    continue
                    
                old_name = old_clip.get('clip_full_name', '')
                if (old_clip.get('file_id') == selected_file_id and 
                    not old_name.startswith('__TEMP_SELECTED_')):
                    original_name = old_name
                    print(f"[CLIP INFO] Inferred original name from file_id: {original_name}", file=sys.stderr)
                    break
            
            # Last resort: use a generic name
            if not original_name or original_name == temp_name:
                original_name = f"video_clip_{selected_file_id[:8]}"
                print(f"[CLIP INFO] Could not find original name, using fallback: {original_name}", file=sys.stderr)
        
        print(f"[CLIP INFO] ✅ Identified clip: {original_name}", file=sys.stderr)
        
        # Step 5: Rename back to original name
        print(f"[CLIP INFO] Restoring original name...", file=sys.stderr)
        
        try:
            engine.rename_selected_clip(
                new_name=original_name,
                rename_file=False,
                clip_location=clip_loc
            )
            print(f"[CLIP INFO] Successfully restored to original name", file=sys.stderr)
        except Exception as e:
            # If restore fails, keep temp name — we already have the clip info we need
            print(f"[CLIP INFO] WARNING: Could not restore to '{original_name}': {e}", file=sys.stderr)
            print(f"[CLIP INFO] Keeping temp name (clip info already extracted): {temp_name}", file=sys.stderr)
            
            # Don't try to rename again — just use temp name as-is
            # The temp name is unique enough (full UUID + timestamp) and won't cause issues
            original_name = temp_name
        
        # Step 6: Extract clip information
        clip_id = selected_clip.get('clip_id')
        clip_type = selected_clip.get('clip_type', '')
        
        # Get frame boundaries from start_point and end_point
        start_point_data = selected_clip.get('start_point', {})
        end_point_data = selected_clip.get('end_point', {})
        
        # Extract frame values (handle both 'value' and 'position' keys)
        if isinstance(start_point_data, dict):
            start_frame = start_point_data.get('value', start_point_data.get('position', 0))
        else:
            start_frame = 0
            
        if isinstance(end_point_data, dict):
            end_frame = end_point_data.get('value', end_point_data.get('position', 0))
        else:
            end_frame = 0
        
        duration_frames = end_frame - start_frame
        
        clip_info = {
            'clip_name': original_name,
            'clip_id': clip_id,
            'file_id': selected_file_id,
            'file_path': file_path,
            'start_frame': start_frame,
            'end_frame': end_frame,
            'duration_frames': duration_frames,
            'clip_type': clip_type
        }
        
        print(f"[CLIP INFO] ✅ Clip info retrieved:", file=sys.stderr)
        print(f"  Name: {original_name}", file=sys.stderr)
        print(f"  Frames: {start_frame} - {end_frame} ({duration_frames} frames)", file=sys.stderr)
        
        return clip_info
    
    except Exception as e:
        print(f"[CLIP INFO ERROR] Failed to get clip info: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None


def calculate_trim_points_from_clip(clip_info: Dict, framerate: float) -> Dict:
    """
    Calculate video trim points from clip information.
    
    Converts frame-based clip boundaries to time-based trim points
    for FFmpeg video processing.
    
    Args:
        clip_info: Dictionary with 'start_frame' and 'end_frame' keys
        framerate: Session framerate (e.g. 29.97, 30.0, 25.0)
    
    Returns:
        Dictionary with:
        - start_seconds: float - Start time in seconds
        - end_seconds: float - End time in seconds
        - duration_seconds: float - Duration in seconds
        - start_frame: int - Original start frame
        - end_frame: int - Original end frame
    
    Example:
        >>> clip_info = {'start_frame': 0, 'end_frame': 150}
        >>> result = calculate_trim_points_from_clip(clip_info, 29.97)
        >>> print(f"Trim: {result['start_seconds']}s - {result['end_seconds']}s")
        Trim: 0.0s - 5.005s
    """
    start_frame = clip_info['start_frame']
    end_frame = clip_info['end_frame']
    
    start_seconds = frames_to_seconds(start_frame, framerate)
    end_seconds = frames_to_seconds(end_frame, framerate)
    duration_seconds = end_seconds - start_seconds
    
    return {
        'start_seconds': start_seconds,
        'end_seconds': end_seconds,
        'duration_seconds': duration_seconds,
        'start_frame': start_frame,
        'end_frame': end_frame
    }
