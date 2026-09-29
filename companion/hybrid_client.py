#!/usr/bin/env python3
"""Hybrid mode: one generated sound per sound event, each on its own track.

The plugin's other generation mode returns one file for the whole selection.
This one asks a *hybrid* backend for the individual sound events in the
selected range and gets one audio file per event back, with the event's start
and end inside the range. Each file is placed on a new track, named after the
event, at the event's position on the timeline.

Where the events come from is the backend's business: with
--use-memory-locations the memory locations inside the range are sent along
(the result of a spotting run, or markers the user set by hand), otherwise the
backend finds the events itself. With --use-database the backend also answers
library recordings that sound like each generated sound, as pieces in time
(stitched, at most "pieces_per_10s" of the profile's match block) and layers;
they go on a track under the generated one, or instead of it with
--replace-generated. The contract is described in the backend repository
(hybrid/README.md) and in api/adapters.py.

Like spotting_client.py this script does the whole job: it reads the
selection, cuts each video clip beneath it, calls the backend, downloads the
sounds and places them. Progress, log and result go to files next to
--progress-file so the plugin can poll them.

    python hybrid_client.py --from-selection --progress-file <json> [--adapter hybrid.json]
                            [--prompt "..."] [--negative-prompt "..."] [--seed N]
                            [--use-memory-locations [--no-auto-spot]]
                            [--use-database [--replace-generated]] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spotting_client import Progress, cut_range, log, set_log_files, emit, place_markers   # noqa: E402  (shared plumbing)
from api.adapters import hybrid_with_profile, load_profile, match_settings, selected_profile  # noqa: E402


def seconds_to_tc(seconds: float, fps: float) -> str:
    frames_total = int(round(seconds * fps))
    frames = frames_total % int(round(fps))
    whole = frames_total // int(round(fps))
    return f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d}:{frames:02d}"


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


def place_pieces(pieces: List[dict], label: str, base_seconds: float, fps: float, args, engine_factory,
                 import_audio) -> int:
    """Library pieces onto one track per layer ("<label> (db)", "<label> (db 2)", ...):
    the first piece of a layer creates the track (named after the piece, then renamed),
    the rest are spotted onto it. Every clip is named after its recording. The backend
    delivers all pieces with the same channel count, or they could not share a track."""
    placed = 0
    for layer in sorted({int(p.get("layer", 1)) for p in pieces}):
        track_label = f"{label} (db)" if layer == 1 else f"{label} (db {layer})"
        track: Optional[str] = None
        for piece in sorted((p for p in pieces if int(p.get("layer", 1)) == layer), key=lambda p: p["start_seconds"]):
            if not piece.get("path"):
                continue
            tc = seconds_to_tc(base_seconds + float(piece["start_seconds"]), fps)
            clip_name = (piece.get("description") or piece.get("external_id") or "library sound")[:31]
            if track is None:
                before = track_names(engine_factory)
                ok = import_audio(piece["path"], timecode=tc, clip_name=clip_name,
                                  host=args.ptsl_host, port=args.ptsl_port)
                new = track_names(engine_factory) - before
                track = rename_track(engine_factory, next(iter(new)), track_label[:31]) if len(new) == 1 else None
            else:
                ok = import_audio(piece["path"], timecode=tc, clip_name=clip_name, track_name=track,
                                  host=args.ptsl_host, port=args.ptsl_port)
            piece["placed"] = bool(ok)
            placed += 1 if ok else 0
            log(f"    {tc}  {track_label}: {clip_name}  (sim {float(piece.get('similarity', 0)):.2f})"
                + ("" if ok else "  (import failed)"))
    return placed


def run(args, progress: Progress, engine_factory) -> dict:
    from ptsl_integration.video_segments import resolve_video_segments
    from ptsl_integration.ptsl_client import import_audio_to_pro_tools

    profile = load_profile(args.adapter) if args.adapter else selected_profile("hybrid")
    if profile is None:
        raise RuntimeError("no hybrid backend: select an adapter profile of kind 'hybrid' in the plugin's Settings")
    log(f"Backend: {profile.get('name')} ({profile.get('file')})")
    match = match_settings(profile) if args.use_database else None
    if match:
        log(f"Library match: up to {match['pieces_per_10s']} pieces per 10 s, {match['layers']} layer(s), "
            f"min similarity {float(match.get('min_similarity', 0)):.2f}"
            + (", replacing the generated sounds" if args.replace_generated else ""))

    progress.update(0, 0, "", "reading selection")
    with engine_factory() as engine:
        resolved = resolve_video_segments(engine, whole_track=False, log=log)
        if not resolved.get("success"):
            raise RuntimeError(resolved.get("error", "could not resolve the video range"))
        sample_rate = resolved.get("sample_rate") or engine.session_sample_rate() or 48000
        segments = resolved["segments"]
        markers = {seg["index"]: memory_locations_in(engine, seg, sample_rate) for seg in segments} \
            if args.use_memory_locations else {}
    for warning in resolved.get("warnings", []):
        log(f"warning: {warning}")
    fps = resolved["fps"]
    total = len(segments)

    out_dir = Path(tempfile.gettempdir()) / "ai_sound_design_hybrid"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_sounds: List[dict] = []
    per_clip: List[dict] = []
    placed = 0
    db_pieces = db_placed = 0
    markers_created = 0
    model: Optional[str] = None

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
        progress.update(i, total, clip, "cutting")
        cut = cut_range(Path(seg["video_path"]), seg["source_start_seconds"], seg["source_end_seconds"])
        try:
            progress.update(i, total, clip, "generating")
            result = hybrid_with_profile(
                profile, video_path=str(cut), start_timecode=seg["in_time"], fps=fps,
                prompt=args.prompt or "", negative_prompt=args.negative_prompt or "", seed=args.seed,
                events=events,
                output_dir=str(out_dir), log=log, match=match,
                on_progress=lambda p, i=i, clip=clip: progress.update(
                    i, total, clip, "generating", fraction=p.get("fraction"), detail=p.get("detail", "")))
        except Exception as exc:  # one failing clip must not lose the others
            log(f"[{i}/{total}] {clip} failed: {exc}")
            per_clip.append({"clip": clip, "in_time": seg["in_time"], "sounds": 0, "error": str(exc)})
            continue
        finally:
            cut.unlink(missing_ok=True)

        sounds = result.get("sounds", [])
        model = result.get("model") or model
        log(f"[{i}/{total}] {clip}: {len(sounds)} sound(s) from the backend"
            + (f" ({result.get('events_source')})" if result.get("events_source") else ""))
        progress.update(i, total, clip, "placing")
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
            start_tc = seconds_to_tc(seg["in_seconds"] + float(sound.get("start_seconds", 0.0)), fps)
            sound.update({"clip": clip, "timecode": start_tc})
            all_sounds.append(sound)
            pieces = [p for p in ((sound.get("match") or {}).get("pieces") or []) if p.get("path")]
            db_pieces += len(pieces)
            if (sound.get("match") or {}).get("error"):
                log(f"  {sound.get('label')}: library match failed: {sound['match']['error']}")
            if args.dry_run or not sound.get("path"):
                continue
            name = (sound.get("label") or f"sound {n}")[:31]
            # With --replace-generated the generated sound stays out, unless nothing matched.
            if not (args.replace_generated and pieces):
                before = track_names(engine_factory) if pieces else set()
                ok = import_audio_to_pro_tools(sound["path"], timecode=start_tc, clip_name=name,
                                               host=args.ptsl_host, port=args.ptsl_port)
                sound["placed"] = bool(ok)
                placed += 1 if ok else 0
                log(f"  {start_tc}  {name}" + ("" if ok else "  (import failed)"))
                if ok and pieces:
                    # Next to a "(db)" track the generated one says what it is, too
                    new = track_names(engine_factory) - before
                    if len(new) == 1:
                        rename_track(engine_factory, next(iter(new)), f"{name} (gen)"[:31])
            if pieces:
                got = place_pieces(pieces, name, seg["in_seconds"] + float(sound.get("start_seconds", 0.0)),
                                   fps, args, engine_factory, import_audio_to_pro_tools)
                db_placed += got
                placed += 1 if (got and args.replace_generated) else 0
        per_clip.append({"clip": clip, "in_time": seg["in_time"], "sounds": len(sounds)})

    progress.update(total, total, "", "done", done=True)
    return {"success": placed > 0 or (args.dry_run and bool(all_sounds)),
            "sounds": all_sounds, "placed": placed, "segments": total, "clips": per_clip,
            "db_pieces": db_pieces, "db_placed": db_placed, "replaced": bool(args.replace_generated and match),
            "markers_created": markers_created,
            "model": model, "range": resolved["range"], "warnings": resolved.get("warnings", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-selection", action="store_true", required=True,
                        help="the video clips beneath the timeline selection")
    parser.add_argument("--adapter", help="hybrid profile (file name in the adapters folder); default: the selected one")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--seed", type=int, default=-1, help="-1 (default) draws a random seed and logs it")
    parser.add_argument("--use-memory-locations", action="store_true",
                        help="send the memory locations inside the range as the sound events")
    parser.add_argument("--no-auto-spot", action="store_true",
                        help="with --use-memory-locations: skip a clip that has none instead of letting the backend spot it")
    parser.add_argument("--use-database", action="store_true",
                        help="also place library recordings that sound like each generated sound (profile 'match' block)")
    parser.add_argument("--replace-generated", action="store_true",
                        help="with --use-database: place only the library pieces, not the generated sound")
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
