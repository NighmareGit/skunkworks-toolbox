#!/usr/bin/env python3
"""decision-log.py — Decision audit trail (BS2: No Decision Log fix) [port of decision-log.sh].

Append-only decision log with structured entries.
Captures WHAT was decided, WHY, alternatives considered, and expected outcome.
This is the orchestrator's memory — enables audit, resume, and learning.

Usage:
  decision-log.py --decision "Rerun T1A with tighter scope" \\
    --rationale "T1A looped (49 calls, 13 min) — scope too broad" \\
    --alternatives "Kill and abandon / Reduce to 1 group" \\
    --outcome "Expect <20 calls, <5 min" \\
    [--task-id T1A] \\
    [--campaign atomic-grinder-research] \\
    [--log-file .scratch/task-state/DECISIONS.md]

  decision-log.py --list [--campaign <id>] [--log-file <path>]
  decision-log.py --last <n> [--log-file <path>]

Exit codes:
  0 = success
  1 = argument error
"""

import argparse
import datetime
import os
import sys
from pathlib import Path


DEFAULT_LOG_FILE = ".scratch/task-state/DECISIONS.md"


def build_entry(
    decision: str,
    rationale: str,
    alternatives: str,
    outcome: str,
    task_id: str,
    dispatch_id: str,
) -> str:
    """Build the byte-exact entry block matching the bash source format."""
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task = task_id if task_id else "orchestration"
    alt = alternatives if alternatives else "none"
    out = outcome if outcome else "not specified"

    lines = [
        f"## {ts} | {task}",
        "",
        f"**DECISION:** {decision}",
        "",
        f"**RATIONALE:** {rationale}",
        "",
        f"**ALTERNATIVES CONSIDERED:** {alt}",
        "",
        f"**EXPECTED OUTCOME:** {out}",
        "",
    ]
    if dispatch_id:
        lines.append(f"**DISPATCH_ID:** {dispatch_id}")
        lines.append("")
    lines.append("---")
    # `echo "$ENTRY" >> file` appends one trailing newline.
    return "\n".join(lines) + "\n"


def build_header(campaign: str) -> str:
    return (
        f"# Decision Log — {campaign}\n"
        "\n"
        "> Append-only audit trail of orchestration decisions.\n"
        "> Each entry captures WHAT, WHY, alternatives, and expected outcome.\n"
        "\n"
        "---\n"
    )


def cmd_log(args) -> int:
    if not args.decision or not args.rationale:
        print("ERROR: --decision and --rationale required")
        return 1

    log_file = Path(args.log_file)
    entry = build_entry(
        args.decision,
        args.rationale,
        args.alternatives or "",
        args.outcome or "",
        args.task_id or "",
        args.dispatch_id or "",
    )

    if not log_file.exists():
        log_file.write_text(build_header(args.campaign))

    with log_file.open("a", newline="") as fh:
        fh.write(entry)

    task = args.task_id if args.task_id else "orchestration"
    print(f"Decision logged to: {args.log_file}")
    print(f"  Task: {task}")
    print(f"  Decision: {args.decision[:80]}...")
    return 0


def cmd_list(args) -> int:
    log_file = Path(args.log_file)
    if not log_file.exists():
        print(f"No decision log found: {args.log_file}")
        return 0
    # errors="replace": a non-UTF8 byte in a log line must not traceback
    # (bash `cat` passes arbitrary bytes through; port must do the same).
    sys.stdout.write(log_file.read_text(errors="replace"))
    return 0


def cmd_last(args) -> int:
    log_file = Path(args.log_file)
    if not log_file.exists():
        print(f"No decision log found: {args.log_file}")
        return 0

    content = log_file.read_text(errors="replace")
    # Mirror the embedded bash python3 one-liner exactly.
    entries = content.split("---")
    entries = [e.strip() for e in entries if "##" in e and "20" in e]

    n = args.last
    for entry in entries[-n:]:
        print(entry)
        print("---")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], add_help=False)
    ap.add_argument("--decision")
    ap.add_argument("--rationale")
    ap.add_argument("--alternatives")
    ap.add_argument("--outcome")
    ap.add_argument("--task-id")
    ap.add_argument("--dispatch-id")
    ap.add_argument("--campaign", default=os.environ.get("CAMPAIGN_ID", ""))
    ap.add_argument("--log-file", default=DEFAULT_LOG_FILE)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--last", type=int, default=None)

    try:
        args, unknown = ap.parse_known_args(argv)
    except SystemExit as e:
        # argparse exits 2 on bad values (e.g. --last abc) and 0 on -h/--help;
        # remap the error case to this tool's documented arg-error code (1).
        return 0 if e.code in (None, 0) else 1

    # Mirror bash: unknown args are an argument error -> exit 1.
    # The source defines no -h/--help, so -h also falls here.
    if unknown:
        print(f"ERROR: Unknown arg: {unknown[0]}")
        return 1

    # Ensure log directory exists (mirrors `mkdir -p "$(dirname "$LOG_FILE")"`).
    Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)

    if args.list:
        return cmd_list(args)
    if args.last is not None:
        return cmd_last(args)
    return cmd_log(args)


if __name__ == "__main__":
    sys.exit(main())
