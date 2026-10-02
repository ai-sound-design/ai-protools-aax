"""Adapter profiles: one JSON file per backend, in the user's config folder.

The plugin does not know MMAudio, HunyuanVideo-Foley or any other model. It knows
three kinds of service (generation, search, spotting) and, for each kind, the
profile the user selected. A profile says where the service runs and, for
generation, how the request is built and how the answer is read. Anything that
sits behind such a description can be used without touching the plugin.

    %APPDATA%\\AI Sound Design\\adapters\\mmaudio.json      (Windows)
    ~/Library/AI Sound Design/adapters/mmaudio.json          (macOS)

Profile (generation):
    {
      "schema": 1,
      "name": "MMAudio (local)",
      "kind": "generation",
      "base_url": "http://localhost:8000",
      "base_url_tunnel": "",
      "health": "/health",
      "protocol": "multipart-generate",
      "request": {
        "endpoint": "/generate",
        "video_field": "video",
        "fields": { "prompt": "{prompt}", "negative_prompt": "{negative_prompt}",
                    "seed": "{seed}", "duration": "{duration?}", "model_name": "large_44k_v2" }
      },
      "response": { "kind": "audio_file" },
      "supports": ["negative_prompt", "seed", "duration", "text_only"],
      "duration": { "min": 4, "max": 12, "default": 8 },
      "timeout_seconds": 600
    }

Field values are templates: {prompt}, {negative_prompt}, {seed}, {duration} are filled
in; a template ending in "?}" is left out when its value is empty. Other values are
sent as they are. "response.kind" is "audio_file" (the body is the audio) or "json"
with "audio_url_field" / "audio_path_field" naming where the audio can be fetched.
"duration" states the lengths the backend accepts in seconds, for a backend whose
health answer does not name them ("min_seconds" / "max_seconds", at the top or under
"capabilities"); the plugin offers them in its T2A list and skips clips outside them
(4-12 s when neither says).

Search and spotting profiles carry name, kind, base_url(s), health and the
protocol name; their request shape is the plugin's own ("ai-sound-design-search-v1",
"ai-sound-design-spotting-v1"). A hybrid profile (kind "hybrid") describes a backend
that answers a video range with one sound per sound event; it carries a request
block like a generation profile plus "response.sounds_field" / "audio_url_field",
and lists "memory_locations" in "supports" when it accepts the events the plugin
found in the session (see hybrid_client.py). With "database_match" in "supports" the
backend can also answer library recordings that sound like each generated sound
(the plugin's "Use database sounds"); the "match" block holds the settings sent
along: "pieces_per_10s" (how finely a sound may be stitched from pieces),
"min_piece_seconds", "layers" (further recordings stacked underneath), "text_weight"
(share of the event's description in the score), "min_similarity" (pieces below it
are not placed; a sound without a convincing match keeps its generated version) and
"ambience_handle_seconds" (an ambience piece keeps that much of its recording before
and after the matched stretch, for fades), "tracks_per_scene" (placement only, not
sent: at most this many tracks per scene, see hybrid_client.py) and the fade of an
ambience clip ("fade_preset", "fade_seconds", "fade_inside": the fade runs over the
handle outside the event, or inside it as at a cut; placement only). "request.scenes_endpoint"
(default "/hybrid/scenes") groups the clips of a range into scenes (see scenes_with_profile).

A search profile may add constant form fields
that are sent with every query, which is how one profile per library is made:

    "request": { "fields": { "library": "mine" } }
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import _USER_CONFIG_DIR, _load_config, _CONFIG_PATH, use_cloudflared, get_cf_headers

ADAPTER_DIR = _USER_CONFIG_DIR / "adapters"
KINDS = ("generation", "search", "spotting", "hybrid")
SERVICE_TO_KIND = {"mmaudio": "generation", "hunyuan": "generation", "hybrid": "hybrid",
                   "sound_search": "search", "spotting": "spotting"}

DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "mmaudio.json": {
        "schema": 1,
        "name": "MMAudio (local)",
        "kind": "generation",
        # The generation gateway (port 8010) in front of the model service: it makes any
        # length up to its own maximum, in windows, so the profile's "duration.max" is the
        # gateway's limit, not the model's 12 s
        "base_url": "http://localhost:8010",
        "base_url_tunnel": "",
        "health": "/health",
        "protocol": "multipart-generate",
        "request": {
            "endpoint": "/generate",
            "video_field": "video",
            "fields": {
                "prompt": "{prompt}",
                "negative_prompt": "{negative_prompt}",
                "seed": "{seed}",
                "duration": "{duration?}",
                "model_name": "large_44k_v2",
                "num_steps": "25",
                "cfg_strength": "4.5",
                "output_format": "wav",
                "full_precision": "false",
            },
        },
        "response": {"kind": "audio_file"},
        "supports": ["negative_prompt", "seed", "duration", "text_only"],
        "duration": {"min": 4, "max": 600, "default": 8},
        "timeout_seconds": 1800,
    },
    "hunyuan_xl.json": {
        "schema": 1,
        "name": "HunyuanVideo-Foley XL (local)",
        "kind": "generation",
        "base_url": "http://localhost:8001",
        "base_url_tunnel": "",
        "health": "/health",
        "protocol": "multipart-generate",
        "request": {
            "endpoint": "/generate",
            "video_field": "video",
            "fields": {
                "prompt": "{prompt}",
                "negative_prompt": "{negative_prompt}",
                "seed": "{seed}",
                "model_size": "xl",
                "num_steps": "50",
                "cfg_strength": "4.5",
                "output_format": "wav",
                "full_precision": "false",
            },
        },
        "response": {"kind": "audio_file"},
        "supports": ["negative_prompt", "seed"],
        "duration": {"min": 4, "max": 12, "default": 8},
        "timeout_seconds": 900,
    },
    "sound_search.json": {
        "schema": 1,
        "name": "Sound archive search (local)",
        "kind": "search",
        "base_url": "http://localhost:8002",
        "base_url_tunnel": "",
        "health": "/health",
        "protocol": "ai-sound-design-search-v1",
    },
    "spotting.json": {
        "schema": 1,
        "name": "Spotting (local)",
        "kind": "spotting",
        "base_url": "http://localhost:8003",
        "base_url_tunnel": "",
        "health": "/health",
        "protocol": "ai-sound-design-spotting-v1",
    },
    "hybrid.json": {
        "schema": 1,
        "name": "Hybrid (local)",
        "kind": "hybrid",
        "base_url": "http://localhost:8004",
        "base_url_tunnel": "",
        "health": "/health",
        "protocol": "ai-sound-design-hybrid-v1",
        "request": {
            "endpoint": "/hybrid",
            "video_field": "video",
            "fields": {"prompt": "{prompt?}", "negative_prompt": "{negative_prompt?}", "seed": "{seed}"},
        },
        "response": {"kind": "json", "sounds_field": "sounds", "audio_url_field": "audio_url"},
        "supports": ["negative_prompt", "seed", "memory_locations", "database_match"],
        "match": {"pieces_per_10s": 0, "min_piece_seconds": 1, "layers": 1, "text_weight": 0.5, "min_similarity": 0.5,
                  "split_gain": 0.0, "ambience_handle_seconds": 10, "tracks_per_scene": 8,
                  "fade_preset": "AI Sound Design", "fade_seconds": 1, "fade_inside": False},
        "timeout_seconds": 1800,
    },
}

_LEGACY_SERVICE_FOR_DEFAULT = {"mmaudio.json": "mmaudio", "hunyuan_xl.json": "hunyuan",
                               "sound_search.json": "sound_search", "spotting.json": "spotting"}


# ── Files ────────────────────────────────────────────────────────────────────

def ensure_default_profiles() -> List[Path]:
    """Create the default profiles the folder lacks. Existing files are left alone, and a
    kind the user already has a profile for gets no default (a deleted default stays
    deleted); URLs the user had set in the old services table are carried over."""
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    present_kinds = set()
    for path in ADAPTER_DIR.glob("*.json"):
        try:
            present_kinds.add(json.loads(path.read_text(encoding="utf-8")).get("kind"))
        except (OSError, ValueError, AttributeError):
            pass
    services = _load_config().get("services", {})
    written = []
    for filename, profile in DEFAULT_PROFILES.items():
        if profile["kind"] in present_kinds or (ADAPTER_DIR / filename).exists():
            continue
        doc = json.loads(json.dumps(profile))
        legacy = services.get(_LEGACY_SERVICE_FOR_DEFAULT.get(filename, ""), {})
        if legacy.get("api_url_direct"):
            doc["base_url"] = legacy["api_url_direct"]
        if legacy.get("api_url_cloudflared"):
            doc["base_url_tunnel"] = legacy["api_url_cloudflared"]
        path = ADAPTER_DIR / filename
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        written.append(path)
    written += _upgrade_default_profiles()
    return written


# Addresses a shipped default used to have, and where the same service lives now: a
# profile still at the old shipped address is moved along (an address the user set
# stays). The generation profile moved from the model service to the gateway in
# front of it, whose length limit is the one its "duration" block has to state.
_MOVED_DEFAULT_ADDRESSES = {"mmaudio.json": ("http://localhost:8000", "http://localhost:8010")}


def _upgrade_default_profiles() -> List[Path]:
    """A shipped default that still carries the default name and protocol learns the
    capabilities a newer plugin added ("supports" entries, "duration"/"match" blocks
    and new keys inside them). Addresses and anything the user changed are left
    alone, except a shipped address that moved (see _MOVED_DEFAULT_ADDRESSES); a
    profile the user renamed is not touched at all."""
    upgraded = []
    for filename, default in DEFAULT_PROFILES.items():
        path = ADAPTER_DIR / filename
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or doc.get("name") != default["name"] \
                or doc.get("protocol") != default.get("protocol"):
            continue
        changed = False
        old_url, new_url = _MOVED_DEFAULT_ADDRESSES.get(filename, (None, None))
        if old_url and str(doc.get("base_url", "")).rstrip("/") == old_url:
            doc["base_url"] = new_url
            # The limits at the old address were the model's; the new service has its own
            for key in ("duration", "timeout_seconds"):
                if key in default:
                    doc[key] = json.loads(json.dumps(default[key]))
            changed = True
        for feature in default.get("supports", []):
            if feature not in doc.setdefault("supports", []):
                doc["supports"].append(feature)
                changed = True
        for block in ("duration", "match"):
            if block in default and block not in doc:
                doc[block] = json.loads(json.dumps(default[block]))
                changed = True
            elif block in default and isinstance(doc.get(block), dict):
                for key, value in default[block].items():
                    if key not in doc[block]:
                        doc[block][key] = json.loads(json.dumps(value))
                        changed = True
        if changed:
            path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            upgraded.append(path)
    return upgraded


def load_profiles(kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """All valid profiles (optionally of one kind), each with 'file' and 'path' added."""
    ensure_default_profiles()
    profiles = []
    for path in sorted(ADAPTER_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or doc.get("kind") not in KINDS or not doc.get("name"):
            continue
        doc = dict(doc)
        doc["file"] = path.name
        doc["path"] = str(path)
        if kind is None or doc["kind"] == kind:
            profiles.append(doc)
    return profiles


def load_profile(name_or_path: str) -> Optional[Dict[str, Any]]:
    """A profile by file name (in the adapter folder) or by full path."""
    candidate = Path(name_or_path)
    if not candidate.is_absolute():
        candidate = ADAPTER_DIR / name_or_path
    if not candidate.exists():
        return None
    try:
        doc = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    doc["file"] = candidate.name
    doc["path"] = str(candidate)
    return doc


def selected_profile(kind: str) -> Optional[Dict[str, Any]]:
    """The profile the plugin selected for `kind` (config.json "adapters"), else the first one."""
    wanted = (_load_config().get("adapters") or {}).get(kind)
    profiles = load_profiles(kind)
    for profile in profiles:
        if profile["file"] == wanted:
            return profile
    # Nothing chosen yet: the shipped default first, else whatever comes first.
    for profile in profiles:
        if profile["file"] in ("mmaudio.json", "sound_search.json", "spotting.json", "hybrid.json"):
            return profile
    return profiles[0] if profiles else None


def search_request_fields() -> Dict[str, str]:
    """Constant form fields of the selected search profile ("request.fields"), e.g. the library."""
    profile = selected_profile("search") or {}
    fields = (profile.get("request") or {}).get("fields") or {}
    return {str(k): str(v) for k, v in fields.items() if v not in (None, "")}


def profile_url(profile: Dict[str, Any]) -> str:
    """Base URL in use: the tunnel address when the tunnel is on and one is given."""
    if use_cloudflared() and profile.get("base_url_tunnel"):
        return str(profile["base_url_tunnel"]).rstrip("/")
    return str(profile.get("base_url", "")).rstrip("/")


def service_url(service: str) -> Optional[str]:
    """Legacy service key (mmaudio, hunyuan, sound_search, spotting) -> selected profile's URL."""
    kind = SERVICE_TO_KIND.get(service)
    if kind is None:
        return None
    profile = selected_profile(kind)
    return profile_url(profile) if profile else None


def save_profile_url(file: str, url: str, tunnel: bool) -> bool:
    profile = load_profile(file)
    if profile is None:
        return False
    path = Path(profile.pop("path"))
    profile.pop("file", None)
    profile["base_url_tunnel" if tunnel else "base_url"] = url.strip()
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return True


def check_health(profile: Dict[str, Any], timeout: float = 5.0) -> Tuple[bool, str]:
    import requests
    url = profile_url(profile) + str(profile.get("health", "/health"))
    try:
        response = requests.get(url, timeout=timeout, headers=get_cf_headers())
        return response.status_code < 400, f"HTTP {response.status_code}"
    except requests.RequestException as exc:  # noqa: BLE001
        return False, str(exc.__class__.__name__)


# ── Generation through a profile ─────────────────────────────────────────────

_TEMPLATE = re.compile(r"^\{(\w+)(\?)?\}$")


def _fill_fields(spec: Dict[str, Any], values: Dict[str, Any]) -> Dict[str, str]:
    """Template fields -> form data; optional templates ("{x?}") vanish when x is empty."""
    data: Dict[str, str] = {}
    for key, raw in (spec or {}).items():
        raw_str = str(raw)
        match = _TEMPLATE.match(raw_str)
        if match is None:
            data[key] = raw_str
            continue
        name, optional = match.group(1), bool(match.group(2))
        value = values.get(name)
        if value is None or value == "":
            if optional:
                continue
            value = ""
        data[key] = str(value)
    return data


RANDOM_SEED = -1


class ProgressPolling:
    """While a blocking request runs, poll `progress_url` every `interval` seconds in a
    thread and hand each JSON answer to `on_progress`. Backends that do not know the
    URL answer 404, which is ignored: progress is a courtesy, the request decides.

        with ProgressPolling(url, on_progress):
            response = requests.post(...)
    """

    def __init__(self, progress_url: Optional[str], on_progress, interval: float = 2.0):
        self.url = progress_url if on_progress else None
        self.on_progress = on_progress
        self.interval = interval
        self.stop = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def _run(self) -> None:
        import requests
        while not self.stop.wait(self.interval):
            try:
                got = requests.get(self.url, headers=get_cf_headers(), timeout=5)
                if got.status_code == 200:
                    self.on_progress(got.json())
            except Exception:
                pass

    def __enter__(self):
        if self.url:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        return False


def progress_url_for(profile: Dict[str, Any], endpoint: str, job_id: str) -> str:
    """`request.progress_endpoint` of the profile, default `<endpoint>/progress/{job_id}`."""
    request_spec = profile.get("request") or {}
    template = str(request_spec.get("progress_endpoint", f"{endpoint}/progress/{{job_id}}"))
    return profile_url(profile) + template.replace("{job_id}", job_id)


def resolve_seed(seed: Optional[int], log=print) -> int:
    """A negative or missing seed means "random": draw one here, so the seed that was
    actually used is logged and ends up in the file name, and can be repeated."""
    if seed is None or int(seed) < 0:
        seed = random.randint(0, 2**31 - 1)
        log(f"Seed: random -> {seed}")
    return int(seed)


def generate_with_profile(profile: Dict[str, Any], *, video_path: Optional[str], prompt: str,
                          negative_prompt: str, seed: int, duration: Optional[float],
                          output_dir: str, output_format: str = "wav", timeout: Optional[int] = None,
                          log=print, on_progress=None) -> Optional[str]:
    """POST the request the profile describes; save the audio; return its path (None on failure).
    `on_progress(dict)` gets the backend's progress answers while the request runs (the
    generation gateway reports its windows: stage, part, parts, fraction, detail)."""
    import requests

    if profile.get("kind") != "generation":
        log(f"ERROR: profile '{profile.get('name')}' is not a generation adapter")
        return None
    request_spec = profile.get("request") or {}
    response_spec = profile.get("response") or {"kind": "audio_file"}
    url = profile_url(profile) + str(request_spec.get("endpoint", "/generate"))
    timeout = timeout or int(profile.get("timeout_seconds", 600))
    supports = set(profile.get("supports", []))

    if video_path is None and "text_only" not in supports:
        log(f"ERROR: '{profile.get('name')}' needs a video (text-only generation not supported)")
        return None

    seed = resolve_seed(seed, log)
    values = {"prompt": prompt or "", "negative_prompt": negative_prompt or "", "seed": seed,
              "duration": duration if duration is not None else "", "output_format": output_format}
    data = _fill_fields(request_spec.get("fields"), values)
    headers = get_cf_headers()
    log(f"Adapter '{profile.get('name')}': POST {url} fields={sorted(data)}"
        + (f" video={Path(video_path).name}" if video_path else " (text only)"))

    job_id = uuid.uuid4().hex
    data["job_id"] = job_id            # the gateway reports its windows under this id; a model service ignores it
    endpoint = str(request_spec.get("endpoint", "/generate"))
    started = time.time()
    try:
        with ProgressPolling(progress_url_for(profile, endpoint, job_id), on_progress):
            if video_path:
                with open(video_path, "rb") as handle:
                    files = {str(request_spec.get("video_field", "video")): (Path(video_path).name, handle, "video/mp4")}
                    response = requests.post(url, files=files, data=data, headers=headers, timeout=timeout)
            else:
                response = requests.post(url, data=data, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        log(f"ERROR: request failed: {exc}")
        return None
    if response.status_code >= 400:
        log(f"ERROR: backend returned {response.status_code}: {response.text[:300]}")
        return None

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if response_spec.get("kind", "audio_file") == "json":
        try:
            payload = response.json()
        except ValueError:
            log("ERROR: backend answered with something other than JSON")
            return None
        audio_url = payload.get(response_spec.get("audio_url_field", "audio_url"))
        audio_path = payload.get(response_spec.get("audio_path_field", "audio_path"))
        if audio_path and Path(str(audio_path)).exists():
            return str(audio_path)
        if not audio_url:
            log(f"ERROR: JSON answer names no audio: {str(payload)[:200]}")
            return None
        if str(audio_url).startswith("/"):
            audio_url = profile_url(profile) + str(audio_url)
        try:
            response = requests.get(str(audio_url), headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            log(f"ERROR: fetching {audio_url} failed: {exc}")
            return None

    filename = None
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition)
    if match:
        filename = Path(match.group(1)).name
    if not filename:
        content_type = response.headers.get("Content-Type", "").lower()
        ext = ".wav" if "wav" in content_type else ".flac" if "flac" in content_type else \
              ".mp3" if "mpeg" in content_type else f".{output_format}"
        safe = re.sub(r"[^\w-]+", "_", (prompt or "generated"))[:24].strip("_") or "generated"
        filename = f"{safe}_{seed}_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
    target = out_dir / filename
    target.write_bytes(response.content)
    parts = response.headers.get("X-Generation-Parts")
    log(f"Saved {target} ({len(response.content) / 1024:.0f} KB) after {time.time() - started:.1f}s"
        + (f", generated in {parts} parts" if parts and parts.isdigit() and int(parts) > 1 else ""))
    return str(target)


MATCH_DEFAULTS = {"pieces_per_10s": 0, "min_piece_seconds": 1.0, "layers": 1, "text_weight": 0.5, "min_similarity": 0.5,
                  "split_gain": 0.0, "ambience_handle_seconds": 10.0, "tracks_per_scene": 8,
                  "fade_preset": "AI Sound Design", "fade_seconds": 1.0, "fade_inside": False}
# pieces_per_10s 0: automatic, the backend counts the generated sound's onsets and reads
# the spotting's word on the event (discrete, continuous, stationary); split_gain: the
# similarity gain a cut must bring to stay, 0 cuts as fine as allowed whenever it does
# not get worse, so each step or bark gets its own library piece, placed where it happens


def match_settings(profile: Dict[str, Any]) -> Dict[str, Any]:
    """The profile's "match" block over the defaults."""
    return {**MATCH_DEFAULTS, **(profile.get("match") or {})}


def hybrid_with_profile(profile: Dict[str, Any], *, video_path: str, start_timecode: str, fps: float,
                        prompt: str, negative_prompt: str, seed: int, events: Optional[List[Dict[str, Any]]],
                        output_dir: str, timeout: Optional[int] = None, log=print,
                        on_progress=None, match: Optional[Dict[str, Any]] = None,
                        categories: Optional[str] = None) -> Dict[str, Any]:
    """POST a video range to a hybrid backend; download every sound it answers with.
    `categories` (comma-separated kinds) tells the backend's spotting what is wanted.

    `on_progress(dict)` gets the backend's progress answers while the request runs.
    `match` (the profile's match settings) asks for library pieces that sound like
    each generated sound; they are downloaded too, as sound["match"]["pieces"][i]["path"].
    Returns the backend's JSON with each sound given a local "path"."""
    import requests

    request_spec = profile.get("request") or {}
    response_spec = profile.get("response") or {}
    url = profile_url(profile) + str(request_spec.get("endpoint", "/hybrid"))
    seed = resolve_seed(seed, log)
    values = {"prompt": prompt or "", "negative_prompt": negative_prompt or "", "seed": seed}
    data = _fill_fields(request_spec.get("fields"), values)
    data["start_timecode"] = start_timecode
    data["fps"] = str(fps)
    if events is not None:
        data["events"] = json.dumps(events, ensure_ascii=False)
    if categories:
        data["categories"] = categories
    if match:
        data["match"] = "true"
        for key in ("pieces_per_10s", "min_piece_seconds", "layers", "text_weight", "library", "category_filter",
                    "min_similarity", "ambience_handle_seconds", "split_gain"):
            if match.get(key) not in (None, ""):
                data[key] = str(match[key]).lower() if isinstance(match[key], bool) else str(match[key])
    job_id = uuid.uuid4().hex
    data["job_id"] = job_id
    endpoint = str(request_spec.get("endpoint", "/hybrid"))
    timeout = timeout or int(profile.get("timeout_seconds", 1800))
    log(f"Adapter '{profile.get('name')}': POST {url} fields={sorted(data)} events={len(events) if events else 'backend'}")

    with open(video_path, "rb") as handle, \
            ProgressPolling(progress_url_for(profile, endpoint, job_id), on_progress):
        files = {str(request_spec.get("video_field", "video")): (Path(video_path).name, handle, "video/mp4")}
        response = requests.post(url, files=files, data=data, headers=get_cf_headers(), timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"{profile.get('name')} answered {response.status_code}: {response.text[:400]}")
    payload = response.json()
    sounds = payload.get(str(response_spec.get("sounds_field", "sounds")), []) or []
    url_field = str(response_spec.get("audio_url_field", "audio_url"))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for n, sound in enumerate(sounds, start=1):
        audio_url = sound.get(url_field)
        if not audio_url:
            continue
        if not str(audio_url).startswith(("http://", "https://")):
            audio_url = profile_url(profile) + ("" if str(audio_url).startswith("/") else "/") + str(audio_url)
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", str(sound.get("label") or f"sound_{n}")).strip("_") or f"sound_{n}"
        target = out / f"{stem}_{int(time.time())}_{n}.wav"
        got = requests.get(audio_url, headers=get_cf_headers(), timeout=timeout)
        if got.status_code != 200:
            log(f"  sound {n}: download failed ({got.status_code})")
            continue
        target.write_bytes(got.content)
        sound["path"] = str(target)
        for k, piece in enumerate((sound.get("match") or {}).get("pieces") or [], start=1):
            piece_url = piece.get(url_field)
            if not piece_url:
                continue
            if not str(piece_url).startswith(("http://", "https://")):
                piece_url = profile_url(profile) + ("" if str(piece_url).startswith("/") else "/") + str(piece_url)
            piece_target = out / f"{stem}_{int(time.time())}_{n}_db_L{piece.get('layer', 1)}_{k}.wav"
            got = requests.get(piece_url, headers=get_cf_headers(), timeout=timeout)
            if got.status_code != 200:
                log(f"  sound {n}: library piece {k} download failed ({got.status_code})")
                continue
            piece_target.write_bytes(got.content)
            piece["path"] = str(piece_target)
    payload[str(response_spec.get("sounds_field", "sounds"))] = sounds
    return payload


def scenes_with_profile(profile: Dict[str, Any], clips: List[Tuple[str, str]], *, timeout: Optional[int] = None,
                        log=print, on_progress=None) -> Dict[str, Any]:
    """POST the clips of a range (path, name), in timeline order, to the hybrid backend's
    scenes endpoint. Returns its JSON: "scenes" [{index, name, description, first_clip,
    last_clip}] and "clip_scenes" (scene index per clip)."""
    import requests

    request_spec = profile.get("request") or {}
    endpoint = str(request_spec.get("scenes_endpoint", "/hybrid/scenes"))
    url = profile_url(profile) + endpoint
    timeout = timeout or int(profile.get("timeout_seconds", 1800))
    job_id = uuid.uuid4().hex
    handles = [open(path, "rb") for path, _ in clips]
    try:
        files = [("videos", (Path(path).name, handle, "video/mp4")) for (path, _), handle in zip(clips, handles)]
        data = {"names": json.dumps([name for _, name in clips], ensure_ascii=False), "job_id": job_id}
        log(f"Adapter '{profile.get('name')}': POST {url} with {len(clips)} clip(s)")
        # Progress is reported under the backend's usual progress endpoint (/hybrid/progress/{job_id})
        with ProgressPolling(progress_url_for(profile, str(request_spec.get("endpoint", "/hybrid")), job_id),
                             on_progress):
            response = requests.post(url, files=files, data=data, headers=get_cf_headers(), timeout=timeout)
    finally:
        for handle in handles:
            handle.close()
    if response.status_code != 200:
        raise RuntimeError(f"{profile.get('name')} answered {response.status_code}: {response.text[:400]}")
    return response.json()


def describe() -> Dict[str, Any]:
    """For the plugin: every profile plus the current selection per kind."""
    return {
        "success": True,
        "folder": str(ADAPTER_DIR),
        "adapters": load_profiles(),
        "selected": {kind: (selected_profile(kind) or {}).get("file") for kind in KINDS},
    }
