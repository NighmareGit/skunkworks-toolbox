#!/usr/bin/env python3
"""tool_preflight.py — Environment validator (FM1: Environment Drift fix).

Verifies the execution environment BEFORE dispatching a sub-agent.
Checks: cwd exists, inputs resolve, disk space, writable directories.

Usage:
  tool_preflight.py --cwd <dir> --inputs <file1>[,<file2>,...] [--min-disk-mb 500]

Exit codes:
  0 = all checks passed (safe to dispatch)
  1 = cwd invalid
  2 = one or more checks failed (input missing / disk / strict)
  4 = target directory not writable
  5 = argument error
"""

import argparse
import os
import shutil
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cwd")
    ap.add_argument("--inputs", default="")
    ap.add_argument("--min-disk-mb", type=int, default=500)
    ap.add_argument("--strict", action="store_true", default=False)
    try:
        args, unknown = ap.parse_known_args(argv)
    except SystemExit as e:
        # argparse exits 2 on bad values (e.g. --min-disk-mb abc) and 0 on -h;
        # remap the error case to this tool's documented arg-error code (5).
        return 0 if e.code in (None, 0) else 5
    if unknown:
        print(f"ERROR: Unknown arg: {unknown[0]}")
        return 5
    if args.cwd is None:
        print("ERROR: --cwd required")
        return 5

    cwd = args.cwd
    inputs = args.inputs
    min_disk_mb = args.min_disk_mb
    strict = args.strict

    passed = 0
    failed = 0
    warned = 0

    print("=== Pre-Flight Environment Check ===")
    print(f"cwd: {cwd}")
    print("")

    # Check 1: cwd exists and is a directory
    if not os.path.isdir(cwd):
        print(f"FAIL [cwd]: Directory does not exist: {cwd}")
        print(f"  Fix: mkdir -p {cwd}")
        return 1
    cwd_abs = os.path.abspath(cwd)
    print(f"PASS [cwd]: exists → {cwd_abs}")
    passed += 1

    # Check 2: cwd is writable
    if not os.access(cwd_abs, os.W_OK):
        print(f"FAIL [cwd]: Not writable: {cwd_abs}")
        return 4
    print("PASS [cwd]: writable")
    passed += 1

    # Check 3: Input files exist
    if inputs:
        for input_entry in inputs.split(","):
            # Resolve relative to cwd
            if not os.path.isabs(input_entry):
                inp = os.path.join(cwd_abs, input_entry)
            else:
                inp = input_entry
            if not os.path.isfile(inp):
                print(f"FAIL [input]: File not found: {inp}")
                # Diagnose (R1): portable wrong-dir check — if the missing file
                # exists at the same relative path in a SIBLING directory of the
                # project root, it was written to the wrong project. No hardcoded
                # project paths; works in any project layout.
                prefix = cwd_abs + os.sep
                if inp.startswith(prefix):
                    parent = os.path.dirname(cwd_abs)
                    rel = inp[len(prefix):]
                    if os.path.isdir(parent):
                        for name in sorted(os.listdir(parent)):
                            if name.startswith("."):
                                continue
                            cand_dir = os.path.join(parent, name)
                            if not os.path.isdir(cand_dir):
                                continue
                            if os.path.normpath(cand_dir) == os.path.normpath(cwd_abs):
                                continue
                            cand = os.path.join(cand_dir, rel)
                            if os.path.isfile(cand):
                                print(f"  DIAGNOSIS: Found in wrong project: {cand}")
                                print(f"  Fix: mv '{cand}' '{inp}'")
                                break
                failed += 1
            else:
                size = os.path.getsize(inp)
                print(f"PASS [input]: exists ({size} bytes) → {inp}")
                passed += 1

    # Check 4: Disk space on the target filesystem
    # (bash guards with `command -v df`; mirror that by skipping on stat failure)
    try:
        available_mb = shutil.disk_usage(cwd_abs).free // (1024 * 1024)
    except OSError:
        print(f"WARN [disk]: cannot stat filesystem for {cwd_abs} — skipping disk check")
        warned += 1
    else:
        if available_mb < min_disk_mb:
            print(f"FAIL [disk]: Insufficient space ({available_mb}MB < {min_disk_mb}MB min)")
            failed += 1
        else:
            print(f"PASS [disk]: {available_mb}MB available (min {min_disk_mb}MB)")
            passed += 1

    # Check 5: Common project directories exist (non-fatal warning)
    for subdir in ("docs", ".scratch"):
        if not os.path.isdir(os.path.join(cwd_abs, subdir)):
            print(f"WARN [layout]: Expected subdirectory missing: {subdir}")
            warned += 1

    # Check 6: Verify we're not in a known "wrong" project (heuristic, R1)
    # Configurable via WRONG_PROJECT_DIRS (space-separated absolute dirs). The
    # reference deployment used to hardcode a sibling dir; new projects set
    # their own, or leave empty (the sibling wrong-dir diagnosis above still
    # covers FM1).
    for wd in os.environ.get("WRONG_PROJECT_DIRS", "").split():
        if cwd_abs == wd:
            print(f"WARN [project]: cwd is {wd} — is this the right project?")
            print(f"  Expected: {cwd_abs}")
            warned += 1
            if strict:
                print("FAIL [project]: Strict mode — refusing to dispatch from wrong project")
                failed += 1

    # Summary
    print("")
    print("=== Pre-Flight Summary ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Warnings: {warned}")

    if failed > 0:
        print("")
        print("RESULT: FAIL — fix issues before dispatching")
        return 2

    print("")
    print("RESULT: PASS — environment validated, safe to dispatch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
