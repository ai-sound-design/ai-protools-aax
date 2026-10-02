"""The audio under the timeline selection, as a file: the query for a search by sound.

The user marks a range on one or more audio tracks and asks for library sounds that
sound like what is there. Pro Tools 2024.10 and later bounce one track over a range offline
(CId_BounceTrack): each marked track is bounced over the selection and the results
mixed, fades and clip gain included. Older versions have no such command, and the
module takes the long way that video_segments.py also takes:
the selected-clips filter says which *files* lie under the edit selection on the
tracks the user dragged across; bisecting the timeline selection finds where each of
those clips begins (frame-exact, a few dozen round trips per clip); the clip list
knows the clip's offset into its file. From that, ffmpeg cuts the selected stretch of
every clip straight out of its source file and mixes them when there are several.

Nothing is edited: the timeline selection and the link options are restored. The
edit selection stays on the user's tracks throughout, which is the point: the sound
query is what they marked, not the whole session.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from ptsl import PTSL_pb2 as pt

from .clip_info import get_clip_list, get_session_framerate
from .video_segments import VIDEO_EXTENSIONS, _Timecode, _edit_mode_options, _flag, _frames

Logger = Optional[Callable[[str], None]]
AUDIO_EXTENSIONS = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".caf", ".bwf", ".wave")


def _is_audio_file(path: str) -> bool:
    low = path.lower()
    return low.endswith(AUDIO_EXTENSIONS) or not low.endswith(VIDEO_EXTENSIONS)


def resolve_audio_under_selection(engine, log: Logger = None) -> Dict:
    """The audio clips under the edit selection, each with the stretch of its file that
    lies inside the selection. Returns ``success``, ``in_time``/``out_time``,
    ``duration_seconds``, ``tracks`` (the edit-selected tracks, when PTSL tells),
    ``clips`` (``path``, ``clip_name``, ``file_offset_seconds``, ``length_seconds``)
    and ``warnings``; ``success`` False with ``error`` when nothing usable is there."""

    def note(msg: str) -> None:
        if log:
            log(msg)

    warnings: List[str] = []
    fps = get_session_framerate(engine)
    try:
        drop = "Drop" in pt.SessionTimeCodeRate.Name(engine.session_timecode_rate())
    except ValueError:
        drop = False
    tc = _Timecode(fps, drop)
    sample_rate = engine.session_sample_rate() or 48000

    saved_in, saved_out = engine.get_timeline_selection(pt.TimeCode)
    sel_in, sel_out = tc.to_frames(saved_in), tc.to_frames(saved_out)
    if sel_out <= sel_in:
        return {"success": False, "error": "Nothing is selected. Mark a time range on the track with the sound first."}
    origin = tc.to_frames(engine.session_start_time())
    all_tracks = engine.track_list()
    edit_selected = [t.name for t in all_tracks if _flag(t, "has_edit_selection")]
    selected_tracks = [t.name for t in all_tracks if _flag(t, "is_selected")]
    options = _edit_mode_options(engine)

    def set_options(**changes) -> None:
        engine.client.run_command(pt.CId_SetEditModeOptions, {"edit_mode_options": {**options, **changes}})

    def files_between(a: int, b: int) -> Set[str]:
        """Audio files under frames [a, b) on the edit-selected tracks."""
        engine.set_timeline_selection(in_time=tc.to_tc(a), out_time=tc.to_tc(max(b, a + 1)))
        return {f.path for f in engine.get_file_location(filters=[pt.SelectedClipsTimeline]) if _is_audio_file(f.path)}

    def first_where(lo: int, hi: int, pred: Callable[[int], bool]) -> int:
        while lo < hi:
            mid = (lo + hi) // 2
            if pred(mid):
                hi = mid
            else:
                lo = mid + 1
        return lo

    clips: List[Dict] = []
    try:
        if options:
            # The timeline selection must move the edit selection (on its own tracks) for
            # the selected-clips filter to follow it; the track link stays as it is
            set_options(link_timeline_and_edit_selection=True)
        else:
            warnings.append("Edit mode options not readable; the selection may not follow the bisection.")

        files = files_between(sel_in, sel_out)
        if not files:
            where = f" on {', '.join(edit_selected)}" if edit_selected else ""
            return {"success": False, "warnings": warnings,
                    "error": f"No audio clip under the selection{where}. Mark a range on a track that holds the sound."}

        file_ids: Dict[str, str] = {}
        engine.set_timeline_selection(in_time=tc.to_tc(sel_in), out_time=tc.to_tc(sel_out))
        for loc in engine.get_file_location(filters=[pt.SelectedClipsTimeline]):
            file_ids[loc.path] = loc.file_id
        by_file_id: Dict[str, List[Dict]] = {}
        for clip in get_clip_list(engine):
            if "Video" not in str(clip.get("clip_type", "")):
                by_file_id.setdefault(clip.get("file_id"), []).append(clip)

        for path in sorted(files):
            # Where the clip begins: the first frame from which it is under the selection
            clip_start = first_where(origin + 1, sel_out, lambda t, p=path: p in files_between(origin, t)) - 1
            part_start = max(sel_in, clip_start)
            # ...and where it ends inside the selection
            clip_end = first_where(part_start + 1, sel_out, lambda t, p=path: p not in files_between(t, t + 1))
            part_end = min(sel_out, clip_end)
            if part_end - part_start < 1:
                continue
            candidates = by_file_id.get(file_ids.get(path), [])
            source_in_seconds = 0.0
            clip_name = Path(path).name
            if candidates:
                clip = candidates[0]
                clip_name = clip.get("clip_full_name", clip_name)
                point = clip.get("start_point") or {}
                unit = str(point.get("time_type", point.get("unit", ""))).lower()
                value = _frames(clip, "start_point")
                if "sample" in unit:
                    source_in_seconds = value / float(sample_rate)
                elif value and clip_start >= origin:
                    # Audio clip points come as the session's main counter; frames are the
                    # safe reading when it is timecode, samples when it says so above
                    source_in_seconds = value / fps if value < 24 * 3600 * fps else value / float(sample_rate)
                if len(candidates) > 1:
                    warnings.append(f"'{clip_name}': several clips share this file; offset taken from the first entry.")
            else:
                warnings.append(f"No clip-list entry for {Path(path).name}; assuming the clip starts at the file start.")
            offset = source_in_seconds + tc.seconds(part_start - clip_start)
            clips.append({"path": path, "clip_name": clip_name,
                          "file_offset_seconds": round(offset, 3),
                          "length_seconds": round(tc.seconds(part_end - part_start), 3),
                          "in_time": tc.to_tc(part_start), "out_time": tc.to_tc(part_end)})
            note(f"audio under selection: {clip_name} {tc.to_tc(part_start)}-{tc.to_tc(part_end)} "
                 f"file offset {offset:.3f}s")
    finally:
        try:
            engine.set_timeline_selection(in_time=saved_in, out_time=saved_out)
            if options:
                set_options()
                if selected_tracks:
                    engine.select_tracks_by_name(selected_tracks)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not fully restore the selection: {exc}")

    if not clips:
        return {"success": False, "warnings": warnings,
                "error": "No audio clip reaches into the selection."}
    return {"success": True, "fps": fps, "sample_rate": sample_rate, "in_time": tc.to_tc(sel_in),
            "out_time": tc.to_tc(sel_out), "duration_seconds": round(tc.seconds(sel_out - sel_in), 3),
            "tracks": edit_selected, "clips": clips, "warnings": warnings, "error": None}


class _NoBounce(Exception):
    """This Pro Tools cannot bounce a track through PTSL."""


def _bounce_selection(engine, output: Path, log: Logger = None) -> Dict:
    """The selection's audio by an offline bounce of each marked audio track over the
    selection (Pro Tools renders it: fades, clip gain, the track's own mix), the tracks
    mixed to one mono 48 kHz WAV at `output`. Raises _NoBounce when this Pro Tools has
    no track bounce, so the caller takes the file-cutting way instead."""
    if not hasattr(pt, "CId_BounceTrack"):
        raise _NoBounce()
    import shutil
    import tempfile
    import numpy as np
    import soundfile as sf

    def note(msg: str) -> None:
        if log:
            log(msg)

    fps = get_session_framerate(engine)
    try:
        drop = "Drop" in pt.SessionTimeCodeRate.Name(engine.session_timecode_rate())
    except ValueError:
        drop = False
    tc = _Timecode(fps, drop)
    rate = engine.session_sample_rate() or 48000
    sel_in_tc, sel_out_tc = engine.get_timeline_selection(pt.TimeCode)
    sel_in, sel_out = tc.to_frames(sel_in_tc), tc.to_frames(sel_out_tc)
    if sel_out <= sel_in:
        return {"success": False, "warnings": [],
                "error": "Nothing is selected. Mark a time range on the track with the sound first."}
    origin = tc.to_frames(engine.session_start_time())
    in_samples = int(round(tc.seconds(sel_in - origin) * rate))
    out_samples = int(round(tc.seconds(sel_out - origin) * rate))

    def is_audio_track(t) -> bool:
        try:
            return pt.TrackFormat.Name(int(t.format)) not in ("TF_None", "TF_Unknown")
        except ValueError:
            return False

    tracks = [t for t in engine.track_list() if is_audio_track(t)]
    marked = [t for t in tracks if _flag(t, "has_edit_selection")] or [t for t in tracks if _flag(t, "is_selected")]
    if not marked:
        return {"success": False, "warnings": [],
                "error": "No audio track is marked. Mark the range on the track that holds the sound."}

    work = Path(tempfile.mkdtemp(prefix="ai_sound_design_query_"))
    mix, used, warnings = None, [], []
    try:
        for t in marked:
            body = {
                "file_name_prefix": "query",
                "file_type": "EMFType_WAV",
                "audio_info": {"compression_type": "CType_PCM", "export_format": "EFormat_Interleaved",
                               "bit_depth": "BDepth_24", "sample_rate": "SRate_48000",
                               "delivery_format": "EMDFormat_SingleFile"},
                "location_info": {"import_after_bounce": "TBool_False",
                                  "file_destination": "EMFDestination_Directory", "directory": str(work)},
                "offline_bounce": "TBool_True",
                "src_track_id": t.id,
                "in_location": {"location": str(in_samples), "time_type": "TLType_Samples"},
                "out_location": {"location": str(out_samples), "time_type": "TLType_Samples"},
            }
            try:
                answer = engine.client.run_command(pt.CId_BounceTrack, body) or {}
            except Exception as exc:  # noqa: BLE001  (an empty range says "no content on the timeline")
                text = str(exc)
                if "no content" in text.lower():
                    note(f"'{t.name}': nothing under the selection")
                    continue
                if "not supported" in text.lower() or "unknown command" in text.lower():
                    raise _NoBounce() from exc
                warnings.append(f"'{t.name}' could not be bounced: {text[:120]}")
                continue
            paths = [p for p in answer.get("file_paths", []) if Path(p).exists()]
            if not paths:
                continue
            data, file_rate = sf.read(paths[0], always_2d=True)
            mono = data.mean(axis=1)
            if len(mono) == 0 or float(np.max(np.abs(mono))) < 1e-4:
                note(f"'{t.name}': silent under the selection")
                continue
            if mix is None:
                mix = mono
            else:
                size = max(len(mix), len(mono))
                mix = np.pad(mix, (0, size - len(mix))) + np.pad(mono, (0, size - len(mono)))
            used.append(t.name)
            note(f"'{t.name}': bounced {len(mono) / float(file_rate):.2f} s")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if mix is None:
        return {"success": False, "warnings": warnings,
                "error": "No sound under the selection on " + ", ".join(t.name for t in marked)
                         + ". Mark a range on a track that holds the sound."}
    peak = float(np.max(np.abs(mix)))
    if peak > 0.98:
        mix = mix * (0.98 / peak)
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), mix, 48000, subtype="PCM_16")
    return {"success": True, "audio_path": str(output), "in_time": sel_in_tc, "out_time": sel_out_tc,
            "duration_seconds": round(tc.seconds(sel_out - sel_in), 3), "fps": fps, "tracks": used,
            "clips": [{"clip_name": name} for name in used], "warnings": warnings}


def export_selection_audio(engine, output: Path, log: Logger = None) -> Dict:
    """The selection's audio as one 48 kHz WAV at `output`. First by an offline bounce
    of the marked tracks (what they play, fades included); where this Pro Tools cannot
    bounce a track, every clip's stretch is cut from its source file and mixed."""
    try:
        return _bounce_selection(engine, output, log)
    except _NoBounce:
        if log:
            log("this Pro Tools cannot bounce a track; cutting the clips from their files")
    found = resolve_audio_under_selection(engine, log)
    if not found.get("success"):
        return found
    clips = found["clips"]
    length = max(c["length_seconds"] for c in clips)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    for c in clips:
        command += ["-ss", f"{c['file_offset_seconds']:.3f}", "-t", f"{c['length_seconds']:.3f}", "-i", c["path"]]
    if len(clips) == 1:
        filters = "aresample=48000,aformat=channel_layouts=mono"
    else:
        # Clips that start later inside the selection are delayed to where they sit
        sel_in = clips[0]["in_time"]
        fps = float(found["fps"])
        tcs = _Timecode(fps, False)
        base = min(tcs.to_frames(c["in_time"]) for c in clips)
        parts = []
        for n, c in enumerate(clips):
            delay_ms = int(round(tcs.seconds(tcs.to_frames(c["in_time"]) - base) * 1000))
            parts.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=mono,adelay={delay_ms}|{delay_ms}[a{n}]")
        filters = ";".join(parts) + ";" + "".join(f"[a{n}]" for n in range(len(clips))) \
            + f"amix=inputs={len(clips)}:normalize=0,alimiter=limit=0.98"
    command += ["-filter_complex", filters] if len(clips) > 1 else ["-af", filters]
    command += ["-t", f"{length:.3f}", "-c:a", "pcm_s16le", str(output)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        err = getattr(exc, "stderr", b"")
        return {"success": False, "warnings": found["warnings"],
                "error": "ffmpeg could not cut the selection's audio: "
                         + (err.decode("utf-8", "replace")[:300] if isinstance(err, bytes) else str(exc))}
    found["audio_path"] = str(output)
    return found


if __name__ == "__main__":     # manual check: python -m ptsl_integration.audio_segments [out.wav]
    import json
    from ptsl import open_engine

    with open_engine(company_name="AI Sound Design", application_name="Audio under selection") as eng:
        if len(sys.argv) > 1:
            print(json.dumps(export_selection_audio(eng, Path(sys.argv[1]), log=print), indent=1))
        else:
            print(json.dumps(resolve_audio_under_selection(eng, log=print), indent=1))
