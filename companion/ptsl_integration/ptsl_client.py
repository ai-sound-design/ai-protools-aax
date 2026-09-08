"""
PTSL Integration - Using py-ptsl library
============================================

Advantages over custom implementation:
- Professional, tested, maintained library
- Better API (Python-native instead of JSON)
- Type safety with .pyi files
- Comprehensive error handling
- PTSL commands already implemented

Installation:
    pip install -e ../external/py-ptsl
    install other dependencies from companion/requirements.txt

Usage:
    >>> from ptsl_client import import_audio_to_pro_tools
    >>> success = import_audio_to_pro_tools("C:/audio/generated.flac")
"""

import sys
from pathlib import Path
from typing import Optional

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False
    print("Warning: soundfile not available - FLAC conversion disabled", file=sys.stderr)

try:
    from ptsl import open_engine
    import ptsl.PTSL_pb2 as pt
    from ptsl.ops import Import, RenameSelectedClip
    PTSL_AVAILABLE = True
except ImportError:
    PTSL_AVAILABLE = False
    print("Error: py-ptsl not installed!", file=sys.stderr)
    print("Install with: pip install -e external/py-ptsl", file=sys.stderr)


def import_audio_to_pro_tools(
    audio_path: str,
    location: str = "SessionStart",  # For API compatibility with old version (currently unused)
    timecode: str = None,  # Timecode position (e.g., "00:00:07:00")
    company_name: str = "Master Thesis",
    app_name: str = "PT V2A Plugin",
    host: str = "localhost",
    port: int = 31416
) -> bool:
    """
    Import audio file to Pro Tools using py-ptsl library.
    
    Features:
        - FLAC → WAV conversion (PTSL requires WAV)
        - Timecode-based positioning (imports at specific timeline position)
        - Connection management
        - Error handling
    
    Args:
        audio_path (str): Path to audio file (WAV or FLAC)
        location (str): Timeline position - kept for API compatibility with v1
                       Currently unused (use timecode parameter instead)
        timecode (str): Timecode position in "HH:MM:SS:FF" format (e.g., "00:00:07:00")
                       If None, imports at session start (00:00:00:00)
        company_name (str): for PTSL logs
        app_name (str): for PTSL logs
        host (str): PTSL server hostname (default: localhost)
        port (int): PTSL server port (default: 31416)
    
    Returns:
        bool: True if import succeeded, False otherwise
        
    Example:
        >>> # Simple usage (imports at session start)
        >>> success = import_audio_to_pro_tools("C:/audio/generated.flac")

        >>> # Import at specific timeline position
        >>> success = import_audio_to_pro_tools(
        >>>     "C:/audio/file.wav",
        >>>     timecode="00:00:07:00"  # Import at 7 seconds
        >>> )
        
        >>> # With custom names
        >>> success = import_audio_to_pro_tools(
        >>>     "C:/audio/file.wav",
        >>>     timecode="00:01:30:15",
        >>>     company_name="My Studio",
        >>>     app_name="Audio Tool"
        >>> )
        
    Note:
        py-ptsl Engine expects 'address' parameter in format "host:port"
        rather than separate host and port arguments.
    """
    if not PTSL_AVAILABLE:
        print("ERROR: py-ptsl library not installed", file=sys.stderr)
        return False
    
    # Convert FLAC to WAV if needed (PTSL limitation)
    # Note: If using output_format="wav" in API call, this conversion is skipped
    audio_path = Path(audio_path)
    actual_path = audio_path
    
    if audio_path.suffix.lower() == '.flac':
        if not SOUNDFILE_AVAILABLE:
            print("ERROR: soundfile required for FLAC conversion", file=sys.stderr)
            print("Install with: pip install soundfile", file=sys.stderr)
            return False
        
        print(f"⚠️  WARNING: Converting FLAC to WAV client-side (slow!)")
        print(f"   Recommendation: Use output_format='wav' in API call for faster import")
        import time
        convert_start = time.time()
        
        try:
            # Read FLAC
            read_start = time.time()
            data, samplerate = sf.read(str(audio_path))
            read_time = time.time() - read_start
            print(f"  Read FLAC: {read_time:.2f}s")
            
            # Write WAV (24-bit PCM)
            write_start = time.time()
            wav_path = audio_path.with_suffix('.wav')
            sf.write(str(wav_path), data, samplerate, subtype='PCM_24')
            write_time = time.time() - write_start
            print(f"  Write WAV: {write_time:.2f}s")
            
            total_convert = time.time() - convert_start
            print(f"  Total conversion: {total_convert:.2f}s")
            
            actual_path = wav_path
            print(f"Converted to: {wav_path}")
            
        except Exception as e:
            print(f"ERROR: FLAC conversion failed: {e}", file=sys.stderr)
            return False
    elif audio_path.suffix.lower() == '.wav':
        print(f"[OK] Audio already in WAV format (no conversion needed)")
    
    # Convert to absolute path (PTSL requires absolute paths)
    actual_path = actual_path.absolute()
    
    # Check file exists
    if not actual_path.exists():
        print(f"ERROR: Audio file not found: {actual_path}", file=sys.stderr)
        return False
    
    # Validate file extension - Pro Tools only accepts pure audio formats via PTSL
    SUPPORTED_EXTENSIONS = {'.wav', '.aiff', '.aif', '.mp3'}
    file_ext = actual_path.suffix.lower()
    
    if file_ext not in SUPPORTED_EXTENSIONS:
        print(f"ERROR: Unsupported file format: {file_ext}", file=sys.stderr)
        print(f"       Pro Tools PTSL Import only supports: {', '.join(sorted(SUPPORTED_EXTENSIONS))}", file=sys.stderr)
        if file_ext in {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm', '.flv', '.wmv', '.f4v', '.mxf', '.m2ts', '.mts', '.ts', '.mpg', '.mpeg', '.vob', '.ogv', '.3gp', '.3g2'}:
            print(f"       For video files ({file_ext}), extract audio first using:", file=sys.stderr)
            print(f"       ffmpeg -i \"{actual_path.name}\" -vn -acodec pcm_s16le output.wav", file=sys.stderr)
        return False
    
    # Import using py-ptsl
    import time
    ptsl_start = time.time()
    
    try:
        # py-ptsl expects address in "host:port" format
        address = f"{host}:{port}"
        print(f"Connecting to Pro Tools at {address}...")
        
        connect_start = time.time()
        with open_engine(
            company_name=company_name,
            application_name=app_name,
            address=address
        ) as engine:
            connect_time = time.time() - connect_start
            print(f"  Connected in {connect_time:.2f}s")
            
            print(f"Importing audio to Pro Tools...")
            print(f"  File: {actual_path}")
            
            # Determine import timecode position
            import_timecode = timecode if timecode else "00:00:00:00"
            print(f"  Position: {import_timecode}")
            
            # Import audio to new track at specified timecode position
            # Note: Using forward slashes even on Windows (PTSL requirement)
            file_path = str(actual_path).replace('\\', '/')
            
            # Build import manually because engine.import_audio() doesn't set session_path
            # For audio-only import, session_path must be empty string (not None)
            location_data = pt.SpotLocationData(
                location_type=pt.Start,
                location_options=pt.TimeCode,
                location_value=import_timecode
            )
            audio_data = pt.AudioData(
                file_list=[file_path],
                audio_destination=pt.MD_NewTrack,
                audio_location=pt.ML_Spot,
                location_data=location_data
            )
            
            # CRITICAL: session_path="" for audio import (not None!)
            import_op = Import(
                session_path="",          # Empty string required for audio-only import
                import_type=pt.Audio,     # Audio file import (not Session)
                audio_data=audio_data
            )
            
            import_start = time.time()
            engine.client.run(import_op)
            import_time = time.time() - import_start
            print(f"  PTSL import operation: {import_time:.2f}s")
            
            # Note: Clip renaming disabled to avoid renaming other selected clips
            # Pro Tools will use the full file path as clip name
            # The server-generated filename is descriptive enough when viewed
            # TODO: Find a way to rename only the newly imported clip without affecting others
            
            total_ptsl = time.time() - ptsl_start
            print(f"  Total PTSL time: {total_ptsl:.2f}s")
            print("[SUCCESS] Audio successfully imported to Pro Tools!")
            return True
            
    except Exception as e:
        print(f"ERROR: Import failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Import audio to Pro Tools using py-ptsl")
    parser.add_argument("--audio", required=True, help="Audio file path")
    parser.add_argument("--host", default="localhost", help="PTSL host")
    parser.add_argument("--port", type=int, default=31416, help="PTSL port")
    
    args = parser.parse_args()
    
    success = import_audio_to_pro_tools(args.audio, host=args.host, port=args.port)
    sys.exit(0 if success else 1)
