"""Owner-gated single-shot ComfyUI video queue, conservative 12 GiB pilot.

Requires an inspected, SHA-pinned owner-installed core-node API workflow.
No model download, arbitrary workflow generation, retries, uploads or hosting.
Successful ComfyUI history is NOT a verified or accepted video artifact.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.client
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from agentforge import ops_control
from agentforge.domains.media import long_form
from agentforge.paths import DATA_DIR, WORKSPACE_DIR

FILMS = WORKSPACE_DIR / "films"
DB = DATA_DIR / "film_studio" / "motion.sqlite3"
PORT = 8188
PROFILE = {"width": 640, "height": 352, "frames": 49, "fps": 12, "batch_size": 1}
MAX_WORKFLOW_BYTES = 160_000
MAX_RESPONSE_BYTES = 131_072
MAX_PROMPT_CHARS = 1100
MAX_ACTIVE_JOBS = 1
SHA = re.compile(r"[0-9a-f]{64}\Z")
NODE_ID = re.compile(r"[0-9]{1,4}\Z")
ALLOWED_NODES = frozenset({
    "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode",
    "ModelSamplingSD3", "KSampler", "EmptyHunyuanLatentVideo",
    "EmptyWanLatentVideo", "Wan22ImageToVideoLatent",
    "VAEDecode", "CreateVideo", "SaveVideo",
    "ConditioningZeroOut", "FluxGuidance",
})
VIDEO_LATENTS = frozenset({"EmptyHunyuanLatentVideo", "EmptyWanLatentVideo"})


class MotionError(ValueError):
    """Invalid or unsupported motion request (no GPU inference started)."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(value: bytes):
    return hashlib.sha256(value).hexdigest()


def _safe_file(path: Path):
    path = Path(path)
    if (not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_WORKFLOW_BYTES
            or path.stat().st_size < 2):
        raise MotionError("Workflow must be an inspected, bounded local JSON file")
    for parent in path.parents:
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise MotionError("Symlink/junction workflow path forbidden")
    return path.read_bytes()


def inspect_workflow(path: Path):
    """Strict schema for an *owner reviewed* ComfyUI API-format T2V workflow.

    Refuse unknown/custom nodes. Non-API ComfyUI UI exports cannot be run.
    Never execute a workflow during inspection.
    """
    raw = _safe_file(path)
    try:
        record = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise MotionError("Invalid workflow JSON") from exc
    keys = {"format", "positive_node", "seed_node", "size_node", "fps_node",
            "output_node", "api"}
    if not isinstance(record, dict) or set(record) != keys or record["format"] != "agentforge.film.comfy.t2v.v1":
        raise MotionError("Expected reviewed AgentForge ComfyUI T2V API workflow wrapper")
    graph = record["api"]
    if not isinstance(graph, dict) or not 6 <= len(graph) <= 50:
        raise MotionError("Workflow graph must have 6-50 trusted nodes")
    for nid, node in graph.items():
        if (not isinstance(nid, str) or not NODE_ID.fullmatch(nid)
                or not isinstance(node, dict)
                or set(node) - {"class_type", "inputs", "_meta"}
                or node.get("class_type") not in ALLOWED_NODES
                or not isinstance(node.get("inputs"), dict)):
            raise MotionError("Unknown or malformed ComfyUI node")
        if len(node["inputs"]) > 40:
            raise MotionError("Too many node inputs")
        for val in node["inputs"].values():
            if isinstance(val, str) and (len(val) > 2000 or "://" in val or
                                        "\x00" in val or "\\" in val or
                                        val.startswith("/") or "../" in val):
                raise MotionError("Unsafe workflow input (path/URL)")
            if isinstance(val, list) and (
                len(val) != 2 or val[0] not in graph or type(val[1]) is not int
                    or not 0 <= val[1] <= 9):
                raise MotionError("Invalid ComfyUI node link")
            if isinstance(val, (dict, list)) and not (
                isinstance(val, list) and len(val) == 2):
                raise MotionError("Untrusted complex workflow input")
    ids = [record[x] for x in
           ("positive_node", "seed_node", "size_node", "fps_node", "output_node")]
    if any(not isinstance(i, str) or i not in graph for i in ids):
        raise MotionError("Workflow binding points to missing nodes")
    p, seed, size, fps, out = (graph[x] for x in ids)
    if (p["class_type"] != "CLIPTextEncode" or not isinstance(p["inputs"].get("text"), str)
            or seed["class_type"] != "KSampler" or type(seed["inputs"].get("seed")) is not int
            or size["class_type"] not in VIDEO_LATENTS
            or fps["class_type"] != "CreateVideo"
            or out["class_type"] != "SaveVideo"
            or not isinstance(out["inputs"].get("filename_prefix"), str)):
        raise MotionError("Workflow binding must map to core T2V prompt/sampler/video nodes")
    params = size["inputs"]
    # Fixed small profile is a guardrail, not an assertion the video model will run.
    if ({k: params.get(k) for k in ("width", "height", "length")} !=
            {"width": PROFILE["width"], "height": PROFILE["height"],
             "length": PROFILE["frames"]}
            or fps["inputs"].get("fps") != PROFILE["fps"]):
        raise MotionError("Workflow exceeds or differs from the fixed 12GB pilot profile")
    if graph[record["output_node"]]["inputs"].get("filename_prefix", "").find("/") >= 0:
        raise MotionError("Output prefix must not contain paths")
    return {"sha256": _sha(raw), "workflow": record, "profile": dict(PROFILE),
            "validated_structure_only": True, "model_installed": False}


def _json_request(path: str, *, body=None, timeout=6):
    """Direct HTTP connection to fixed loopback only; no proxy or redirects."""
    if not isinstance(path, str) or not re.fullmatch(r"/(?:system_stats|prompt|history/[0-9a-f-]{36})", path):
        raise MotionError("Unknown local ComfyUI route")
    payload = (None if body is None else json.dumps(
        body, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    try:
        conn.request("POST" if payload is not None else "GET", path, body=payload,
                     headers={"Content-Type": "application/json",
                              "Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError("Local ComfyUI returned non-success status")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    finally:
        conn.close()
    if len(data) > MAX_RESPONSE_BYTES:
        raise MotionError("ComfyUI response exceeds safe limit")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise MotionError("ComfyUI returned invalid JSON") from exc


def health():
    """GPU presence only, not a model speed/memory/cinematic-quality guarantee."""
    try:
        stats = _json_request("/system_stats")
        devices = stats.get("devices", []) if isinstance(stats, dict) else []
        if not isinstance(devices, list):
            raise MotionError("Invalid local ComfyUI device report")
        gpu = [d for d in devices if isinstance(d, dict)
               and isinstance(d.get("vram_total"), int) and d["vram_total"] > 0
               and any(x in str(d.get("type", "")).lower()
                       for x in ("cuda", "directml", "rocm", "hip"))]
        if not gpu:
            return {"status": "GPU_NOT_DETECTED", "video_verified": False,
                    "profile": dict(PROFILE)}
        vram = max(d["vram_total"] for d in gpu)
        return {"status": "GPU_DETECTED_UNBENCHMARKED",
                "vram_gib": round(vram / 2**30, 2),
                "profile": dict(PROFILE), "video_verified": False}
    except (OSError, RuntimeError, MotionError, http.client.HTTPException):
        return {"status": "COMFYUI_UNAVAILABLE", "video_verified": False,
                "profile": dict(PROFILE)}


def _db(path: Path, *, write=False):
    path = Path(path)
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise MotionError("Motion ledger symlink forbidden")
    if not write and not path.is_file():
        return None
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    if write:
        conn.execute("""CREATE TABLE IF NOT EXISTS motion_jobs(
            job_id TEXT PRIMARY KEY, film_slug TEXT NOT NULL, shot_id TEXT NOT NULL,
            plan_sha TEXT NOT NULL, workflow_sha TEXT NOT NULL, prompt_sha TEXT NOT NULL,
            seed INTEGER NOT NULL, provider_id TEXT, state TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(film_slug, shot_id, plan_sha))""")
        conn.commit()
    return conn


def submit_shot(*, film_slug, shot_id, plan_sha, prompt, workflow_path,
                workflow_sha, seed, confirmed=False,
                film_root: Path = FILMS, db_path: Path = DB):
    """One-shot owner dispatch, checkpointed BEFORE any GPU/HTTP work.

    Ambiguous SUBMITTING is never blindly retried. No import, verification,
    public upload, or auto-publishing action is implemented.
    """
    if confirmed is not True:
        raise PermissionError("Owner must explicitly confirm local GPU generation")
    ops_control.require_active()
    plan = long_form.load_plan(film_root, film_slug)
    if not isinstance(plan_sha, str) or plan["plan_sha256"] != plan_sha:
        raise PermissionError("Film plan has changed since Owner review")
    shot = next((s for s in plan["shots"] if s["shot_id"] == shot_id), None)
    if shot is None or shot["duration_seconds"] > 5:
        raise MotionError("Pilot only supports known 4-5 second planned shot slots")
    if (not isinstance(prompt, str) or not 30 <= len(prompt.strip()) <= MAX_PROMPT_CHARS
            or any(ord(ch) < 32 and ch not in "\n\t" for ch in prompt)):
        raise MotionError("Invalid motion shot prompt")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise MotionError("Seed must be an explicit unsigned 32-bit integer")
    template = inspect_workflow(workflow_path)
    if not isinstance(workflow_sha, str) or template["sha256"] != workflow_sha:
        raise PermissionError("Trusted workflow SHA is stale; inspect it again")
    environment = health()
    if environment["status"] != "GPU_DETECTED_UNBENCHMARKED":
        raise RuntimeError("ComfyUI with a local GPU is not ready")
    graph = copy.deepcopy(template["workflow"]["api"])
    bindings = template["workflow"]
    graph[bindings["positive_node"]]["inputs"]["text"] = prompt.strip()
    graph[bindings["seed_node"]]["inputs"]["seed"] = seed
    job_id = uuid4().hex
    graph[bindings["output_node"]]["inputs"]["filename_prefix"] = "af_motion_" + job_id
    now = _now()
    with closing(_db(db_path, write=True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute("SELECT COUNT(*) FROM motion_jobs WHERE state IN "
                              "('SUBMITTING','SUBMITTED')").fetchone()[0]
        if active >= MAX_ACTIVE_JOBS:
            raise PermissionError("Only one outstanding GPU shot is allowed in pilot")
        conn.execute("""INSERT INTO motion_jobs
            (job_id, film_slug, shot_id, plan_sha, workflow_sha, prompt_sha,
             seed, provider_id, state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'SUBMITTING', ?, ?)""",
            (job_id, film_slug, shot_id, plan_sha, workflow_sha,
             _sha(prompt.strip().encode("utf-8")), seed, now, now))
    # Network failure leaves SUBMITTING_UNCERTAIN (must reconcile manually).
    result = _json_request("/prompt", body={"prompt": graph}, timeout=12)
    if not isinstance(result, dict) or not isinstance(result.get("prompt_id"), str):
        raise MotionError("Local ComfyUI did not return prompt_id; dispatch uncertain")
    provider_id = str(UUID(result["prompt_id"]))
    with closing(_db(db_path, write=True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        updated = conn.execute("""UPDATE motion_jobs
            SET provider_id=?, state='SUBMITTED', updated_at=?
            WHERE job_id=? AND state='SUBMITTING'""",
            (provider_id, _now(), job_id))
        if updated.rowcount != 1:
            raise RuntimeError("Motion job ledger changed after dispatch")
    return {"job_id": job_id, "status": "SUBMITTED", "provider": "LOCAL_COMFYUI",
            "shot_id": shot_id, "video_verified": False, "youtube_uploaded": False,
            "model_quality_verified": False}


def job_status(job_id, *, db_path: Path = DB):
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise MotionError("Invalid motion job ID")
    db = _db(db_path)
    if db is None:
        raise KeyError("Motion job does not exist")
    with closing(db):
        row = db.execute("SELECT * FROM motion_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise KeyError("Motion job does not exist")
    if row["provider_id"] is None:
        status = "SUBMITTING_UNCERTAIN"
    else:
        record = _json_request("/history/" + row["provider_id"])
        details = record.get(row["provider_id"]) if isinstance(record, dict) else None
        if details is None:
            status = "PROVIDER_QUEUED_OR_UNKNOWN"
        elif (isinstance(details, dict) and isinstance(details.get("status"), dict)
              and details["status"].get("completed") is True
              and details["status"].get("status_str") == "success"):
            status = "COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED"
        else:
            status = "PROVIDER_FAILED_OR_INCOMPLETE"
    if status == "COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED":
        # Provider completion is a durable, limited-scope status. It is NOT
        # a video QA PASS. Release the one-active-shot quota only after the
        # provider confirms terminal success; do not re-run this shot.
        with closing(_db(db_path, write=True)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""UPDATE motion_jobs SET state='COMPLETE_UNVERIFIED',
                updated_at=? WHERE job_id=? AND state='SUBMITTED'
                AND provider_id=?""", (_now(), job_id, row["provider_id"]))
    return {"job_id": job_id, "film_slug": row["film_slug"], "shot_id": row["shot_id"],
            "status": status, "plan_sha": row["plan_sha"], "workflow_sha": row["workflow_sha"],
            "video_verified": False, "youtube_uploaded": False}


def main(argv=None):
    p = argparse.ArgumentParser(description="Owner-only local motion pilot; no auto-upload")
    choices = p.add_subparsers(dest="action", required=True)
    choices.add_parser("health")
    inspect = choices.add_parser("inspect-workflow")
    inspect.add_argument("--workflow", type=Path, required=True)
    submit = choices.add_parser("submit")
    for name in ("film-slug", "shot-id", "plan-sha", "workflow-sha"):
        submit.add_argument("--" + name, required=True)
    submit.add_argument("--workflow", type=Path, required=True)
    submit.add_argument("--prompt-file", type=Path, required=True,
                        help="Local Owner-authored shot prompt; avoids command-line prompt history")
    submit.add_argument("--seed", type=int, required=True)
    submit.add_argument("--confirm-gpu-run", action="store_true")
    status = choices.add_parser("status")
    status.add_argument("--job-id", required=True)
    args = p.parse_args(argv)
    if args.action == "health":
        result = health()
    elif args.action == "inspect-workflow":
        info = inspect_workflow(args.workflow)
        result = {k: v for k, v in info.items() if k != "workflow"}
    elif args.action == "status":
        result = job_status(args.job_id)
    else:
        result = submit_shot(
            film_slug=args.film_slug, shot_id=args.shot_id,
            plan_sha=args.plan_sha, workflow_path=args.workflow,
            workflow_sha=args.workflow_sha,
            prompt=args.prompt_file.read_text(encoding="utf-8"),
            seed=args.seed, confirmed=args.confirm_gpu_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
