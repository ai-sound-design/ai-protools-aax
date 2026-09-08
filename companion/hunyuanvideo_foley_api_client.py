#!/usr/bin/env python3
"""
HunyuanVideo-Foley Standalone API Client

A client script that uses the HunyuanVideo-Foley standalone API server for video-to-audio generation.

Usage:
    # Interactive Mode
    python hunyuanvideo_foley_api_client.py
    
    # CLI Mode (Pro Tools ready)
    python hunyuanvideo_foley_api_client.py --video /path/to/video.mp4 --prompt "footsteps on concrete"
    
    # Full CLI Mode
    python hunyuanvideo_foley_api_client.py \
        --video /path/to/video.mp4 \
        --prompt "rain on window" \
        --negative-prompt "voices, music" \
        --seed 42 \
        --model-size xxl \
        --output /path/to/output.wav

Features:
- Interactive parameter input (prompt, negative prompt, seed, model size)
- CLI arguments for Pro Tools integration
- Automatic video duration detection
- Progress feedback and timing information
- Compatible with existing video test files
- Multiple video format support (MP4, MOV, AVI)
- Model size selection (xl: faster, xxl: higher quality)

Note:
    This client is analogous to standalone_api_client.py but targets the HunyuanVideo-Foley API
    which runs on port 8001 with 48kHz audio output and different model parameters.
"""

import argparse
import json
import sys
import os
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime

# Import from refactored modules
from api import (
    get_api_url,
    SUPPORTED_VIDEO_FORMATS,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_SEED,
    DEFAULT_TIMEOUT,
    VIDEO_DOWNSCALE_THRESHOLD_MB,
    HYVF_DEFAULT_API_URL,
    HYVF_DEFAULT_NUM_STEPS,
    HYVF_DEFAULT_CFG_STRENGTH,
    HYVF_DEFAULT_MODEL_SIZE,
    DEFAULT_OUTPUT_FORMAT,
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
)

from cli.error_handler import safe_action_wrapper

# HunyuanVideo-Foley specific imports
from api.hunyuanvideo_foley_client import (
    check_api_health,
    get_available_models,
    generate_audio,
)

# Legacy configuration (for backwards compatibility)
DEFAULT_VIDEO_PATH = r"C:\Users\Username\model-tests\data\MMAudio_examples\noSound\sora_galloping.mp4"

# =============================================================================
# CLI Functions (parse arguments, interactive mode, main entry point)
# =============================================================================

def parse_arguments():
    """Parse command line arguments for CLI mode and Pro Tools integration"""
    parser = argparse.ArgumentParser(
        description="HunyuanVideo-Foley Standalone API Client - Generate Foley audio from video using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python hunyuanvideo_foley_api_client.py
  
  # CLI mode (Pro Tools ready)
  python hunyuanvideo_foley_api_client.py --video /tmp/protools_clip.mov --prompt "footsteps"
  
  # Full CLI mode with all options
  python hunyuanvideo_foley_api_client.py \\
    --video /path/to/video.mp4 \\
    --prompt "rain and thunder" \\
    --negative-prompt "voices, music" \\
    --seed 42 \\
    --model-size xl \\
    --output /path/to/custom_output.wav \\
    --duration 10.0 \\
    --steps 50 \\
    --cfg-strength 4.5
        """
    )
    
    # Video input (required for CLI mode)
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
        help=f'Random seed for reproducible results (default: {DEFAULT_SEED})'
    )
    
    parser.add_argument(
        '--model-size',
        type=str,
        choices=['xl', 'xxl'],
        default=HYVF_DEFAULT_MODEL_SIZE,
        help=f'Model size: "xl" (faster, 8-12GB VRAM) or "xxl" (higher quality, 16-20GB VRAM, default: {HYVF_DEFAULT_MODEL_SIZE})'
    )
    
    # Output options
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output file path (default: auto-generated in ./hunyuanvideo-foley-outputs/)'
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
    
    # Advanced parameters
    parser.add_argument(
        '--duration', '-d',
        type=float,
        help='Duration in seconds (default: auto-detect from video)'
    )
    
    parser.add_argument(
        '--steps',
        type=int,
        default=HYVF_DEFAULT_NUM_STEPS,
        help=f'Number of generation steps (default: {HYVF_DEFAULT_NUM_STEPS})'
    )
    
    parser.add_argument(
        '--cfg-strength',
        type=float,
        default=HYVF_DEFAULT_CFG_STRENGTH,
        help=f'CFG strength for prompt guidance (default: {HYVF_DEFAULT_CFG_STRENGTH})'
    )
    
    parser.add_argument(
        '--output-format',
        type=str,
        choices=['wav', 'flac'],
        default=DEFAULT_OUTPUT_FORMAT,
        help=f'Output audio format: "wav" (Pro Tools compatible) or "flac" (smaller, default: {DEFAULT_OUTPUT_FORMAT})'
    )
    
    parser.add_argument(
        '--full-precision',
        action='store_true',
        help='Use float32 for features/latents instead of bfloat16 (default). '
             'NOTE: Model inference is always bfloat16→float32 (hardcoded). '
             'Effect is minimal, mainly for numerical stability. ~10-20%% more VRAM.'
    )
    
    # API options
    parser.add_argument(
        '--api-url',
        type=str,
        default=None,  # Will be set to get_api_url("hunyuan") if not provided
        help=f'API server URL (default: from config.json or {HYVF_DEFAULT_API_URL})'
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
    
    # CLI Actions (for potential future integration)
    parser.add_argument(
        '--action',
        type=str,
        choices=['generate', 'check_ffmpeg', 'get_video_info'],
        default='generate',
        help='Action to perform (default: generate)'
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
        seed_input = input(f"🎲 Seed (Default: {DEFAULT_SEED}): ").strip()
        if not seed_input:
            seed = DEFAULT_SEED
            break
        try:
            seed = int(seed_input)
            break
        except ValueError:
            print("   ⚠️  Please enter a valid number.")
    
    while True:
        model_size_input = input(f"🎛️  Model Size [xl/xxl] (Default: {HYVF_DEFAULT_MODEL_SIZE}): ").strip().lower()
        if not model_size_input:
            model_size = HYVF_DEFAULT_MODEL_SIZE
            break
        if model_size_input in ['xl', 'xxl']:
            model_size = model_size_input
            break
        else:
            print("   ⚠️  Please enter 'xl' or 'xxl'.")
    
    print(f"\n✅ Parameters set:")
    print(f"   Prompt: '{prompt}'")
    print(f"   Negative Prompt: '{negative_prompt}'")
    print(f"   Seed: {seed}")
    print(f"   Model Size: {model_size.upper()}")
    
    return prompt, negative_prompt, seed, model_size


def main():
    """Main entry point for the HunyuanVideo-Foley API client"""
    # Parse command line arguments  
    args = parse_arguments()
    
    # Set API URL from config if not explicitly provided
    if args.api_url is None:
        args.api_url = get_api_url("hunyuan")
    
    # DEBUG: File-based logging for background processes (stdout/stderr not captured!)
    log_file = os.path.join(tempfile.gettempdir(), "pt_v2a_hyvf_debug.log")
    
    def log_debug(msg):
        """Write to file and stderr for maximum visibility"""
        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            f.write(f"[{timestamp}] {msg}\n")
            f.flush()
        # Only write to stderr (not stdout) to avoid duplication in plugin output
        print(msg, file=sys.stderr)
        sys.stderr.flush()
    
    log_debug(f"=== DEBUG HYVF: Script started, sys.argv={sys.argv} ===")
    log_debug(f"=== DEBUG HYVF: Log file: {log_file} ===")
    log_debug(f"=== DEBUG HYVF: args.action={args.action} ===")
    log_debug(f"=== DEBUG HYVF: args.video={args.video} ===")
    log_debug(f"=== DEBUG HYVF: args.prompt={args.prompt} ===")
    log_debug(f"=== DEBUG HYVF: args.model_size={args.model_size} ===")
    log_debug(f"=== DEBUG HYVF: args.seed={args.seed} ===")
    
    # Determine operation mode
    quiet = args.quiet
    verbose = args.verbose
    
    # =============================================================================
    # Handle CLI Actions
    # =============================================================================
    
    if args.action == 'check_ffmpeg':
        """Check FFmpeg availability"""
        return safe_action_wrapper(lambda: action_check_ffmpeg(log_debug_func=log_debug))
    
    elif args.action == 'get_video_info':
        """Get timeline selection AND video file in one PTSL call"""
        return safe_action_wrapper(lambda: action_get_video_info(log_debug_func=log_debug))
    
    # =============================================================================
    # Standard Generation Mode (action == 'generate')
    # =============================================================================
    
    def run_generation():
        """Main generation logic wrapped for consistent error handling"""
        is_cli_mode = args.video is not None
        
        if not quiet:
            print("🌐 HunyuanVideo-Foley Standalone API Client")
            print("=" * 50)
            if is_cli_mode:
                print("📋 CLI Mode (Pro Tools Ready)")
            else:
                print("🎮 Interactive Mode")
            print()
        
        # === CLI MODE ===
        if is_cli_mode:
            log_debug("=== DEBUG HYVF: CLI mode detected ===")
            # Validate video file
            video_path = str(validate_video_file(args.video))
            log_debug(f"=== DEBUG HYVF: Video validated: {Path(video_path).name} ===")
            
            # Use CLI parameters
            prompt = args.prompt
            negative_prompt = args.negative_prompt  
            seed = args.seed
            model_size = args.model_size
            
            if verbose and not quiet:
                print(f"📋 CLI Parameters:")
                print(f"   Video: {Path(video_path).name}")
                print(f"   Prompt: '{prompt}'")
                print(f"   Negative Prompt: '{negative_prompt}'")
                print(f"   Seed: {seed}")
                print(f"   Model Size: {model_size.upper()}")
        
        # === INTERACTIVE MODE ===
        else:
            # Get video path interactively
            video_path = get_video_path_interactive()
            
            # Get generation parameters interactively
            prompt, negative_prompt, seed, model_size = get_user_inputs_interactive()
        
        # === COMMON PROCESSING ===
        
        # Force WAV format if importing to Pro Tools (PTSL requires WAV)
        if args.import_to_protools and args.output_format != 'wav':
            if not quiet:
                print(f"⚠️  Forcing WAV format for Pro Tools import (was: {args.output_format})")
            args.output_format = 'wav'
        
        # Check API health
        log_debug(f"=== DEBUG HYVF: Checking API at {args.api_url} ===")
        if not quiet:
            print(f"\n🔗 Checking API connection to {args.api_url}...")
        
        if not check_api_health(args.api_url, quiet=quiet):
            log_debug(f"=== DEBUG HYVF: API health check FAILED ===")
            if not quiet:
                print(f"❌ API not available at {args.api_url}")
                print(f"   Make sure the HunyuanVideo-Foley API server is running on port 8001")
            return 1
        
        log_debug(f"=== DEBUG HYVF: API health check PASSED ===")
        if not quiet:
            print("✅ API is online!")
        
        # Get available models (optional info)
        if verbose and not quiet:
            models_info = get_available_models(args.api_url, quiet=quiet)
            if models_info:
                print(f"📦 Available models: {models_info.get('available_models', [])}")
                print(f"💾 Loaded models: {models_info.get('loaded_models', [])}")
        
        # === Video Preprocessing ===
        # Important: Downscaling is now ALWAYS done after trimming in trim_and_maybe_downscale_video()
        # or at the end if video was not trimmed. This prevents timeout issues with large videos.
        # 
        # Workflow:
        #   1. Trim video (if needed) - reduces file size significantly (e.g., 419MB → 5MB)
        #   2. Downscale trimmed result (if > 2MB) - fast operation on small file (5MB → 2MB)
        #   3. For untrimmed videos, downscale at the end before generate_audio()
        # 
        # Note: Downscaling is now ALWAYS done after trimming in trim_and_maybe_downscale_video()
        # or at the end (see below before generate_audio()). Early downscaling removed to prevent
        # FFmpeg timeout (30s) when processing large untrimmed videos.
        
        # Log video size for debugging
        file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
        log_debug(f"=== DEBUG HYVF: Original video size: {file_size_mb:.1f} MB (threshold: {VIDEO_DOWNSCALE_THRESHOLD_MB} MB) ===")
        
        if file_size_mb > VIDEO_DOWNSCALE_THRESHOLD_MB:
            log_debug(f"=== DEBUG HYVF: Video will be trimmed first, then downscaled if needed ===")
        else:
            log_debug(f"=== DEBUG HYVF: File size OK, no downscaling needed ===")
        
        # === Video Trimming (if needed) ===
        # Support same workflows as MMAudio client for consistency
        
        if args.clip_start_seconds is not None and args.clip_end_seconds is not None:
            # Clip bounds provided (auto-detected or manual)
            log_debug(f"=== DEBUG HYVF: Trimming video from {args.clip_start_seconds}s to {args.clip_end_seconds}s ===")
            if not quiet:
                print(f"\n✂️  Trimming video to clip bounds...")
                print(f"   Source range: {args.clip_start_seconds}s - {args.clip_end_seconds}s")
            
            trim_result = trim_and_maybe_downscale_video(
                video_path=video_path,
                start_seconds=args.clip_start_seconds,
                end_seconds=args.clip_end_seconds
            )
            
            if not trim_result['success']:
                log_debug(f"=== DEBUG HYVF: Trimming FAILED: {trim_result.get('error')} ===")
                if not quiet:
                    print(f"❌ Trimming failed: {trim_result.get('error', 'Unknown error')}")
                return 1
            
            video_path = trim_result['output_path']
            log_debug(f"=== DEBUG HYVF: Processed video saved: {Path(video_path).name} ===")
            log_debug(f"=== DEBUG HYVF: Original size: {trim_result['original_size_mb']:.1f} MB, Estimated: {trim_result['estimated_size_mb']:.1f} MB, Final: {trim_result['final_size_mb']:.1f} MB ===")
            log_debug(f"=== DEBUG HYVF: Downscaled: {trim_result['downscaled']}, Encoding time: {trim_result['encoding_time']:.1f}s ===")
            
            if not quiet:
                if trim_result['downscaled']:
                    print(f"✅ Video trimmed and downscaled to 480p in {trim_result['encoding_time']:.1f}s")
                else:
                    print(f"✅ Video trimmed in {trim_result['encoding_time']:.1f}s")
                print(f"   📦 Final size: {trim_result['final_size_mb']:.1f} MB")
        
        elif args.video_offset:
            # Manual offset provided (legacy workflow)
            if not quiet:
                print(f"\n✂️  Processing video with manual offset...")
                print(f"   Video clip starts at timeline: {args.video_offset}")
            
            # Get timeline selection
            if args.timeline_start == 0.0 and args.timeline_end == 0.0:
                if not quiet:
                    print("⚠️  No timeline selection provided, skipping trim")
            else:
                try:
                    video_clip_timeline_start = timecode_to_seconds(args.video_offset)
                except Exception as e:
                    if not quiet:
                        print(f"❌ Invalid video offset: {e}")
                    return 1
                
                timeline_in_seconds = args.timeline_start
                timeline_out_seconds = args.timeline_end
                
                # Calculate source video trim points
                relative_in_clip = timeline_in_seconds - video_clip_timeline_start
                start_in_source = max(0, relative_in_clip)
                end_in_source = relative_in_clip + (timeline_out_seconds - timeline_in_seconds)
                
                if not quiet:
                    print(f"   Trimming source video: {start_in_source}s - {end_in_source}s")
                
                trim_result = trim_and_maybe_downscale_video(
                    video_path=video_path,
                    start_seconds=start_in_source,
                    end_seconds=end_in_source
                )
                
                if not trim_result['success']:
                    if not quiet:
                        print(f"❌ Trimming failed: {trim_result.get('error', 'Unknown error')}")
                    return 1
                
                video_path = trim_result['output_path']
                log_debug(f"=== DEBUG HYVF: Original size: {trim_result['original_size_mb']:.1f} MB, Final: {trim_result['final_size_mb']:.1f} MB ===")
                log_debug(f"=== DEBUG HYVF: Downscaled: {trim_result['downscaled']}, Encoding time: {trim_result['encoding_time']:.1f}s ===")
                
                if not quiet:
                    if trim_result['downscaled']:
                        print(f"✅ Video trimmed and downscaled to 480p in {trim_result['encoding_time']:.1f}s")
                    else:
                        print(f"✅ Video trimmed in {trim_result['encoding_time']:.1f}s")
        
        # Final check: If video was NOT trimmed, we may still need to downscale large videos
        # before generate_audio() to prevent timeout issues
        if not (args.clip_start_seconds or args.video_offset):
            file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            log_debug(f"=== DEBUG HYVF: Untrimmed video final size check: {file_size_mb:.1f} MB (threshold: {VIDEO_DOWNSCALE_THRESHOLD_MB} MB) ===")
            
            if file_size_mb > VIDEO_DOWNSCALE_THRESHOLD_MB:
                log_debug(f"=== DEBUG HYVF: Untrimmed video exceeds threshold, downscaling to 480p... ===")
                downscale_result = downscale_video(video_path)
                if downscale_result['success']:
                    log_debug(f"=== DEBUG HYVF: Downscaled: {downscale_result['original_size_mb']:.1f} MB → {downscale_result['downscaled_size_mb']:.1f} MB ({downscale_result['compression_ratio']:.0f}x smaller, {downscale_result['encoding_time']:.1f}s) ===")
                    video_path = downscale_result['output_path']
                    if not quiet:
                        print(f"⚡ Video downscaled to 480p ({downscale_result['compression_ratio']:.0f}x smaller)")
                else:
                    log_debug(f"=== DEBUG HYVF: Downscaling failed: {downscale_result['error']} ===")
                    if not quiet:
                        print(f"⚠️ Downscaling failed, using original video")
        
        # Generate audio
        log_debug(f"=== DEBUG HYVF: Starting audio generation ===")
        log_debug(f"=== DEBUG HYVF: Video: {Path(video_path).name}, Model: {model_size}, Prompt: '{prompt}' ===")
        output_file = generate_audio(
            api_url=args.api_url,
            video_path=video_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            model_size=model_size,
            duration=args.duration,
            num_steps=args.steps,
            cfg_strength=args.cfg_strength,
            output_format=args.output_format,
            full_precision=args.full_precision,
            output_path=args.output,
            use_temp=args.temp,
            timeout=args.timeout,
            quiet=quiet,
            verbose=verbose
        )
        
        if output_file:
            log_debug(f"=== DEBUG HYVF: Audio generation SUCCESS: {output_file} ===")
            if not quiet:
                print(f"\n🎉 Success! Audio file generated:")
                print(f"   {output_file}")
                print(f"\n💡 Note: HunyuanVideo-Foley generates 48kHz audio (professional Foley standard)")
            
            # Import to Pro Tools if requested
            if args.import_to_protools:
                log_debug("=== DEBUG HYVF: Starting Pro Tools import ===")
                if not quiet:
                    print(f"\n📥 Importing audio to Pro Tools...")
                
                try:
                    timecode = args.video_offset if args.video_offset else None
                    log_debug(f"=== DEBUG HYVF: Import timecode: {timecode} ===")
                    success = import_audio_to_pro_tools(
                        audio_path=output_file,
                        timecode=timecode
                    )
                    
                    if success:
                        log_debug("=== DEBUG HYVF: Pro Tools import SUCCESS ===")
                        if not quiet:
                            print("✅ Audio imported to Pro Tools timeline!")
                    else:
                        log_debug("=== DEBUG HYVF: Pro Tools import FAILED ===")
                        if not quiet:
                            print("❌ Failed to import audio to Pro Tools")
                        return 1
                        
                except Exception as e:
                    log_debug(f"=== DEBUG HYVF: Pro Tools import EXCEPTION: {e} ===")
                    if not quiet:
                        print(f"❌ Pro Tools import error: {e}")
                    return 1
            
            log_debug("=== DEBUG HYVF: Script exiting with success ===")
            return {'success': True}
        else:
            log_debug("=== DEBUG HYVF: Audio generation FAILED ===")
            if not quiet:
                print("\n❌ Audio generation failed")
            return {'success': False, 'error': 'Audio generation failed'}
    
    # Wrap generation logic with error handler
    return safe_action_wrapper(run_generation)


if __name__ == "__main__":
    exit(main())
