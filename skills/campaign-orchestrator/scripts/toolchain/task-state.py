#!/usr/bin/env python3
"""
task-state.py — Anti-Context-Rot state persistence.

Atomic file operations: mkdir lock, .tmp + rename, fsync.
Schema versioning, error recovery, task-ID discovery.

Usage:
    python3 task-state.py save --task-id <id> --set '<json>'
    python3 task-state.py save --task-id <id> --merge '<json>'
    python3 task-state.py read --task-id <id>
    python3 task-state.py read --task-id <id> --field <dot.notation>
    python3 task-state.py list
    python3 task-state.py prune --older-than <Nd> [--force]
    python3 task-state.py current [--set <id>]
"""

import json
import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCHEMA_VERSION = "2.0.0"
STATE_DIR = Path(".scratch/task-state")
LOCK_TIMEOUT = 5.0  # seconds
LOCK_RETRY = 0.05   # seconds


TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_task_id(task_id: str) -> str:
    """Validate task_id to prevent path traversal. Raises ValueError on bad ids."""
    if not task_id or not isinstance(task_id, str):
        raise ValueError(f"Invalid task_id: {task_id!r}")
    if not TASK_ID_RE.match(task_id):
        raise ValueError(
            f"Invalid task_id {task_id!r}: must match ^[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}$ "
            f"(no slashes, no '..', no NUL)"
        )
    return task_id


def acquire_lock(task_id: str) -> bool:
    """mkdir-based advisory lock with timeout.

    Uses mkdir() WITHOUT exist_ok so concurrent callers actually exclude each other
    (exist_ok=True never raises, which made the old lock non-exclusive).
    """
    validate_task_id(task_id)
    lock_path = STATE_DIR / f"{task_id}.lock"
    deadline = time.monotonic() + LOCK_TIMEOUT
    while time.monotonic() < deadline:
        try:
            # O_EXCL semantics: raises FileExistsError if the dir already exists
            lock_path.mkdir()
            # Write PID + timestamp for debugging
            (lock_path / ".pid").write_text(str(os.getpid()))
            return True
        except FileExistsError:
            # Check if lock is stale (holder died)
            pid_file = lock_path / ".pid"
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    if pid <= 0:
                        lock_path.rmdir()
                        continue
                    # Check if process exists (signal 0 = check only)
                    os.kill(pid, 0)
                except (ProcessLookupError, PermissionError, ValueError):
                    # Stale lock — holder died
                    lock_path.rmdir()
                    continue
            time.sleep(LOCK_RETRY)
    return False


def release_lock(task_id: str):
    lock_path = STATE_DIR / f"{task_id}.lock"
    try:
        pid_file = lock_path / ".pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            # Only remove the lock if WE hold it (prevents removing a
            # lock re-acquired by another process after we were preempted)
            if pid != str(os.getpid()):
                return
            pid_file.unlink()
        lock_path.rmdir()
    except FileNotFoundError:
        pass


def atomic_write(path: Path, data: dict):
    """Write to a unique .tmp, then rename (atomic on POSIX), then fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(
        f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp"
    )
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, path)
    finally:
        # Clean up on failure (e.g. exception mid-dump)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def save_state(task_id: str, data: dict, merge: bool = False):
    """Save state atomically. Merge or replace."""
    validate_task_id(task_id)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not acquire_lock(task_id):
        print(f"ERROR: Could not acquire lock for {task_id}", file=sys.stderr)
        sys.exit(1)

    try:
        path = STATE_DIR / f"{task_id}.json"
        if merge and path.exists():
            try:
                existing = json.loads(path.read_text())
            except (json.JSONDecodeError, Exception):
                existing = {"schema_version": SCHEMA_VERSION, "task_id": task_id}
            # Deep merge
            for key, value in data.items():
                if isinstance(value, dict) and isinstance(existing.get(key), dict):
                    existing[key].update(value)
                else:
                    existing[key] = value
            existing["last_checkpoint"] = datetime.now(timezone.utc).isoformat()
            atomic_write(path, existing)
        else:
            data["schema_version"] = SCHEMA_VERSION
            data["task_id"] = task_id
            data["last_checkpoint"] = datetime.now(timezone.utc).isoformat()
            atomic_write(path, data)

        # Update CURRENT file
        current_path = STATE_DIR / "CURRENT"
        current_path.write_text(task_id)
    finally:
        release_lock(task_id)


def read_state(task_id: str = None, field: str = None):
    """Read state. Optionally extract a dot-notation field."""
    if task_id is None:
        task_id = get_current_task_id()
    if task_id is None:
        sys.exit(1)
    # M7 fix: validate on the read path too (CURRENT file can be poisoned)
    try:
        validate_task_id(task_id)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    path = STATE_DIR / f"{task_id}.json"
    if not path.exists():
        sys.exit(1)

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, Exception) as e:
        # Recover: return minimal state
        data = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "status": "corrupted",
            "recovered": True,
            "recovery_note": str(e)
        }

    if field:
        keys = field.split(".")
        val = data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                sys.exit(1)
        if val is None:
            sys.exit(1)
        print(json.dumps(val, default=str))
    else:
        print(json.dumps(data, indent=2, default=str))


def list_states():
    """List all state files with metadata."""
    if not STATE_DIR.exists():
        print("No state directory found.")
        return

    states = []
    for f in sorted(STATE_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            states.append({
                "task_id": data.get("task_id", f.stem),
                "status": data.get("status", "unknown"),
                "stage": data.get("stage", "unknown"),
                "last_checkpoint": data.get("last_checkpoint", "unknown"),
                "needs_resume": data.get("needs_resume", False)
            })
        except Exception:
            states.append({
                "task_id": f.stem,
                "status": "corrupted",
                "stage": "unknown",
                "last_checkpoint": "unknown",
                "needs_resume": False
            })

    print(json.dumps(states, indent=2))


def prune_states(older_than: str, force: bool = False):
    """Prune state files older than N days."""
    # Parse "7d", "30d", etc.
    try:
        days = int(older_than.rstrip("d"))
    except ValueError:
        print(f"ERROR: Invalid format '{older_than}'. Use '7d', '30d', etc.", file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if not STATE_DIR.exists():
        return

    pruned = []
    for f in STATE_DIR.glob("*.json"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                if force:
                    f.unlink()
                    pruned.append(f.name)
                else:
                    pruned.append(f"{f.name} (dry run)")
        except Exception:
            pass

    if pruned:
        print(json.dumps(pruned, indent=2))
    else:
        print("Nothing to prune.")


def get_current_task_id() -> str:
    """Read current task ID from CURRENT file."""
    current_path = STATE_DIR / "CURRENT"
    if current_path.exists():
        return current_path.read_text().strip()
    # Fallback: env var
    return os.environ.get("CURRENT_TASK_ID")


def set_current_task_id(task_id: str):
    """Set the current task ID."""
    # M7 fix: validate before writing CURRENT (a poisoned CURRENT poisons all reads)
    try:
        validate_task_id(task_id)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    current_path = STATE_DIR / "CURRENT"
    current_path.write_text(task_id)
    print(f"Current task ID set to: {task_id}")


def main():
    parser = argparse.ArgumentParser(description="Task state persistence")
    subparsers = parser.add_subparsers(dest="command")

    # save
    save_parser = subparsers.add_parser("save")
    save_parser.add_argument("--task-id", required=True)
    save_parser.add_argument("--set", help="JSON to set (replace)")
    save_parser.add_argument("--merge", help="JSON to merge (update)")

    # read
    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("--task-id", default=None)
    read_parser.add_argument("--field", default=None)

    # list
    subparsers.add_parser("list")

    # prune
    prune_parser = subparsers.add_parser("prune")
    prune_parser.add_argument("--older-than", required=True)
    prune_parser.add_argument("--force", action="store_true")

    # current
    current_parser = subparsers.add_parser("current")
    current_parser.add_argument("--set", default=None)

    args = parser.parse_args()

    if args.command == "save":
        if args.set:
            data = json.loads(args.set)
            save_state(args.task_id, data, merge=False)
        elif args.merge:
            data = json.loads(args.merge)
            save_state(args.task_id, data, merge=True)
        else:
            print("ERROR: --set or --merge required", file=sys.stderr)
            sys.exit(1)
    elif args.command == "read":
        read_state(args.task_id, args.field)
    elif args.command == "list":
        list_states()
    elif args.command == "prune":
        prune_states(args.older_than, args.force)
    elif args.command == "current":
        if args.set:
            set_current_task_id(args.set)
        else:
            tid = get_current_task_id()
            if tid:
                print(tid)
            else:
                sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
