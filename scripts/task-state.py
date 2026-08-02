#!/usr/bin/env python3
"""
task-state.py — atomic read/write helper for ticket state files.

Schema (per ticket):
  {
    "ticket": "T0",
    "stage": "pending|read|implement|redteam|verify|review|mark",
    "status": "pending|in_progress|done|failed|blocked",
    "heartbeat": "ISO-8601 timestamp",
    "next_action": "...",
    "artifacts": ["worktrees/...", "branch ..."],
    "tool_history": ["cmd1", "cmd2", ...],   # tail (~10)
    "blocked_by": ["T0", "T2a"]
  }

Usage:
  task-state.py get <ticket>                       # print full JSON
  task-state.py get <ticket> <field>               # print one field
  task-state.py set <ticket> field=value [..]      # set fields (atomic write)
  task-state.py heartbeat <ticket>                 # update heartbeat to now
  task-state.py history <ticket> "cmd"             # append to tool_history (tail 10)
  task-state.py bump <ticket> stage=verify        # shortcut: set stage + heartbeat

Atomic write: writes to <file>.tmp then os.replace() (rename is atomic on POSIX).
"""

import json
import os
import sys
from datetime import datetime, timezone

STATE_DIR = os.environ.get(
    "TASK_STATE_DIR",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "task-state"
    )
)

def state_path(ticket):
    return os.path.join(STATE_DIR, f"{ticket}.json")

def load(ticket):
    p = state_path(ticket)
    if not os.path.exists(p):
        # init skeleton
        return {"ticket": ticket, "stage": "pending", "status": "pending",
                "heartbeat": now_iso(), "next_action": "", "artifacts": [],
                "tool_history": [], "blocked_by": []}
    with open(p) as f:
        return json.load(f)

def save(ticket, state):
    p = state_path(ticket)
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp, p)  # atomic on POSIX

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def parse_kv(s):
    if "=" not in s:
        raise ValueError(f"expected key=value, got: {s!r}")
    k, v = s.split("=", 1)
    # try JSON parse for non-strings
    try:
        v = json.loads(v)
    except (json.JSONDecodeError, ValueError):
        pass
    return k.strip(), v

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    ticket = sys.argv[2]

    if cmd == "get":
        state = load(ticket)
        if len(sys.argv) == 3:
            print(json.dumps(state, indent=2))
        else:
            field = sys.argv[3]
            print(state.get(field, f"<field {field} not present>"))

    elif cmd == "set":
        state = load(ticket)
        for kv in sys.argv[3:]:
            k, v = parse_kv(kv)
            state[k] = v
        state["heartbeat"] = now_iso()
        save(ticket, state)
        print(f"[{ticket}] updated: {', '.join(sys.argv[3:])}")

    elif cmd == "heartbeat":
        state = load(ticket)
        state["heartbeat"] = now_iso()
        if len(sys.argv) > 3:
            state["next_action"] = " ".join(sys.argv[3:])
        save(ticket, state)
        print(f"[{ticket}] heartbeat: {state['heartbeat']}")

    elif cmd == "history":
        if len(sys.argv) < 4:
            print("usage: task-state.py history <ticket> \"command\"")
            sys.exit(1)
        state = load(ticket)
        hist = state.setdefault("tool_history", [])
        hist.append(sys.argv[3])
        state["tool_history"] = hist[-10:]  # tail 10
        state["heartbeat"] = now_iso()
        save(ticket, state)
        print(f"[{ticket}] history appended (len={len(state['tool_history'])})")

    elif cmd == "bump":
        state = load(ticket)
        for kv in sys.argv[3:]:
            k, v = parse_kv(kv)
            state[k] = v
        state["heartbeat"] = now_iso()
        save(ticket, state)
        print(f"[{ticket}] bumped: stage={state.get('stage')} status={state.get('status')}")

    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
