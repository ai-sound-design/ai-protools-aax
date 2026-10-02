#!/usr/bin/env python3
"""
Standalone MMAudio API Client

A client script that uses the standalone MMAudio API server for video-to-audio generation.

Usage:
    # Interactive Mode (current)
    python standalone_api_client.py
    
    # CLI Mode (Pro Tools ready)
    python standalone_api_client.py --video /path/to/video.mp4 --prompt "ocean waves"
    
    # Full CLI Mode
    python standalone_api_client.py \
        --video /path/to/video.mp4 \
        --prompt "drums and bass" \
        --negative-prompt "voices, music" \
        --seed 42 \
        --output /path/to/output.flac

Features:
- Interactive parameter input (prompt, negative prompt, seed)
- CLI arguments for Pro Tools integration
- Automatic video duration detection
- Progress feedback and timing information
- Compatible with existing video test files
- Multiple video format support (MP4, MOV, AVI)

Note:
    This file has been refactored. Core functionality moved to:
    - api/adapters.py: adapter profiles and the generation request
    - api/config.py: Configuration constants
    - video/ffmpeg.py: FFmpeg operations
    - video/validation.py: Video validation
    - ptsl_integration/timeline.py: Timeline operations
    - ptsl_integration/video.py: Video file detection
"""

import argparse
import sys
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

# Import from refactored modules
from api import (
    get_api_url,
    SUPPORTED_VIDEO_FORMATS,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_SEED,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_TIMEOUT,
    VIDEO_DOWNSCALE_THRESHOLD_MB,
)
from video import (
    check_ffmpeg_available,
    trim_video_segment,
    trim_and_maybe_downscale_video,
    validate_video_duration,
    validate_video_file,
    get_video_bitrate,
    downscale_video,
)
from ptsl_integration import (
    get_video_timeline_selection,
    timecode_to_seconds,
    get_video_file_from_protools,
    import_audio_to_pro_tools,
)

# Import shared CLI actions
from cli.actions import (
    action_check_ffmpeg,
    action_get_video_info,
    action_get_duration,
    action_import_audio,
)
from cli.error_handler import safe_action_wrapper, wrap_main_with_json_error_handling

# Legacy configuration (for backwards compatibility)
# Use relative path for cross-platform compatibility
try:
    # Try to find test video relative to companion/ directory
    DEFAULT_VIDEO_PATH = str(Path(__file__).parents[2] / "model-tests" / "data" / "MMAudio_examples" / "noSound" / "sora_galloping.mp4")
except Exception:
    # Fallback: Use a placeholder path
    DEFAULT_VIDEO_PATH = "test_video.mp4"

# =============================================================================
# CLI Functions (parse arguments, interactive mode, main entry point)
# =============================================================================

def parse_arguments():
    """Parse command line arguments for CLI mode and Pro Tools integration"""
    parser = argparse.ArgumentParser(
        description="MMAudio Standalone API Client - Generate audio from video using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python standalone_api_client.py
  
  # CLI mode (Pro Tools ready)
  python standalone_api_client.py --video /tmp/protools_clip.mov --prompt "drums"
  
  # Full CLI mode with all options
  python standalone_api_client.py \\
    --video /path/to/video.mp4 \\
    --prompt "ocean waves and seagulls" \\
    --negative-prompt "voices, music" \\
    --seed 42 \\
    --output /path/to/custom_output.flac \\
    --duration 10.0 \\
    --adapter mmaudio.json
        """
    )
    
    # Video input (required for CLI mode)
    parser.add_argument(
        '--progress-file',
        help="Generation: JSON file rewritten with the backend's progress (stage, current/total parts, fraction, overall) for the plugin's bar"
    )
    parser.add_argument(
        '--video', '-v',
        type=str,
        help='Path to input video file (MP4, MOV, AVI, etc.)'
    )
    
    # Generation parameters
    parser.add_argument(
        '--prompt', '-p',
        type=str,
        default='',
        help='Text prompt describing desired audio (default: empty)'
    )
    
    parser.add_argument(
        '--negative-prompt', '-n',
        type=str,
        default=DEFAULT_NEGATIVE_PROMPT,
        help=f'Negative prompt to avoid certain sounds (default: "{DEFAULT_NEGATIVE_PROMPT}")'
    )
    
    parser.add_argument(
        '--seed', '-s',
        type=int,
        default=DEFAULT_SEED,
        help=f'Seed; -1 draws a random one and logs it, any other value reproduces a result (default: {DEFAULT_SEED})'
    )
    
    # Output options
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output file path (default: auto-generated in ./standalone-API_outputs/)'
    )
    
    parser.add_argument(
        '--temp',
        action='store_true',
        help='Use system temp directory for output (useful when called from Pro Tools)'
    )
    
    parser.add_argument(
        '--import-to-protools',
        action='store_true',
        help='Automatically import generated audio to Pro Tools timeline via PTSL'
    )
    
    parser.add_argument(
        '--video-offset',
        type=str,
        default='',
        help='Timeline position where video clip starts (e.g., "00:02" or "00:00:02:00"). '
             'Used to calculate offset into source video when trimming. '
             'Leave empty if video starts at timeline beginning (00:00:00:00).'
    )
    
    parser.add_argument(
        '--timeline-start',
        type=float,
        default=0.0,
        help='Timeline selection start time in seconds (passed from C++ plugin)'
    )
    
    parser.add_argument(
        '--timeline-end',
        type=float,
        default=0.0,
        help='Timeline selection end time in seconds (passed from C++ plugin)'
    )
    
    parser.add_argument(
        '--auto-detect-clip-bounds',
        action='store_true',
        help='Automatically detect video clip boundaries from Pro Tools Clips List. '
             'Use when video clip is cut/trimmed in Pro Tools. '
             'When enabled, --video-offset is ignored.'
    )
    
    # Advanced parameters
    parser.add_argument(
        '--duration', '-d',
        type=float,
        help='Duration in seconds (default: auto-detect from video)'
    )
    
    parser.add_argument(
        '--adapter',
        type=str,
        help='Adapter profile (file name in the adapters folder, or a path) describing the generation '
             'backend. Default: the profile selected in the plugin.'
    )
    
    parser.add_argument(
        '--output-format',
        type=str,
        choices=['flac', 'wav'],
        default=DEFAULT_OUTPUT_FORMAT,
        help=f'Output audio format: "flac" (smaller) or "wav" (Pro Tools compatible, default: {DEFAULT_OUTPUT_FORMAT})'
    )
    
    # API options
    parser.add_argument(
        '--api-url',
        type=str,
        default=None,
        help='Backend address (default: the address of the adapter profile)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f'Request timeout in seconds (default: {DEFAULT_TIMEOUT})'
    )
    
    # Utility options
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Minimal output (useful for Pro Tools integration)'
    )
    
    parser.add_argument(
        '--verbose', '-V',
        action='store_true',
        help='Verbose output with detailed progress'
    )
    
    # CLI Actions for C++ Plugin Integration
    parser.add_argument(
        '--action',
        type=str,
        choices=['generate', 't2a', 'check_ffmpeg', 'get_video_selection', 'get_video_file', 'get_video_info', 'trim_video', 'validate_duration', 'get_duration', 'import_audio', 'clip_detect_and_trim', 'get_clip_bounds', 'resolve_video_segments', 'list_video_tracks', 'export_selection_audio', 'test_cloudflare', 'list_adapters', 'ensure_adapters'],
        default='generate',
        help='Action to perform (default: generate)'
    )
    
    # Cloudflare credential test parameters
    parser.add_argument(
        '--whole-track',
        action='store_true',
        help='resolve_video_segments: use the whole video track instead of the timeline selection'
    )
    parser.add_argument(
        '--video-track',
        default=None,
        help='resolve_video_segments: the video track to map onto (default: the topmost, or the one the selection lies on)'
    )
    parser.add_argument(
        '--cf-client-id',
type=str,
        help='Cloudflare Access Client ID (for test_cloudflare action)'
    )
    
    parser.add_argument(
        '--cf-client-secret',
        type=str,
        help='Cloudflare Access Client Secret (for test_cloudflare action)'
    )
    
    # Clip bounds parameters (for background trimming)
    parser.add_argument(
        '--clip-start-seconds',
        type=float,
        help='Clip start time in seconds (for background trimming)'
    )
    
    parser.add_argument(
        '--clip-end-seconds',
        type=float,
        help='Clip end time in seconds (for background trimming)'
    )
    
    # Audio import parameter
    parser.add_argument(
        '--audio-path',
        type=str,
        help='Path to audio file (for import_audio action)'
    )
    
    # Audio import timecode position
    parser.add_argument(
        '--track-name',
        help='Existing track to place the imported clip on (import_audio action); new track if omitted or occupied'
    )
    parser.add_argument(
        '--clip-name',
        help='Name for the imported clip (import_audio action)'
    )
    parser.add_argument(
        '--timecode-out',
        help='End of the selection (import_audio action): a longer clip is trimmed to it'
    )
    parser.add_argument(
        '--cut',
        action='store_true',
        help='import_audio: trim the clip to the selection (--timecode..--timecode-out); the rest of the file stays as handles'
    )
    parser.add_argument(
        '--handle-before',
        type=float,
        default=0.0,
        help='import_audio with --cut: this many seconds of the file lie before the selection (imported that much earlier)'
    )
    parser.add_argument(
        '--fade-preset',
        help='import_audio with --cut: Pro Tools batch-fades preset for the clip\'s edges'
    )
    parser.add_argument(
        '--fade-seconds',
        type=float,
        default=1.0,
        help='import_audio with --cut: the preset\'s fade length'
    )
    parser.add_argument(
        '--fade-inside',
        action='store_true',
        help='import_audio with --cut: the fade runs inside the selection (the clip ends at it) instead of over the handle'
    )
    parser.add_argument(
        '--timecode',
        type=str,
        help='Timecode position for import_audio action (e.g., "00:00:07:00")'
    )
    
    # Trimming parameters
    parser.add_argument(
        '--start-time',
        type=float,
        help='Start time in seconds (for trim_video action)'
    )
    
    parser.add_argument(
        '--end-time',
        type=float,
        help='End time in seconds (for trim_video action)'
    )
    
    parser.add_argument(
        '--max-duration',
        type=float,
        default=10.0,
        help='Maximum video duration in seconds (default: 10.0)'
    )
    
    return parser.parse_args()


def get_video_path_interactive() -> str:
    """Interactive video path selection"""
    print("\n📹 Video File Selection")
    print("=" * 40)
    
    while True:
        video_input = input(f"🎬 Video Path (Default: {Path(DEFAULT_VIDEO_PATH).name}): ").strip()
        
        if not video_input:
            video_path = DEFAULT_VIDEO_PATH
        else:
            video_path = video_input
        
        try:
            validated_path = validate_video_file(video_path)
            file_size_mb = validated_path.stat().st_size / (1024 * 1024)
            print(f"✅ Video file: {validated_path.name} ({file_size_mb:.1f} MB)")
            return str(validated_path)
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ {e}")
            print("   Please try again with a valid video file path.")
            continue


def get_user_inputs_interactive():
    """Interactive parameter input for generation settings"""
    print("\n🎵 Generation Parameters")
    print("=" * 40)

    prompt = input("🎵 Prompt (Default: ''): ").strip()
    negative_prompt = input(f"❌ Negative Prompt (Default: '{DEFAULT_NEGATIVE_PROMPT}'): ").strip()
    if not negative_prompt:
        negative_prompt = DEFAULT_NEGATIVE_PROMPT
    
    while True:
        seed_input = input(f"🎲 Seed (-1 = random, default: {DEFAULT_SEED}): ").strip()
        if not seed_input:
            seed = DEFAULT_SEED
            break
        try:
            seed = int(seed_input)
            break
        except ValueError:
            print("   ⚠️  Please enter a valid number.")
    
    print(f"\n✅ Parameters set:")
    print(f"   Prompt: '{prompt}'")
    print(f"   Negative Prompt: '{negative_prompt}'")
    print(f"   Seed: {seed}")
    
    return prompt, negative_prompt, seed



def _generation_progress_writer(path):
    """A callback for generate_with_profile that mirrors the backend's progress into the
    plugin's progress file (same keys the spotting and hybrid runs use). The generation
    gateway reports stage, part, parts, fraction and detail; a plain model service reports
    nothing, so the file is written only when parts are known."""
    if not path:
        return None
    import time as _time
    target = Path(path)

    def write(doc):
        parts = int(doc.get("parts") or 0)
        if parts <= 0:
            return
        part = int(doc.get("part") or 0)
        fraction = doc.get("fraction")
        stage = str(doc.get("stage") or "generating")
        body = {"current": part, "total": parts, "clip": "", "stage": "generating" if stage == "generating" else stage,
                "done": stage == "done", "fraction": fraction, "overall": fraction,
                "detail": f"part {max(1, part)} of {parts}" if stage == "generating" else str(doc.get("detail") or ""),
                "eta_seconds": None, "alive": _time.time()}
        try:
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(body), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            pass
    return write

def main():
    """Main entry point for the standalone API client"""
    # Parse command line arguments  
    args = parse_arguments()
    
    # Adapter profile: where the generation backend runs and how to talk to it.
    # Named on the command line, else the profile selected in the plugin.
    from api.adapters import load_profile, profile_url, selected_profile
    if getattr(args, 'adapter', None):
        adapter_profile = load_profile(args.adapter)
        if adapter_profile is None:
            print(json.dumps({"success": False, "error": f"adapter profile not found: {args.adapter}"}))
            return 1
    else:
        adapter_profile = selected_profile("generation")
    if adapter_profile is not None:
        if args.api_url:
            # An explicit address wins over the profile's, e.g. to try a backend on another port
            adapter_profile = dict(adapter_profile, base_url=args.api_url, base_url_tunnel="")
        args.api_url = profile_url(adapter_profile)

    # Set API URL from config if not explicitly provided
    if args.api_url is None:
        args.api_url = get_api_url("mmaudio")
    
    # DEBUG: File-based logging for background processes (stdout/stderr not captured!)
    import tempfile
    log_file = os.path.join(tempfile.gettempdir(), "pt_v2a_debug.log")
    
    from api.config import logs_enabled
    write_log_file = logs_enabled()

    def log_debug(msg):
        """Write to file (unless log saving is off in the settings) and stderr"""
        if write_log_file:
            with open(log_file, "a", encoding="utf-8") as f:
                timestamp = __import__('datetime').datetime.now().strftime("%H:%M:%S.%f")[:-3]
                f.write(f"[{timestamp}] {msg}\n")
                f.flush()
        # Only write to stderr (not stdout) to avoid duplication in plugin output
        print(msg, file=sys.stderr)
        sys.stderr.flush()
    
    log_debug(f"=== DEBUG: Script started, sys.argv={sys.argv} ===")
    log_debug(f"=== DEBUG: Log file: {log_file} ===")
    log_debug(f"=== DEBUG: args.action={args.action} ===")
    log_debug(f"=== DEBUG: args.auto_detect_clip_bounds={args.auto_detect_clip_bounds} ===")
    log_debug(f"=== DEBUG: args.video={args.video} ===")
    
    # Determine operation mode
    quiet = args.quiet
    verbose = args.verbose
    
    # =============================================================================
    # Handle CLI Actions
    # =============================================================================
    
    if args.action == 'check_ffmpeg':
        """Check FFmpeg availability"""
        return safe_action_wrapper(lambda: action_check_ffmpeg(log_debug_func=log_debug))
    
    elif args.action == 'get_video_selection':
        """Get timeline selection from Pro Tools"""
        def get_video_selection_logic():
            log_debug("=== DEBUG: get_video_selection action START ===")
            result = get_video_timeline_selection()
            log_debug(f"=== DEBUG: PTSL call completed, result={result['success']} ===")
            return result
        
        return safe_action_wrapper(get_video_selection_logic)
    
    elif args.action == 'get_clip_bounds':
        """Get clip boundaries from Pro Tools Clips List (async, fast, no deadlock!)"""
        def get_clip_bounds_logic():
            log_debug(f"=== DEBUG: get_clip_bounds action START ===")
            
            # Import PTSL
            from ptsl import open_engine
            from ptsl_integration.clip_info import (
                get_session_framerate,
                get_clip_info_for_selected_video,
                calculate_trim_points_from_clip
            )
            
            log_debug("Connecting to Pro Tools for clip bounds...")
            
            # Connect to Pro Tools (this is FAST - just reads data, no waiting!)
            with open_engine(
                company_name="YourCompany",
                application_name="ProTools V2A Plugin"
            ) as engine:
                log_debug("Connected!")
                
                # Get framerate
                fps = get_session_framerate(engine)
                log_debug(f"Framerate: {fps} fps")
                
                # Get clip info
                clip_info = get_clip_info_for_selected_video(engine)
                
                if not clip_info:
                    log_debug("ERROR: No video clip found in Clips List")
                    return {
                        'success': False,
                        'error': 'No video clip found in Clips List'
                    }
                
                # Calculate trim points
                trim_info = calculate_trim_points_from_clip(clip_info, fps)
                
                result = {
                    'success': True,
                    'clip_name': clip_info.get('clip_name', 'Unknown'),
                    'start_seconds': trim_info['start_seconds'],
                    'end_seconds': trim_info['end_seconds'],
                    'duration_seconds': trim_info['duration_seconds'],
                    'start_frame': trim_info['start_frame'],
                    'end_frame': trim_info['end_frame'],
                    'fps': fps
                }
                
                log_debug(f"Clip bounds: {result['start_seconds']}s - {result['end_seconds']}s")
                return result
        
        return safe_action_wrapper(get_clip_bounds_logic)
    
    elif args.action == 'resolve_video_segments':
        """Map the timeline selection (any track) onto the video clips beneath it"""
        def resolve_video_segments_logic():
            from ptsl import open_engine
            from ptsl_integration.video_segments import resolve_video_segments

            log_debug(f"=== DEBUG: resolve_video_segments START (whole_track={args.whole_track}) ===")
            with open_engine(company_name="AI Sound Design", application_name="Video segments") as engine:
                return resolve_video_segments(engine, whole_track=args.whole_track,
                                              track_name=args.video_track or None, log=log_debug)

        return safe_action_wrapper(resolve_video_segments_logic)

    elif args.action == 'export_selection_audio':
        """The audio under the selection on the selected tracks as one WAV (--output): the
        query for a search by sound"""
        def export_selection_audio_logic():
            import tempfile as _tempfile
            from ptsl import open_engine
            from ptsl_integration.audio_segments import export_selection_audio

            target = Path(args.output) if args.output else \
                Path(_tempfile.gettempdir()) / "ai_sound_design_selection_audio.wav"
            with open_engine(company_name="AI Sound Design", application_name="Selection audio") as engine:
                return export_selection_audio(engine, target, log=log_debug)

        return safe_action_wrapper(export_selection_audio_logic)

    elif args.action == 'list_video_tracks':
        """The session's video tracks, top to bottom (for the plugin's Video track list)"""
        def list_video_tracks_logic():
            from ptsl import open_engine
            from ptsl_integration.video_segments import _is_video_track

            with open_engine(company_name="AI Sound Design", application_name="Video tracks") as engine:
                return {"success": True, "tracks": [t.name for t in engine.track_list() if _is_video_track(t)]}

        return safe_action_wrapper(list_video_tracks_logic)

    elif args.action == 'get_video_info':
        """Get timeline selection AND video file in one PTSL call (faster!)"""
        return safe_action_wrapper(lambda: action_get_video_info(log_debug_func=log_debug))
    
    elif args.action == 'get_video_file':
        """Get video file path from Pro Tools"""
        return safe_action_wrapper(lambda: get_video_file_from_protools())
    
    elif args.action == 'trim_video':
        """Trim video segment"""
        def trim_video_logic():
            if not args.video:
                return {
                    'success': False,
                    'error': '--video argument required for trim_video action'
                }
            
            if args.start_time is None or args.end_time is None:
                return {
                    'success': False,
                    'error': '--start-time and --end-time required for trim_video action'
                }
            
            return trim_video_segment(
                video_path=args.video,
                start_seconds=args.start_time,
                end_seconds=args.end_time,
                output_path=args.output
            )
        
        return safe_action_wrapper(trim_video_logic)
    
    elif args.action == 'validate_duration':
        """Validate video duration"""
        def validate_duration_logic():
            if args.duration is None:
                return {
                    'valid': False,
                    'error': '--duration argument required for validate_duration action'
                }
            
            return validate_video_duration(
                duration_seconds=args.duration,
                max_duration=args.max_duration
            )
        
        return safe_action_wrapper(validate_duration_logic)
    
    elif args.action == 'get_duration':
        """Get video file duration using FFprobe"""
        return safe_action_wrapper(lambda: action_get_duration(video_path=args.video, log_debug_func=log_debug))
    
    elif args.action in ('list_adapters', 'ensure_adapters'):
        """Adapter profiles for the plugin: the folder, every profile, the selection per kind."""
        def adapters_logic():
            from api.adapters import describe, ensure_default_profiles
            ensure_default_profiles()
            return describe()

        return safe_action_wrapper(adapters_logic)

    elif args.action == 'import_audio':
        """Import audio file to Pro Tools timeline"""
        def import_audio_logic():
            log_debug("=== DEBUG: import_audio action START ===")
            
            if not args.audio_path:
                log_debug("ERROR: --audio-path argument required")
                return {
                    'success': False,
                    'error': '--audio-path argument required for import_audio action'
                }
            
            log_debug(f"Audio path: {args.audio_path}")
            
            # Get timecode if provided
            timecode = args.timecode if hasattr(args, 'timecode') and args.timecode else None
            if timecode:
                log_debug(f"Import timecode: {timecode}")
            else:
                log_debug("Import timecode: Not specified (will use session start)")
            
            # Import to Pro Tools timeline
            return action_import_audio(
                audio_path=args.audio_path,
                timecode=timecode,
                log_debug_func=log_debug,
                track_name=getattr(args, 'track_name', None) or None,
                clip_name=getattr(args, 'clip_name', None) or None,
                timecode_out=getattr(args, 'timecode_out', None) or None,
                cut=bool(getattr(args, 'cut', False)),
                handle_before=float(getattr(args, 'handle_before', 0.0) or 0.0),
                fade_preset=getattr(args, 'fade_preset', None) or None,
                fade_seconds=float(getattr(args, 'fade_seconds', 1.0) or 0.0),
                fade_inside=bool(getattr(args, 'fade_inside', False)),
            )
        
        return safe_action_wrapper(import_audio_logic)
    
    elif args.action == 'clip_detect_and_trim':
        """Detect clip boundaries and trim video (synchronous, foreground)"""
        def clip_detect_and_trim_logic():
            log_debug("=== DEBUG: clip_detect_and_trim action START ===")
            
            if not args.video:
                log_debug("ERROR: --video argument required")
                return {
                    'success': False,
                    'error': '--video argument required for clip_detect_and_trim action'
                }
            
            log_debug(f"Video path: {args.video}")
            
            # Import PTSL modules
            log_debug("Importing PTSL...")
            from ptsl import open_engine
            from ptsl_integration.clip_info import (
                get_session_framerate,
                get_clip_info_for_selected_video,
                calculate_trim_points_from_clip
            )
            log_debug("PTSL imported successfully")
            
            # Connect to Pro Tools (FOREGROUND = has UI access!)
            log_debug("Connecting to Pro Tools...")
            with open_engine(
                company_name="YourCompany",
                application_name="ProTools V2A Plugin"
            ) as engine:
                log_debug("Connected to Pro Tools")
                
                # Get session framerate
                fps = get_session_framerate(engine)
                log_debug(f"Session framerate: {fps} fps")
                
                # Get clip info from Clips List
                log_debug("Getting clip info...")
                clip_info = get_clip_info_for_selected_video(engine)
                
                if not clip_info:
                    log_debug("ERROR: No video clip found in Clips List. Make sure a video clip is selected.")
                    return {
                        'success': False,
                        'error': 'No video clip found in Clips List. Make sure a video clip is selected.'
                    }
                
                clip_name = clip_info.get('clip_name', 'Unknown')
                start_frame = clip_info['start_frame']
                end_frame = clip_info['end_frame']
                log_debug(f"Found clip '{clip_name}': frames {start_frame}-{end_frame}")
                
                # Calculate trim points
                trim_info = calculate_trim_points_from_clip(clip_info, fps)
                start_seconds = trim_info['start_seconds']
                end_seconds = trim_info['end_seconds']
                log_debug(f"Trim points: {start_seconds}s - {end_seconds}s")
            
            # Trim video using FFmpeg
            log_debug(f"Trimming video: {start_seconds}s - {end_seconds}s")
            trim_result = trim_video_segment(
                video_path=args.video,
                start_seconds=start_seconds,
                end_seconds=end_seconds
            )
            
            if not trim_result['success']:
                error_msg = f"Video trimming failed: {trim_result['error']}"
                log_debug(f"ERROR: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
            
            trimmed_path = trim_result['output_path']
            log_debug(f"Trimmed video saved: {trimmed_path}")
            
            # Return success with trimmed video path
            return {
                'success': True,
                'trimmed_video_path': trimmed_path,
                'clip_name': clip_name,
                'start_seconds': start_seconds,
                'end_seconds': end_seconds,
                'duration_seconds': trim_info['duration_seconds']
            }
        
        return safe_action_wrapper(clip_detect_and_trim_logic)
    
    elif args.action == 'test_cloudflare':
        """Test Cloudflare Access credentials"""
        def test_cloudflare_logic():
            log_debug("=== DEBUG: test_cloudflare action START ===")
            
            if not args.cf_client_id or not args.cf_client_secret:
                log_debug("ERROR: --cf-client-id and --cf-client-secret required")
                return {
                    'success': False,
                    'error': '--cf-client-id and --cf-client-secret required for test_cloudflare action'
                }
            
            log_debug(f"Client ID: {args.cf_client_id}")
            log_debug(f"Client Secret: {args.cf_client_secret[:10]}...")
            
            import requests
            # get_api_url already imported at top of file (line 52)
            
            # Get cloudflared URL (both services should work)
            mmaudio_url = "https://mmaudio.example.com"
            hyvf_url = "https://hyvf.example.com"
            
            log_debug(f"Testing MMAudio API: {mmaudio_url}")
            
            # Test connection with credentials
            headers = {
                "CF-Access-Client-Id": args.cf_client_id,
                "CF-Access-Client-Secret": args.cf_client_secret
            }
            
            log_debug("Sending request with CF-Access headers...")
            response = requests.get(
                f"{mmaudio_url}/",
                headers=headers,
                timeout=10
            )
            
            log_debug(f"Response status: {response.status_code}")
            log_debug(f"Response preview: {response.text[:200]}")
            
            if response.status_code == 200:
                # Check if response is JSON (not HTML login page)
                try:
                    data = response.json()
                    log_debug(f"Response is JSON: {data}")
                    
                    log_debug("✓ Credential test SUCCESS")
                    return {
                        'success': True,
                        'message': 'Credentials are valid and API is accessible',
                        'api_response': data
                    }
                    
                except ValueError:
                    # Response is HTML, authentication failed
                    error_msg = 'Credentials may be invalid or Access Policy misconfigured.'
                    log_debug(f"ERROR: {error_msg}")
                    return {
                        'success': False,
                        'error': error_msg
                    }
            else:
                error_msg = f'API returned status code {response.status_code}. Check Cloudflare Access configuration.'
                log_debug(f"ERROR: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
        
        return safe_action_wrapper(test_cloudflare_logic)
    
    # =============================================================================
    # Standard Generation Mode (action == 'generate' or 't2a')
    # =============================================================================
    
    # CLI mode if video OR duration is provided (V2A or T2A) OR explicit action is t2a
    is_cli_mode = args.video is not None or args.duration is not None or args.action == 't2a'
    # T2A mode: explicit via --action t2a OR inferred (no video + has duration)
    is_t2a_mode = args.action == 't2a' or (args.video is None and args.duration is not None)
    
    if not quiet:
        print("🌐 MMAudio Standalone API Client")
        print("=" * 50)
        if is_cli_mode:
            mode_str = "T2A (Text-Only)" if is_t2a_mode else "V2A (Video-to-Audio)"
            print(f"📋 CLI Mode ({mode_str})")
        else:
            print("🎮 Interactive Mode")
        print()
    
    try:
        # === CLI MODE ===
        if is_cli_mode:
            # Validate video file (skip for T2A mode)
            if not is_t2a_mode:
                try:
                    video_path_obj = validate_video_file(args.video)
                    video_path = str(video_path_obj)
                    
                except (FileNotFoundError, ValueError) as e:
                    error_msg = f"Video validation failed: {e}"
                    if not quiet:
                        print(f"❌ {error_msg}")
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    return 1
                
                if verbose and not quiet:
                    file_size_mb = video_path_obj.stat().st_size / (1024 * 1024)
                    print(f"📹 Video: {video_path_obj.name} ({file_size_mb:.1f} MB)")
            else:
                # T2A mode: no video
                video_path = None
                if verbose and not quiet:
                    print(f"🎵 T2A Mode: Duration = {args.duration}s")
            
            # Use CLI parameters
            prompt = args.prompt
            negative_prompt = args.negative_prompt  
            seed = args.seed
        
        # === INTERACTIVE MODE ===
        else:
            # Get video path interactively
            video_path = get_video_path_interactive()
            
            # Get generation parameters interactively
            prompt, negative_prompt, seed = get_user_inputs_interactive()
        
        # === COMMON PROCESSING ===
        
        # Force WAV format if importing to Pro Tools (PTSL requires WAV)
        if args.import_to_protools and args.output_format != 'wav':
            if not quiet:
                print(f"\n⚠️  Forcing WAV format (Pro Tools requires WAV, not FLAC)")
            print(f"=== DEBUG: Forcing output_format to 'wav' for Pro Tools import ===", file=sys.stderr)
            args.output_format = 'wav'
        
        # Check API health
        if not quiet:
            print(f"\n🔗 Checking API connection to {args.api_url}...")
        
        print(f"=== DEBUG: Checking API health at {args.api_url} ===", file=sys.stderr)

        if adapter_profile is None:
            error_msg = ("no generation backend: no adapter profile is selected and none was given "
                         "with --adapter (see the plugin's Settings, Open Adapter Folder)")
            print(f"ERROR: {error_msg}", file=sys.stderr)
            return 1

        from api.adapters import check_health, generate_with_profile
        healthy, note = check_health(adapter_profile)
        if not healthy:
            error_msg = f"{adapter_profile.get('name', 'The backend')} is not reachable at {args.api_url}: {note}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            if not quiet:
                print("\n💡 Make sure the backend is running and the address in Settings is right.")
            return 1

        print(f"=== DEBUG: API health check passed ===", file=sys.stderr)
        if not quiet:
            print("✅ Backend is online!")
        
        # === Video Preprocessing (Downscaling) ===
        # Check if video needs downscaling BEFORE workflow processing
        # This handles untrimmed videos (trimmed videos are checked after trimming)
        # Skip for T2A mode (no video)
        # Note: Downscaling is now ALWAYS done after trimming in trim_and_maybe_downscale_video()
        # This prevents timeout issues with very large videos
        will_be_trimmed = (
            (args.video_offset and args.clip_start_seconds is not None and args.clip_end_seconds is not None) or
            (args.clip_start_seconds is not None and args.clip_end_seconds is not None) or
            args.auto_detect_clip_bounds or
            (args.video_offset and args.timeline_start != 0.0 and args.timeline_end != 0.0)
        )
        
        # Log video size for debugging
        if not is_t2a_mode:
            file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            log_debug(f"=== DEBUG: Input video size: {file_size_mb:.1f} MB (threshold: {VIDEO_DOWNSCALE_THRESHOLD_MB} MB) ===")
            
            if will_be_trimmed:
                log_debug(f"=== DEBUG: Video will be trimmed first, then downscaled if needed ===")
            else:
                log_debug(f"=== DEBUG: Video will not be trimmed, may need downscaling ===")
        
        # === Video Trimming (Four workflows supported) ===
        # 1. MANUAL OFFSET + CLIP BOUNDS (trimmed clip + manual offset): Both --video-offset AND --clip-start-seconds provided
        # 2. CLIP BOUNDS ONLY (auto-detect): --clip-start-seconds and --clip-end-seconds provided
        # 3. MANUAL OFFSET ONLY (untrimmed clip): --video-offset provided
        # 4. AUTO-DETECT (legacy): --auto-detect-clip-bounds (runs PTSL in background - can deadlock!)
        
        # NEW Workflow 1: Manual offset on TRIMMED clip (combined workflow)
        # When user provides manual offset AND we have clip bounds, we need BOTH to calculate correctly:
        # source_start = clip_source_start + (timeline_start - clip_timeline_start)
        if args.video_offset and args.clip_start_seconds is not None and args.clip_end_seconds is not None:
            log_debug(f"=== DEBUG: Manual offset + clip bounds (trimmed clip workflow) ===")
            log_debug(f"Video offset (timeline pos): {args.video_offset}")
            log_debug(f"Clip bounds (source): {args.clip_start_seconds}s - {args.clip_end_seconds}s")
            
            if not quiet:
                print(f"\n✂️  Manual offset on trimmed clip...")
                print(f"   Clip bounds: {args.clip_start_seconds:.3f}s - {args.clip_end_seconds:.3f}s in source")
            
            # Parse video offset to timeline seconds
            try:
                video_clip_timeline_start = timecode_to_seconds(args.video_offset)
                log_debug(f"Video clip timeline position: {video_clip_timeline_start}s")
            except Exception as e:
                error_msg = f"Failed to parse video offset '{args.video_offset}': {e}"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                return 1
            
            # Get timeline selection
            if args.timeline_start == 0.0 and args.timeline_end == 0.0:
                error_msg = "Timeline selection required (--timeline-start and --timeline-end) with --video-offset"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                return 1
            
            timeline_in_seconds = args.timeline_start
            timeline_out_seconds = args.timeline_end
            
            log_debug(f"Timeline selection: {timeline_in_seconds}s - {timeline_out_seconds}s")
            
            # Calculate: source_start = clip_source_start + (timeline_start - clip_timeline_start)
            relative_in_clip = timeline_in_seconds - video_clip_timeline_start
            start_in_source = args.clip_start_seconds + relative_in_clip
            end_in_source = args.clip_start_seconds + (timeline_out_seconds - video_clip_timeline_start)
            
            log_debug(f"Relative offset in clip: {relative_in_clip}s")
            log_debug(f"Final source range: {start_in_source}s - {end_in_source}s")
            
            if relative_in_clip < 0:
                error_msg = f"Selection starts before clip (timeline={timeline_in_seconds}s, clip_start={video_clip_timeline_start}s)"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                return 1
            
            if not quiet:
                print(f"   Timeline selection: {timeline_in_seconds}s - {timeline_out_seconds}s")
                print(f"   Clip timeline position: {video_clip_timeline_start}s")
                print(f"   Trimming source: {start_in_source:.3f}s - {end_in_source:.3f}s")
            
            # Trim video (with automatic downscaling if needed)
            trim_result = trim_and_maybe_downscale_video(
                video_path=video_path,
                start_seconds=start_in_source,
                end_seconds=end_in_source
            )
            
            if not trim_result['success']:
                error_msg = f"Video trimming failed: {trim_result.get('error', 'Unknown error')}"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                return 1
            
            video_path = trim_result['output_path']
            log_debug(f"=== DEBUG: Trimmed video saved to: {video_path} ===")
            log_debug(f"=== DEBUG: Original size: {trim_result['original_size_mb']:.1f} MB, Final size: {trim_result['final_size_mb']:.1f} MB ===")
            log_debug(f"=== DEBUG: Downscaled: {trim_result['downscaled']}, Encoding time: {trim_result['encoding_time']:.1f}s ===")
            
            if trim_result['downscaled']:
                if not quiet:
                    print(f"⚡ Video trimmed and downscaled to 480p in {trim_result['encoding_time']:.1f}s")
            else:
                if not quiet:
                    print(f"✂️  Video trimmed in {trim_result['encoding_time']:.1f}s")
            
            log_debug(f"=== DEBUG: Will use trimmed video: {video_path} ===")
        
        # Workflow 2: Clip bounds provided by C++ plugin (async, safe, no deadlock!)
        elif args.clip_start_seconds is not None and args.clip_end_seconds is not None:
            log_debug(f"=== DEBUG: Clip bounds provided by plugin ===")
            log_debug(f"Start: {args.clip_start_seconds}s, End: {args.clip_end_seconds}s")
            
            if not quiet:
                print(f"\n✂️  Trimming video to clip boundaries...")
                print(f"   {args.clip_start_seconds:.3f}s - {args.clip_end_seconds:.3f}s")
            
            # Trim video using provided boundaries (with automatic downscaling if needed)
            trim_result = trim_and_maybe_downscale_video(
                video_path=video_path,
                start_seconds=args.clip_start_seconds,
                end_seconds=args.clip_end_seconds
            )
            
            if not trim_result['success']:
                error_msg = f"Video trimming failed: {trim_result['error']}"
                log_debug(f"ERROR: {error_msg}")
                if not quiet:
                    print(f"❌ {error_msg}")
                return 1
            
            # Use trimmed video for generation
            video_path = trim_result['output_path']
            log_debug(f"=== DEBUG: Trimmed video saved to: {video_path} ===")
            log_debug(f"=== DEBUG: Original size: {trim_result['original_size_mb']:.1f} MB, Estimated: {trim_result['estimated_size_mb']:.1f} MB, Final: {trim_result['final_size_mb']:.1f} MB ===")
            log_debug(f"=== DEBUG: Downscaled: {trim_result['downscaled']}, Encoding time: {trim_result['encoding_time']:.1f}s ===")
            
            if not quiet:
                print(f"✅ Video processed successfully ({trim_result['duration']:.1f}s)")
                if trim_result['downscaled']:
                    print(f"   ⚡ Trimmed + downscaled to 480p in {trim_result['encoding_time']:.1f}s")
                else:
                    print(f"   ✂️  Trimmed in {trim_result['encoding_time']:.1f}s")
                print(f"   📦 Final size: {trim_result['final_size_mb']:.1f} MB")
            
            log_debug(f"=== DEBUG: Will use processed video: {video_path} ===")
        
        # Workflow 4 (LEGACY): Automatic clip detection (can cause deadlock if called from plugin!)
        # This workflow is deprecated - use C++ async clip bounds read instead
        elif args.auto_detect_clip_bounds:
            log_debug(f"=== DEBUG: Automatic clip detection requested (legacy workflow) ===")
            
            if not quiet:
                print(f"\n🔍 Auto-detecting clip boundaries from Pro Tools (legacy)...")
            
            log_debug(f"=== DEBUG: Starting PTSL imports... ===")
            
            try:
                log_debug(f"=== DEBUG: Importing ptsl module... ===")
                from ptsl import open_engine
                log_debug(f"=== DEBUG: ptsl imported successfully ===")  
                
                log_debug(f"=== DEBUG: Importing clip_info functions... ===")
                from ptsl_integration.clip_info import (
                    get_session_framerate,
                    get_clip_info_for_selected_video,
                    calculate_trim_points_from_clip
                )
                log_debug(f"=== DEBUG: All imports successful! ===")
                
                # Connect to Pro Tools to read clip info
                clip_timeline_position = None  # Store timeline position for later import
                
                log_debug(f"=== DEBUG: Opening PTSL engine connection... ===")
                
                with open_engine(
                    company_name="YourCompany",
                    application_name="ProTools V2A Plugin"
                ) as engine:
                    log_debug(f"=== DEBUG: PTSL engine connected ===")
                    
                    # Get session framerate
                    log_debug(f"=== DEBUG: Getting session framerate... ===")
                    fps = get_session_framerate(engine)
                    log_debug(f"=== DEBUG: Session framerate: {fps} fps ===")
                    
                    if not quiet:
                        print(f"   Session framerate: {fps} fps")
                    
                    # Get timeline selection (position where clip is placed)
                    log_debug(f"=== DEBUG: Getting timeline selection... ===")
                    import ptsl.PTSL_pb2 as pt
                    timeline_in, timeline_out = engine.get_timeline_selection(pt.TimeCode)
                    clip_timeline_position = timeline_in  # Store for audio import
                    log_debug(f"=== DEBUG: Timeline position: {timeline_in} ===")
                    
                    if not quiet:
                        print(f"   Timeline position: {timeline_in}")
                    
                    # Get clip info from Clips List
                    log_debug(f"=== DEBUG: Getting clip info from Clips List... ===")
                    clip_info = get_clip_info_for_selected_video(engine)
                    log_debug(f"=== DEBUG: Clip info retrieved: {clip_info is not None} ===")
                    
                    if not clip_info:
                        error_msg = "No video clip found in Clips List. Make sure a video clip is selected in Pro Tools."
                        print(f"ERROR: {error_msg}", file=sys.stderr)
                        if not quiet:
                            print(f"❌ {error_msg}")
                            print(f"   💡 Workflow:")
                            print(f"      1. Cut video clip in Pro Tools (if needed)")
                            print(f"      2. Select the clip")
                            print(f"      3. Clip should appear in Clips List")
                        return 1
                    
                    clip_name = clip_info.get('clip_name', 'Unknown')
                    start_frame = clip_info['start_frame']
                    end_frame = clip_info['end_frame']
                    
                    print(f"=== DEBUG: Found clip '{clip_name}': frames {start_frame}-{end_frame} ===", file=sys.stderr)
                    
                    if not quiet:
                        print(f"   Found clip: {clip_name}")
                        print(f"   Frame range: {start_frame} - {end_frame}")
                    
                    # Calculate trim points
                    trim_info = calculate_trim_points_from_clip(clip_info, fps)
                    start_seconds = trim_info['start_seconds']
                    end_seconds = trim_info['end_seconds']
                    duration = trim_info['duration_seconds']
                    
                    print(f"=== DEBUG: Trim points: {start_seconds}s - {end_seconds}s (duration: {duration}s) ===", file=sys.stderr)
                    
                    if not quiet:
                        print(f"   Time range: {start_seconds:.3f}s - {end_seconds:.3f}s")
                        print(f"   Duration: {duration:.3f}s")
                
                # Trim video using detected boundaries
                log_debug(f"=== DEBUG: Starting video trim: {start_seconds}s - {end_seconds}s ===")
                
                if not quiet:
                    print(f"   Trimming source video to clip boundaries...")
                
                trim_result = trim_video_segment(
                    video_path=video_path,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds
                )
                
                log_debug(f"=== DEBUG: Trim result: success={trim_result['success']} ===")
                
                if not trim_result['success']:
                    error_msg = f"Video trimming failed: {trim_result['error']}"
                    log_debug(f"ERROR: {error_msg}")
                    if not quiet:
                        print(f"❌ {error_msg}")
                    return 1
                
                # Use trimmed video for generation
                trimmed_video_path = trim_result['output_path']
                log_debug(f"=== DEBUG: Trimmed video saved to: {trimmed_video_path} ===")
                log_debug(f"=== DEBUG: Replacing video_path for generation ===")
                
                if not quiet:
                    print(f"✅ Video trimmed successfully ({trim_result['duration']:.1f}s)")
                    print(f"   Trimmed video: {Path(trimmed_video_path).name}")
                
                # Check if trimmed video should be downscaled
                file_size_mb = Path(trimmed_video_path).stat().st_size / (1024 * 1024)
                log_debug(f"=== DEBUG: Trimmed video size: {file_size_mb:.1f} MB (threshold: {VIDEO_DOWNSCALE_THRESHOLD_MB} MB) ===")
                
                if file_size_mb > VIDEO_DOWNSCALE_THRESHOLD_MB:
                    log_debug(f"=== DEBUG: File size exceeds threshold, downscaling to 480p... ===")
                    downscale_result = downscale_video(trimmed_video_path)
                    if downscale_result['success']:
                        log_debug(f"=== DEBUG: Downscaled: {downscale_result['original_size_mb']:.1f} MB → {downscale_result['downscaled_size_mb']:.1f} MB ({downscale_result['compression_ratio']:.0f}x smaller, {downscale_result['encoding_time']:.1f}s) ===")
                        trimmed_video_path = downscale_result['output_path']
                        if not quiet:
                            print(f"⚡ Video downscaled to 480p ({downscale_result['compression_ratio']:.0f}x smaller)")
                    else:
                        log_debug(f"=== DEBUG: Downscaling failed: {downscale_result['error']} ===")
                else:
                    log_debug(f"=== DEBUG: File size OK, no downscaling needed ===")
                
                # Replace video_path with trimmed version
                video_path = trimmed_video_path
                
                log_debug(f"=== DEBUG: Will use trimmed video: {video_path} ===")
                
            except Exception as e:
                import traceback
                error_msg = f"Automatic clip detection failed: {e}"
                traceback_str = traceback.format_exc()
                log_debug(f"ERROR: {error_msg}")
                log_debug(f"=== DEBUG: Traceback ===")
                # Log each line of traceback separately for better visibility
                for line in traceback_str.split('\n'):
                    if line.strip():
                        log_debug(line)
                if not quiet:
                    print(f"❌ {error_msg}")
                    print(f"   💡 Try using manual --video-offset instead")
                return 1
        
        # Workflow 3: Manual video offset WITHOUT clip bounds (untrimmed clip only)
        # This workflow assumes the clip starts at the beginning of the source video
        elif args.video_offset:
            if not quiet:
                print(f"\n✂️  Manual offset (untrimmed clip): {args.video_offset}")
                print(f"   Trimming video to match timeline selection...")
            
            print(f"=== DEBUG: Manual offset workflow (untrimmed) ===", file=sys.stderr)
            print(f"=== DEBUG: Video offset={args.video_offset} ===", file=sys.stderr)
            
            # Parse video offset to seconds (function already imported at top)
            try:
                video_clip_start_seconds = timecode_to_seconds(args.video_offset)
                print(f"=== DEBUG: Video clip starts at {video_clip_start_seconds}s on timeline ===", file=sys.stderr)
            except Exception as e:
                error_msg = f"Failed to parse video offset '{args.video_offset}': {e}"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                    print(f"   Video offset format: 'MM:SS' or 'HH:MM:SS:FF'")
                return 1
            
            # Get timeline selection from C++ plugin parameters (passed via --timeline-start/end)
            if args.timeline_start == 0.0 and args.timeline_end == 0.0:
                error_msg = "Timeline selection times not provided (--timeline-start and --timeline-end required with --video-offset)"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                return 1
            
            timeline_in_seconds = args.timeline_start
            timeline_out_seconds = args.timeline_end
            
            print(f"=== DEBUG: Timeline selection (from C++ plugin): {timeline_in_seconds}s - {timeline_out_seconds}s ===", file=sys.stderr)
            
            # Calculate offset into source video (round to full seconds)
            # Example: Video starts at 2s on timeline, selection starts at 5s
            #          → Need to start at (5-2) = 3s into source video
            start_in_video = round(timeline_in_seconds - video_clip_start_seconds)
            end_in_video = round(timeline_out_seconds - video_clip_start_seconds)
            
            if start_in_video < 0:
                error_msg = f"Invalid offset: Selection starts before video clip (selection={timeline_in_seconds}s, clip_start={video_clip_start_seconds}s)"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                    print(f"   Make sure video clip offset is correct")
                return 1
            
            if not quiet:
                print(f"   Timeline selection: {timeline_in_seconds}s - {timeline_out_seconds}s")
                print(f"   Video clip starts at: {video_clip_start_seconds}s")
                print(f"   Trimming source video: {start_in_video}s - {end_in_video}s")
            
            print(f"=== DEBUG: Trimming video from {start_in_video}s to {end_in_video}s ===", file=sys.stderr)
            
            # Trim video (function already imported at top)
            trim_result = trim_video_segment(
                video_path=video_path,
                start_seconds=start_in_video,
                end_seconds=end_in_video
            )
            
            if not trim_result['success']:
                error_msg = f"Video trimming failed: {trim_result['error']}"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if not quiet:
                    print(f"❌ {error_msg}")
                return 1
            
            # Use trimmed video for generation
            trimmed_video_path = trim_result['output_path']
            print(f"=== DEBUG: Trimmed video saved to: {trimmed_video_path} ===", file=sys.stderr)
            
            if not quiet:
                print(f"✅ Video trimmed successfully ({trim_result['duration']:.1f}s)")
                print(f"   Trimmed video: {Path(trimmed_video_path).name}")
            
            # Check if trimmed video should be downscaled
            file_size_mb = Path(trimmed_video_path).stat().st_size / (1024 * 1024)
            log_debug(f"=== DEBUG: Trimmed video size: {file_size_mb:.1f} MB (threshold: {VIDEO_DOWNSCALE_THRESHOLD_MB} MB) ===")
            
            if file_size_mb > VIDEO_DOWNSCALE_THRESHOLD_MB:
                log_debug(f"=== DEBUG: File size exceeds threshold, downscaling to 480p... ===")
                downscale_result = downscale_video(trimmed_video_path)
                if downscale_result['success']:
                    log_debug(f"=== DEBUG: Downscaled: {downscale_result['original_size_mb']:.1f} MB → {downscale_result['downscaled_size_mb']:.1f} MB ({downscale_result['compression_ratio']:.0f}x smaller, {downscale_result['encoding_time']:.1f}s) ===")
                    trimmed_video_path = downscale_result['output_path']
                    if not quiet:
                        print(f"⚡ Video downscaled to 480p ({downscale_result['compression_ratio']:.0f}x smaller)")
                else:
                    log_debug(f"=== DEBUG: Downscaling failed: {downscale_result['error']} ===")
            else:
                log_debug(f"=== DEBUG: File size OK, no downscaling needed ===")
            
            # Replace video_path with trimmed version
            video_path = trimmed_video_path
        
        # Final check: If video was NOT trimmed, we may still need to downscale large videos
        # (For trimmed videos, downscaling already happened after trimming)
        if not is_t2a_mode and not will_be_trimmed:
            file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            log_debug(f"=== DEBUG: Untrimmed video final size check: {file_size_mb:.1f} MB (threshold: {VIDEO_DOWNSCALE_THRESHOLD_MB} MB) ===")
            
            if file_size_mb > VIDEO_DOWNSCALE_THRESHOLD_MB:
                log_debug(f"=== DEBUG: Untrimmed video exceeds threshold, downscaling to 480p... ===")
                downscale_result = downscale_video(video_path)
                if downscale_result['success']:
                    log_debug(f"=== DEBUG: Downscaled: {downscale_result['original_size_mb']:.1f} MB → {downscale_result['downscaled_size_mb']:.1f} MB ({downscale_result['compression_ratio']:.0f}x smaller, {downscale_result['encoding_time']:.1f}s) ===")
                    video_path = downscale_result['output_path']
                    if not quiet:
                        print(f"⚡ Video downscaled to 480p ({downscale_result['compression_ratio']:.0f}x smaller)")
                else:
                    log_debug(f"=== DEBUG: Downscaling failed: {downscale_result['error']} ===")
                    if not quiet:
                        print(f"⚠️ Downscaling failed, using original video (may be slow)")
            else:
                log_debug(f"=== DEBUG: Untrimmed video size OK, no downscaling needed ===")
        
        # Generate audio through the adapter profile: it knows the endpoint, the
        # field names and how the answer is read. The plugin knows no model.
        import tempfile as _tempfile
        adapter_out_dir = args.output if args.output and not Path(args.output).suffix else \
            str(Path(_tempfile.gettempdir()) / "pt_v2a_outputs")
        output_file = generate_with_profile(
            adapter_profile,
            video_path=None if is_t2a_mode else video_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            duration=args.duration,
            output_dir=adapter_out_dir,
            output_format=args.output_format,
            timeout=args.timeout,
            log=lambda m: print(m, file=sys.stderr),
            on_progress=_generation_progress_writer(args.progress_file),
        )
        
        if output_file:
            # Import to Pro Tools if requested
            if args.import_to_protools:
                if not quiet:
                    print(f"\n📥 Importing to Pro Tools timeline...")
                
                print(f"=== DEBUG: Starting PTSL import ===", file=sys.stderr)
                print(f"Audio file: {output_file}", file=sys.stderr)
                
                # Use clip timeline position if available (from auto-detect workflow)
                import_timecode = None
                if args.auto_detect_clip_bounds and 'clip_timeline_position' in locals():
                    import_timecode = clip_timeline_position
                    print(f"=== DEBUG: Importing at clip position: {import_timecode} ===", file=sys.stderr)
                    if not quiet:
                        print(f"   Importing at timeline position: {import_timecode}")
                
                try:
                    success = import_audio_to_pro_tools(
                        audio_path=output_file,
                        timecode=import_timecode  # Use timeline position or None (session start)
                    )
                    
                    if success:
                        print(f"=== DEBUG: PTSL import SUCCESS ===", file=sys.stderr)
                        if not quiet:
                            print(f"✅ Audio imported to Pro Tools timeline!")
                    else:
                        print(f"WARNING: PTSL import returned False", file=sys.stderr)
                        if not quiet:
                            print(f"⚠️  PTSL import failed - audio file saved but not imported")
                except Exception as e:
                    print(f"ERROR: PTSL import exception: {e}", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    if not quiet:
                        print(f"⚠️  PTSL import failed: {e}")
                        print(f"   Audio file saved at: {output_file}")
            
            if quiet:
                # Pro Tools integration: just print the output path
                print(output_file)
            else:
                print(f"\n🎉 Success! Audio generated and saved.")
                print(f"   Output: {output_file}")
            
            print(f"=== DEBUG: Generation completed successfully ===", file=sys.stderr)
            print(f"Output file: {output_file}", file=sys.stderr)
            return 0
        else:
            error_msg = "Audio generation failed - no output file returned"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            if not quiet:
                print(f"\n❌ Audio generation failed.")
            return 1
            
    except KeyboardInterrupt:
        if not quiet:
            print(f"\n\n⚠️  Operation cancelled by user.", file=sys.stderr)
        return 1
    except Exception as e:
        # Print errors to BOTH stdout and stderr for maximum visibility
        # stdout: For C++ plugin to parse
        # stderr: For python_stderr.log debugging
        import traceback
        error_msg = f"ERROR: {e}"
        print(error_msg)  # stdout for C++ parsing
        print(error_msg, file=sys.stderr)  # stderr for logging
        print("\nFull traceback:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    exit(main())
