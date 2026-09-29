"""Which parts of which video clips lie under a time range of the session?

The plugin's three workflows all start from the same question: the user marked a
time range somewhere in the Edit window; which video is under it, and which part
of the source file does that correspond to? PTSL offers no direct answer. The
clip list (GetClipList) knows every clip's source in/out but not where it sits on
the timeline, the session text export leaves video tracks out entirely, and the
selected-clips filter only says which *files* are under the current selection.

So this module asks that last question repeatedly. It selects the video track,
moves the timeline selection and bisects until the frame where the set of files
under the selection changes. That gives frame-exact clip boundaries in about 30
round trips per boundary (a few seconds for a handful of clips), without touching
the session: the selection is restored afterwards, nothing is edited.

Limitations, all reported in the result's ``warnings``:
- Source offsets are taken from the first clip-list entry with the same file id
  when several exist (a file cut into several clips) and no entry matches the
  observed length.
- A file that appears twice in a row on the track with a gap between them is
  treated as one clip starting at the first occurrence.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional, Set

from ptsl import PTSL_pb2 as pt

from .clip_info import get_clip_list, get_session_framerate

Logger = Optional[Callable[[str], None]]

# 24 h is Pro Tools' maximum session length.
_MAX_SESSION_HOURS = 24
# Shorter pieces of a clip under the selection are boundary artefacts, not clips.
MIN_SEGMENT_FRAMES = 2

# What counts as a video clip when the selection also covers audio tracks.
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".flv", ".wmv", ".f4v",
                    ".mxf", ".m2ts", ".mts", ".ts", ".mpg", ".mpeg", ".vob", ".ogv", ".3gp", ".3g2")


@dataclass
class VideoSegment:
    index: int
    video_path: str
    clip_name: str
    in_time: str              # session timecode where the segment starts
    out_time: str             # session timecode where it ends (exclusive)
    in_seconds: float         # seconds from session start
    out_seconds: float
    duration_seconds: float
    source_start_seconds: float   # position in the source video file
    source_end_seconds: float


class _Timecode:
    """Frame counting in the session's timecode, drop-frame aware."""

    def __init__(self, fps: float, drop_frame: bool):
        self.fps = fps
        self.nominal = int(round(fps))          # 30 for 29.97, 60 for 59.94
        self.drop_frame = drop_frame and self.nominal in (30, 60)
        self.dropped_per_minute = (2 if self.nominal == 30 else 4) if self.drop_frame else 0

    def to_frames(self, tc: str) -> int:
        hh, mm, ss, ff = (int(part) for part in tc.split(".")[0].split(":")[:4])
        total_minutes = hh * 60 + mm
        frames = ((hh * 3600 + mm * 60 + ss) * self.nominal) + ff
        if self.drop_frame:
            frames -= self.dropped_per_minute * (total_minutes - total_minutes // 10)
        return frames

    def to_tc(self, frames: int) -> str:
        if self.drop_frame:
            d = self.dropped_per_minute
            frames_per_10min = 10 * 60 * self.nominal - 9 * d
            frames_per_min = 60 * self.nominal - d
            tens, rem = divmod(frames, frames_per_10min)
            if rem >= d:
                ones = (rem - d) // frames_per_min
                frames += d * (tens * 9 + ones)
            else:
                frames += d * tens * 9
        ff = frames % self.nominal
        ss = (frames // self.nominal) % 60
        mm = (frames // (self.nominal * 60)) % 60
        hh = frames // (self.nominal * 3600)
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    def seconds(self, frames: int) -> float:
        return frames / self.fps


def _is_video_track(track) -> bool:
    try:
        return pt.TrackType.Name(track.type) == "VideoTrack"
    except (ValueError, AttributeError):
        return track.type == 4


def _video_fps(path: str, fallback: float, log: Logger) -> float:
    """Frame rate of the source file, for turning clip-list frames into seconds."""
    try:
        from video.ffmpeg import get_video_fps
        fps = float(get_video_fps(path))
        if fps > 0:
            return fps
    except Exception as exc:  # noqa: BLE001 - any probe failure means "use the session rate"
        if log:
            log(f"video fps probe failed for {path}: {exc}")
    return fallback


def resolve_video_segments(engine, whole_track: bool = False, track_name: Optional[str] = None,
                           log: Logger = None) -> Dict:
    """Map the timeline selection (or the whole video track) onto video clip segments.

    Returns a dict with ``success``, ``fps``, ``sample_rate``, ``track``, ``range``
    (``in_time``/``out_time``), ``segments`` (list of VideoSegment dicts) and
    ``warnings``; on failure ``success`` is False and ``error`` says why.
    """
    def note(msg: str) -> None:
        if log:
            log(msg)

    warnings: List[str] = []
    fps = get_session_framerate(engine)
    rate_enum = engine.session_timecode_rate()
    try:
        drop = "Drop" in pt.SessionTimeCodeRate.Name(rate_enum)
    except ValueError:
        drop = False
    tc = _Timecode(fps, drop)
    sample_rate = engine.session_sample_rate() or 48000

    video_tracks = [t for t in engine.track_list() if _is_video_track(t)]
    if not video_tracks:
        return {"success": False, "error": "The session has no video track."}
    track = next((t for t in video_tracks if t.name == track_name), None) if track_name else video_tracks[0]
    if track is None:
        return {"success": False, "error": f"No video track named '{track_name}' in the session."}
    if len(video_tracks) > 1:
        warnings.append(f"{len(video_tracks)} video tracks in the session; using '{track.name}'.")

    saved_in, saved_out = engine.get_timeline_selection(pt.TimeCode)
    origin = tc.to_frames(engine.session_start_time())

    def files_between(a: int, b: int) -> Set[str]:
        """Video files under frames [a, b) on the video track."""
        engine.set_timeline_selection(in_time=tc.to_tc(a), out_time=tc.to_tc(max(b, a + 1)))
        return {f.path for f in engine.get_file_location(filters=[pt.SelectedClipsTimeline])
                if f.path.lower().endswith(VIDEO_EXTENSIONS)}

    # The selected-clips filter looks at the *edit* selection, which lives on the tracks the
    # user dragged across. Moving it onto the video track needs Pro Tools' "Link Track and
    # Edit Selection" option, which is switched on for the duration of this call (and
    # "Link Timeline and Edit Selection", without which SetTimelineSelection would not move
    # the edit selection at all). Both are restored afterwards, as is the edit selection.
    all_tracks = engine.track_list()
    edit_selected_tracks = [t.name for t in all_tracks if _flag(t, "has_edit_selection")]
    selected_tracks = [t.name for t in all_tracks if _flag(t, "is_selected")]
    options = _edit_mode_options(engine)

    def set_options(**changes) -> None:
        engine.client.run_command(pt.CId_SetEditModeOptions, {"edit_mode_options": {**options, **changes}})

    def move_edit_selection_to(names: List[str]) -> None:
        if options:
            engine.select_tracks_by_name(names)          # track link is on: edit selection follows
        else:
            # No option access: select every clip on the track, which also moves the edit
            # selection there; the following SetTimelineSelection narrows the range again.
            engine.select_all_clips_on_track(names[0])

    def first_where(lo: int, hi: int, pred: Callable[[int], bool]) -> int:
        """Smallest x in [lo, hi] with pred(x) true; pred must be monotone. hi if none."""
        while lo < hi:
            mid = (lo + hi) // 2
            if pred(mid):
                hi = mid
            else:
                lo = mid + 1
        return lo

    try:
        if options:
            set_options(link_timeline_and_edit_selection=True, link_track_and_edit_selection=True)
        else:
            warnings.append("Edit mode options not readable; used select-all-clips to reach the video track.")
        move_edit_selection_to([track.name])

        if whole_track:
            # One frame short of 24 h: Pro Tools rejects 24:00:00:00 as a selection end.
            end_of_session = origin + _MAX_SESSION_HOURS * 3600 * tc.nominal - 1
            first = first_where(origin, end_of_session, lambda t: bool(files_between(origin, t)))
            if first >= end_of_session:
                return {"success": False, "error": f"The video track '{track.name}' is empty."}
            range_in = max(origin, first - 1)          # first == origin: content at the very first frame
            range_out = first_where(range_in + 1, end_of_session, lambda t: not files_between(t, end_of_session))
        else:
            range_in, range_out = tc.to_frames(saved_in), tc.to_frames(saved_out)
            if range_out <= range_in:
                return {"success": False,
                        "error": "Nothing is selected. Mark a time range on any track first "
                                 "(the video track is looked up automatically)."}
        note(f"range {tc.to_tc(range_in)} - {tc.to_tc(range_out)} on track '{track.name}'")

        # Walk the range: each run is a stretch of frames with the same set of files under it.
        runs: List[tuple] = []          # (start_frame, end_frame_exclusive, files)
        pos = range_in
        while pos < range_out:
            base = files_between(pos, pos + 1)
            change = first_where(pos + 1, range_out, lambda t: files_between(pos, t) != base)
            run_end = change - 1 if change < range_out else range_out
            if run_end <= pos:          # cannot happen (frame `pos` is in base), guard anyway
                run_end = pos + 1
            runs.append((pos, run_end, base))
            pos = run_end

        clip_list = get_clip_list(engine)
        by_file_id = {}
        for clip in clip_list:
            if "Video" in str(clip.get("clip_type", "")):
                by_file_id.setdefault(clip.get("file_id"), []).append(clip)
        file_ids = {}
        engine.set_timeline_selection(in_time=tc.to_tc(range_in), out_time=tc.to_tc(range_out))
        for loc in engine.get_file_location(filters=[pt.SelectedClipsTimeline]):
            file_ids[loc.path] = loc.file_id

        segments: List[VideoSegment] = []
        fps_cache: Dict[str, float] = {}
        for start, end, files in runs:
            if not files:
                continue                                  # gap on the track
            if len(files) > 1:
                warnings.append(f"{len(files)} overlapping video clips at {tc.to_tc(start)}; skipped.")
                continue
            path = next(iter(files))

            # Where does this clip begin on the timeline? Known when the run starts at a
            # boundary we found; for a run starting at the range start, look left.
            clip_start = start
            if start == range_in and start > origin and files_between(start - 1, start + 1) == files:
                only_this = first_where(origin, start, lambda t: files_between(t, start + 1) <= files)
                gap_end = first_where(only_this, start + 1, lambda t: bool(files_between(only_this, t)))
                clip_start = max(only_this, gap_end - 1)

            candidates = by_file_id.get(file_ids.get(path), [])
            clip = None
            if len(candidates) == 1:
                clip = candidates[0]
            elif candidates:
                full_length = (start != range_in or clip_start == start) and end != range_out
                if full_length:
                    clip = next((c for c in candidates
                                 if _frames(c, "end_point") - _frames(c, "start_point") == end - start), None)
                if clip is None:
                    clip = candidates[0]
                    warnings.append(f"'{clip.get('clip_full_name')}': several clips share this file; "
                                    f"source offset taken from the first entry.")
            if clip is None:
                warnings.append(f"No clip-list entry for {path}; assuming the clip starts at the file start.")
                clip_name, source_in_frames = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1], 0
            else:
                clip_name, source_in_frames = clip.get("clip_full_name", ""), _frames(clip, "start_point")

            if end - start < MIN_SEGMENT_FRAMES:
                # Clip boundaries are sample-accurate but the selection is read in whole
                # frames, so a selection that starts exactly on a cut reports one frame of
                # the clip before it. That frame is not a clip the user chose.
                note(f"ignoring {clip_name}: only {end - start} frame(s) inside the range")
                continue

            if path not in fps_cache:
                fps_cache[path] = _video_fps(path, fps, note)
            source_start = source_in_frames / fps_cache[path] + tc.seconds(start - clip_start)
            segments.append(VideoSegment(
                index=len(segments), video_path=path, clip_name=clip_name,
                in_time=tc.to_tc(start), out_time=tc.to_tc(end),
                in_seconds=tc.seconds(start - origin), out_seconds=tc.seconds(end - origin),
                duration_seconds=tc.seconds(end - start),
                source_start_seconds=round(source_start, 3),
                source_end_seconds=round(source_start + tc.seconds(end - start), 3)))
            note(f"segment {segments[-1].index}: {clip_name} {segments[-1].in_time}-{segments[-1].out_time} "
                 f"source {segments[-1].source_start_seconds:.3f}-{segments[-1].source_end_seconds:.3f}s")
    finally:
        try:
            engine.set_timeline_selection(in_time=saved_in, out_time=saved_out)
            if options:
                if edit_selected_tracks:
                    engine.select_tracks_by_name(edit_selected_tracks)   # edit selection back (link still on)
                set_options()                                            # original options
                if selected_tracks:
                    engine.select_tracks_by_name(selected_tracks)        # track selection back
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not fully restore the selection: {exc}")

    if not segments:
        return {"success": False, "error": f"No video clip on track '{track.name}' under "
                                           f"{tc.to_tc(range_in)} - {tc.to_tc(range_out)}.",
                "warnings": warnings}
    return {"success": True, "fps": fps, "sample_rate": sample_rate, "track": track.name,
            "range": {"in_time": tc.to_tc(range_in), "out_time": tc.to_tc(range_out),
                      "in_seconds": tc.seconds(range_in - origin), "out_seconds": tc.seconds(range_out - origin)},
            "segments": [asdict(s) for s in segments], "warnings": warnings, "error": None}


def _flag(track, attribute: str) -> bool:
    """A TripleBool track attribute (is_selected, has_edit_selection, ...) that is set."""
    attrs = getattr(track, "track_attributes", None)
    value = getattr(attrs, attribute, None)
    if value is None:
        return False
    try:
        return pt.TripleBool.Name(value) == "SetExplicitly"
    except (ValueError, AttributeError):
        return value == getattr(pt, "SetExplicitly", 1)


def _edit_mode_options(engine) -> Dict:
    """Pro Tools' Options-menu link settings, or {} if PTSL will not tell."""
    try:
        return dict(engine.client.run_command(pt.CId_GetEditModeOptions, {}).get("edit_mode_options", {}))
    except Exception:  # noqa: BLE001
        return {}


def _frames(clip: Dict, key: str) -> int:
    point = clip.get(key) or {}
    return int(point.get("position", point.get("value", 0)) or 0)


if __name__ == "__main__":     # manual check: python -m ptsl_integration.video_segments [--whole-track]
    import json
    from ptsl import open_engine

    with open_engine(company_name="AI Sound Design", application_name="Segments") as eng:
        result = resolve_video_segments(eng, whole_track="--whole-track" in sys.argv,
                                        log=lambda m: print(m, file=sys.stderr))
    print(json.dumps(result, indent=2))
