#!/usr/bin/env python3
"""
BBC Sound Search API Client for Pro Tools Plugin

This script is called by the AAX plugin (C++) to perform semantic sound search.
It uses the sound_search_client module to interact with the Sound Search API.

Actions:
    search - Search for sounds using video and/or text
    download - Download a specific sound by ID
    cleanup - Clean up temporary files for a session

Examples:
    # Text search
    python sound_search_api_client.py --action search --text "footsteps" --limit 5
    
    # Video search
    python sound_search_api_client.py --action search --video /path/to/video.mp4 --limit 5
    
    # Hybrid search (video + text)
    python sound_search_api_client.py --action search --video /path/to/video.mp4 --text "door closing" --limit 5
    
    # Download sound
    python sound_search_api_client.py --action download --sound-id 5362 --output /tmp/sound.wav
    
    # Cleanup session
    python sound_search_api_client.py --action cleanup --session-id abc123
"""

import argparse
import json
import sys
import os
import tempfile
import datetime
from pathlib import Path

# Add api module to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Global log file path
LOG_FILE = os.path.join(tempfile.gettempdir(), "sound_search_debug.log")

def log_debug(msg):
    """Write debug message to log file ONLY (not to stderr to avoid mixing with JSON output)"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            f.write(f"[{timestamp}] {msg}\n")
            f.flush()
    except Exception:
        pass

from api.sound_search_client import (
    search_sounds,
    download_sound,
    search_and_download,
    cleanup_session,
    check_api_health,
)

from cli.error_handler import safe_action_wrapper

# Import video preprocessing functions
from video import (
    trim_and_maybe_downscale_video,
    validate_video_file,
    get_video_duration,
)
from ptsl_integration import (
    timecode_to_seconds,
)
from api import VIDEO_DOWNSCALE_THRESHOLD_MB


def action_health_check(args):
    """Check if Sound Search API is available"""
    log_debug("Action: health_check")
    
    if check_api_health(quiet=True):
        log_debug("Sound Search API is available")
        return {
            "status": "success",
            "message": "Sound Search API is available"
        }
    else:
        log_debug("ERROR: Sound Search API is not available")
        return {
            "status": "error",
            "message": "Sound Search API is not available"
        }


def action_search(args):
    """Search for sounds using video and/or text"""
    log_debug("Action: search")
    log_debug(f"Video: {args.video}, Text: {args.text}, Limit: {args.limit}")
    log_debug(f"Timeline: {args.timeline_start}s - {args.timeline_end}s, Video offset: {args.video_offset}")
    log_debug(f"Clip bounds: {args.clip_start_seconds}s - {args.clip_end_seconds}s")
    
    if not args.video and not args.text:
        log_debug("ERROR: Must provide either --video or --text")
        return {
            "status": "error",
            "message": "Must provide either --video or --text"
        }
    
    # === Video Preprocessing (Trim + Downscale) ===
    # If video is provided, preprocess it before sending to server
    # Important: Trim FIRST (reduces file size), then downscale if needed
    video_path = args.video
    
    if video_path:
        log_debug(f"=== DEBUG SOUND_SEARCH: Starting video preprocessing ===")
        log_debug(f"=== DEBUG SOUND_SEARCH: Original video: {video_path} ===")
        
        # Check video file
        file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
        log_debug(f"=== DEBUG SOUND_SEARCH: Original video size: {file_size_mb:.1f} MB ===")
        
        # === Video Trimming (if needed) ===
        # Support same workflows as MMAudio/HunyuanVideo for consistency
        
        if args.clip_start_seconds is not None and args.clip_end_seconds is not None:
            # Clip bounds provided (auto-detected or manual)
            log_debug(f"=== DEBUG SOUND_SEARCH: Trimming video from {args.clip_start_seconds}s to {args.clip_end_seconds}s ===")
            
            trim_result = trim_and_maybe_downscale_video(
                video_path=video_path,
                start_seconds=args.clip_start_seconds,
                end_seconds=args.clip_end_seconds
            )
            
            if not trim_result['success']:
                log_debug(f"=== DEBUG SOUND_SEARCH: Trimming FAILED: {trim_result.get('error')} ===")
                return {
                    "status": "error",
                    "message": f"Video trimming failed: {trim_result.get('error')}"
                }
            
            video_path = trim_result['output_path']
            log_debug(f"=== DEBUG SOUND_SEARCH: Processed video: {Path(video_path).name} ===")
            log_debug(f"=== DEBUG SOUND_SEARCH: {trim_result['original_size_mb']:.1f}MB → {trim_result['final_size_mb']:.1f}MB ===")
        
        elif args.video_offset and args.timeline_start != 0.0 and args.timeline_end != 0.0:
            # Manual offset provided
            log_debug(f"=== DEBUG SOUND_SEARCH: Processing with manual offset ===")
            
            try:
                video_clip_timeline_start = timecode_to_seconds(args.video_offset)
            except Exception as e:
                log_debug(f"ERROR: Invalid video offset: {e}")
                return {
                    "status": "error",
                    "message": f"Invalid video offset: {e}"
                }
            
            timeline_in_seconds = args.timeline_start
            timeline_out_seconds = args.timeline_end
            
            # Calculate source video trim points
            relative_in_clip = timeline_in_seconds - video_clip_timeline_start
            start_in_source = max(0, relative_in_clip)
            end_in_source = relative_in_clip + (timeline_out_seconds - timeline_in_seconds)
            
            log_debug(f"=== DEBUG SOUND_SEARCH: Trimming source: {start_in_source}s - {end_in_source}s ===")
            
            trim_result = trim_and_maybe_downscale_video(
                video_path=video_path,
                start_seconds=start_in_source,
                end_seconds=end_in_source
            )
            
            if not trim_result['success']:
                log_debug(f"=== DEBUG SOUND_SEARCH: Trimming FAILED: {trim_result.get('error')} ===")
                return {
                    "status": "error",
                    "message": f"Video trimming failed: {trim_result.get('error')}"
                }
            
            video_path = trim_result['output_path']
            log_debug(f"=== DEBUG SOUND_SEARCH: Processed video: {Path(video_path).name} ===")
            log_debug(f"=== DEBUG SOUND_SEARCH: {trim_result['original_size_mb']:.1f}MB → {trim_result['final_size_mb']:.1f}MB ===")
        
        else:
            # No trimming parameters provided - process full video
            # Use trim_and_maybe_downscale_video with full duration to match audio generation workflow
            # This ensures consistent >2MB downscaling logic
            log_debug(f"=== DEBUG SOUND_SEARCH: No trimming parameters, processing full video ===")
            
            duration_result = get_video_duration(video_path)
            if not duration_result['success']:
                log_debug(f"=== DEBUG SOUND_SEARCH: Could not get video duration: {duration_result.get('error')} ===")
                return {
                    "status": "error",
                    "message": f"Could not determine video duration: {duration_result.get('error')}"
                }
            
            video_duration = duration_result['duration']
            log_debug(f"=== DEBUG SOUND_SEARCH: Video duration: {video_duration:.2f}s ===")
            
            # "Trim" from 0 to end (effectively only downscales if >2MB)
            trim_result = trim_and_maybe_downscale_video(
                video_path=video_path,
                start_seconds=0,
                end_seconds=video_duration
            )
            
            if not trim_result['success']:
                log_debug(f"=== DEBUG SOUND_SEARCH: Processing FAILED: {trim_result.get('error')} ===")
                return {
                    "status": "error",
                    "message": f"Video processing failed: {trim_result.get('error')}"
                }
            
            video_path = trim_result['output_path']
            log_debug(f"=== DEBUG SOUND_SEARCH: Processed video: {Path(video_path).name} ===")
            log_debug(f"=== DEBUG SOUND_SEARCH: {trim_result['original_size_mb']:.1f}MB → {trim_result['final_size_mb']:.1f}MB ===" )
            if trim_result['downscaled']:
                log_debug(f"=== DEBUG SOUND_SEARCH: Video was downscaled (>{VIDEO_DOWNSCALE_THRESHOLD_MB}MB) ===")
            else:
                log_debug(f"=== DEBUG SOUND_SEARCH: Video was not downscaled (<={VIDEO_DOWNSCALE_THRESHOLD_MB}MB) ===")
        
        log_debug(f"=== DEBUG SOUND_SEARCH: Final video for search: {video_path} ===")
    
    # Adjust text_weight based on input type
    effective_text_weight = args.text_weight
    if not args.video and args.text:
        # Text-only search: 100% text weight
        effective_text_weight = 1.0
        log_debug("Text-only search - using text_weight=1.0 (100% text)")
    elif args.video and not args.text:
        # Video-only search: 0% text weight (100% video)
        effective_text_weight = 0.0
        log_debug("Video-only search - using text_weight=0.0 (100% video)")
    else:
        # Hybrid search: use configured weight
        log_debug(f"Hybrid search (video + text) - using text_weight={effective_text_weight}")
    
    # Perform search only (no download)
    log_debug(f"Starting search with text_weight={effective_text_weight}, num_frames={args.num_frames}")
    
    log_debug("Calling search_sounds() (search only, no download)...")
    log_debug(f"  video_path: {video_path}")
    log_debug(f"  text_query: {args.text}")
    log_debug(f"  limit: {args.limit}")
    
    results = search_sounds(
        video_path=video_path,  # Use preprocessed video (trimmed/downscaled if needed)
        text_query=args.text,
        limit=args.limit,
        text_weight=effective_text_weight,
        num_frames=args.num_frames,
        quiet=args.quiet,  # Use CLI argument (True when called from plugin)
        verbose=args.verbose,  # Use CLI argument (False when called from plugin)
    )
    log_debug(f"search_sounds() returned: {type(results)} with {len(results) if results else 0} items")
    
    if not results:
        log_debug("ERROR: Search failed or no results found (results is None or empty)")
        return {
            "status": "error",
            "message": "Search failed or no results found"
        }
    
    log_debug(f"Search successful: {len(results)} results found")
    
    # Format output for plugin
    log_debug("Formatting JSON output...")
    output = {
        "status": "success",
        "count": len(results),
        "session_id": args.session_id,
        "results": []
    }
    
    for i, sound in enumerate(results, 1):
        log_debug(f"Formatting sound {i}/{len(results)}: ID={sound.get('id')}")
        output["results"].append({
            "id": sound["id"],
            "description": sound["description"],
            "category": sound["category"],
            "similarity": sound["similarity"],
            "file_path": sound.get("file_path", ""),  # Include but may not be needed yet
        })
    
    log_debug(f"Formatting output with {len(output['results'])} results")
    json_output = json.dumps(output, indent=2)
    log_debug(f"JSON output length: {len(json_output)} chars")
    log_debug(f"First 200 chars of JSON: {json_output[:200]}")
    
    # CRITICAL DEBUG: Write full JSON to log file for inspection
    log_debug("=== FULL JSON OUTPUT START ===")
    log_debug(json_output)
    log_debug("=== FULL JSON OUTPUT END ===")
    
    # Determine output file path
    if args.output_json:
        output_file = args.output_json
    else:
        # Write to temp dir with session ID for easy polling
        import tempfile
        if args.session_id:
            output_file = os.path.join(tempfile.gettempdir(), f"sound_search_{args.session_id}.json")
        else:
            output_file = os.path.join(tempfile.gettempdir(), "sound_search_results.json")
    
    # Write results to file (avoids stdout/stderr blocking issues on Windows)
    log_debug(f"Writing results to file: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(json_output)
    log_debug(f"✓ Results written to: {output_file}")
    
    # Print file path to stdout for plugin to read
    # Note: safe_action_wrapper will wrap this in JSON, so we return dict
    log_debug("=== Output operation completed successfully ===")
    return {
        "status": "success",
        "output_file": output_file
    }


def action_download(args):
    """Download a specific sound by ID"""
    log_debug(f"Action: download - sound_id={args.sound_id}")
    
    if not args.sound_id:
        log_debug("ERROR: Must provide --sound-id")
        return {
            "status": "error",
            "message": "Must provide --sound-id"
        }
    
    local_path = download_sound(
        sound_id=args.sound_id,
        output_path=args.output,
        session_id=args.session_id,
        quiet=args.quiet,
    )
    
    if not local_path:
        log_debug(f"ERROR: Failed to download sound {args.sound_id}")
        return {
            "status": "error",
            "message": f"Failed to download sound {args.sound_id}"
        }
    
    log_debug(f"Download successful: {local_path}")
    
    # Prepare output
    output = {
        "status": "success",
        "sound_id": args.sound_id,
        "local_path": local_path,
        "filename": Path(local_path).name
    }
    
    # Write to output file if specified (for plugin integration)
    if args.output_json:
        log_debug(f"Writing download result to file: {args.output_json}")
        json_output = json.dumps(output, indent=2)
        with open(args.output_json, 'w', encoding='utf-8') as f:
            f.write(json_output)
        log_debug(f"✓ Download result written to: {args.output_json}")
        
        return {
            "status": "success",
            "output_file": args.output_json
        }
    
    return output


def action_cleanup(args):
    """Clean up temporary files for a session"""
    log_debug(f"Action: cleanup - session_id={args.session_id}")
    
    if not args.session_id:
        log_debug("ERROR: Must provide --session-id")
        return {
            "status": "error",
            "message": "Must provide --session-id"
        }
    
    success = cleanup_session(args.session_id, quiet=args.quiet)
    
    if success:
        log_debug(f"Session {args.session_id} cleaned up successfully")
        return {
            "status": "success",
            "message": f"Session {args.session_id} cleaned up"
        }
    else:
        log_debug(f"ERROR: Failed to clean up session {args.session_id}")
        return {
            "status": "error",
            "message": f"Failed to clean up session {args.session_id}"
        }


def main():
    parser = argparse.ArgumentParser(
        description="BBC Sound Search API Client for Pro Tools Plugin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Action selection
    parser.add_argument(
        '--action',
        type=str,
        choices=['health', 'search', 'download', 'cleanup'],
        default='search',
        help='Action to perform (default: search)'
    )
    
    # Search parameters
    parser.add_argument(
        '--video',
        type=str,
        help='Path to video file for video-based search'
    )
    
    parser.add_argument(
        '--text',
        type=str,
        help='Text query for text-based search'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=5,
        help='Number of results to return (default: 5)'
    )
    
    parser.add_argument(
        '--text-weight',
        type=float,
        default=0.65,
        help='Weight for text vs video (0-1, default: 0.65)'
    )
    
    parser.add_argument(
        '--num-frames',
        type=int,
        default=16,
        help='Number of frames to extract from video (default: 16)'
    )
    
    # Video trimming parameters (Pro Tools integration)
    parser.add_argument(
        '--video-offset',
        type=str,
        default='',
        help='Timeline position where video clip starts (e.g., "00:02" or "00:00:02:00")'
    )
    
    parser.add_argument(
        '--timeline-start',
        type=float,
        default=0.0,
        help='Timeline selection start time in seconds'
    )
    
    parser.add_argument(
        '--timeline-end',
        type=float,
        default=0.0,
        help='Timeline selection end time in seconds'
    )
    
    parser.add_argument(
        '--clip-start-seconds',
        type=float,
        default=None,
        help='Clip start time in source video (seconds)'
    )
    
    parser.add_argument(
        '--clip-end-seconds',
        type=float,
        default=None,
        help='Clip end time in source video (seconds)'
    )
    
    # Download parameters
    parser.add_argument(
        '--sound-id',
        type=int,
        help='Sound ID to download'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output path for downloaded file'
    )
    
    # Session management
    parser.add_argument(
        '--session-id',
        type=str,
        help='Session ID for organizing temp files (auto-generated if not provided)'
    )
    
    # Output file path (for plugin integration - avoids stdout issues)
    parser.add_argument(
        '--output-json',
        type=str,
        help='Output JSON file path (default: writes to temp dir)'
    )
    
    # Output control
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress messages'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed output'
    )
    
    args = parser.parse_args()
    
    # Log script start
    log_debug(f"Sound Search API Client started - Action: {args.action}")
    log_debug(f"Arguments: {vars(args)}")
    log_debug(f"Log file: {LOG_FILE}")
    
    # Route to appropriate action handler
    if args.action == 'health':
        return safe_action_wrapper(lambda: action_health_check(args))
    elif args.action == 'search':
        return safe_action_wrapper(lambda: action_search(args))
    elif args.action == 'download':
        return safe_action_wrapper(lambda: action_download(args))
    elif args.action == 'cleanup':
        return safe_action_wrapper(lambda: action_cleanup(args))
    else:
        return safe_action_wrapper(lambda: {
            "status": "error",
            "message": f"Unknown action: {args.action}"
        })


if __name__ == "__main__":
    sys.exit(main())
