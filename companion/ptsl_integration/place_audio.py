"""Put a generated or downloaded audio file onto an existing track.

The PTSL import can only create a new track or drop a file into the clip list.
Pro Tools 2025.6 adds SpotClipsByID, which places a clip-list clip on any track
at a timecode. So: import to the clip list, find the new clip, check that the
target range on the track is free, spot it there, give it a readable name.

`place_on_track` returns the track name it used, or None when placement was not
possible (track missing, range occupied, older Pro Tools); the caller then falls
back to the classic new-track import.
"""
from __future__ import annotations

import contextlib
import re
import wave
from pathlib import Path
from typing import Iterator, List, Optional

from ptsl import PTSL_pb2 as pt
from ptsl.ops import Import

from .clip_info import get_session_framerate
from .video_segments import _edit_mode_options, _flag  # same package, same Pro Tools quirks

AUDIO_EXTENSIONS = (".wav", ".aif", ".aiff", ".mp3", ".flac")


def audio_duration_seconds(path: str) -> float:
    with wave.open(path, "rb") as handle:
        return handle.getnframes() / float(handle.getframerate() or 1)


def add_frames(tc: str, frames: int, fps: float) -> str:
    """HH:MM:SS:FF plus `frames`, non-drop arithmetic (good enough for a range check)."""
    rate = int(round(fps))
    hh, mm, ss, ff = (int(p) for p in tc.replace(";", ":").split(":"))
    total = ((hh * 60 + mm) * 60 + ss) * rate + ff + frames
    ff = total % rate
    total //= rate
    ss = total % 60
    total //= 60
    return f"{total // 60:02d}:{total % 60:02d}:{ss:02d}:{ff:02d}"


def clip_list(engine) -> List[dict]:
    return engine.client.run_command(pt.CId_GetClipList, {}).get("clip_list", [])


@contextlib.contextmanager
def linked_selection(engine, log) -> Iterator[None]:
    """Temporarily link track/edit/timeline selection so a selection made by
    script lands on the track we select; restore everything afterwards."""
    tracks = engine.track_list()
    edit_selected = [t.name for t in tracks if _flag(t, "has_edit_selection")]
    selected = [t.name for t in tracks if _flag(t, "is_selected")]
    saved = engine.client.run_command(pt.CId_GetTimelineSelection, {"time_scale": "TimeCode"})
    options = _edit_mode_options(engine)

    def set_options(**changes):
        engine.client.run_command(pt.CId_SetEditModeOptions, {"edit_mode_options": {**options, **changes}})

    try:
        if options:
            set_options(link_timeline_and_edit_selection=True, link_track_and_edit_selection=True)
        yield
    finally:
        try:
            if saved.get("in_time"):
                engine.set_timeline_selection(in_time=saved["in_time"], out_time=saved["out_time"])
            if options:
                if edit_selected:
                    engine.select_tracks_by_name(edit_selected)
                set_options()
            if selected:
                engine.select_tracks_by_name(selected)
        except Exception as exc:  # noqa: BLE001
            log(f"selection not fully restored: {exc}")


def range_is_free(engine, track: str, in_tc: str, out_tc: str, fps: float = 0.0) -> bool:
    """True if no audio clip lies inside (in_tc, out_tc). The range is checked half-open:
    a clip that ends exactly at in_tc (the previous clip's tail) does not count."""
    if fps:
        inner_in, inner_out = add_frames(in_tc, 1, fps), add_frames(out_tc, -1, fps)
        if inner_out > inner_in:
            in_tc, out_tc = inner_in, inner_out
    engine.select_tracks_by_name([track])
    engine.set_timeline_selection(in_time=in_tc, out_time=out_tc)
    # The filter must be the enum value; a filter given by name is ignored and the
    # query then returns every file in the session.
    files = [f.path for f in engine.get_file_location(filters=[pt.SelectedClipsTimeline])]
    return not any(p.lower().endswith(AUDIO_EXTENSIONS) for p in files)


def rename_clip(engine, current: str, new_name: str, log) -> None:
    """Rename the clip `current`; for a split-stereo clip (listed as name.L / name.R) the
    parent name is tried first, then the channel clips one by one."""
    if not new_name or new_name == current:
        return
    taken = {c.get("clip_full_name") for c in clip_list(engine)}
    name, n = new_name, 2
    while name in taken or f"{name}.L" in taken:
        name, n = f"{new_name} {n}", n + 1

    base = re.sub(r"\.(L|R)$", "", current)
    candidates = [base] if base != current else [current]
    if base != current:
        candidates += [f"{base}.L", f"{base}.R"]
    for candidate in candidates:
        try:
            engine.client.run_command(pt.CId_RenameTargetClip,
                                      {"clip_name": candidate, "new_name": name if candidate == base else name + candidate[len(base):],
                                       "rename_file": False})
            if candidate == base:
                return
        except Exception as exc:  # noqa: BLE001
            log(f"clip '{candidate}' not renamed: {str(exc)[:120]}")


def rename_new_track(engine, tracks_before, new_name: str, log) -> Optional[str]:
    """After a new-track import: name the track that appeared after its clip."""
    new_tracks = [t.name for t in engine.track_list() if t.name not in tracks_before]
    if len(new_tracks) != 1 or not new_name:
        return new_tracks[0] if new_tracks else None
    taken = {t.name for t in engine.track_list()}
    name, n = new_name, 2
    while name in taken:
        name, n = f"{new_name} {n}", n + 1
    try:
        engine.client.run_command(pt.CId_RenameTargetTrack, {"current_name": new_tracks[0], "new_name": name})
        return name
    except Exception as exc:  # noqa: BLE001
        log(f"track not renamed: {str(exc)[:120]}")
        return new_tracks[0]


def place_on_track(engine, audio_path: str, track_name: str, timecode: str,
                   clip_name: Optional[str] = None, log=print,
                   trim_out: Optional[str] = None) -> Optional[str]:
    """Import `audio_path` into the clip list and spot it on `track_name` at `timecode`.

    With `trim_out` (the end of the user's selection) a sound longer than the selection is
    not placed here at all: the caller then imports it in full length onto a new track, so
    a two-minute archive recording neither spills over the next scene nor gets cut.
    """
    tracks = {t.name: t for t in engine.track_list()}
    if track_name not in tracks:
        log(f"track '{track_name}' not in session")
        return None
    if not hasattr(pt, "CId_SpotClipsByID"):
        log("this Pro Tools has no SpotClipsByID")
        return None

    fps = get_session_framerate(engine)
    duration = audio_duration_seconds(audio_path)
    out_tc = add_frames(timecode, max(1, int(round(duration * fps))), fps)
    if trim_out and trim_out > timecode and trim_out < out_tc:
        log(f"{duration:.1f} s is longer than the selection {timecode}-{trim_out}: goes to a new track in full length")
        return None

    with linked_selection(engine, log):
        if not range_is_free(engine, track_name, timecode, out_tc, fps):
            log(f"{timecode}-{out_tc} on '{track_name}' is occupied")
            return None

        before = {c["clip_id"] for c in clip_list(engine)}
        engine.client.run(Import(session_path="", import_type=pt.Audio,
                                 audio_data=pt.AudioData(file_list=[str(Path(audio_path))],
                                                         audio_destination=pt.MD_ClipList,
                                                         audio_location=pt.ML_None)))
        new = [c for c in clip_list(engine) if c["clip_id"] not in before and c.get("clip_type") == "CType_Audio"]
        if not new:
            log("import to clip list produced no new clip")
            return None
        # A stereo file arrives as two channel clips (name.L, name.R) with one root name;
        # they have to be spotted together, one alone does not fit a stereo track.
        clip = new[0]
        root = clip.get("clip_root_name")
        family = [c for c in new if root and c.get("clip_root_name") == root] or [clip]
        engine.client.run_command(pt.CId_SpotClipsByID, {
            "src_clips": [c["clip_id"] for c in family],
            "dst_track_name": track_name,
            "dst_location_data": {"location_type": "SLType_Start",
                                  "location": {"location": timecode, "time_type": "TLType_TimeCode"}},
        })
        rename_clip(engine, clip.get("clip_full_name", ""), clip_name or "", log)
    log(f"placed on '{track_name}' at {timecode} ({duration:.2f} s)")
    return track_name
