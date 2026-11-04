"""Owner-started local read-only scheduler daemon with durable once-only slots.

No self-install, no cloud connection, no unattended model/process/network
tasks. Foreground process stops when PC sleeps/shuts down or Ctrl+C.
All state transitions use existing S4 trusted brain_scheduler.tick.
"""
import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from agentforge import brain_scheduler, brain_store

LOCK = brain_store.ROOT / "data" / "company" / "ops_daemon.lock"
HEARTBEAT = brain_store.ROOT / "data" / "company" / "ops_heartbeat.json"
MAX_BEAT_BYTES = 4096


@contextmanager
def exclusive_instance(lock_path=None):
    """OS advisory 1-byte file lock; prevents competing local daemon loops."""
    path = Path(lock_path) if lock_path is not None else LOCK
    brain_store._safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Another AgentForge scheduler may be active") from exc
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("Another AgentForge scheduler may be active") from exc
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def write_heartbeat(status, *, claimed=0, error=None, path=None):
    if status not in ("STARTING", "IDLE", "TICK_COMPLETED", "ERROR", "STOPPED"):
        raise ValueError("Unsupported heartbeat status")
    if type(claimed) is not int or claimed < 0 or claimed > 3:
        raise ValueError("Invalid heartbeat claimed count")
    target = Path(path) if path is not None else HEARTBEAT
    brain_store._safe(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"status": status, "updated_at_utc": _utc(),
            "pid": os.getpid(), "claimed": claimed,
            "last_error_type": error if error in (
                None, "PermissionError", "ValueError", "RuntimeError",
                "OSError", "DatabaseError") else "Exception",
            "external_actions_enabled": False,
            "read_only_schedules_only": True}
    tmp = target.with_name(target.name + "." + str(os.getpid()) + ".tmp")
    brain_store._safe(tmp)
    try:
        with tmp.open("x", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return data


def read_heartbeat(*, path=None, max_age_seconds=180):
    target = Path(path) if path is not None else HEARTBEAT
    brain_store._safe(target)
    if not target.is_file() or target.stat().st_size > MAX_BEAT_BYTES:
        return {"status": "NOT_RUNNING", "fresh": False,
                "read_only_schedules_only": True}
    data = json.loads(target.read_text(encoding="utf-8"))
    updated = datetime.fromisoformat(data["updated_at_utc"])
    if updated.tzinfo is None:
        raise ValueError("Invalid heartbeat timezone")
    age = (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds()
    fresh = (0 <= age <= max_age_seconds and data.get("status")
             in ("STARTING", "IDLE", "TICK_COMPLETED"))
    return {"status": data.get("status", "UNKNOWN") if fresh else "NOT_RUNNING",
            "fresh": bool(fresh), "updated_at_utc": data["updated_at_utc"],
            "claimed": data.get("claimed", 0),
            "read_only_schedules_only": True,
            "trusted_pid_verification": False}


def tick_once(*, db_path=None, task_db_path=None, heartbeat_path=None):
    write_heartbeat("STARTING", path=heartbeat_path)
    try:
        result = brain_scheduler.tick(confirm_tick=True, db_path=db_path,
                                      task_db_path=task_db_path, max_due=3)
        write_heartbeat("TICK_COMPLETED", claimed=len(result["claimed"]),
                        path=heartbeat_path)
        return result
    except Exception as exc:
        write_heartbeat("ERROR", error=type(exc).__name__, path=heartbeat_path)
        raise


def run_loop(*, interval_seconds=60, confirm_unattended=False,
             stop_event=None, db_path=None, task_db_path=None,
             heartbeat_path=None, lock_path=None):
    if confirm_unattended is not True:
        raise PermissionError("Explicit owner confirmation required for foreground daemon")
    if type(interval_seconds) is not int or not 30 <= interval_seconds <= 3600:
        raise ValueError("Loop interval must be 30–3600 seconds")
    stopped = stop_event or Event()
    with exclusive_instance(lock_path):
        write_heartbeat("STARTING", path=heartbeat_path)
        cycles = 0
        try:
            while not stopped.is_set():
                try:
                    tick_once(db_path=db_path, task_db_path=task_db_path,
                              heartbeat_path=heartbeat_path)
                except Exception:
                    # Never retry an ambiguous execution. S4 slots are already
                    # claimed; next tick checks only future *new* due slots.
                    pass
                cycles += 1
                if stopped.wait(interval_seconds):
                    break
            return {"status": "STOPPED", "cycles": cycles,
                    "background_service_installed": False}
        finally:
            write_heartbeat("STOPPED", path=heartbeat_path)


def main():
    cli = argparse.ArgumentParser(description="Explicit local read-only S4 scheduler")
    cmd = cli.add_subparsers(dest="command", required=True)
    run = cmd.add_parser("run", help="Foreground loop until Ctrl+C; not 24/7 if PC is off")
    run.add_argument("--confirm-unattended", action="store_true")
    run.add_argument("--interval", type=int, default=60)
    once = cmd.add_parser("once", help="Do one read-only scheduler tick")
    once.add_argument("--confirm-tick", action="store_true")
    cmd.add_parser("status", help="Read last local heartbeat")
    args = cli.parse_args()
    if args.command == "status":
        result = read_heartbeat()
    elif args.command == "once":
        if not args.confirm_tick:
            cli.error("Explicit --confirm-tick required")
        with exclusive_instance():
            result = tick_once()
            write_heartbeat("STOPPED")
    else:
        if not args.confirm_unattended:
            cli.error("Explicit --confirm-unattended required")
        print("Read-only local scheduler started. Ctrl+C to stop; no cloud/paid actions.",
              flush=True)
        try:
            result = run_loop(interval_seconds=args.interval, confirm_unattended=True)
        except KeyboardInterrupt:
            result = {"status": "STOPPED", "reason": "Ctrl+C"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
