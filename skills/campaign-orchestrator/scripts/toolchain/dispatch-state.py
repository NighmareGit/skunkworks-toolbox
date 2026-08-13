#!/usr/bin/env python3
"""dispatch-state.py — the stateless-interpreter state machine (value-order completion).

The files ARE the state; the orchestrator is a deterministic reader + writer. Every
dispatch record (brief.json) carries an explicit status, and `next-action` computes THE
next command from files alone — so any session can boot anywhere, read the same state,
and continue with no/low friction.

States per dispatch:
    pending_spawn  -> pre-dispatch minted the DISPATCH_ID + wrote the brief
    spawned        -> dispatch-trace.py link recorded the harness agent id
    verified       -> post-dispatch verification passed (gates green)
    done           -> task advanced in the ledger
    failed         -> verification failed / recovery needed

Transitions (legal only):
    (none)        -> pending_spawn   (dispatch-wrapper --mode pre)
    pending_spawn -> spawned         (dispatch-trace.py link)
    spawned       -> verified        (dispatch-wrapper --mode post, success)
    spawned       -> failed          (dispatch-wrapper --mode post, failure)
    verified      -> done            (orchestrator advances the ledger)

Usage:
  dispatch-state.py transition --dispatch-id ID --to <state> [--cwd DIR]
  dispatch-state.py status [--cwd DIR]                  # table of dispatch states
  dispatch-state.py next-action [--cwd DIR]             # deterministic next commands
  dispatch-state.py handoff [--settle] [--cwd DIR]      # one-command session handoff (Side A)

Exit codes: 0 ok, 1 transition error / state error, 2 usage.
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

DISPATCH_RE = re.compile(r"^dc_[0-9a-f]{32}$")
STATES = ("pending_spawn", "spawned", "verified", "done", "failed")
# Legal transitions: from -> set(to)
TRANSITIONS = {
    "pending_spawn": {"spawned"},
    "spawned": {"verified", "failed"},
    "verified": {"done"},
    "done": set(),
    "failed": {"pending_spawn"},  # re-dispatch after recovery
}

BRIEFS_REL = ".scratch/dispatch-briefs"


def briefs_dir(cwd: Path) -> Path:
    return cwd / BRIEFS_REL


def all_briefs(cwd: Path) -> list[tuple[Path, dict]]:
    bd = briefs_dir(cwd)
    if not bd.is_dir():
        return []
    out = []
    for sub in sorted(bd.iterdir()):
        brief = sub / "brief.json"
        if brief.is_file():
            try:
                data = json.loads(brief.read_text())
                out.append((brief, data))
            except (OSError, json.JSONDecodeError):
                continue
    return out


def find_brief(cwd: Path, dispatch_id: str) -> tuple[Path, dict] | None:
    for brief, data in all_briefs(cwd):
        if data.get("dispatch_id") == dispatch_id:
            return brief, data
    return None


def write_brief(brief: Path, data: dict) -> None:
    tmp = brief.with_name("brief.json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(brief)


def cmd_transition(args) -> int:
    cwd = Path(args.cwd or os.getcwd())
    if not DISPATCH_RE.match(args.dispatch_id):
        print(f"ERROR: malformed dispatch_id '{args.dispatch_id}' (expected dc_<32 hex>)", file=sys.stderr)
        return 1
    if args.to not in STATES:
        print(f"ERROR: unknown state '{args.to}' (use: {', '.join(STATES)})", file=sys.stderr)
        return 1
    found = find_brief(cwd, args.dispatch_id)
    if found is None:
        print(f"ERROR: no brief for {args.dispatch_id} under {briefs_dir(cwd)} — run --mode pre first",
              file=sys.stderr)
        return 1
    brief, data = found
    # A brief written by pre-dispatch already IS pending_spawn even if the field
    # predates the state machine — treat missing status as the initial state.
    current = data.get("status") or "pending_spawn"
    if current == args.to:
        # Materialize the field when transitioning to the implicit initial state,
        # so `status` shows the explicit state machine rather than '(none)'.
        if "status" not in data and args.to == "pending_spawn":
            data["status"] = "pending_spawn"
            data["status_changed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            write_brief(brief, data)
        print(f"OK: already '{args.to}' (idempotent no-op)")
        return 0
    if current not in TRANSITIONS or args.to not in TRANSITIONS.get(current, set()):
        print(f"ERROR: illegal transition '{current}' -> '{args.to}' "
              f"(legal: {sorted(TRANSITIONS.get(current, set())) or 'terminal state'})", file=sys.stderr)
        return 1
    data["status"] = args.to
    data["status_changed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write_brief(brief, data)
    print(f"transitioned {args.dispatch_id}: {current or '(none)'} -> {args.to}")
    return 0


def cmd_status(args) -> int:
    cwd = Path(args.cwd or os.getcwd())
    briefs = all_briefs(cwd)
    if not briefs:
        print("No dispatch records found (no briefs under .scratch/dispatch-briefs/).")
        return 0
    print(f"{'TASK':<10} {'DISPATCH_ID':<36} {'STATUS':<13} {'AGENT':<24} {'CREATED':<20}")
    print("-" * 104)
    for brief, data in sorted(briefs, key=lambda b: b[1].get("created", "")):
        print(f"{str(data.get('task_id', '?')):<10} "
              f"{str(data.get('dispatch_id', '?')):<36} "
              f"{str(data.get('status') or 'pending_spawn'):<13} "
              f"{str(data.get('agent_id', '-')):<24} "
              f"{str(data.get('created', '')):<20}")
    return 0


def cmd_handoff(args) -> int:
    """One-command handoff (Side A, minimal).

    Settles the only MECHANICAL move (verified -> done) and reports exactly what
    the fresh session will handle on boot. Everything else is informational:
    spawned/failed/pending_spawn are resolved deterministically by next-action,
    so a handoff is safe without settling them.
    """
    cwd = Path(args.cwd or os.getcwd())
    briefs = all_briefs(cwd)
    if not briefs:
        # Fail LOUDLY when the cwd isn't a campaign at all — a silent
        # "nothing to hand off" in the wrong directory would let a real
        # campaign be skipped during a session handoff.
        ledger = cwd / ".scratch" / "task-state" / "TASKS.json"
        if ledger.is_file():
            print("HANDOFF: no dispatches in flight — nothing to settle (campaign exists).")
            return 0
        print(f"ERROR: no campaign state under {cwd} — run with --cwd <project-dir> "
              f"(the one containing .scratch/dispatch-briefs/)", file=sys.stderr)
        return 1

    settled = 0
    upcoming: list[tuple[str, str, str]] = []  # (tid, status, what-boot-does)
    for brief, data in briefs:
        status = data.get("status", "pending_spawn")
        tid = str(data.get("task_id", "?"))
        if status == "verified" and args.settle:
            data["status"] = "done"
            data["status_changed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            write_brief(brief, data)
            settled += 1
        elif status == "verified":
            upcoming.append((tid, status, "ADVANCE on boot (or re-run handoff --settle)"))
        elif status == "spawned":
            upcoming.append((tid, status, "VERIFY on boot: --mode post / post-workflow"))
        elif status == "failed":
            upcoming.append((tid, status, "RECOVER on boot: recovery-playbook or re-dispatch"))
        elif status == "pending_spawn":
            upcoming.append((tid, status, "DISPATCH on boot (safe — next-action handles it)"))
        # done: nothing to do

    if settled:
        print(f"HANDOFF: auto-advanced {settled} verified dispatch(es) -> done.")
    if upcoming:
        print("HANDOFF: the fresh session will handle these on boot (next-action, in order):")
        for tid, status, hint in upcoming:
            print(f"  - {tid:<12} {status:<14} {hint}")
    else:
        print("HANDOFF-READY: nothing unsettled — hand off and boot.")
    print("Fresh-session command: python3 .scratch/scripts/dispatch-state.py next-action --cwd <project>")
    return 0


def cmd_next_action(args) -> int:
    cwd = Path(args.cwd or os.getcwd())
    briefs = all_briefs(cwd)
    if not briefs:
        # fall back to ledger presence for a useful message
        ledger = cwd / ".scratch" / "task-state" / "TASKS.json"
        if ledger.is_file():
            print("NEXT-ACTION: no dispatches in flight; inspect the ledger for the first ready task.")
        else:
            print("NEXT-ACTION: no campaign state found — nothing to do.")
        return 0

    actions = []
    # Priority: in-flight (spawned) first, then ready-to-dispatch, then advances, then recovery.
    def priority(data: dict) -> int:
        return {"spawned": 0, "pending_spawn": 1, "verified": 2, "failed": 3, "done": 4}.get(
            data.get("status"), 1)

    for brief, data in sorted(briefs, key=lambda b: (priority(b[1]), b[1].get("created", ""))):
        status = data.get("status", "pending_spawn")
        tid = data.get("task_id", "?")
        did = data.get("dispatch_id", "?")
        if status == "spawned":
            actions.append(
                f"VERIFY   task {tid} (dispatch {did}) — run: "
                f"toolchain.py dispatch --mode post --task-id {tid} --cwd {data.get('cwd', cwd)}"
            )
        elif status == "pending_spawn":
            actions.append(
                f"DISPATCH task {tid} (dispatch {did}) — spawn subagent with 'dispatch={did}' in its "
                f"description, then: dispatch-trace.py link --dispatch-id {did} --agent-id <id>"
            )
        elif status == "verified":
            actions.append(
                f"ADVANCE  task {tid} (dispatch {did}) — mark done in the ledger (TASKS.json / "
                f"CAMPAIGN.json) + log the decision"
            )
        elif status == "failed":
            actions.append(
                f"RECOVER  task {tid} (dispatch {did}) — toolchain.py recovery --task-id {tid} "
                f"--symptom <...> or re-dispatch"
            )
        # done: no action

    if not actions:
        print("NEXT-ACTION: all dispatches done — nothing pending.")
        return 0
    print("NEXT-ACTION (in priority order — do the first, then re-run):")
    for i, a in enumerate(actions, 1):
        print(f"  {i}. {a}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("transition")
    p.add_argument("--dispatch-id", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--cwd")
    p.set_defaults(fn=cmd_transition)

    p = sub.add_parser("status")
    p.add_argument("--cwd")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("next-action")
    p.add_argument("--cwd")
    p.set_defaults(fn=cmd_next_action)

    p = sub.add_parser("handoff")
    p.add_argument("--settle", action="store_true",
                   help="auto-advance verified -> done (the only mechanical move); "
                        "spawned/failed/pending_spawn are left for next-action on boot")
    p.add_argument("--cwd")
    p.set_defaults(fn=cmd_handoff)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
