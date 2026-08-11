#!/usr/bin/env python3
"""
task-ledger.py — Full CRUD over TASKS.json (the machine-readable task ledger).

The ledger is the single source of truth for campaign state. This script
provides create/read/update/delete operations plus reporting.

Usage:
    python3 task-ledger.py list [--phase P3] [--status done]
    python3 task-ledger.py show <task_id>
    python3 task-ledger.py update <task_id> --status done --verification verified
    python3 task-ledger.py update <task_id> --output "path/to/file.md"
    python3 task-ledger.py update <task_id> --issue "wrong_directory"
    python3 task-ledger.py add <task_id> <description> --phase P5 --depends D1,D2
    python3 task-ledger.py report
    python3 task-ledger.py issues
    python3 task-ledger.py ready  # tasks with all dependencies met
    python3 task-ledger.py drain  # next tasks to work (ready + pending)
    python3 task-ledger.py verify <task_id>  # mark verified
    python3 task-ledger.py phases  # summary by phase

Ledger path: docs/research/task-atomization-low-cap-agents/TASKS.json
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Project-ledger location (R4 resolution chain, identical in reference + bundle):
#   1. TASKS_LEDGER env or --ledger  → explicit pin
#   2. .scratch/task-state/TASKS.json → the generic convention (seeded by
#      bootstrap-project.sh; matches task-state.py / context-budget.py)
#   3. docs/research/task-atomization-low-cap-agents/TASKS.json → legacy path for
#      the reference project (kept so old campaigns work without layout changes)
def _resolve_default_ledger() -> Path:
    env = os.environ.get("TASKS_LEDGER")
    if env:
        return Path(env)
    generic = Path(".scratch/task-state/TASKS.json")
    if generic.exists():
        return generic
    legacy = Path("docs/research/task-atomization-low-cap-agents/TASKS.json")
    return legacy


DEFAULT_LEDGER = _resolve_default_ledger()

# Statuses that count as "done" for dependency purposes (exact match, not substring)
DONE_STATUSES = ("done",)
# Statuses that exist but must NOT unblock downstream work
BLOCKING_STATUSES = ("done_unverified", "failed", "blocked")


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict:
    if not path.exists():
        print(f"Ledger not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def save_ledger(data: dict, path: Path = DEFAULT_LEDGER):
    """Atomic write (tmp + rename) to prevent torn writes on crash."""
    data["updated"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def list_tasks(args):
    data = load_ledger()
    tasks = data.get("tasks", {})

    # Filter
    phase_filter = getattr(args, "phase", None)
    status_filter = getattr(args, "status", None)

    rows = []
    for tid, task in sorted(tasks.items()):
        if phase_filter and task.get("phase") != phase_filter:
            continue
        if status_filter and task.get("status") != status_filter:
            continue
        rows.append({
            "id": tid,
            "phase": task.get("phase", "?"),
            "status": task.get("status", "?"),
            "verification": task.get("verification", "?"),
            "description": task.get("description", "")[:60],
        })

    # Print table
    print(f"{'ID':<8} {'Phase':<6} {'Status':<18} {'Verify':<12} Description")
    print("-" * 90)
    for r in rows:
        print(f"{r['id']:<8} {r['phase']:<6} {r['status']:<18} {r['verification']:<12} {r['description']}")
    print(f"\nTotal: {len(rows)} tasks")


def show_task(args):
    data = load_ledger()
    tid = args.task_id
    tasks = data.get("tasks", {})

    if tid not in tasks:
        print(f"Task not found: {tid}")
        sys.exit(1)

    task = tasks[tid]
    print(f"=== Task: {tid} ===")
    print(f"Phase: {task.get('phase', '?')}")
    print(f"Status: {task.get('status', '?')}")
    print(f"Verification: {task.get('verification', '?')}")
    print(f"Description: {task.get('description', '')}")
    print(f"Depends on: {', '.join(task.get('depends_on', [])) or 'none'}")
    print(f"Outputs: {', '.join(task.get('outputs', [])) or 'none'}")
    if task.get("issues"):
        print(f"Issues: {', '.join(task['issues'])}")
    if task.get("note"):
        print(f"Note: {task['note']}")


def update_task(args):
    data = load_ledger()
    tid = args.task_id
    tasks = data.get("tasks", {})

    if tid not in tasks:
        print(f"Task not found: {tid}")
        sys.exit(1)

    task = tasks[tid]
    updated = False

    if hasattr(args, "status") and args.status:
        task["status"] = args.status
        updated = True

    if hasattr(args, "verification") and args.verification:
        task["verification"] = args.verification
        updated = True

    if hasattr(args, "output") and args.output:
        # Append to outputs list
        if "outputs" not in task:
            task["outputs"] = []
        if args.output not in task["outputs"]:
            task["outputs"].append(args.output)
        updated = True

    if hasattr(args, "issue") and args.issue:
        if "issues" not in task:
            task["issues"] = []
        task["issues"].append(args.issue)
        updated = True

    if updated:
        tasks[tid] = task
        data["tasks"] = tasks
        save_ledger(data)
        print(f"Updated: {tid}")
    else:
        print(f"No changes specified for {tid}")


def add_task(args):
    data = load_ledger()
    tid = args.task_id
    tasks = data.get("tasks", {})

    if tid in tasks:
        print(f"Task already exists: {tid}")
        sys.exit(1)

    task = {
        "phase": getattr(args, "phase", "P0"),
        "description": args.description,
        "status": getattr(args, "status", "pending"),
        "outputs": [],
        "depends_on": [],
        "issues": [],
        "verification": "unverified",
    }

    if hasattr(args, "depends") and args.depends:
        task["depends_on"] = [d.strip() for d in args.depends.split(",") if d.strip()]

    if hasattr(args, "outputs") and args.outputs:
        task["outputs"] = [o.strip() for o in args.outputs.split(",") if o.strip()]

    tasks[tid] = task
    data["tasks"] = tasks
    save_ledger(data)
    print(f"Added: {tid} [{task['status']}]")


def generate_report(args):
    data = load_ledger()
    tasks = data.get("tasks", {})

    # Count by status
    status_counts = {}
    phase_counts = {}
    verified_count = 0
    total = len(tasks)

    for tid, task in tasks.items():
        status = task.get("status", "unknown")
        phase = task.get("phase", "?")
        verification = task.get("verification", "unverified")

        status_counts[status] = status_counts.get(status, 0) + 1
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        if verification == "verified":
            verified_count += 1

    print("=" * 50)
    print("Task Ledger Report")
    print("=" * 50)
    print(f"Total tasks: {total}")
    print(f"Verified: {verified_count} ({verified_count/total*100:.0f}%)" if total > 0 else "Verified: 0")
    print()

    print("By Status:")
    for status, count in sorted(status_counts.items()):
        bar = "█" * count
        print(f"  {status:<20} {count:>3} {bar}")
    print()

    print("By Phase:")
    for phase in sorted(phase_counts.keys()):
        count = phase_counts[phase]
        # Count done in this phase
        done = sum(1 for t in tasks.values()
                   if t.get("phase") == phase and "done" in t.get("status", ""))
        print(f"  {phase}: {done}/{count} done")


def list_issues(args):
    data = load_ledger()
    tasks = data.get("tasks", {})

    print("=== Issue Log ===")
    found = False
    for tid, task in sorted(tasks.items()):
        if task.get("issues"):
            found = True
            print(f"\n{tid}: {task.get('description', '')[:50]}")
            for issue in task["issues"]:
                print(f"  - {issue}")

    if not found:
        print("No issues logged.")


def _deps_met(deps, tasks):
    """True only if ALL dependencies are exactly 'done' (never 'done_unverified')."""
    for dep in deps:
        dep_task = tasks.get(dep, {})
        if dep_task.get("status") not in DONE_STATUSES:
            return False
    return True


def find_ready(args):
    """Find tasks that are pending and have all dependencies met."""
    data = load_ledger()
    tasks = data.get("tasks", {})

    ready = []
    for tid, task in sorted(tasks.items()):
        if task.get("status") not in ("pending",):
            continue

        deps = task.get("depends_on", [])
        if _deps_met(deps, tasks):
            ready.append((tid, task))

    if not ready:
        print("No ready tasks (all pending tasks have unmet dependencies).")
        return

    print("=== Ready Tasks (dependencies met, ready to dispatch) ===")
    for tid, task in ready:
        print(f"  {tid}: {task.get('description', '')[:60]}")
        if task.get("depends_on"):
            print(f"    depends: {', '.join(task['depends_on'])}")


def find_drain(args):
    """Find next tasks to work — ready tasks in priority order."""
    data = load_ledger()
    tasks = data.get("tasks", {})

    ready = []
    for tid, task in sorted(tasks.items()):
        if task.get("status") not in ("pending",):
            continue

        deps = task.get("depends_on", [])
        if _deps_met(deps, tasks):
            ready.append((tid, task))

    if not ready:
        print("No tasks to drain. All pending tasks are blocked or all done.")
        return

    print("=== Drain Order (next tasks to work) ===")
    for i, (tid, task) in enumerate(ready, 1):
        phase = task.get("phase", "?")
        print(f"  {i}. [{phase}] {tid}: {task.get('description', '')[:55]}")


def verify_task(args):
    """Mark a task as verified — but only if outputs actually exist."""
    data = load_ledger()
    tid = args.task_id
    tasks = data.get("tasks", {})

    if tid not in tasks:
        print(f"Task not found: {tid}")
        sys.exit(1)

    outputs = tasks[tid].get("outputs", [])
    missing = [o for o in outputs if not Path(o).exists()]
    if missing:
        print(f"REFUSED: outputs missing — cannot mark {tid} verified:")
        for m in missing:
            print(f"  MISSING: {m}")
        sys.exit(1)

    if not outputs:
        print(f"WARN: {tid} has no declared outputs; marking verified anyway "
              f"(use toolchain.py contract --verify for a real check)")

    tasks[tid]["verification"] = "verified"
    data["tasks"] = tasks
    save_ledger(data)
    print(f"Verified: {tid}")


def phase_summary(args):
    """Summary by phase."""
    data = load_ledger()
    tasks = data.get("tasks", {})

    phases = {}
    for tid, task in tasks.items():
        phase = task.get("phase", "?")
        if phase not in phases:
            phases[phase] = {"total": 0, "done": 0, "verified": 0}
        phases[phase]["total"] += 1
        if "done" in task.get("status", ""):
            phases[phase]["done"] += 1
        if task.get("verification") == "verified":
            phases[phase]["verified"] += 1

    print("=== Phase Summary ===")
    print(f"{'Phase':<8} {'Total':>5} {'Done':>5} {'Verified':>8} {'Progress'}")
    print("-" * 50)
    for phase in sorted(phases.keys()):
        p = phases[phase]
        pct = p["done"] / p["total"] * 100 if p["total"] > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"{phase:<8} {p['total']:>5} {p['done']:>5} {p['verified']:>8} {bar} {pct:.0f}%")


def main():
    parser = argparse.ArgumentParser(description="Task ledger management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--phase", help="Filter by phase")
    list_parser.add_argument("--status", help="Filter by status")

    # show
    show_parser = subparsers.add_parser("show", help="Show task details")
    show_parser.add_argument("task_id")

    # update
    update_parser = subparsers.add_parser("update", help="Update task")
    update_parser.add_argument("task_id")
    update_parser.add_argument("--status", help="New status")
    update_parser.add_argument("--verification", help="Verification state")
    update_parser.add_argument("--output", help="Add output path")
    update_parser.add_argument("--issue", help="Add issue")

    # add
    add_parser = subparsers.add_parser("add", help="Add new task")
    add_parser.add_argument("task_id")
    add_parser.add_argument("description")
    add_parser.add_argument("--phase", default="P0")
    add_parser.add_argument("--status", default="pending")
    add_parser.add_argument("--depends", help="Comma-separated dependency IDs")
    add_parser.add_argument("--outputs", help="Comma-separated output paths")

    # report
    subparsers.add_parser("report", help="Generate summary report")

    # issues
    subparsers.add_parser("issues", help="List all issues")

    # ready
    subparsers.add_parser("ready", help="Find ready tasks (deps met)")

    # drain
    subparsers.add_parser("drain", help="Next tasks to work")

    # verify
    verify_parser = subparsers.add_parser("verify", help="Mark task verified")
    verify_parser.add_argument("task_id")

    # phases
    subparsers.add_parser("phases", help="Summary by phase")

    args = parser.parse_args()

    commands = {
        "list": list_tasks,
        "show": show_task,
        "update": update_task,
        "add": add_task,
        "report": generate_report,
        "issues": list_issues,
        "ready": find_ready,
        "drain": find_drain,
        "verify": verify_task,
        "phases": phase_summary,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
