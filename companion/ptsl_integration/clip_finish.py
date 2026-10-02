"""Finishing an imported clip: trimmed to its event or selection with the handles left in
the file, and Pro Tools' own fades at its edges. Shared by the hybrid run (library pieces)
and the recommendation import (archive recordings)."""
from __future__ import annotations

from typing import Optional, Tuple


def seconds_to_tc(seconds: float, fps: float) -> str:
    """HH:MM:SS:FF, non-drop arithmetic."""
    rate = max(1, int(round(fps)))
    frames_total = int(round(max(0.0, seconds) * rate))
    frames = frames_total % rate
    whole = frames_total // rate
    return f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d}:{frames:02d}"


def tc_to_seconds(tc: str, fps: float) -> float:
    """Seconds from HH:MM:SS:FF (or HH:MM:SS;FF), non-drop arithmetic."""
    rate = max(1, int(round(fps)))
    hh, mm, ss, ff = (int(p) for p in tc.strip().replace(";", ":").split(":"))
    return ((hh * 60 + mm) * 60 + ss) + ff / float(rate)


def finish_clip(engine_factory, track: str, start: float, end: float, before: float, after: float, fps: float,
                preset: Optional[str], fade: float = 0.0, inside: bool = False, log=print) -> Tuple[bool, bool]:
    """The clip just imported on `track` (with its handles) trimmed to `start`..`end`
    (seconds on the timeline), so the handles stay in the file and can be pulled out
    with the Trim tool. With a batch-fades `preset`, the clip gets Pro Tools' own
    fade-in and fade-out (their length comes from the preset; give it `fade`):

        ....|  event  |....        handles in the file (`before` and `after` seconds)
        fade|  sound  |fade        outside: the clip keeps `fade` of the handle on each
                                   side that has one, full level at the event's edges
            |fade  fade|           inside: the clip ends at the event, the fade runs
                                   within it, as an ambience starts at a cut

    An edge without a handle (the library piece begins or ends right there) fades
    inside in either mode, so the sound never starts or stops with a click.

    The batch-fade range covers only the edge in question, so the seam to the next
    piece of the same ambience gets no fade. The edit selection has to be put on the
    track through a clip selection first (a track selection alone does not make one).
    `engine_factory()` is a context manager giving a PTSL engine. Returns (trimmed, faded)."""
    trimmed = faded = False
    frame = 1.0 / max(1.0, fps)
    lead = min(fade, before) if preset and before > 0.0 and not inside else 0.0   # the handle kept before the event
    tail = min(fade, after) if preset and after > 0.0 and not inside else 0.0     # ... and after it
    clip_start, clip_end = start - lead, end + tail
    reach = min(0.5, max(0.0, clip_end - clip_start) / 2.0)          # into the clip, at most half of it
    fade_in = fade_out = bool(preset)   # where lead or tail is 0 the fade runs inside the clip
    try:
        with engine_factory() as engine:
            engine.select_all_clips_on_track(track)
            engine.set_timeline_selection(in_time=seconds_to_tc(max(0.0, clip_start), fps),
                                          out_time=seconds_to_tc(clip_end, fps))
            engine.trim_to_selection()
            trimmed = True
            for edge, wanted in (("in", fade_in), ("out", fade_out)):
                if not wanted:
                    continue
                if edge == "in":     # a frame before the edge (our own handle room, when there is any) to a little inside
                    lo, hi = clip_start - (frame if before - lead >= frame else 0.0), clip_start + reach
                else:
                    lo, hi = clip_end - reach, clip_end + (frame if after - tail >= frame else 0.0)
                engine.select_all_clips_on_track(track)
                engine.set_timeline_selection(in_time=seconds_to_tc(max(0.0, lo), fps), out_time=seconds_to_tc(hi, fps))
                engine.create_batch_fades(preset, False)
                faded = True
    except Exception as exc:  # noqa: BLE001
        log(f"    {'fades' if trimmed else 'trim'} on '{track}' failed: {str(exc)[:160]}")
    return trimmed, faded
