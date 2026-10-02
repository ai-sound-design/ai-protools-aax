#!/usr/bin/env python3
"""Hybrid mode: one generated sound per sound event, placed per scene on shared tracks.

The plugin's other generation mode returns one file for the whole selection.
This one asks a *hybrid* backend for the individual sound events in the
selected range and gets one audio file per event back, with the event's start
and end inside the range. The sounds of a scene go on at most "tracks_per_scene"
tracks (profile match block, default 8, the guideline of about eight tracks
per scene): sounds that do not overlap share a track, the tracks are named
after the scene ("Living room, day 1 (db)", "... 2 (gen)"), and every clip is
named after its event or recording.

Where the events come from is the backend's business: with
--use-memory-locations the memory locations inside the range are sent along
(the result of a spotting run, or markers the user set by hand) and scene
markers are the scenes; a clip without events is spotted by the backend and
scenes without markers are detected (--no-auto-spot skips such a clip instead).
Otherwise the backend finds everything itself, kept to the kinds in
--categories. --replace-earlier clears the range on every hybrid track
("(gen)", "(db)") first, so a repeated run does not pile clips on the old ones. With --use-database the backend also answers
library recordings that sound like each generated sound, as pieces in time
(stitched, at most "pieces_per_10s" of the profile's match block) and layers;
they replace the generated sound (which stays only where nothing matched), or
go on a track under it with --keep-generated. An ambience piece comes with
"ambience_handle_seconds" of its recording before and after the matched stretch;
the clip is trimmed to the event, so the handles stay in the file to be pulled
out with the Trim tool. --fade-handles gives the clip Pro Tools' own fades from
the batch-fades preset --fade-preset: the clip keeps --fade-seconds of the handle
outside the event on each side for the fade to run over, or, with --fade-inside,
ends at the event and the fade runs within it (as at a cut); --no-handles cuts
the piece to the event instead. With --scenes
the clips of the range are grouped into scenes first (one memory location per
scene). The contract is described in the backend repository (hybrid/README.md)
and in api/adapters.py.

Like spotting_client.py this script does the whole job: it reads the
selection, cuts each video clip beneath it, calls the backend, downloads the
sounds and places them. Progress, log and result go to files next to
--progress-file so the plugin can poll them.

    python hybrid_client.py --from-selection|--whole-track --progress-file <json> [--adapter hybrid.json]
                            [--prompt "..."] [--negative-prompt "..."] [--seed N]
                            [--use-memory-locations [--no-auto-spot]]
                            [--use-database [--keep-generated] [--no-handles | --fade-handles [--fade-preset NAME]]]
                            [--scenes]
                            [--estimate] [--resume] [--dry-run]

--whole-track runs over every clip on the video track, which for a whole film
takes hours. Three things make that workable: the progress file carries a
heartbeat (the plugin waits as long as the script is alive), --estimate answers
with the clip count and a rough duration before anything starts, and a journal
in the temp folder records every backend answer and every placed clip, so a
run that was stopped or crashed continues where it was with --resume. Scene
memory locations already in the session ("Scene 3: kitchen, night", from a
spotting run with Detect scenes) are used instead of detecting again.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spotting_client import (Progress, RunShare, cut_range, cut_segments, log, set_log_files, emit,   # noqa: E402  (shared plumbing)
                             place_markers, scene_markers)
from api.adapters import (hybrid_with_profile, load_profile, match_settings, scenes_with_profile,   # noqa: E402
                          selected_profile)
from ptsl_integration.clip_finish import finish_clip, seconds_to_tc   # noqa: E402


SCENE_MARK = re.compile(r"^Scene \d+\s*:")


def memory_locations_in(engine, seg: Dict, sample_rate: int) -> List[dict]:
    """The session's memory locations inside one segment, as events relative to its start."""
    events = []
    for m in engine.get_memory_locations():
        try:
            start = int(m.start_time) / sample_rate
            end = int(m.end_time) / sample_rate if str(m.end_time).strip() else start
        except (TypeError, ValueError):
            continue
        if not (seg["in_seconds"] <= start < seg["out_seconds"]):
            continue
        if SCENE_MARK.match(str(m.name or "")):
            continue   # a scene marker ("Scene 2: Kitchen"), not a sound event
        comment = str(getattr(m, "comments", "") or "")
        category = comment.split(":", 1)[0].strip().lower() if ":" in comment else ""
        events.append({
            "label": m.name,
            "description": comment or m.name,
            "category": category if category in ("dialogue", "foley", "sfx", "ambience", "music") else "sfx",
            "start_seconds": round(start - seg["in_seconds"], 3),
            "end_seconds": round(min(max(end, start), seg["out_seconds"]) - seg["in_seconds"], 3),
        })
    # A marker has no end of its own: let an event run to the next distinct start, else the range end.
    starts = sorted({e["start_seconds"] for e in events})
    for e in events:
        if e["end_seconds"] <= e["start_seconds"]:
            later = [s for s in starts if s > e["start_seconds"]]
            e["end_seconds"] = round(later[0] if later else seg["duration_seconds"], 3)
    # Clip-boundary markers of a spotting run describe the cut, not a sound
    events = [e for e in events if not e["description"].startswith("Clip ") and e["label"] != "end of spotting range"]
    return events


def track_names(engine_factory) -> set:
    with engine_factory() as engine:
        return {t.name for t in engine.track_list()}


def rename_track(engine_factory, current: str, wanted: str) -> str:
    """Rename a track, with a numeric suffix if the name is taken; returns the name used."""
    from ptsl import PTSL_pb2 as pt
    with engine_factory() as engine:
        taken = {t.name for t in engine.track_list()} - {current}
        name, n = wanted, 2
        while name in taken:
            name, n = f"{wanted} {n}", n + 1
        try:
            engine.client.run_command(pt.CId_RenameTargetTrack, {"current_name": current, "new_name": name})
            return name
        except Exception as exc:  # noqa: BLE001
            log(f"    track '{current}' not renamed: {str(exc)[:120]}")
            return current


def scene_markers_in(engine, segments: List[dict], sample_rate: int) -> Optional[dict]:
    """Scenes from memory locations named "Scene <n>: <name>" that cover every segment
    (a spotting run with Detect scenes, possibly corrected by hand). None if the
    session has none, or they leave a segment uncovered."""
    marks = []
    for m in engine.get_memory_locations():
        name = str(m.name or "")
        if not name.startswith("Scene "):
            continue
        try:
            start = int(m.start_time) / sample_rate
            end = int(m.end_time) / sample_rate if str(m.end_time).strip() else start
            head, _, title = name[6:].partition(":")
            index = int(head.strip())
        except (TypeError, ValueError):
            continue
        marks.append({"index": index, "name": title.strip() or f"Scene {index}", "start": start, "end": max(end, start),
                      "description": str(getattr(m, "comments", "") or "")})
    if not marks:
        return None
    clip_scenes = []
    for seg in segments:
        mid = (seg["in_seconds"] + seg["out_seconds"]) / 2
        hit = next((m for m in sorted(marks, key=lambda m: m["start"]) if m["start"] <= mid <= m["end"]), None)
        if hit is None:
            return None
        clip_scenes.append(hit["index"])
    scenes = []
    for m in sorted(marks, key=lambda m: m["start"]):
        covered = [i for i, k in enumerate(clip_scenes) if k == m["index"]]
        if covered:
            scenes.append({"index": m["index"], "name": m["name"], "description": m["description"],
                           "first_clip": covered[0], "last_clip": covered[-1]})
    return {"scenes": scenes, "clip_scenes": clip_scenes}


def journal_file(session: str, resolved: dict, adapter: str) -> Path:
    """One journal per session, range and backend, in the temp folder."""
    key = hashlib.sha1(f"{session}|{resolved['range']['in_time']}|{resolved['range']['out_time']}|{adapter}"
                       .encode("utf-8")).hexdigest()[:12]
    folder = Path(tempfile.gettempdir()) / "ai_sound_design_hybrid"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"journal_{key}.json"


def load_journal(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def save_journal(path: Path, journal: dict) -> None:
    try:
        path.write_text(json.dumps(journal), encoding="utf-8")
    except OSError as exc:
        log(f"journal not written: {exc}")


def files_present(payload: dict) -> bool:
    for sound in payload.get("sounds", []):
        if sound.get("path") and not Path(sound["path"]).exists():
            return False
        for piece in (sound.get("match") or {}).get("pieces") or []:
            if piece.get("path") and not Path(piece["path"]).exists():
                return False
    return True


def estimate_run(resolved: dict, args, scenes_known: bool, journal: dict) -> dict:
    """Rough numbers for the plugin's dialog before a long run: clips, seconds of
    video, a duration estimate from the stages, and whether a journal can be resumed."""
    segments = resolved["segments"]
    seconds = sum(float(s["duration_seconds"]) for s in segments)
    events = max(1, int(seconds / 8))                       # about one event per eight seconds
    est = 0.0
    if args.scenes and not scenes_known:
        est += 20.0 * max(0, len(segments) - 1) + 20.0 * max(1, len(segments) // 3)
    if not (args.use_memory_locations and args.no_auto_spot):
        est += seconds * 6.0                                # spotting: about a minute per ten seconds
    est += max(events, seconds / 11.0) * 35.0               # generation: about 35 s per 12 s window
    if args.use_database:
        est += events * 12.0                                # library search per event
    est += len(segments) * 8.0 + events * 4.0               # cutting, downloads, placement
    done = len(journal.get("segments", {}))
    return {"success": True, "estimate": True, "clips": len(segments), "video_seconds": round(seconds, 1),
            "events_estimated": events, "estimate_seconds": int(est), "scene_markers_present": scenes_known,
            "resumable": done > 0, "clips_done": done, "range": resolved["range"]}


def trim_head(path: str, seconds: float) -> str:
    """A copy of the WAV without its first `seconds` (a handle that would begin before
    the session start); the copy's path, or the original when trimming fails."""
    if seconds <= 0.0:
        return path
    try:
        import soundfile as sf
        src = Path(path)
        info = sf.info(str(src))
        data, rate = sf.read(str(src), always_2d=True)
        keep = data[int(round(seconds * rate)):]
        if len(keep) == 0:
            return path
        dst = src.with_name(f"{src.stem}_trim{src.suffix}")
        sf.write(str(dst), keep, rate, subtype=info.subtype)
        return str(dst)
    except Exception as exc:  # noqa: BLE001
        log(f"  could not trim {Path(path).name}: {exc}")
        return path


def clear_hybrid_range(engine_factory, segments: List[dict], fps: float) -> int:
    """Clear the range of every segment on the tracks of earlier hybrid runs (names ending
    in "(gen)" or "(db)"), so a repeated run replaces their clips instead of stacking new
    ones on top. Returns the number of tracks cleared. The edit selection has to be put
    on a track through a clip selection first, then narrowed to the range."""
    cleared = 0
    tracks = sorted(t for t in track_names(engine_factory) if t.endswith(" (gen)") or t.endswith(" (db)"))
    if not tracks:
        return 0
    try:
        with engine_factory() as engine:
            for track in tracks:
                for seg in segments:
                    engine.select_all_clips_on_track(track)
                    engine.set_timeline_selection(in_time=seg["in_time"], out_time=seg["out_time"])
                    engine.clear()
                cleared += 1
    except Exception as exc:  # noqa: BLE001
        log(f"clearing earlier hybrid clips failed on '{track}': {str(exc)[:160]}")
    log(f"{cleared} hybrid track(s) cleared in the range: {', '.join(tracks[:6])}{', ...' if len(tracks) > 6 else ''}")
    return cleared


def lane_name(scene_name: str, lane: int, kind: str) -> str:
    """Track name of a lane: "<scene> 3 (db)", within Pro Tools' 31 characters."""
    suffix = f" {lane} ({kind})"
    return f"{scene_name[:31 - len(suffix)].rstrip()}{suffix}"


def assign_lanes(items: List[dict], budget: int) -> Tuple[int, List[dict]]:
    """Give the items of one scene their lanes (tracks). An item is a generated sound or
    one layer of library pieces, with its span on the timeline. Every sound gets a lane
    of its own while the budget allows (rain followed by an engine on one track would
    read as one sound with a gap); pieces of the same sound share theirs. Only when the
    budget is used up do different sounds share a lane where they do not overlap, a
    lane of the same category first. Items that must be placed (priority 0: the generated sound
    and the first library layer) always get a lane, beyond the
    budget if that many overlap; further layers (priority = layer) only where a lane
    within the budget is free, best similarity first. The budget counts per kind, so
    with the generated sounds kept each event has both. A lane holds one kind only,
    "gen" or "db": mono and stereo clips cannot share a track, and the track name
    says what is on it. Returns the number of lanes used and the items left out."""
    lanes: List[dict] = []

    def free(lane: dict, item: dict) -> bool:
        return lane["kind"] == item["kind"] and all(item["end"] <= s or item["start"] >= e
                                                    for s, e in lane["intervals"])

    def label(item: dict) -> str:
        return str((item.get("sound") or {}).get("label") or item.get("label") or "").strip().lower()

    def room(item: dict) -> bool:
        # The budget counts per kind: with the generated sounds kept, they and the
        # library pieces each get `budget` tracks, instead of the generated ones
        # taking all of them and every library piece being left out.
        return sum(1 for l in lanes if l["kind"] == item["kind"]) < budget

    def pick(item: dict) -> Optional[int]:
        fitting = [i for i, l in enumerate(lanes) if free(l, item)]
        same = [i for i in fitting if label(item) and label(item) in lanes[i]["labels"]]
        if same:
            return same[0]
        if room(item):
            return None   # a new lane of its own
        related = [i for i in fitting if item.get("category") and item.get("category") in lanes[i]["categories"]]
        return (related or fitting or [None])[0]

    dropped: List[dict] = []
    order = sorted(items, key=lambda it: (it["priority"], -float(it.get("similarity", 1.0)),
                                          0 if it.get("category") == "ambience" else 1, it["start"]))
    for item in order:
        lane = pick(item)
        if lane is None:
            if room(item) or item["priority"] == 0:
                lanes.append({"kind": item["kind"], "intervals": [], "labels": set(), "categories": set()})
                lane = len(lanes) - 1
            else:
                item["lane"] = None
                dropped.append(item)
                continue
        lanes[lane]["intervals"].append((item["start"], item["end"]))
        lanes[lane]["labels"].add(label(item))
        lanes[lane]["categories"].add(item.get("category"))
        item["lane"] = lane + 1
    # Track order: with the generated sounds kept, each generated lane is followed by the
    # library lane of the same sound, so the two versions of an event lie one above the
    # other (instead of all generated tracks first and all library tracks after them).
    order_of: List[int] = []
    for i, l in enumerate(lanes):
        if l["kind"] != "gen":
            continue
        order_of.append(i)
        for j, other in enumerate(lanes):
            if other["kind"] != "gen" and j not in order_of and other["labels"] & l["labels"]:
                order_of.append(j)
    order_of += [j for j in range(len(lanes)) if j not in order_of]
    number = {old: new + 1 for new, old in enumerate(order_of)}
    for item in items:
        if item.get("lane"):
            item["lane"] = number[item["lane"] - 1]
    return len(lanes), dropped


def place_lanes(scene_name: str, items: List[dict], args, engine_factory, import_audio,
                already: Optional[set] = None, on_placed=None) -> Tuple[int, int]:
    """Place the items of one scene on their lanes. The first clip of a lane creates the
    track (Pro Tools names it after the clip, then it is renamed), the rest are spotted
    onto it; a track that already has the lane's name is reused. Clips whose id is in
    `already` (the journal of an earlier run) count as placed without importing again;
    `on_placed(clip)` is told about every clip that went in. Returns (clips placed,
    tracks used)."""
    placed = 0
    used: set = set()
    existing = track_names(engine_factory)
    by_lane: Dict[Tuple[int, str], List[dict]] = {}
    for item in items:
        if item.get("lane"):
            by_lane.setdefault((item["lane"], item["kind"]), []).append(item)
    for (lane, kind), lane_items in sorted(by_lane.items()):
        name = lane_name(scene_name, lane, kind)
        track: Optional[str] = name if name in existing else None
        clips = sorted((c for item in lane_items for c in item["clips"]), key=lambda c: c["start"])
        for c in clips:
            if already and c.get("id") in already:
                c["placed"] = True
                placed += 1
                used.add(name)
                continue
            if track is None:
                before = track_names(engine_factory)
                ok = import_audio(c["path"], timecode=c["tc"], clip_name=c["name"],
                                  host=args.ptsl_host, port=args.ptsl_port)
                # Pro Tools lists the new track a moment after the import answers; asking
                # too early found nothing, and the lane kept the clip's name
                new = track_names(engine_factory) - before
                for _ in range(15):
                    if new:
                        break
                    time.sleep(0.2)
                    new = track_names(engine_factory) - before
                if len(new) == 1:
                    track = rename_track(engine_factory, next(iter(new)), name)
                    existing.add(track)
                elif ok:
                    log(f"    new track for {c['name']} not found after the import; lane name not applied")
            else:
                ok = import_audio(c["path"], timecode=c["tc"], clip_name=c["name"], track_name=track,
                                  host=args.ptsl_host, port=args.ptsl_port)
            c["placed"] = bool(ok)
            placed += 1 if ok else 0
            if ok and (c.get("before") or c.get("after")):
                # The handles stay in the file: the clip is trimmed to the event, and faded
                # by Pro Tools when the user asked for it
                preset = getattr(args, "fade_preset", "") if getattr(args, "fade_handles", False) else None
                c["fade_wanted"] = bool(preset)
                c["trimmed"], c["faded"] = finish_clip(engine_factory, track or name, c["event_start"], c["event_end"],
                                                       c["before"], c["after"], c["fps"], preset,
                                                       max(0.0, float(getattr(args, "fade_seconds", 1.0) or 0.0)),
                                                       bool(getattr(args, "fade_inside", False)), log=log)
            if ok and on_placed:
                on_placed(c)
            log(f"    {c['tc']}  {track or name}: {c['name']}"
                + (f"  (sim {c['similarity']:.2f})" if c.get("similarity") is not None else "")
                + (f"  handles {c['before']:.0f}+{c['after']:.0f} s" if c.get("before") or c.get("after") else "")
                + ("  trimmed" if c.get("trimmed") else "")
                + ("  faded" if c.get("faded") else "")
                + ("" if ok else "  (import failed)"))
        used.add(name)
    return placed, len(used)


def run(args, progress: Progress, engine_factory) -> dict:
    from ptsl_integration.video_segments import resolve_video_segments
    from ptsl_integration.ptsl_client import import_audio_to_pro_tools

    profile = load_profile(args.adapter) if args.adapter else selected_profile("hybrid")
    if profile is None:
        raise RuntimeError("no hybrid backend: select an adapter profile of kind 'hybrid' in the plugin's Settings")
    log(f"Backend: {profile.get('name')} ({profile.get('file')})")
    match = match_settings(profile) if args.use_database else None
    replace = bool(match) and not args.keep_generated
    if match:
        if args.no_handles:
            match["ambience_handle_seconds"] = 0
        log(f"Library match: up to {match['pieces_per_10s']} pieces per 10 s, {match['layers']} layer(s), "
            f"min similarity {float(match.get('min_similarity', 0)):.2f}, "
            f"ambience handles {float(match.get('ambience_handle_seconds', 0)):.0f} s"
            + (", replacing the generated sounds" if replace else ", generated sounds kept"))

    progress.update(0, 0, "", "reading selection")
    with engine_factory() as engine:
        resolved = resolve_video_segments(engine, whole_track=args.whole_track,
                                          track_name=getattr(args, "video_track", None) or None, log=log)
        if not resolved.get("success"):
            raise RuntimeError(resolved.get("error", "could not resolve the video range"))
        sample_rate = resolved.get("sample_rate") or engine.session_sample_rate() or 48000
        segments = resolved["segments"]
        session = str(engine.session_name() or "session")
        markers = {seg["index"]: memory_locations_in(engine, seg, sample_rate) for seg in segments} \
            if args.use_memory_locations else {}
        known_scenes = scene_markers_in(engine, segments, sample_rate) \
            if args.scenes and args.use_memory_locations else None
    for warning in resolved.get("warnings", []):
        log(f"warning: {warning}")
    fps = resolved["fps"]
    total = len(segments)

    # The journal of this range: every backend answer and every placed clip, so that
    # a stopped run continues (--resume) instead of generating and placing twice.
    journal_path = journal_file(session, resolved, str(profile.get("file")))
    journal = load_journal(journal_path) if args.resume else {}
    journal.setdefault("segments", {})
    journal.setdefault("placed", [])
    if args.estimate:
        progress.update(0, 0, "", "done", done=True)
        return estimate_run(resolved, args, known_scenes is not None, journal)
    if args.resume and journal["segments"]:
        log(f"Resuming: {len(journal['segments'])} clip(s) answered before, {len(journal['placed'])} clip(s) placed")
    elif not args.resume:
        journal_path.unlink(missing_ok=True)
    already_placed = set(journal["placed"])

    # Scenes: which clips belong together; one memory location per scene, and every
    # sound remembers its scene for the placement.
    cuts: Dict[int, Path] = {}
    scenes: List[dict] = []
    scene_of: Dict[int, int] = {}
    scene_markers_created = 0
    # The bar's share of the run: scenes (when detected), one unit per clip, a little for placing
    share = RunShare(total, scenes=bool(args.scenes and known_scenes is None), events=True, placing=0.1)
    if args.scenes and known_scenes is not None:
        # Scene memory locations already in the session cover the range: no detection.
        scenes = known_scenes["scenes"]
        scene_of = {seg["index"]: int(k) for seg, k in zip(segments, known_scenes["clip_scenes"])}
        log(f"{len(scenes)} scene(s) from the session's memory locations: "
            + "; ".join(f"{s.get('index')}: {s.get('name')}" for s in scenes))
    elif args.scenes:
        cuts = cut_segments(segments, progress, overall_of=lambda i: share.scenes(0.05 * i / total))
        try:
            progress.update(0, total, "", "detecting scenes", overall=share.scenes(0.05))
            found = scenes_with_profile(profile, [(str(cuts[s["index"]]), s.get("clip_name") or Path(s["video_path"]).stem)
                                                  for s in segments], log=log,
                                        on_progress=lambda p: progress.update(0, total, "", "detecting scenes",
                                                                              fraction=p.get("fraction"),
                                                                              detail=p.get("detail", ""),
                                                                              overall=share.scenes(max(0.05, p.get("fraction")))))
            scenes = found.get("scenes", [])
            scene_of = {seg["index"]: int(k) for seg, k in zip(segments, found.get("clip_scenes", []))}
            log(f"{len(scenes)} scene(s): " + "; ".join(f"{s.get('index')}: {s.get('name')}" for s in scenes))
            marks = scene_markers(scenes, segments)
            if marks and not args.dry_run:
                with engine_factory() as engine:
                    scene_markers_created = place_markers(engine, marks, fps, None).get("created", 0)
        except Exception as exc:  # noqa: BLE001  (scenes are a courtesy; the sounds still come)
            log(f"scene detection failed: {exc}")
    clip_seconds: List[float] = []      # time per answered clip, for the estimate of what is left

    out_dir = Path(tempfile.gettempdir()) / "ai_sound_design_hybrid"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_sounds: List[dict] = []
    per_clip: List[dict] = []
    placed = 0
    db_pieces = db_placed = 0
    markers_created = 0
    model: Optional[str] = None
    # Everything to place, per scene; placed at the end so a scene's tracks are shared
    items: Dict[int, List[dict]] = {}
    scene_names = {int(sc.get("index", 0)): str(sc.get("name") or f"Scene {sc.get('index')}") for sc in scenes}

    for i, seg in enumerate(segments, start=1):
        clip = seg.get("clip_name") or Path(seg["video_path"]).stem
        events = markers.get(seg["index"], [])
        if args.use_memory_locations:
            log(f"[{i}/{total}] {clip}: {len(events)} memory location(s) in range")
            if not events and args.no_auto_spot:
                log(f"[{i}/{total}] {clip}: skipped (no memory locations, automatic spotting is off)")
                per_clip.append({"clip": clip, "in_time": seg["in_time"], "sounds": 0, "skipped": True})
                continue
            if not events:
                log(f"[{i}/{total}] {clip}: the backend spots the range first")
                events = None
        else:
            events = None
        eta = (sum(clip_seconds) / len(clip_seconds)) * (total - i + 1) if clip_seconds else None
        earlier = journal["segments"].get(str(seg["index"]))
        if earlier and files_present(earlier):
            log(f"[{i}/{total}] {clip}: answered in an earlier run, reused")
            result = earlier
            cuts.pop(seg["index"], None)
        else:
            began = time.time()
            progress.update(i, total, clip, "cutting", eta_seconds=eta, overall=share.clip(i))
            cut = cuts.pop(seg["index"], None) or cut_range(Path(seg["video_path"]), seg["source_start_seconds"],
                                                            seg["source_end_seconds"])
            try:
                progress.update(i, total, clip, "generating", eta_seconds=eta, overall=share.clip(i))
                result = hybrid_with_profile(
                    profile, video_path=str(cut), start_timecode=seg["in_time"], fps=fps,
                    prompt=args.prompt or "", negative_prompt=args.negative_prompt or "", seed=args.seed,
                    events=events,
                    output_dir=str(out_dir), log=log, match=match,
                    categories=(getattr(args, "categories", "") or "") if events is None else None,
                    on_progress=lambda p, i=i, clip=clip, eta=eta: progress.update(
                        i, total, clip, "generating", fraction=p.get("fraction"), detail=p.get("detail", ""),
                        eta_seconds=eta, overall=share.clip(i, p.get("fraction"))))
            except Exception as exc:  # one failing clip must not lose the others
                log(f"[{i}/{total}] {clip} failed: {exc}")
                per_clip.append({"clip": clip, "in_time": seg["in_time"], "sounds": 0, "error": str(exc)})
                continue
            finally:
                cut.unlink(missing_ok=True)
            clip_seconds.append(time.time() - began)
            journal["segments"][str(seg["index"])] = result
            save_journal(journal_path, journal)

        sounds = result.get("sounds", [])
        model = result.get("model") or model
        log(f"[{i}/{total}] {clip}: {len(sounds)} sound(s) from the backend"
            + (f" ({result.get('events_source')})" if result.get("events_source") else ""))
        progress.update(i, total, clip, "placing", overall=share.clip(i, 1.0))
        if result.get("events_source") == "spotting" and sounds and not args.dry_run:
            # The backend found the events itself: write them into the session as memory
            # locations too, as a spotting run would, so the user sees what was found and
            # can rerun with them edited.
            events = [{"label": s.get("label") or f"sound {n}", "category": s.get("category", "sfx"),
                       "description": s.get("description", ""),
                       "comment": f"{s.get('category', 'sfx')}: {s.get('description', '')} (hybrid run)",
                       "start_timecode": seconds_to_tc(seg["in_seconds"] + float(s.get("start_seconds", 0.0)), fps),
                       "end_timecode": seconds_to_tc(seg["in_seconds"] + float(s.get("end_seconds", 0.0)), fps)}
                      for n, s in enumerate(sounds, start=1)]
            try:
                with engine_factory() as engine:
                    outcome = place_markers(engine, events, fps, None)
                markers_created += outcome.get("created", 0)
                log(f"[{i}/{total}] {clip}: {outcome.get('created', 0)} memory location(s) placed for the events")
            except Exception as exc:  # noqa: BLE001  (markers are a courtesy; the sounds still go in)
                log(f"[{i}/{total}] {clip}: memory locations not placed: {exc}")
        for n, sound in enumerate(sounds, start=1):
            start_abs = seg["in_seconds"] + float(sound.get("start_seconds", 0.0))
            end_abs = seg["in_seconds"] + float(sound.get("end_seconds", sound.get("start_seconds", 0.0)))
            start_tc = seconds_to_tc(start_abs, fps)
            sound.update({"clip": clip, "timecode": start_tc, "scene": scene_of.get(seg["index"], 0)})
            all_sounds.append(sound)
            pieces = [p for p in ((sound.get("match") or {}).get("pieces") or []) if p.get("path")]
            db_pieces += len(pieces)
            if (sound.get("match") or {}).get("error"):
                log(f"  {sound.get('label')}: library match failed: {sound['match']['error']}")
            if args.dry_run or not sound.get("path"):
                continue
            name = (sound.get("label") or f"sound {n}")[:31]
            scene_items = items.setdefault(sound["scene"], [])
            # The generated sound stays out when library pieces replace it (unless nothing
            # matched); with --keep-generated it goes on a lane of its own kind.
            if not (replace and pieces):
                scene_items.append({"kind": "gen", "priority": 0, "category": sound.get("category"),
                                    "start": start_abs, "end": max(end_abs, start_abs + 0.1), "sound": sound,
                                    "clips": [{"path": sound["path"], "start": start_abs, "tc": start_tc,
                                               "name": name, "sound": sound, "id": f"{seg['index']}:{n}:gen"}]})
            for layer in sorted({int(p.get("layer", 1)) for p in pieces}):
                clips = []
                for p in sorted((p for p in pieces if int(p.get("layer", 1)) == layer), key=lambda p: p["start_seconds"]):
                    before = float(p.get("handle_before_seconds", 0.0) or 0.0)
                    after = float(p.get("handle_after_seconds", 0.0) or 0.0)
                    at = start_abs + float(p["start_seconds"])
                    trim = max(0.0, before - at)   # a handle that would begin before the session start
                    if trim > 0.0:
                        log(f"  handle before {name} cut from {before:.1f} to {at:.1f} s (session start)")
                        before = at
                    path = trim_head(p["path"], trim)
                    clips.append({"path": path, "start": at - before, "end": at + float(p["length_seconds"]) + after,
                                  "tc": seconds_to_tc(at - before, fps), "before": before, "after": after,
                                  "event_start": at, "event_end": at + float(p["length_seconds"]), "fps": fps,
                                  "id": f"{seg['index']}:{n}:db:{layer}:{len(clips) + 1}",
                                  "name": (p.get("description") or p.get("external_id") or "library sound")[:31],
                                  "similarity": float(p.get("similarity", 0.0)), "piece": p})
                scene_items.append({"kind": "db", "priority": 0 if layer == 1 else layer,
                                    "category": sound.get("category"), "label": name, "layer": layer,
                                    "similarity": sum(c["similarity"] for c in clips) / len(clips),
                                    "start": min(c["start"] for c in clips), "end": max(c["end"] for c in clips),
                                    "sound": sound, "clips": clips})
        per_clip.append({"clip": clip, "in_time": seg["in_time"], "sounds": len(sounds)})

    for path in cuts.values():
        path.unlink(missing_ok=True)

    # Placement: per scene, at most `tracks_per_scene` tracks (a guideline: the sounds
    # that must be there open more lanes if they overlap that much), non-overlapping
    # clips sharing a track, extra library layers only where a lane is free.
    budget = max(1, int(match_settings(profile).get("tracks_per_scene", 8)))
    tracks_used = dropped_layers = 0
    tracks_cleared = 0
    if getattr(args, "replace_earlier", False) and items and not args.dry_run:
        progress.update(total, total, "", "placing", detail="clearing earlier hybrid clips",
                        overall=share.placing(0.0))
        tracks_cleared = clear_hybrid_range(engine_factory, segments, fps)
    handles_trimmed = fades_created = fades_wanted = 0
    scene_count = len(items)
    for k, (scene_index, scene_items) in enumerate(sorted(items.items()), start=1):
        scene_name = scene_names.get(scene_index, "Hybrid")
        progress.update(total, total, scene_name, "placing", detail=f"scene {k} of {scene_count}",
                        overall=share.placing((k - 1) / scene_count))
        lanes, dropped = assign_lanes(scene_items, budget)
        dropped_layers += len(dropped)
        log(f"Scene {scene_index or '-'} '{scene_name}': {len(scene_items)} item(s) on {lanes} track(s), "
            f"budget {budget}" + (f", {len(dropped)} extra layer(s) left out" if dropped else "")
            + (f"  (over budget: {lanes - budget} more tracks for sounds that had to be placed)" if lanes > budget else ""))
        for item in dropped:
            log(f"    left out: {item.get('label')} library layer {item.get('layer')} "
                f"(sim {float(item.get('similarity', 0)):.2f}), no free track within the budget")
        def remember(c, k=k):
            journal["placed"].append(c["id"])
            save_journal(journal_path, journal)
            progress.update(total, total, scene_name, "placing",
                            detail=f"scene {k} of {scene_count}: {len(journal['placed'])} clip(s) placed",
                            overall=share.placing((k - 0.5) / scene_count))

        got, used = place_lanes(scene_name, scene_items, args, engine_factory, import_audio_to_pro_tools,
                                already=already_placed, on_placed=remember)
        tracks_used += used
        for item in scene_items:
            for c in item["clips"]:
                handles_trimmed += 1 if c.get("trimmed") else 0
                fades_created += 1 if c.get("faded") else 0
                fades_wanted += 1 if c.get("fade_wanted") else 0
                if c.get("placed") and item["kind"] == "gen":
                    item["sound"]["placed"] = True
                if c.get("placed") and item["kind"] == "db":
                    c["piece"]["placed"] = True
                    db_placed += 1
                    if item["priority"] == 0:
                        item["sound"]["placed"] = True
    placed = sum(1 for snd in all_sounds if snd.get("placed"))
    if fades_wanted and segments and not args.dry_run:
        # The last fade's edit selection would stay on its track and look like part of
        # the clip; a cursor at the range's start leaves nothing selected.
        try:
            with engine_factory() as engine:
                at = segments[0]["in_time"]
                engine.set_timeline_selection(in_time=at, out_time=at)
        except Exception:  # noqa: BLE001  (only cosmetic)
            pass

    progress.update(total, total, "", "done", done=True)
    return {"success": placed > 0 or (args.dry_run and bool(all_sounds)),
            "sounds": all_sounds, "placed": placed, "segments": total, "clips": per_clip,
            "db_pieces": db_pieces, "db_placed": db_placed, "replaced": replace,
            "tracks_used": tracks_used, "tracks_per_scene": budget, "dropped_layers": dropped_layers,
            "tracks_cleared": tracks_cleared,
            "handles_trimmed": handles_trimmed, "fades_created": fades_created, "fades_wanted": fades_wanted,
            "fade_preset": getattr(args, "fade_preset", ""),
            "markers_created": markers_created, "scenes": scenes, "scene_markers": scene_markers_created,
            "model": model, "range": resolved["range"], "warnings": resolved.get("warnings", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-selection", action="store_true", help="the video clips beneath the timeline selection")
    source.add_argument("--whole-track", action="store_true", help="every clip on the video track (a whole film)")
    parser.add_argument("--adapter", help="hybrid profile (file name in the adapters folder); default: the selected one")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--seed", type=int, default=-1, help="-1 (default) draws a random seed and logs it")
    parser.add_argument("--use-memory-locations", action="store_true",
                        help="send the memory locations inside the range as the sound events")
    parser.add_argument("--no-auto-spot", action="store_true",
                        help="with --use-memory-locations: skip a clip that has none instead of letting the backend spot it")
    parser.add_argument("--categories", default="",
                        help="comma-separated kinds of events the backend's spotting keeps (dialogue, foley, sfx, "
                             "ambience, music); clips with memory locations are not affected")
    parser.add_argument("--replace-earlier", action="store_true",
                        help="clear the range on the tracks of earlier hybrid runs ('(gen)', '(db)') before placing")
    parser.add_argument("--use-database", action="store_true",
                        help="also place library recordings that sound like each generated sound (profile 'match' block)")
    parser.add_argument("--video-track", default=None,
                        help="the video track to map the range onto (default: the topmost, or the one the selection lies on)")
    parser.add_argument("--keep-generated", action="store_true",
                        help="with --use-database: place the generated sound too, on its own track above the pieces")
    parser.add_argument("--no-handles", action="store_true",
                        help="with --use-database: cut ambience pieces to the event instead of keeping the "
                             "profile's ambience_handle_seconds before and after for fades")
    parser.add_argument("--fade-handles", action="store_true",
                        help="with --use-database: give an ambience piece Pro Tools' own fades at both ends, "
                             "from the batch-fades preset --fade-preset")
    parser.add_argument("--fade-preset", default="AI Sound Design",
                        help="the Pro Tools batch-fades preset used by --fade-handles (default: AI Sound Design)")
    parser.add_argument("--fade-seconds", type=float, default=1.0,
                        help="with --fade-handles: how much of its handle a clip keeps outside the event on each "
                             "side, for the fade to run over (the preset's fade length; default 1)")
    parser.add_argument("--fade-inside", action="store_true",
                        help="with --fade-handles: the clip ends at the event and the fade runs within it "
                             "(as at a cut) instead of over the handle outside")
    parser.add_argument("--scenes", action="store_true",
                        help="group the clips of the range into scenes first and place one memory location per scene")
    parser.add_argument("--estimate", action="store_true",
                        help="only count the clips and estimate the duration; answers with the numbers, runs nothing")
    parser.add_argument("--resume", action="store_true",
                        help="continue the journal of an earlier run over the same range: clips already answered "
                             "by the backend and clips already placed are not done again")
    parser.add_argument("--progress-file", type=Path, help="JSON file to keep updated with progress")
    parser.add_argument("--ptsl-host", default="localhost")
    parser.add_argument("--ptsl-port", type=int, default=31416)
    parser.add_argument("--dry-run", action="store_true", help="generate and download, place nothing")
    args = parser.parse_args()

    progress = Progress(args.progress_file)
    set_log_files(args.progress_file)

    def engine_factory():
        from ptsl import open_engine
        return open_engine(company_name="AI Sound Design", application_name="Hybrid",
                           address=f"{args.ptsl_host}:{args.ptsl_port}")

    try:
        output = run(args, progress, engine_factory)
        emit(output)
        return 0 if output["success"] else 1
    except Exception as exc:
        progress.update(0, 0, "", f"failed: {exc}", done=True)
        emit({"success": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
