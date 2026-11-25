"""Versioned AI cue plans and local multi-track audio rendering."""
import hashlib
import json
import re
import tempfile
import wave
from contextlib import contextmanager
from pathlib import Path

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import studio_speech
from agentforge.features.media import render
from agentforge.paths import WORKSPACE_DIR, ensure_local_root

KINDS = ("dialogue", "narration", "sfx", "ambience", "music")
SPEECH = frozenset(("dialogue", "narration"))
MAX_CUES = 32
MAX_ASSETS = 24
ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.wav\Z", re.IGNORECASE)


def _hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _asset_path(name):
    if not isinstance(name, str) or not ASSET_NAME.fullmatch(name):
        raise ValueError("Invalid local audio asset name")
    return ensure_local_root(WORKSPACE_DIR / "audio-library" / name)


def library():
    """Read approved local WAV files only; no discovery beyond this directory."""
    from agentforge.features.film_studio import draft_audio
    folder = ensure_local_root(WORKSPACE_DIR / "audio-library")
    if not folder.is_dir():
        return {}
    result = {}
    for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold())[:200]:
        if len(result) >= MAX_ASSETS:
            break
        if not ASSET_NAME.fullmatch(path.name) or path.is_symlink():
            continue
        try:
            safe = _asset_path(path.name)
            seconds = draft_audio._pcm_duration(safe)
            result[path.name] = {"sha256": _hash(safe), "seconds": round(seconds, 3)}
        except (ValueError, OSError):
            continue
    return result


def _profile_hash(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _voice(engine, name):
    from agentforge.features.film_studio import draft_audio
    if engine == "cloud":
        if not isinstance(name, str) or not 1 <= len(name) <= 100 or any(ord(c) < 32 for c in name):
            raise ValueError("Nhập mã voice cloud đã đăng ký.")
    else:
        if draft_audio.plan(engine, name) is None:
            raise ValueError("Choose a speech engine")
    return name


def _config(engine, voice_name, voices, cast):
    default = _voice(engine, voice_name)
    if (not isinstance(voices, dict) or not voices.keys() <= cast.keys()
            or any(not isinstance(value, str) for value in voices.values())):
        raise ValueError("Invalid character voice assignment")
    mapping = {key: _voice(engine, value) for key, value in voices.items() if value}
    return {"engine": engine, "voice_name": default, "voices": mapping}


def _cue(row, scene, config, assets):
    if not isinstance(row, dict) or set(row) != {
            "kind", "start_frame", "end_frame", "gain_db", "speaker", "text", "asset"}:
        raise ValueError("Invalid AI audio cue")
    kind, start, end, gain = (row[k] for k in ("kind", "start_frame", "end_frame", "gain_db"))
    if (kind not in KINDS or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= scene["frames"] or type(gain) is not int or not -30 <= gain <= 0):
        raise ValueError("Audio cue exceeds shot timeline or gain limits")
    speaker, text, asset = (row[key] for key in ("speaker", "text", "asset"))
    if not all(isinstance(value, str) for value in (speaker, text, asset)):
        raise ValueError("Invalid audio cue fields")
    result = {**row, "shot_id": scene["shot_id"], "shot_frames": scene["frames"]}
    if kind in SPEECH:
        if (speaker not in {"narrator", "unregistered", *scene.get("character_ids", [])}
                or not 1 <= len(text.strip()) <= 180 or asset):
            raise ValueError("Invalid speech cue or character")
        result["voice"] = config["voices"].get(speaker, config["voice_name"])
    else:
        if speaker or text or asset not in assets:
            raise ValueError("Audio cue must use an existing local library WAV")
        result["asset_sha256"] = assets[asset]["sha256"]
    return result


def propose(job, engine, voice_name, voices, infer):
    config = _config(engine, voice_name, voices, job.get("cast", {}))
    if engine == "cloud":
        _, profile, _ = model_hub.speech_binding()
        config["cloud_profile_sha"] = _profile_hash(profile)
        config["cloud_model_id"] = profile["id"]
    assets = library()
    scenes = job["board"]["scenes"]
    cues, unresolved = [], []
    for index in range(0, len(scenes), 4):
        batch = scenes[index:index+4]
        ids = [scene["shot_id"] for scene in batch]
        schema = {"type": "object", "additionalProperties": False, "required": ["shots"],
                  "properties": {"shots": {"type": "array", "minItems": len(ids), "maxItems": len(ids),
                   "items": {"type": "object", "additionalProperties": False,
                    "required": ["shot_id", "cues", "unresolved"],
                    "properties": {"shot_id": {"type": "string", "enum": ids},
                     "unresolved": {"type": "string", "maxLength": 160},
                     "cues": {"type": "array", "maxItems": 3, "items": {
                      "type": "object", "additionalProperties": False,
                      "required": ["kind", "start_frame", "end_frame", "gain_db", "speaker", "text", "asset"],
                      "properties": {"kind": {"type": "string", "enum": list(KINDS)},
                       "start_frame": {"type": "integer", "minimum": 0},
                       "end_frame": {"type": "integer", "minimum": 1},
                       "gain_db": {"type": "integer", "minimum": -30, "maximum": 0},
                       "speaker": {"type": "string"}, "text": {"type": "string", "maxLength": 180},
                       "asset": {"type": "string", "enum": ["", *assets]}}}}}}}}}
        from agentforge.features.film_studio import draft_pipeline as draft
        data = {"fps": draft._job_fps(job), "cast": job.get("cast", {}),
                "local_library": {name: {"seconds": item["seconds"]} for name, item in assets.items()},
                "shots": [{**{key: scene[key] for key in ("shot_id", "description", "audio", "caption",
                          "character_ids", "frames", "motion_prompt", "continuity_plan") if key in scene},
                          "source": job["brief"]["idea"][slice(*scene["script_range"])][:800]
                          if scene.get("script_range") else job["brief"]["idea"][:1200]} for scene in batch]}
        result = infer(
            "Direct sound for these existing shots; preserve authored dialogue and events. Subtitles are not automatically "
            "speech. Use dialogue for spoken words, narration only when helpful, or silence. Use narrator, unregistered, "
            "or a registered character ID present in the shot as speaker for speech; asset must be empty. "
            "For sfx/ambience/music choose an exact listed WAV asset or omit it and describe missing sound in unresolved; "
            "do not invent a filename. Empty speaker and text for non-speech. Frame positions are relative to each shot; "
            "end_frame is exclusive. Keep speech very short, allow natural reading time, use lower gains for background. "
            "Maximum three cues per shot; prefer purposeful sound. Return every shot in order, including silent shots. "
            "Do not add dialogue that contradicts the original story.", data, schema)
        rows = result.get("shots") if isinstance(result, dict) and set(result) == {"shots"} else None
        if not isinstance(rows, list) or len(rows) != len(ids):
            raise ValueError("AI returned incomplete audio plan")
        for scene, row in zip(batch, rows):
            if (not isinstance(row, dict) or set(row) != {"shot_id", "cues", "unresolved"}
                    or row["shot_id"] != scene["shot_id"] or not isinstance(row["cues"], list)
                    or len(row["cues"]) > 3 or not isinstance(row["unresolved"], str)
                    or len(row["unresolved"]) > 160):
                raise ValueError("Invalid audio plan shot")
            cues.extend(_cue(cue, scene, config, assets) for cue in row["cues"])
            if row["unresolved"]:
                unresolved.append({"shot_id": scene["shot_id"], "detail": row["unresolved"]})
    if len(cues) > MAX_CUES:
        raise ValueError("Audio plan exceeds 32 cues; split the production")
    return {**config, "format": "directed.v1", "cues": cues, "unresolved": unresolved}


def validate(job, audio):
    if audio.get("format") != "directed.v1":
        raise ValueError("Invalid directed audio format")
    keys = {"format", "engine", "voice_name", "voices", "cues", "unresolved"}
    if audio.get("engine") == "cloud":
        keys |= {"cloud_profile_sha", "cloud_model_id"}
    if set(audio) != keys:
        raise ValueError("Invalid directed audio plan fields")
    config = _config(audio["engine"], audio["voice_name"], audio["voices"], job.get("cast", {}))
    scenes = {scene["shot_id"]: scene for scene in job["board"]["scenes"]}
    cues = audio["cues"]
    if not isinstance(cues, list) or len(cues) > MAX_CUES:
        raise ValueError("Invalid directed audio cue count")
    counts = {}
    for cue in cues:
        if not isinstance(cue, dict) or cue.get("shot_id") not in scenes:
            raise ValueError("Audio plan needs to be rebuilt after editing shots")
        scene = scenes[cue["shot_id"]]
        counts[cue["shot_id"]] = counts.get(cue["shot_id"], 0)+1
        if counts[cue["shot_id"]] > 3:
            raise ValueError("Too many audio cues in a shot")
        asset = cue.get("asset")
        assets = {asset: {"sha256": cue.get("asset_sha256")}} if isinstance(asset, str) and asset else {}
        row = {key: cue.get(key) for key in ("kind", "start_frame", "end_frame", "gain_db", "speaker", "text", "asset")}
        if _cue(row, scene, config, assets) != cue:
            raise ValueError("Audio plan needs to be rebuilt after editing shots")
        if asset:
            path = _asset_path(asset)
            digest = cue.get("asset_sha256")
            if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or not path.is_file() or not 44 <= path.stat().st_size <= 32_000_000
                    or _hash(path) != digest):
                raise ValueError("Local audio asset changed; rebuild the audio plan")
    unresolved = audio["unresolved"]
    if (not isinstance(unresolved, list) or len(unresolved) > len(scenes)
            or any(not isinstance(item, dict) or set(item) != {"shot_id", "detail"}
                   or item["shot_id"] not in scenes or not isinstance(item["detail"], str)
                   or len(item["detail"]) > 160 for item in unresolved)):
        raise ValueError("Invalid unresolved audio notes")
    if audio["engine"] == "cloud" and any(cue["kind"] in SPEECH for cue in cues):
        _, profile, _ = model_hub.speech_binding()
        if _profile_hash(profile) != audio["cloud_profile_sha"] or profile["id"] != audio["cloud_model_id"]:
            raise ValueError("Cloud speech model changed; rebuild the audio plan")
    return audio


def _speech(job, audio, cue, folder):
    from agentforge.features.film_studio import draft_pipeline as draft
    wav = folder / "voiceover.partial.wav"
    if audio["engine"] == "cloud":
        _, profile, limit = model_hub.speech_binding()
        if _profile_hash(profile) != audio["cloud_profile_sha"]:
            raise ValueError("Cloud speech model changed; rebuild the audio plan")
        limit = min(limit, job.get("cloud_call_limit", limit))
        used = job.get("cloud_calls", 0)
        if used >= limit:
            raise ValueError("Đã hết ngân sách lượt gọi AI cloud của production.")
        job.update(cloud_calls=used+1, cloud_call_limit=limit)
        draft._save(job)
        wav.write_bytes(studio_speech.synthesize(profile, cue["text"], cue["voice"]))
    else:
        (folder / "narration.txt").write_text(cue["text"], encoding="utf-8")
        cmd, stdin = render._voice_command(audio["engine"], folder, cue["voice"])
        render._run_process(cmd, cwd=folder, timeout=150, input_text=stdin)
    return wav


@contextmanager
def prepare(job, folder, fps):
    from agentforge.features.film_studio import draft_audio
    audio = validate(job, job["audio_plan"])
    rate = draft_audio.SAMPLE_RATE
    positions, frames = {}, 0
    for scene in job["board"]["scenes"]:
        positions[scene["shot_id"]] = frames
        frames += scene["frames"]
    total = round(frames*rate/fps)
    with tempfile.TemporaryDirectory(dir=folder, prefix="directed-audio-") as tmp:
        root = ensure_local_root(Path(tmp))
        args = [render._ffmpeg(), "-nostdin", "-n", "-v", "error"]
        filters = [f"anullsrc=r={rate}:cl=mono,atrim=end_sample={total}[base]"]
        streams, receipts = ["[base]"], []
        for i, cue in enumerate(audio["cues"]):
            ops_control.require_active()
            path = ensure_local_root(root / f"c{i:02d}")
            path.mkdir()
            absolute = positions[cue["shot_id"]]
            start = round((absolute+cue["start_frame"])*rate/fps)
            end = round((absolute+cue["end_frame"])*rate/fps)
            samples = end-start
            if cue["kind"] in SPEECH:
                wav = _speech(job, audio, cue, path)
                if draft_audio._pcm_duration(wav) > samples/rate:
                    raise ValueError(f"Lời thoại cue {i+1} dài hơn timeline; hãy lập lại kế hoạch âm thanh.")
            else:
                wav = path / "asset.wav"
                with _asset_path(cue["asset"]).open("rb") as source, wav.open("xb") as target:
                    data = source.read(32_000_001)
                    if len(data) > 32_000_000:
                        raise ValueError("Local audio asset exceeds byte budget")
                    target.write(data)
                if _hash(wav) != cue["asset_sha256"]:
                    raise ValueError("Local audio asset changed during render")
                draft_audio._pcm_duration(wav)
                if cue["kind"] in {"ambience", "music"}:
                    args += ["-stream_loop", "-1"]
            args += ["-i", str(wav)]
            filters.append(f"[{i}:a]aresample={rate},aformat=sample_fmts=fltp:channel_layouts=mono,"
                           f"atrim=end_sample={samples},asetpts=PTS-STARTPTS,"
                           f"volume={cue['gain_db']}dB,adelay={start}S,apad=whole_len={total},"
                           f"atrim=end_sample={total}[a{i}]")
            streams.append(f"[a{i}]")
            receipts.append({"shot_id": cue["shot_id"], "kind": cue["kind"],
                             "start_sample": start, "end_sample": end, "source_sha256": _hash(wav),
                             "gain_db": cue["gain_db"]})
        filters.append("".join(streams) + f"amix=inputs={len(streams)}:duration=first:normalize=0,"
                       f"alimiter=limit=0.95:level=false:latency=true,apad=whole_len={total},"
                       f"atrim=end_sample={total}[out]")
        output = root / "mix.wav"
        render._run_process(args+["-filter_complex_threads", "1", "-filter_complex", ";".join(filters),
                                 "-map", "[out]", "-c:a", "pcm_s16le", "-ar", str(rate),
                                 "-ac", "1", str(output)], cwd=root, timeout=120)
        draft_audio._pcm_duration(output)
        with wave.open(str(output), "rb") as wav:
            if wav.getnframes() != total or wav.getframerate() != rate or wav.getnchannels() != 1:
                raise ValueError("Mixed audio does not match approved timeline")
        yield {"path": output, "evidence": {"kind": "directed_audio_v1", "engine": audio["engine"],
               "sample_rate": rate, "samples": total, "source_sha256": _hash(output),
               "cues": receipts, "unresolved": audio["unresolved"], "voice_language_verified": False,
               "source_wav_retained": False}}
