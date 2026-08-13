#!/usr/bin/env python3
"""dispatch-trace.py — campaign-layer DISPATCH_ID lineage (own layer, verified design).

Implements design decisions from the grok-build source investigation
(INVESTIGATION-FINDINGS.md + VERIFICATION.md):

  D1  DISPATCH_ID = fresh UUIDv7, namespaced `dc_<32-hex>` (no hyphens) so it can
      never collide with the harness namespaces (`wf_`, `auto:`, `c{value}`).
  D2  Own the id in the campaign layer; propagate via the subagent description
      and the brief registry; do NOT touch the wire protocol.
  D5  Persist it in the dispatch brief registry + decision log + workflow args.

Chain: pre-dispatch mints dc_ id -> brief.json (brief registry) -> orchestrator
spawns subagent (id rides in the description, e.g. "dispatch=dc_...") -> `link`
records the harness agent id into the brief -> decision log stamps the id ->
`trace` resolves the full chain from any entry point.

Usage:
  dispatch-trace.py mint                     # print a fresh dc_ UUIDv7 (for wrapper use)
  dispatch-trace.py link --dispatch-id ID --agent-id AID [--cwd DIR]
  dispatch-trace.py trace --dispatch-id ID [--cwd DIR]
  dispatch-trace.py trace --task-id TID [--cwd DIR]
  dispatch-trace.py trace --artifact PATH [--cwd DIR]
  dispatch-trace.py locate --dispatch-id ID [--cwd DIR]    # prints the brief.json path

Exit codes: 0 ok, 1 not found / validation, 2 usage.
"""

import argparse
import datetime
import json
import os
import random
import re
import sys
from pathlib import Path

DISPATCH_RE = re.compile(r"^dc_[0-9a-f]{32}$")
BRIEFS_REL = ".scratch/dispatch-briefs"


def uuid7_hex() -> str:
    """Real UUIDv7 (RFC 9562): 48-bit Unix-ms timestamp + random, hex, no hyphens."""
    ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    rand = random.getrandbits(74)
    # 48 bits time | 4 bits version (0111) | 12 bits rand_a | 2 bits variant (10) | 62 bits rand_b
    # (parenthesized shift: `(x & 0x0FFF) << 64` — without parens, `&` binds
    # tighter than `<<` and rand_a is silently always 0, wasting 12 of 74 bits)
    value = (ms << 80) | (0x7 << 76) | (((rand >> 62) & 0x0FFF) << 64) | (0x2 << 62) | (rand & ((1 << 62) - 1))
    return f"{value:032x}"


def mint() -> str:
    return f"dc_{uuid7_hex()}"


def briefs_dir(cwd: Path) -> Path:
    return cwd / BRIEFS_REL


def find_brief_for_dispatch(cwd: Path, dispatch_id: str) -> Path | None:
    bd = briefs_dir(cwd)
    if not bd.is_dir():
        return None
    for sub in sorted(bd.iterdir()):
        brief = sub / "brief.json"
        if brief.is_file():
            try:
                data = json.loads(brief.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("dispatch_id") == dispatch_id:
                return brief
    return None


def find_brief_for_task(cwd: Path, task_id: str) -> Path | None:
    brief = briefs_dir(cwd) / task_id / "brief.json"
    return brief if brief.is_file() else None


def find_brief_for_artifact(cwd: Path, artifact: str) -> Path | None:
    bd = briefs_dir(cwd)
    if not bd.is_dir():
        return None
    art_abs = str(Path(artifact).expanduser().resolve())
    for sub in sorted(bd.iterdir()):
        brief = sub / "brief.json"
        if brief.is_file():
            try:
                data = json.loads(brief.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            outputs = data.get("outputs", "")
            for out in outputs.split(","):
                out = out.strip()
                if out and str(Path(out).expanduser().resolve()) == art_abs:
                    return brief
    return None


def read_brief(path: Path) -> dict:
    return json.loads(path.read_text())


def cmd_mint(_args) -> int:
    print(mint())
    return 0


def cmd_link(args) -> int:
    cwd = Path(args.cwd or os.getcwd())
    if not DISPATCH_RE.match(args.dispatch_id):
        print(f"ERROR: malformed dispatch_id '{args.dispatch_id}' (expected dc_<32 hex>)", file=sys.stderr)
        return 1
    brief = find_brief_for_dispatch(cwd, args.dispatch_id)
    if brief is None:
        print(f"ERROR: no brief registry entry for dispatch_id {args.dispatch_id} under {briefs_dir(cwd)}",
              file=sys.stderr)
        print("  Run toolchain.py dispatch --mode pre first (it mints and persists the id).", file=sys.stderr)
        return 1
    data = read_brief(brief)
    # Multiple agent ids (e.g. a workflow wave: workers + verifiers) are passed
    # comma-separated in --agent-id. Store the full list; keep the legacy single
    # `agent_id` field as the PRIMARY agent (first worker) for back-compat.
    ids = [a.strip() for a in args.agent_id.split(",") if a.strip()]
    if not ids:
        print("ERROR: --agent-id empty", file=sys.stderr)
        return 2
    data["agent_id"] = ids[0]
    data["agent_ids"] = ids
    data["agent_linked_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # atomic write
    tmp = brief.with_name("brief.json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(brief)
    # State machine (single source of truth in dispatch-state.py): linking the
    # harness agent id moves the dispatch to 'spawned'. Non-fatal — the brief
    # write above already succeeded.
    import subprocess
    state_py = Path(__file__).resolve().parent / "dispatch-state.py"
    subprocess.run(
        [sys.executable, str(state_py), "transition",
         "--dispatch-id", args.dispatch_id, "--to", "spawned", "--cwd", str(cwd)],
        capture_output=True, check=False,
    )
    print(f"Linked {len(ids)} agent(s) ({', '.join(ids)}) -> dispatch {args.dispatch_id} in {brief}")
    return 0


def cmd_trace(args) -> int:
    cwd = Path(args.cwd or os.getcwd())
    brief = None
    entry = None
    if args.dispatch_id:
        if not DISPATCH_RE.match(args.dispatch_id):
            print(f"ERROR: malformed dispatch_id '{args.dispatch_id}'", file=sys.stderr)
            return 1
        entry = f"dispatch_id={args.dispatch_id}"
        brief = find_brief_for_dispatch(cwd, args.dispatch_id)
    elif args.task_id:
        entry = f"task_id={args.task_id}"
        brief = find_brief_for_task(cwd, args.task_id)
    elif args.artifact:
        entry = f"artifact={args.artifact}"
        brief = find_brief_for_artifact(cwd, args.artifact)
    else:
        print("ERROR: one of --dispatch-id | --task-id | --artifact required", file=sys.stderr)
        return 2

    if brief is None:
        print(f"TRACE: no brief found for {entry}")
        print("  Chain incomplete: pre-dispatch never ran (or brief registry cleared).")
        return 1

    data = read_brief(brief)
    print(f"=== DISPATCH TRACE ({entry}) ===")
    print(f"  brief registry : {brief}")
    print(f"  dispatch_id    : {data.get('dispatch_id', '(missing)')}")
    print(f"  task_id        : {data.get('task_id', '?')}")
    print(f"  role           : {data.get('role', 'unknown')}")
    print(f"  cwd            : {data.get('cwd', '?')}")
    print(f"  created        : {data.get('created', '?')}")
    print(f"  outputs        : {data.get('outputs', '')}")
    print(f"  min_bytes      : {data.get('min_bytes', '?')}")
    print(f"  format         : {data.get('format', 'any')}")
    print(f"  brief_sha256   : {data.get('brief_sha256', '(none)')}")
    agent_id = data.get("agent_id")
    agent_ids = data.get("agent_ids")
    if agent_ids:
        print(f"  agent_ids      : {', '.join(agent_ids)}")
    elif agent_id:
        print(f"  agent_id       : {agent_id}")
    else:
        print(f"  agent_id       : (not linked — orchestrator must run: "
              f"dispatch-trace.py link --dispatch-id {data.get('dispatch_id', '')} --agent-id <harness-id>)")
    if data.get("agent_linked_at"):
        print(f"  agent linked   : {data['agent_linked_at']}")
    # decision log entries mentioning this dispatch id
    dec = cwd / ".scratch" / "task-state" / "DECISIONS.md"
    if data.get("dispatch_id") and dec.is_file():
        hits = [ln for ln in dec.read_text(errors="replace").splitlines() if data["dispatch_id"] in ln]
        print(f"  decision log   : {len(hits)} entry/entries mention {data['dispatch_id']}")
    return 0


def cmd_locate(args) -> int:
    cwd = Path(args.cwd or os.getcwd())
    if not DISPATCH_RE.match(args.dispatch_id):
        print(f"ERROR: malformed dispatch_id '{args.dispatch_id}'", file=sys.stderr)
        return 1
    brief = find_brief_for_dispatch(cwd, args.dispatch_id)
    if brief is None:
        print(f"ERROR: no brief for {args.dispatch_id}", file=sys.stderr)
        return 1
    print(brief)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("mint")
    p.set_defaults(fn=cmd_mint)

    p = sub.add_parser("link")
    p.add_argument("--dispatch-id", required=True)
    p.add_argument("--agent-id", required=True, help="harness agent id(s); comma-separated for a workflow wave")
    p.add_argument("--cwd")
    p.set_defaults(fn=cmd_link)

    p = sub.add_parser("trace")
    p.add_argument("--dispatch-id")
    p.add_argument("--task-id")
    p.add_argument("--artifact")
    p.add_argument("--cwd")
    p.set_defaults(fn=cmd_trace)

    p = sub.add_parser("locate")
    p.add_argument("--dispatch-id", required=True)
    p.add_argument("--cwd")
    p.set_defaults(fn=cmd_locate)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
