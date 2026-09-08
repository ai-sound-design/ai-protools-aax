"""
Pro Tools video file operations via PTSL

Provides:
- Video file detection from Pro Tools session
"""

from typing import Dict


def get_video_file_from_protools(
    company_name: str = "Master Thesis",
    app_name: str = "PT V2A Plugin",
    timeline_in_seconds: float = None,
    timeline_out_seconds: float = None
) -> Dict[str, any]:
    """
    Get video file path from Pro Tools session using py-ptsl.
    
    Uses PTSL's SelectedClipsTimeline filter to identify which video clip
    the user has selected in the Pro Tools timeline.
    
    Args:
        company_name (str): Company name for PTSL connection
        app_name (str): Application name for PTSL connection
        timeline_in_seconds (float, optional): IGNORED - selection determined by Pro Tools
        timeline_out_seconds (float, optional): IGNORED - selection determined by Pro Tools
    
    Returns:
        dict: {
            'success': bool,
            'video_path': str or None,
            'video_files': list of str (all found videos),
            'video_count': int (number of videos in timeline selection),
            'error': str or None
        }
    
    Example:
        >>> result = get_video_file_from_protools()
        >>> if result['success']:
        >>>     print(f"Selected video: {result['video_path']}")
    
    Workflow:
        1. Query PTSL for clips selected on timeline using SelectedClipsTimeline filter
        2. Filter results to only video files
        3. Validate: Exactly 1 video clip must be selected
        4. Return the video file path
    """
    try:
        # Import py-ptsl
        from ptsl import open_engine
        import ptsl.PTSL_pb2 as pt
        
        # Connect to Pro Tools via PTSL
        with open_engine(
            company_name=company_name,
            application_name=app_name
        ) as engine:
            import sys
            print(f"=== DEBUG video.py: Querying selected clips on timeline... ===", file=sys.stderr)
            sys.stderr.flush()
            
            # Get SELECTED clips from timeline using the SelectedClipsTimeline filter
            # This filter returns only clips that are currently selected by the user
            selected_clips = engine.get_file_location(filters=[pt.SelectedClipsTimeline])
            
            if not selected_clips:
                print(f"=== DEBUG video.py: No clips selected on timeline ===", file=sys.stderr)
                sys.stderr.flush()
                
                return {
                    'success': False,
                    'video_path': None,
                    'video_files': [],
                    'video_count': 0,
                    'error': 'No clips selected on timeline. Please select a video clip in Pro Tools.'
                }
            
            # Filter to only video files
            video_clips_selected = []
            for file_loc in selected_clips:
                file_path = file_loc.path if hasattr(file_loc, 'path') else str(file_loc)
                
                # Check if this is a video file (by extension)
                import os
                file_ext = os.path.splitext(file_path)[1].lower()
                video_extensions = [
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
                ]
                
                if file_ext in video_extensions:
                    video_clips_selected.append(file_path)
                    print(f"=== DEBUG video.py: Found selected video clip: {file_path} ===", file=sys.stderr)
                    sys.stderr.flush()
            
            # Validate: exactly 1 video clip must be selected
            if len(video_clips_selected) == 0:
                print(f"=== DEBUG video.py: {len(selected_clips)} clip(s) selected, but none are video files ===", file=sys.stderr)
                sys.stderr.flush()
                
                return {
                    'success': False,
                    'video_path': None,
                    'video_files': [],
                    'video_count': 0,
                    'error': f'{len(selected_clips)} clip(s) selected, but none are video files. Please select a video clip.'
                }
            
            if len(video_clips_selected) > 1:
                print(f"=== DEBUG video.py: Multiple video clips selected: {len(video_clips_selected)} ===", file=sys.stderr)
                for i, path in enumerate(video_clips_selected):
                    print(f"  Video {i+1}: {path}", file=sys.stderr)
                sys.stderr.flush()
                
                return {
                    'success': False,
                    'video_path': None,
                    'video_files': video_clips_selected,
                    'video_count': len(video_clips_selected),
                    'error': f'Multiple video clips selected ({len(video_clips_selected)}). Please select exactly one video clip.'
                }
            
            # Success: exactly 1 video clip selected
            selected_video = video_clips_selected[0]
            print(f"=== DEBUG video.py: SUCCESS - Selected video: {selected_video} ===", file=sys.stderr)
            sys.stderr.flush()
            
            return {
                'success': True,
                'video_path': selected_video,
                'video_files': video_clips_selected,
                'video_count': 1,
                'error': None
            }
    
    except ImportError as e:
        return {
            'success': False,
            'video_path': None,
            'video_files': [],
            'video_count': 0,
            'error': f'Failed to import py-ptsl: {str(e)}'
        }
    except Exception as e:
        import sys
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        
        return {
            'success': False,
            'video_path': None,
            'video_files': [],
            'video_count': 0,
            'error': f'Error communicating with Pro Tools: {str(e)}'
        }
