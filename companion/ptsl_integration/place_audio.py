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
import time
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


def is_audio_clip(clip: dict) -> bool:
    """Older Pro Tools say CType_Audio, newer ones ClipType_Audio."""
    return str(clip.get("clip_type", "")) in ("CType_Audio", "ClipType_Audio")


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
    # Current Pro Tools list no audio files for a selection (only video), so the clips'
    # own extent decides: selecting all clips on the track spans from the first clip's
    # start to the last one's end. A range that touches that span counts as occupied;
    # a gap between two clips is not looked into, the sound then goes to a new track.
    # On a track without clips the selection is left as it was (the user's range), so
    # an empty track is told by its own flag first.
    try:
        found = next((t for t in engine.track_list() if t.name == track), None)
        attrs = getattr(found, "track_attributes", None)
        if found is not None and attrs is not None and not getattr(attrs, "contains_clips", False):
            return True
    except Exception:  # noqa: BLE001  (no track list: the extent check below decides)
        pass
    try:
        engine.select_all_clips_on_track(track)
        first, last = engine.get_timeline_selection()
    except Exception:  # noqa: BLE001  (an empty track has no clips to select)
        return True
    if not first or not last or first >= last:
        return True
    return out_tc <= first or in_tc >= last


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
    """After a new-track import: name the track that appeared after its clip (Pro Tools
    lists it a moment after the import answers, so this waits up to three seconds)."""
    import time as _time
    new_tracks: list = []
    for _ in range(15):
        new_tracks = [t.name for t in engine.track_list() if t.name not in tracks_before]
        if new_tracks:
            break
        _time.sleep(0.2)
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


def track_channels(track) -> int:
    """1 for a mono track, 2 for stereo, 0 when the format says something else."""
    try:
        name = pt.TrackFormat.Name(int(getattr(track, "format", 0)))
    except Exception:  # noqa: BLE001
        return 0
    if "Mono" in name:
        return 1
    if "Stereo" in name:
        return 2
    return 0


def file_channels(audio_path: str) -> int:
    """Channel count of an audio file; 0 when it cannot be read."""
    try:
        import soundfile as sf
        return int(sf.info(audio_path).channels)
    except Exception:  # noqa: BLE001
        return 0


def fit_channels(audio_path: str, channels: int, log=print) -> str:
    """The file with `channels` channels: itself when it already has them (or `channels`
    is 0), otherwise a mono mix or a doubled mono written next to it."""
    if channels not in (1, 2):
        return audio_path
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return audio_path
    try:
        info = sf.info(audio_path)
    except Exception as exc:  # noqa: BLE001
        log(f"could not read {Path(audio_path).name}: {str(exc)[:120]}")
        return audio_path
    if info.channels == channels:
        return audio_path
    target = Path(audio_path).with_name(Path(audio_path).stem + (".mono.wav" if channels == 1 else ".stereo.wav"))
    if target.exists() and target.stat().st_mtime >= Path(audio_path).stat().st_mtime:
        return str(target)
    data, rate = sf.read(audio_path, always_2d=True)
    if channels == 1:
        data = data.mean(axis=1, keepdims=True)
    else:
        data = np.repeat(data[:, :1], 2, axis=1) if data.shape[1] == 1 else data[:, :2]
    sf.write(str(target), data, rate, subtype="PCM_24")
    log(f"{Path(audio_path).name}: {info.channels} channel(s) -> {channels} for the track ({target.name})")
    return str(target)


def place_on_track(engine, audio_path: str, track_name: str, timecode: str,
                   clip_name: Optional[str] = None, log=print,
                   trim_out: Optional[str] = None, span_out: Optional[str] = None) -> Optional[str]:
    """Import `audio_path` into the clip list and spot it on `track_name` at `timecode`.

    With `trim_out` (the end of the user's selection) a sound longer than the selection is
    not placed here at all: the caller then imports it in full length onto a new track, so
    a two-minute archive recording neither spills over the next scene nor gets cut.
    With `span_out` the caller will trim the clip to that end right after, so only the
    range up to it has to be free on the track.
    """
    tracks = {t.name: t for t in engine.track_list()}
    if track_name not in tracks:
        log(f"track '{track_name}' not in session")
        return None
    if not hasattr(pt, "CId_SpotClipsByID"):
        log("this Pro Tools has no SpotClipsByID")
        return None

    # A clip only spots onto a track of its own width. A recording wider than the track
    # (stereo onto the plugin's mono track) keeps its width and goes to a new track of its
    # own instead (the caller's fallback); a mono file on a stereo track is doubled.
    wanted, have = track_channels(tracks[track_name]), file_channels(audio_path)
    if wanted and have > wanted:
        log(f"{Path(audio_path).name} has {have} channels, '{track_name}' is {'mono' if wanted == 1 else 'stereo'}: "
            f"goes to a new track in its own width")
        return None
    fitted = fit_channels(audio_path, wanted, log)
    if fitted != audio_path:
        audio_path = fitted

    fps = get_session_framerate(engine)
    duration = audio_duration_seconds(audio_path)
    out_tc = add_frames(timecode, max(1, int(round(duration * fps))), fps)
    if trim_out and trim_out > timecode and trim_out < out_tc:
        log(f"{duration:.1f} s is longer than the selection {timecode}-{trim_out}: goes to a new track in full length")
        return None
    needed_out = min(out_tc, span_out) if span_out and span_out > timecode else out_tc

    with linked_selection(engine, log):
        if not range_is_free(engine, track_name, timecode, needed_out, fps):
            log(f"{timecode}-{needed_out} on '{track_name}' is occupied")
            return None

        before = {c["clip_id"] for c in clip_list(engine)}
        engine.client.run(Import(session_path="", import_type=pt.Audio,
                                 audio_data=pt.AudioData(file_list=[str(Path(audio_path))],
                                                         audio_destination=pt.MD_ClipList,
                                                         audio_location=pt.ML_None)))
        # The clip list lags behind the import by a moment: without the wait the diff was
        # empty and a sound that belonged on this track went to a new one
        new = []
        for _ in range(15):
            new = [c for c in clip_list(engine) if c["clip_id"] not in before and is_audio_clip(c)]
            if new:
                break
            time.sleep(0.2)
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
