#!/usr/bin/env python3
"""wf-guard.py — pre-dispatch liveness gate for workflow runs.

WHY (2026-08-11 incident): twice a "dead" workflow was relaunched while its
agents were still executing (v1: state frozen "active" after a host restart,
agents orphaned but alive; v2: state "cancelled" but agent subprocesses kept
running for ~8 more minutes). Run state is NOT a liveness oracle in either
direction — the only ground truth is agent metas + live processes.

This guard blocks launching/relaunching a workflow when a prior run of the
same workflow still has live agents or matching workload processes.

Usage:
  python3 wf-guard.py --name lower-stage-bench-2 --pattern "benchmarks.py"
  python3 wf-guard.py --name lower-stage-bench-2 --pattern "benchmarks.py" --exclude "run_lsv2_local" --json

Exit codes:
  0  CLEAR          — no live work for this workflow; safe to launch
  1  LIVE           — a run has running agents or matching processes; DO NOT launch

Pure stdlib. Scan is read-only. Never kills anything.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

LIVE_STATUSES = {"running", "active", "started"}

def sessions_root() -> str:
    return os.path.expanduser("~/.grok/sessions")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def find_runs(name: str):
    """Yield (session_dir, run_id, state, state_path, state_mtime) for runs whose
    display name equals `name` or starts with `name-` (the tool suffixes dupes).

    Session layout is nested: sessions/<encoded-workspace>/<session-id>/workflows/<rid>/.
    Walk to max depth 4 (root + 3) so the encoded workspace level is handled.
    """
    root = sessions_root()
    if not os.path.isdir(root):
        return
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth > 4:
            dirnames[:] = []
            continue
        if os.path.basename(dirpath) != "workflows":
            continue
        session_dir = os.path.dirname(dirpath)
        if not os.path.isdir(os.path.join(session_dir, "subagents")):
            continue
        for run_id in sorted(os.listdir(dirpath)):
            sp = os.path.join(dirpath, run_id, "state.json")
            if not os.path.isfile(sp):
                continue
            try:
                with open(sp, "r", encoding="utf-8") as fh:
                    state = json.load(fh).get("state", {})
            except Exception:
                state = {}
            run_name = state.get("name") or ""
            if run_name != name and not run_name.startswith(name + "-"):
                continue
            mtime = os.path.getmtime(sp)
            yield session_dir, run_id, state, sp, mtime

def agent_liveness(session_dir: str, state: dict):
    """Return (live_agents, all_agents, notes) for one run's agents."""
    live, total, notes = [], [], []
    for a in state.get("agents", []):
        aid = a.get("agent_id")
        label = a.get("label") or aid
        total.append(label)
        if not aid:
            continue
        meta_path = os.path.join(session_dir, "subagents", aid, "meta.json")
        if not os.path.isfile(meta_path):
            notes.append(f"{label}: meta.json missing (fail-closed)")
            live.append(label)
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception as e:
            notes.append(f"{label}: meta unreadable ({e})")
            live.append(label)
            continue
        status = str(meta.get("status") or "")
        completed = meta.get("completed_at")
        if status in LIVE_STATUSES and not completed:
            live.append(label)
            notes.append(f"{label}: {status} since {str(meta.get('started_at'))[:19]}, no completed_at")
        elif completed:
            notes.append(f"{label}: {status} at {str(completed)[:19]}")
        else:
            notes.append(f"{label}: status={status!r}, completed_at absent (fail-closed)")
            live.append(label)
    return live, total, notes

def live_processes(pattern: str, exclude: str):
    """Regex-match `ps -eo pid,ppid,args`; never match ourselves."""
    self_pid = str(os.getpid())
    hits = []
    if not pattern:
        return hits
    pat = re.compile(pattern)
    excl = re.compile(exclude) if exclude else None
    try:
        out = subprocess.run(["ps", "-eo", "pid,ppid,args"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return hits
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, ppid, args = parts[0], parts[1], parts[2]
        if pid == self_pid:
            continue
        if excl and excl.search(args):
            continue
        if pat.search(args):
            hits.append((pid, ppid, args[:160]))
    return hits

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="workflow display name to guard (substring on suffixed dupes)")
    ap.add_argument("--pattern", default="", help="regex matched against process args (e.g. 'benchmarks.py')")
    ap.add_argument("--exclude", default="", help="regex of processes to ignore (e.g. your local serial runner)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    runs = list(find_runs(args.name))
    live_agents, all_labels, notes, run_summaries = [], [], [], []
    for sdir, run_id, state, sp, mtime in runs:
        status = state.get("status", "?")
        live, total, n = agent_liveness(sdir, state)
        live_agents += live
        all_labels += total
        notes += n
        run_summaries.append({
            "run_id": run_id,
            "status": status,
            "phase": state.get("current_phase"),
            "state_mtime": datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds"),
            "agents": total,
            "live_agents": live,
        })

    procs = live_processes(args.pattern, args.exclude)

    if live_agents or procs:
        verdict, code = "LIVE", 1
    else:
        verdict, code = "CLEAR", 0

    report = {
        "verdict": verdict,
        "exit_code": code,
        "checked_at": now_iso(),
        "workflow": args.name,
        "matching_runs": len(runs),
        "runs": run_summaries,
        "live_agent_labels": live_agents,
        "live_process_count": len(procs),
        "notes": notes,
        "processes": procs,
    }
    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        print(f"wf-guard: {verdict}  ({args.name}, {len(runs)} prior run(s), "
              f"{len(live_agents)} live agent(s), {len(procs)} matching process(es))")
        for r in run_summaries:
            print(f"  run {r['run_id'][:8]} status={r['status']} phase={r['phase']} "
                  f"state_mtime={r['state_mtime']} agents={r['agents']} live={r['live_agents']}")
        for pid, ppid, a in procs:
            print(f"  PROC {pid} (ppid {ppid}): {a}")
        for note in notes:
            print(f"  note: {note}")
    return code

if __name__ == "__main__":
    sys.exit(main())
