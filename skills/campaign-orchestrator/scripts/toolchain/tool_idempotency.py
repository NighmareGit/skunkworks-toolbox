#!/usr/bin/env python3
"""tool_idempotency.py — Duplicate work guard (BS3: No Idempotency fix).

Before dispatching, checks if a task is already done AND verified.
Prevents re-doing work that's already complete (avoids duplicates like
t1-primary-search.md + t1-primary-search-v2.md).

Usage:
  tool_idempotency.py --task-id <id> --outputs <file1>[,<file2>,...] [--ledger <path>] [--min-bytes 100]

Exit codes:
  0 = not done (safe to dispatch)
  1 = already done + verified (SKIP — do not dispatch)
  2 = outputs exist but unverified (verify first)
  3 = argument error
"""

import argparse
import json
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task-id")
    ap.add_argument("--outputs")
    ap.add_argument("--ledger", default="docs/research/task-atomization-low-cap-agents/TASKS.json")
    ap.add_argument("--min-bytes", type=int, default=100)
    try:
        args, unknown = ap.parse_known_args(argv)
    except SystemExit as e:
        # argparse exits 2 on bad values and 0 on -h; remap the error case to
        # this tool's documented arg-error code (3).
        return 0 if e.code in (None, 0) else 3
    if unknown:
        print(f"ERROR: Unknown arg: {unknown[0]}")
        return 3
    if args.task_id is None or args.outputs is None:
        print("ERROR: --task-id and --outputs required")
        return 3

    task_id = args.task_id
    outputs = args.outputs
    ledger = args.ledger
    min_bytes = args.min_bytes

    print("=== Idempotency Check ===")
    print(f"Task: {task_id}")
    print("")

    # Check 1: Look in ledger for task status
    if os.path.isfile(ledger):
        status = "not_found"
        verification = "not_found"
        try:
            with open(ledger) as f:
                data = json.load(f)
            if "tasks" in data and task_id in data["tasks"]:
                t = data["tasks"][task_id]
                if isinstance(t, dict):
                    status = t.get("status", "unknown")
                    verification = t.get("verification", "unverified")
            elif task_id in data:
                t = data[task_id]
                if isinstance(t, dict):
                    status = t.get("status", "unknown")
                    verification = t.get("verification", "unverified")
        except (OSError, json.JSONDecodeError, ValueError):
            pass

        print(f"Ledger status: {status} (verification: {verification})")

        if status == "done" and verification == "verified":
            print("")
            print("RESULT: SKIP — task already done and verified")
            print(f"  Task {task_id} is complete. Do not re-dispatch.")
            return 1
        elif status == "done" or status == "done_unverified":
            print("")
            print("RESULT: VERIFY — task marked done but unverified")
            print("  Run verification before deciding to re-dispatch")
            return 2
    else:
        print(f"Ledger not found: {ledger} (skipping ledger check)")

    # Check 2: Verify output files exist and meet minimum size
    print("")
    print("Checking output files:")
    all_exist = True
    all_valid = True

    for output in outputs.split(","):
        # Resolve relative paths
        if not os.path.isabs(output):
            output = os.path.join(os.getcwd(), output)

        if not os.path.isfile(output):
            print(f"  MISSING: {output}")
            all_exist = False
        else:
            size = os.path.getsize(output)
            if size < min_bytes:
                print(f"  TOO SMALL: {output} ({size} bytes < {min_bytes} min)")
                all_valid = False
            else:
                print(f"  EXISTS: {output} ({size} bytes)")

    print("")
    if all_exist and all_valid:
        print("RESULT: SKIP — all outputs exist and meet size threshold")
        print("  If outputs are correct, mark task done in ledger.")
        print("  If outputs are wrong, delete them first, then dispatch.")
        return 1
    elif all_exist and not all_valid:
        print("RESULT: RECHECK — outputs exist but some are too small")
        print("  Verify content quality. May need re-dispatch.")
        return 2
    else:
        print("RESULT: DISPATCH — outputs missing, safe to dispatch")
        return 0


if __name__ == "__main__":
    sys.exit(main())
