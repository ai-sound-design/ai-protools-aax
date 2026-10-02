#!/usr/bin/env python3
"""Real spotting: send video ranges to the spotting backend, place markers.

Asks the spotting service (the backend's spotting-api) for the sound events in
video ranges and creates one memory location per event in the open Pro Tools
session. Three ways to say which ranges:

    python spotting_client.py --from-selection      # video clips under the timeline selection
    python spotting_client.py --whole-track         # every clip on the video track
    python spotting_client.py --video seg.mp4 --start-tc 00:00:18:06 [--clip-start s --clip-end s]
    python spotting_client.py --events events.json --start-tc 00:00:18:06

With --from-selection the selection may be on any track: the video clips beneath
it are looked up through PTSL (see ptsl_integration/video_segments.py). Each clip
is a scene of its own, so each segment is cut, sent and marked separately, in
timeline order.

--progress-file PATH keeps a small JSON document up to date while running
({"current", "total", "clip", "stage", "done"}) so the plugin can show progress.

Markers go to the main marker ruler unless --ruler names a marker ruler that
exists in the session. Named rulers cannot be created over PTSL, so if the named
ruler is missing the markers fall back to the main ruler and the fallback is
reported; nothing is silently dropped.

Output is one JSON object on stdout, as the plugin expects from companion
scripts. Progress goes to stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api.config import get_api_url, get_cf_headers  # noqa: E402

DEFAULT_SPOTTING_URL = get_api_url("spotting") or "http://localhost:8003"

# Pro Tools marker colours (colour palette indices), one per event category.
CATEGORY_COLOURS = {"dialogue": 3, "foley": 8, "sfx": 9, "ambience": 12, "music": 5, "clip": 1, "scene": 2}

# The backend samples 2 frames/s and shows the model 8 frames per call. A clip
# shorter than 4 s would give it fewer frames, so the rate is raised until the
# clip fills one call (capped so a one-second clip is not sampled 60 times).
BACKEND_SAMPLE_FPS = 2.0
BACKEND_FRAMES_PER_CALL = 8
MAX_SAMPLE_FPS = 8.0

# Segments shorter than this are not analysed (they still get their clip marker):
# a sliver of a neighbouring clip caught by the edge of the selection has too few
# frames to judge and produced nonsense ("leopard footsteps" for 0.8 s of a dog).
MIN_SEGMENT_SECONDS = 1.0


# Set from --progress-file: log lines then go to <progress>.log instead of stderr and
# the result document to <progress>.result.json instead of stdout. The plugin reads
# the pipe only after the process has exited, and a Windows pipe holds 4 KB: a run
# over many clips filled it, the script blocked on its final print, the plugin waited
# for the exit, and both sat there until the ten-minute timeout. Files have no such
# limit, and the log file also survives a kill.
LOG_FILE: Optional[Path] = None
RESULT_FILE: Optional[Path] = None
STDOUT: Optional[object] = None      # the real stdout while everything else is sent to the log file


def log(message: str) -> None:
    if LOG_FILE is None:
        try:
            print(message, file=sys.stderr, flush=True)
        except OSError:
            pass                     # stderr pipe gone (plugin window closed): keep going
    else:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        except OSError:
            pass


class Progress:
    """Writes the progress document the plugin polls; a no-op without a path.

    A heartbeat thread rewrites the document every few seconds with a fresh
    `alive` timestamp, so the plugin can tell a slow stage (a long placement, a
    cold backend) from a dead script and does not have to guess a time limit."""

    HEARTBEAT_SECONDS = 5.0

    def __init__(self, path: Optional[Path]):
        import threading

        self.path = path
        self.doc: dict = {}
        self.finished = False
        self.lock = threading.Lock()
        if path is not None:
            threading.Thread(target=self._heartbeat, name="progress-heartbeat", daemon=True).start()

    def _heartbeat(self) -> None:
        import time

        while not self.finished:
            time.sleep(self.HEARTBEAT_SECONDS)
            with self.lock:
                if self.doc and not self.finished:
                    self._write({**self.doc, "alive": time.time()})

    def update(self, current: int, total: int, clip: str, stage: str, done: bool = False,
               fraction: Optional[float] = None, detail: str = "", eta_seconds: Optional[float] = None,
               overall: Optional[float] = None) -> None:
        """Best effort: progress must never abort the run itself.

        `fraction` (0..1) is how far the backend is with the current clip, when it
        says; `detail` its own words for that ("frames 16 of 40"); `eta_seconds` a
        rough time left, when the script can tell; `overall` (0..1) the share of the
        whole run that is done (see RunShare), which the plugin's bar follows when
        it is given, instead of counting clips."""
        if self.path is None:
            return
        import time

        with self.lock:
            self.doc = {"current": current, "total": total, "clip": clip, "stage": stage, "done": done,
                        "fraction": fraction, "detail": detail, "eta_seconds": eta_seconds, "overall": overall,
                        "alive": time.time()}
            self.finished = done
            self._write(self.doc)

    def _write(self, document: dict) -> None:
        import time

        doc = json.dumps(document)
        tmp = self.path.with_suffix(".tmp")
        for attempt in range(5):
            try:
                tmp.write_text(doc, encoding="utf-8")
                tmp.replace(self.path)      # atomic when it works
                return
            except OSError:
                # On Windows the rename fails while the plugin has the file open for
                # reading (every 100 ms); wait a moment and try again.
                time.sleep(0.05 * (attempt + 1))
        try:
            self.path.write_text(doc, encoding="utf-8")     # non-atomic fallback; the reader tolerates half files
        except OSError as exc:
            log(f"progress file not writable: {exc}")


def sample_fps_for(duration: float | None) -> float | None:
    """Frame sampling rate so that a short clip still yields a full call of frames."""
    if not duration or duration <= 0:
        return None
    wanted = BACKEND_FRAMES_PER_CALL / duration
    if wanted <= BACKEND_SAMPLE_FPS:
        return None                      # backend default is fine
    return round(min(MAX_SAMPLE_FPS, wanted), 2)


def spot_video(video: Path, start_tc: str, fps: float, url: str, hints: str | None,
               duration: float | None = None, on_progress=None) -> dict:
    """Ask the spotting service for the events in `video`.

    `on_progress(dict)` gets the service's progress answers (stage, fraction,
    detail) every two seconds while the request runs, if the service offers them."""
    import uuid

    import httpx

    from api.adapters import ProgressPolling

    sample_fps = sample_fps_for(duration)
    job_id = uuid.uuid4().hex
    log(f"Spotting {video.name} via {url}" + (f" at {sample_fps} frames/s" if sample_fps else "") + " ...")
    with video.open("rb") as handle, \
            ProgressPolling(f"{url.rstrip('/')}/spot/progress/{job_id}", on_progress):
        data = {"start_timecode": start_tc, "fps": str(fps), "job_id": job_id}
        if hints:
            data["hints"] = hints
        if sample_fps:
            data["sample_fps"] = str(sample_fps)
        response = httpx.post(f"{url.rstrip('/')}/spot", files={"video": (video.name, handle, "video/mp4")},
                              data=data, headers=get_cf_headers(), timeout=900)
    if response.status_code != 200:
        raise RuntimeError(f"spotting service returned {response.status_code}: {response.text[:400]}")
    return response.json()


def cut_range(video: Path, start: float, end: float) -> Path:
    """Cut [start, end) out of the source video into a temp file, re-encoded.

    A stream copy would snap the cut to the previous keyframe and shift every
    event time by up to a GOP; spotting needs the range to start exactly where
    the selection starts, so this re-encodes. The clips are seconds long.
    """
    import subprocess
    import tempfile

    import imageio_ffmpeg

    out = Path(tempfile.gettempdir()) / f"spotting_{start:.3f}_{end:.3f}_{video.stem}.mp4"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video),
         "-t", f"{end - start:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True, text=True)
    log(f"Cut {start:.3f}s-{end:.3f}s of {video.name} -> {out.name}")
    return out


def tc_to_samples(tc: str, fps: float, sample_rate: int) -> int:
    hh, mm, ss, ff = (int(part) for part in tc.split(":"))
    seconds = (hh * 3600 + mm * 60 + ss) + ff / fps
    return int(round(seconds * sample_rate))


def place_markers(engine, events: List[dict], fps: float, ruler: str | None) -> dict:
    """Create one memory location per event. Returns counts and fallbacks."""
    import ptsl.PTSL_pb2 as pt

    created, failed, fell_back = 0, [], 0
    sample_rate = engine.session_sample_rate() or 48000
    existing = engine.get_memory_locations()
    next_number = max((m.number for m in existing), default=0) + 1
    log(f"Session {engine.session_name()} at {sample_rate} Hz, "
        f"{len(existing)} markers present, {len(events)} to create")

    for event in events:
        start = str(tc_to_samples(event["start_timecode"], fps, sample_rate))
        end = str(tc_to_samples(event["end_timecode"], fps, sample_rate))
        name = event["label"][:31]
        comment = event.get("comment") or (
            f"{event['category']}: {event['description']} (confidence {event['confidence']:.2f})")
        colour = CATEGORY_COLOURS.get(event["category"], 8)
        props = pt.MemoryLocationProperties(zoom_settings=False, pre_post_roll_times=False,
                                            track_visibility=False, track_heights=False,
                                            group_enables=False, window_configuration=False)

        def create(location, track_name):
            engine.create_memory_location(
                memory_number=next_number, name=name, start_time=start, end_time=end,
                time_properties=pt.TP_Marker, reference=pt.MLR_Absolute,
                general_properties=props, comments=comment, color_index=colour,
                location=location, track_name=track_name)

        try:
            if ruler:
                try:
                    create(pt.MarkerLocation_NamedRuler, ruler)
                except Exception as exc:
                    # Pro Tools reports PT_NoTracksFound for a missing named
                    # ruler but has already placed the marker on the main
                    # ruler. Retrying would duplicate it, so count it as a
                    # fallback and move on.
                    if "PT_NoTracksFound" not in str(exc):
                        raise
                    fell_back += 1
            else:
                create(pt.MarkerLocation_MainRuler, None)
            created += 1
            next_number += 1
        except Exception as exc:
            failed.append({"name": name, "error": str(exc)})
    return {"created": created, "failed": failed, "fell_back_to_main_ruler": fell_back}


def spot_segment(video: Path, source_start: float | None, source_end: float | None,
                 start_tc: str, fps: float, url: str, hints: str | None, on_progress=None) -> dict:
    """Cut (if a source range is given), send, return the service's result."""
    cut = None
    duration = None
    if source_start is not None and source_end is not None:
        cut = video = cut_range(video, source_start, source_end)
        duration = source_end - source_start
    try:
        return spot_video(video, start_tc, fps, url, hints, duration, on_progress)
    finally:
        if cut is not None:
            cut.unlink(missing_ok=True)


def clip_marker(seg: Dict, index: int, total: int, clip: str) -> dict:
    """A marker spanning one video clip: the cut between two clips is a scene change."""
    return {"label": clip, "category": "clip", "confidence": 1.0, "clip": clip,
            "description": f"clip {index}/{total}",
            "comment": (f"Clip {index}/{total}: {Path(seg['video_path']).name}, "
                        f"source {seg['source_start_seconds']:.2f}-{seg['source_end_seconds']:.2f} s"),
            "start_timecode": seg["in_time"], "end_timecode": seg["out_time"],
            "start_seconds": seg["in_seconds"], "end_seconds": seg["out_seconds"]}


def detect_scenes(clips: List[Tuple[Path, str]], url: str, on_progress=None) -> dict:
    """Ask the spotting service which consecutive clips (path, name; timeline order) form
    one scene. Returns its JSON: "scenes" [{index, name, description, first_clip,
    last_clip}] and "clip_scenes" (scene index per clip)."""
    import uuid

    import httpx

    from api.adapters import ProgressPolling

    job_id = uuid.uuid4().hex
    handles = [path.open("rb") for path, _ in clips]
    try:
        files = [("videos", (path.name, handle, "video/mp4")) for (path, _), handle in zip(clips, handles)]
        data = {"names": json.dumps([name for _, name in clips], ensure_ascii=False), "job_id": job_id}
        log(f"Scenes: {len(clips)} clip(s) via {url} ...")
        with ProgressPolling(f"{url.rstrip('/')}/spot/progress/{job_id}", on_progress):
            response = httpx.post(f"{url.rstrip('/')}/scenes", files=files, data=data,
                                  headers=get_cf_headers(), timeout=900)
    finally:
        for handle in handles:
            handle.close()
    if response.status_code != 200:
        raise RuntimeError(f"spotting service returned {response.status_code}: {response.text[:400]}")
    return response.json()


def scene_markers(scenes: List[dict], segments: List[Dict]) -> List[dict]:
    """One memory location per scene, spanning its clips ("Scene 2: kitchen, night")."""
    out = []
    for scene in scenes:
        try:
            first, last = segments[int(scene["first_clip"])], segments[int(scene["last_clip"])]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        clips = int(scene["last_clip"]) - int(scene["first_clip"]) + 1
        out.append({"label": f"Scene {scene.get('index')}: {scene.get('name', '')}"[:31], "category": "scene",
                    "confidence": 1.0, "clip": "", "scene": scene.get("index"),
                    "description": scene.get("description", ""),
                    "comment": (f"Scene {scene.get('index')}: {scene.get('name', '')}. {scene.get('description', '')} "
                                f"({clips} clip{'s' if clips != 1 else ''})"),
                    "start_timecode": first["in_time"], "end_timecode": last["out_time"],
                    "start_seconds": first["in_seconds"], "end_seconds": last["out_seconds"]})
    return out


EVENT_CATEGORIES = ("dialogue", "foley", "sfx", "ambience", "music")
CATEGORY_WORDS = {"dialogue": "dialogue (human speech)",
                  "foley": "foley (footsteps, clothes, objects handled by people)",
                  "sfx": "sound effects (machines, vehicles, animals, impacts, weather)",
                  "ambience": "ambience (the room tone or atmosphere of the place)",
                  "music": "music with a visible source"}


def category_hint(categories: List[str], hints: str | None) -> str | None:
    """The editor's hint to the model, extended by which kinds of sound are wanted."""
    wanted = [c for c in EVENT_CATEGORIES if c in categories]
    if not wanted or len(wanted) == len(EVENT_CATEGORIES):
        return hints
    text = "Only these kinds of sound are needed: " + "; ".join(CATEGORY_WORDS[c] for c in wanted) + "."
    return f"{hints.strip()} {text}" if hints and hints.strip() else text


def keep_categories(events: List[dict], categories: List[str]) -> List[dict]:
    if not categories:
        return events
    return [e for e in events if e.get("category") in categories]


class RunShare:
    """The share of a whole run that is done, for the plugin's progress bar.

    Every clip counts one unit for its spotting or generation; detecting the scenes
    counts half a unit per clip beforehand (one whole unit per clip when scenes are
    all the run does); placing the sounds afterwards `placing` units per clip."""

    def __init__(self, clips: int, scenes: bool, events: bool, placing: float = 0.0):
        clips = max(1, clips)
        self.scene_units = (0.5 * clips if events else float(clips)) if scenes else 0.0
        self.clip_units = float(clips) if events else 0.0
        self.place_units = placing * clips if events else 0.0
        self.units = max(self.scene_units + self.clip_units + self.place_units, 1e-9)

    def scenes(self, fraction: Optional[float]) -> float:
        return self.scene_units * max(0.0, min(1.0, fraction or 0.0)) / self.units

    def clip(self, i: int, fraction: Optional[float] = 0.0) -> float:
        """Clip `i` (1-based) is in progress, `fraction` of it done."""
        return (self.scene_units + max(0, i - 1) + max(0.0, min(1.0, fraction or 0.0))) / self.units

    def placing(self, fraction: float) -> float:
        return (self.scene_units + self.clip_units + self.place_units * max(0.0, min(1.0, fraction))) / self.units


def cut_segments(segments: List[Dict], progress: Progress, overall_of=None) -> Dict[int, Path]:
    """Cut every segment out of its source video; {segment index: temp file}.
    `overall_of(i)` names the run's share done after cutting clip i, when known."""
    cuts: Dict[int, Path] = {}
    total = len(segments)
    for i, seg in enumerate(segments, start=1):
        progress.update(i, total, seg.get("clip_name") or Path(seg["video_path"]).stem, "cutting",
                        overall=overall_of(i) if overall_of else None)
        cuts[seg["index"]] = cut_range(Path(seg["video_path"]), seg["source_start_seconds"], seg["source_end_seconds"])
    return cuts


def run_segments(segments: List[Dict], fps: float, args, progress: Progress,
                 engine_factory: Callable) -> dict:
    """Spot every segment in timeline order, then place all markers in one PTSL session."""
    total = len(segments)
    all_events: List[dict] = []
    clip_markers: List[dict] = []
    scene_marks: List[dict] = []
    scenes: List[dict] = []
    per_clip: List[dict] = []
    model = None
    cuts: Dict[int, Path] = {}
    share = RunShare(total, scenes=bool(getattr(args, "scenes", False)), events=not getattr(args, "no_events", False))
    if getattr(args, "scenes", False):
        # Scenes first: the backend sees every clip of the range at once, and the
        # cut files are reused for the spotting below.
        cuts = cut_segments(segments, progress, overall_of=lambda i: share.scenes(0.05 * i / total))
        try:
            progress.update(0, total, "", "detecting scenes", overall=share.scenes(0.05))
            found = detect_scenes([(cuts[s["index"]], s.get("clip_name") or Path(s["video_path"]).stem)
                                   for s in segments], args.url,
                                  on_progress=lambda p: progress.update(0, total, "", "detecting scenes",
                                                                        fraction=p.get("fraction"),
                                                                        detail=p.get("detail", ""),
                                                                        overall=share.scenes(max(0.05, p.get("fraction")))))
            scenes = found.get("scenes", [])
            scene_marks = scene_markers(scenes, segments)
            log(f"{len(scenes)} scene(s): " + "; ".join(f"{s.get('index')}: {s.get('name')}" for s in scenes))
        except Exception as exc:  # noqa: BLE001  (scenes are a courtesy; the spotting still runs)
            log(f"scene detection failed: {exc}")
    categories = [c.strip().lower() for c in (getattr(args, "categories", "") or "").split(",") if c.strip()]
    hints = category_hint(categories, args.hints)
    for i, seg in enumerate(segments, start=1):
        clip = seg.get("clip_name") or Path(seg["video_path"]).stem
        if not args.no_clip_markers:
            clip_markers.append(clip_marker(seg, i, total, clip))
        if getattr(args, "no_events", False):
            per_clip.append({"clip": clip, "in_time": seg["in_time"], "events": 0, "skipped": "events off"})
            continue
        if seg["duration_seconds"] < MIN_SEGMENT_SECONDS:
            log(f"[{i}/{total}] {clip}: {seg['duration_seconds']:.2f}s is too short, skipped")
            per_clip.append({"clip": clip, "in_time": seg["in_time"], "events": 0, "skipped": "too short"})
            continue
        progress.update(i, total, clip, "cutting", overall=share.clip(i))
        log(f"[{i}/{total}] {clip} {seg['in_time']}-{seg['out_time']}")
        try:
            progress.update(i, total, clip, "spotting", overall=share.clip(i))

            def report(p, i=i, clip=clip):
                progress.update(i, total, clip, "spotting", fraction=p.get("fraction"), detail=p.get("detail", ""),
                                overall=share.clip(i, p.get("fraction")))

            if seg["index"] in cuts:
                result = spot_video(cuts[seg["index"]], seg["in_time"], fps, args.url, hints,
                                    seg["duration_seconds"], report)
            else:
                result = spot_segment(Path(seg["video_path"]), seg["source_start_seconds"],
                                      seg["source_end_seconds"], seg["in_time"], fps, args.url, hints,
                                      on_progress=report)
        except Exception as exc:  # one failing clip must not lose the others
            log(f"[{i}/{total}] {clip} failed: {exc}")
            per_clip.append({"clip": clip, "in_time": seg["in_time"], "events": 0, "error": str(exc)})
            continue
        finally:
            if seg["index"] in cuts:
                cuts.pop(seg["index"]).unlink(missing_ok=True)
        events = keep_categories(result.get("events", []), categories)
        for event in events:
            event["clip"] = clip
        all_events.extend(events)
        model = result.get("model") or model
        per_clip.append({"clip": clip, "in_time": seg["in_time"], "events": len(events),
                         "seconds_taken": result.get("seconds_taken")})
        log(f"[{i}/{total}] {clip}: {len(events)} events")

    if clip_markers:
        # Pro Tools draws a marker's name rightwards until the next marker, so the
        # last event would look as if it ran on forever. A closing marker at the
        # end of the analysed range gives the ruler its right edge.
        last = segments[-1]
        clip_markers.append({"label": "end of spotting range", "category": "clip", "confidence": 1.0,
                             "clip": "", "description": "end of the analysed range",
                             "comment": f"End of the spotted range ({segments[0]['in_time']} - {last['out_time']}), "
                                        f"{total} clip(s)",
                             "start_timecode": last["out_time"], "end_timecode": last["out_time"],
                             "start_seconds": last["out_seconds"], "end_seconds": last["out_seconds"]})
    for path in cuts.values():
        path.unlink(missing_ok=True)
    output = {"success": True, "events": all_events, "model": model, "clips": per_clip, "segments": total,
              "clip_markers": len(clip_markers), "scenes": scenes, "scene_markers": len(scene_marks)}
    markers = scene_marks + clip_markers + all_events
    if not args.dry_run and markers:
        progress.update(total, total, "", "placing markers", overall=1.0)
        with engine_factory() as engine:
            output.update(place_markers(engine, markers, fps, args.ruler))
        output["success"] = output["created"] > 0
    if not all_events:
        output["success"] = any("error" not in c and "skipped" not in c for c in per_clip) \
            or (getattr(args, "no_events", False) and output.get("created", 0) > 0)
        if not output["success"]:
            output["error"] = "; ".join(c.get("error") or c.get("skipped", "") for c in per_clip) or "no events"
    progress.update(total, total, "", "done", done=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-selection", action="store_true",
                        help="spot the video clips under the timeline selection (selection may be on any track)")
    source.add_argument("--whole-track", action="store_true", help="spot every clip on the video track")
    source.add_argument("--video", type=Path, help="video range to spot")
    source.add_argument("--events", type=Path, help="spotting result JSON to place instead of calling the service")
    parser.add_argument("--start-tc", default="00:00:00:00", help="--video/--events: timecode where the range starts")
    parser.add_argument("--fps", type=float, default=30.0, help="--video/--events: timecode frame rate of the session")
    parser.add_argument("--clip-start", type=float, help="--video: cut the video from this second (source time) ...")
    parser.add_argument("--clip-end", type=float, help="... to this second before spotting")
    parser.add_argument("--hints", help="free-text context for the model")
    parser.add_argument("--video-track", default=None,
                        help="the video track to map the range onto (default: the topmost, or the one the selection lies on)")
    parser.add_argument("--scenes", action="store_true",
                        help="group the clips of the range into scenes first and place one memory location per scene")
    parser.add_argument("--no-events", action="store_true",
                        help="do not look for sound events (only scenes and clip markers)")
    parser.add_argument("--categories", default="",
                        help="comma-separated kinds of events to keep (dialogue, foley, sfx, ambience, music); "
                             "the model is told which kinds are wanted, and other events are dropped")
    parser.add_argument("--no-clip-markers", action="store_true",
                        help="do not add one marker per video clip (clip boundaries)")
    parser.add_argument("--ruler", help="named marker ruler to use, e.g. 'Foley and SFX'; main ruler if absent")
    parser.add_argument("--url", default=DEFAULT_SPOTTING_URL, help="spotting service base URL")
    parser.add_argument("--progress-file", type=Path, help="JSON file to keep updated with progress")
    parser.add_argument("--ptsl-host", default="localhost")
    parser.add_argument("--ptsl-port", type=int, default=31416)
    parser.add_argument("--dry-run", action="store_true", help="spot, print events, create no markers")
    args = parser.parse_args()

    progress = Progress(args.progress_file)
    set_log_files(args.progress_file)

    def engine_factory():
        from ptsl import open_engine
        return open_engine(company_name="AI Sound Design", application_name="Spotting",
                           address=f"{args.ptsl_host}:{args.ptsl_port}")

    try:
        if args.from_selection or args.whole_track:
            from ptsl_integration.video_segments import resolve_video_segments

            progress.update(0, 0, "", "reading selection")
            with engine_factory() as engine:
                resolved = resolve_video_segments(engine, whole_track=args.whole_track,
                                                  track_name=getattr(args, "video_track", None) or None, log=log)
            if not resolved.get("success"):
                raise RuntimeError(resolved.get("error", "could not resolve the video range"))
            for warning in resolved.get("warnings", []):
                log(f"warning: {warning}")
            output = run_segments(resolved["segments"], resolved["fps"], args, progress, engine_factory)
            output["range"] = resolved["range"]
            output["warnings"] = resolved.get("warnings", [])
        else:
            if args.events:
                result = json.loads(args.events.read_text(encoding="utf-8"))
            else:
                progress.update(1, 1, args.video.stem, "spotting")
                result = spot_segment(args.video, args.clip_start, args.clip_end, args.start_tc, args.fps,
                                      args.url, args.hints,
                                      on_progress=lambda p: progress.update(
                                          1, 1, args.video.stem, "spotting",
                                          fraction=p.get("fraction"), detail=p.get("detail", "")))
            events = result.get("events", [])
            log(f"{len(events)} events" + (f" in {result.get('seconds_taken')}s" if "seconds_taken" in result else ""))
            output = {"success": True, "events": events, "model": result.get("model")}
            if not args.dry_run and events:
                with engine_factory() as engine:
                    output.update(place_markers(engine, events, args.fps, args.ruler))
                output["success"] = output["created"] > 0
            progress.update(1, 1, "", "done", done=True)

        for event in output["events"]:
            log(f"  {event['start_timecode']} - {event['end_timecode']}  [{event['category']}] {event['label']}")
        emit(output)
        return 0 if output["success"] else 1
    except Exception as exc:
        progress.update(0, 0, "", f"failed: {exc}", done=True)
        emit({"success": False, "error": str(exc)})
        return 1


def set_log_files(progress_file) -> None:
    """Log and result go to files next to the progress file (the plugin reads them after exit).

    Everything the run prints (the import helpers report every step on stdout) goes to
    the log file as well: with many imports those lines alone fill the 4 KB pipe, the
    script blocks on a print, the plugin waits for the exit, and the run times out
    although it finished. Only emit() still speaks through the pipe."""
    global LOG_FILE, RESULT_FILE, STDOUT
    if progress_file is None:
        return
    LOG_FILE = Path(progress_file).with_suffix(".log")
    LOG_FILE.unlink(missing_ok=True)
    RESULT_FILE = Path(progress_file).with_suffix(".result.json")
    RESULT_FILE.unlink(missing_ok=True)
    try:
        STDOUT = sys.stdout
        sink = LOG_FILE.open("a", encoding="utf-8", buffering=1)
        sys.stdout = sink
        sys.stderr = sink
    except OSError:
        STDOUT = None


def emit(output: dict) -> None:
    """Hand the result to the caller: a file when the plugin asked for one, else stdout."""
    text = json.dumps(output, ensure_ascii=False)
    if RESULT_FILE is not None:
        RESULT_FILE.write_text(text, encoding="utf-8")
        text = json.dumps({"success": output.get("success", False), "result_file": str(RESULT_FILE),
                           "error": output.get("error")}, ensure_ascii=False)
    try:
        print(text, file=STDOUT or sys.stdout, flush=True)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
