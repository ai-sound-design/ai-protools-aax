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


def _convert_to_wav(source: Path) -> Optional[Path]:
    """Decode `source` to a 24-bit stereo WAV next to it (ffmpeg from imageio-ffmpeg)."""
    import subprocess
    import time

    target = source.with_suffix('.wav')
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        print(f"[OK] Using existing WAV: {target.name}")
        return target
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: ffmpeg not available for WAV conversion: {exc}", file=sys.stderr)
        return None
    started = time.time()
    result = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "2",
                             "-c:a", "pcm_s24le", str(target)], capture_output=True, text=True)
    if result.returncode != 0 or not target.exists():
        print(f"ERROR: WAV conversion failed: {result.stderr.strip()[:300]}", file=sys.stderr)
        return None
    print(f"[OK] Converted {source.name} to WAV in {time.time() - started:.1f}s")
    return target


def _duration_seconds(path) -> float:
    """Length of an audio file in seconds; 0 when it cannot be read."""
    try:
        from .place_audio import audio_duration_seconds
        return float(audio_duration_seconds(str(path)))
    except Exception:  # noqa: BLE001  (not a WAV, or an odd header)
        pass
    if SOUNDFILE_AVAILABLE:
        try:
            info = sf.info(str(path))
            return float(info.frames) / float(info.samplerate or 1)
        except Exception:  # noqa: BLE001
            pass
    return 0.0


def import_audio_to_pro_tools(
    audio_path: str,
    location: str = "SessionStart",  # For API compatibility with old version (currently unused)
    timecode: str = None,  # Timecode position (e.g., "00:00:07:00")
    company_name: str = "AI Sound Design",
    app_name: str = "Audio import",
    host: str = "localhost",
    port: int = 31416,
    track_name: str = None,   # existing track to place the clip on (the plugin's own track)
    clip_name: str = None,    # readable clip name instead of the file stem
    timecode_out: str = None, # end of the selection: a longer clip is trimmed to it
    cut: bool = False,        # trim the clip to the selection (timecode..timecode_out); the rest stays in the file
    handle_before: float = 0.0,   # with cut: this much of the file goes before the selection (imported that much earlier), as far as the file allows
    fade_preset: str = None,  # with cut: Pro Tools batch-fades preset for the clip's edges
    fade_seconds: float = 1.0,    # the preset's fade length
    fade_inside: bool = False,    # the fade runs inside the selection (clip ends at it) instead of over the handle
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
    elif audio_path.suffix.lower() in ('.mp3', '.ogg', '.m4a', '.aac'):
        # Pro Tools converts compressed files into dual-mono .L/.R clips, which cannot be
        # spotted onto a stereo track and take long to convert. A stereo WAV imports as one
        # clip in a fraction of the time.
        converted = _convert_to_wav(audio_path)
        if converted is None:
            return False
        actual_path = converted
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
            # Cut to the selection: the file goes in `handle_before` seconds early (that much
            # of the recording lies before the selection as a handle), the clip is then
            # trimmed to the selection and, with a preset, faded at its edges
            finishing = bool(cut and timecode and timecode_out)
            fps = sel_in = sel_out = clip_end = None
            lead = 0.0
            span_out_tc = None
            if finishing:
                from .clip_info import get_session_framerate
                from .clip_finish import seconds_to_tc, tc_to_seconds
                fps = get_session_framerate(engine)
                sel_in, sel_out = tc_to_seconds(timecode, fps), tc_to_seconds(timecode_out, fps)
                duration = _duration_seconds(actual_path)
                if sel_out <= sel_in:
                    finishing = False
                else:
                    # As much handle as asked, as the timeline allows (not before the session
                    # start) and as the file allows (the selection stays covered to its end)
                    lead = max(0.0, min(float(handle_before or 0.0), sel_in))
                    if duration > 0:
                        lead = max(0.0, min(lead, duration - (sel_out - sel_in)))
                    import_timecode = seconds_to_tc(sel_in - lead, fps)
                    clip_end = (sel_in - lead + duration) if duration > 0 else None
                    span_out_tc = seconds_to_tc(min(sel_out, clip_end) if clip_end else sel_out, fps)
                    print(f"  Cut to the selection {timecode}-{timecode_out}, handle before {lead:.2f} s"
                          + (f", file {duration:.1f} s" if duration > 0 else ""))
            print(f"  Position: {import_timecode}")

            def finish(track: str) -> None:
                if not finishing or not track:
                    return
                from contextlib import nullcontext
                from .clip_finish import finish_clip
                end = min(sel_out, clip_end) if clip_end else sel_out
                after = max(0.0, clip_end - sel_out) if clip_end else 0.0
                trimmed, faded = finish_clip(lambda: nullcontext(engine), track, sel_in, end, lead, after, fps,
                                             (fade_preset or None), max(0.0, float(fade_seconds or 0.0)),
                                             bool(fade_inside), log=lambda m: print(f"  {m}"))
                print(f"IMPORT_FINISH trimmed={trimmed} faded={faded} handle_before={lead:.2f} handle_after={after:.2f}")

            # First choice: onto the track the plugin sits on. Falls back to a new
            # track when the range there is occupied or the command is unavailable.
            if track_name:
                from .place_audio import place_on_track
                try:
                    placed = place_on_track(engine, str(actual_path), track_name, import_timecode,
                                            clip_name=clip_name, log=lambda m: print(f"  {m}"),
                                            trim_out=None if finishing else timecode_out, span_out=span_out_tc)
                except Exception as exc:  # noqa: BLE001
                    placed = None
                    print(f"  placing on '{track_name}' failed: {exc}", file=sys.stderr)
                if placed:
                    finish(placed)
                    print(f"[SUCCESS] Audio placed on track '{placed}'")
                    print(f"IMPORT_TRACK={placed}")
                    return True
                print(f"  falling back to a new track")
            
            # Import audio to new track at specified timecode position.
            # The path goes through as the OS spells it: with forward slashes on
            # Windows, Pro Tools names the clip and track after the mangled path
            # ("/Users/<you>/.../generated_42"); with backslashes after the file stem.
            file_path = str(actual_path)
            
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
            
            tracks_before = {t.name for t in engine.track_list()}
            clips_before = {c["clip_id"] for c in engine.client.run_command(pt.CId_GetClipList, {}).get("clip_list", [])}
            import_start = time.time()
            engine.client.run(import_op)
            import_time = time.time() - import_start
            print(f"  PTSL import operation: {import_time:.2f}s")
            new_track = None
            if clip_name:
                from .place_audio import rename_clip, rename_new_track, is_audio_clip
                # The clip list lags behind the import by a moment; without the wait the
                # rename aimed at a name that was not there yet and the file name stayed
                import time as _time
                new_clips = []
                for _ in range(15):
                    new_clips = [c for c in engine.client.run_command(pt.CId_GetClipList, {}).get("clip_list", [])
                                 if c["clip_id"] not in clips_before and is_audio_clip(c)]
                    if new_clips:
                        break
                    _time.sleep(0.2)
                rename_clip(engine, new_clips[0]["clip_full_name"] if new_clips else actual_path.stem,
                            clip_name, lambda m: print(f"  {m}"))
                new_track = rename_new_track(engine, tracks_before, clip_name, lambda m: print(f"  {m}"))
            if finishing and not new_track:
                print("  the new track's name is unknown, the clip stays untrimmed")
            finish(new_track)
            print(f"IMPORT_TRACK={new_track or 'new'}")
            
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
