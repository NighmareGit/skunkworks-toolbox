#!/usr/bin/env python3
"""tool_recovery.py — Automated failure recovery (FM5: Recovery Absence fix).

Detects failure mode from symptoms, applies the matching recovery procedure.
Integrates with fix-workdir.py, verify-output.py, and output-contract.py.

Usage:
  tool_recovery.py --task-id <id> --symptom <symptom> [--cwd <dir>] [--output <path>] [--expected-output <path>]

Symptoms:
  wrong-dir        — Output written to wrong project directory
  missing-output   — Expected output file does not exist
  too-small        — Output exists but below min bytes
  wrong-format     — Output exists but wrong format (e.g., JSON instead of markdown)
  partial-output   — Output exists but incomplete (sub-agent timed out)
  timeout           — Sub-agent exceeded time limit
  loop              — Sub-agent stuck in loop (too many tool calls)
  derived-content  — Sub-agent created/derived content instead of reading inputs

Exit codes:
  0 = recovery applied successfully
  1 = recovery attempted but failed
  2 = unknown symptom / argument error
"""

import argparse
import json
import os
import sys

from tool_common import move_noclobber


VALID_SYMPTOMS = [
    "wrong-dir",
    "missing-output",
    "too-small",
    "wrong-format",
    "partial-output",
    "timeout",
    "loop",
    "derived-content",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task-id")
    ap.add_argument("--symptom")
    ap.add_argument("--cwd", default="")
    ap.add_argument("--output", default="")
    ap.add_argument("--expected-output", default="")
    ap.add_argument("--min-bytes", type=int, default=100)
    ap.add_argument("--format", default="any")
    args, unknown = ap.parse_known_args(argv)
    if unknown:
        print(f"ERROR: Unknown arg: {unknown[0]}")
        return 2
    if args.task_id is None or args.symptom is None:
        print("ERROR: --task-id and --symptom required")
        return 2

    task_id = args.task_id
    symptom = args.symptom
    cwd = args.cwd
    output = args.output
    expected_output = args.expected_output
    min_bytes = args.min_bytes
    fmt = args.format

    print("=== Recovery Playbook ===")
    print(f"Task: {task_id}")
    print(f"Symptom: {symptom}")
    print("")

    recovery_applied = False
    recovery_result = 0

    if symptom == "wrong-dir":
        print("Recovery: Wrong directory — moving the task's artifact to correct location")
        print("")

        if not cwd:
            cwd = os.getcwd()

        # SAFETY: wrong-dir recovery NEVER bulk-moves. It only moves the single
        # artifact named by --expected-output. Whole-project moves (the old
        # fix-workdir.py fallback) could migrate unrelated files or flip direction
        # on a cwd-heuristic misfire — that is worse than the bug being fixed.
        if not expected_output:
            print("  ERROR: --expected-output REQUIRED for wrong-dir recovery.")
            print("  Refusing to bulk-move (destructive). Pass the exact artifact path.")
            return 2

        # Determine source (wrong dir) and target (correct dir) PORTABLY (R1):
        # target = the project root (--cwd); source = a sibling dir containing
        # the same relative artifact. No hardcoded project pair. Can be pinned
        # explicitly via WRONG_PROJECT_SOURCE / WRONG_PROJECT_TARGET.
        target_dir = os.path.realpath(cwd)
        prefix = target_dir + os.sep
        if not expected_output.startswith(prefix):
            print(f"  ERROR: --expected-output must be under --cwd: {expected_output}")
            return 2
        rel_path = expected_output[len(prefix):]

        source_dir = os.environ.get("WRONG_PROJECT_SOURCE", "")
        if not source_dir:
            parent = os.path.dirname(target_dir)
            if os.path.isdir(parent):
                for name in sorted(os.listdir(parent)):
                    cand_dir = os.path.join(parent, name)
                    if not os.path.isdir(cand_dir):
                        continue
                    if os.path.normpath(cand_dir) == os.path.normpath(target_dir):
                        continue
                    if os.path.isfile(os.path.join(cand_dir, rel_path)):
                        source_dir = cand_dir
                        break
        if not source_dir:
            print(f"  ERROR: no sibling project contains '{rel_path}' — cannot infer wrong-dir source.")
            print("  Pin the pair explicitly with WRONG_PROJECT_SOURCE / WRONG_PROJECT_TARGET env.")
            return 2

        # Refuse if the target already exists with content (mv would clobber)
        if os.path.isfile(expected_output) and os.path.getsize(expected_output) > 0:
            print(f"  REFUSE: target already exists and is non-empty: {expected_output}")
            print("  Move it aside manually before retrying recovery.")
            return 1

        source_file = os.path.join(source_dir, rel_path)
        if os.path.isfile(source_file):
            os.makedirs(os.path.dirname(expected_output), exist_ok=True)
            # mv -n: never clobber a pre-existing target (EXDEV-safe via tool_common)
            if move_noclobber(source_file, expected_output):
                print(f"  MOVED: {source_file} → {expected_output}")
                recovery_applied = True
            else:
                print("  MOVE FAILED (mv -n refused or error)")
                recovery_result = 1
        else:
            print(f"  NOT FOUND in wrong dir: {source_file}")
            print("  Files may have already been moved or never written")
            recovery_result = 1

    elif symptom == "missing-output":
        print("Recovery: Missing output — checking for partial or wrong-location output")
        print("")

        if not expected_output:
            print("  ERROR: --expected-output required for missing-output recovery")
            return 2

        # Check if output exists in wrong directory (R1 — portable sibling search)
        wrong = ""
        if cwd:
            parent = os.path.dirname(os.path.realpath(cwd))
            cwd_abs = os.path.realpath(cwd)
            if expected_output.startswith(cwd_abs + os.sep):
                rel = expected_output[len(cwd_abs + os.sep):]
                if os.path.isdir(parent):
                    for name in sorted(os.listdir(parent)):
                        cand_dir = os.path.join(parent, name)
                        if not os.path.isdir(cand_dir):
                            continue
                        if os.path.normpath(cand_dir) == os.path.normpath(cwd_abs):
                            continue
                        cand = os.path.join(cand_dir, rel)
                        if os.path.isfile(cand):
                            wrong = cand
                            break
        if wrong:
            # M3 fix: refuse to clobber a healthy target; mirror wrong-dir hardening
            if os.path.isfile(expected_output) and os.path.getsize(expected_output) > 0:
                print(f"  REFUSE: target already exists and is non-empty: {expected_output}")
                print("  Move it aside manually before retrying recovery.")
                return 1
            print(f"  FOUND in wrong dir: {wrong}")
            os.makedirs(os.path.dirname(expected_output), exist_ok=True)
            # mv -n: never clobber (EXDEV-safe via tool_common)
            if move_noclobber(wrong, expected_output):
                print("  MOVED to correct location")
                recovery_applied = True
            else:
                print("  MOVE FAILED (mv -n refused or error)")
                recovery_result = 1

        # Check for partial output (.tmp files)
        if not recovery_applied:
            tmp_file = expected_output + ".tmp"
            if os.path.isfile(tmp_file):
                print(f"  FOUND partial output: {tmp_file}")
                print("  Sub-agent may have been interrupted")
                print("  Action: dispatch continuation agent with partial context")
                recovery_applied = True
                recovery_result = 2  # signal: needs continuation, not just move

        if not recovery_applied:
            print("  No output found anywhere — full re-dispatch needed")
            recovery_result = 1

    elif symptom == "too-small":
        print("Recovery: Output too small — likely partial or derived content")
        print("")

        if not output:
            print("  ERROR: --output required for too-small recovery")
            return 2

        try:
            actual_bytes = os.path.getsize(output)
        except OSError:
            actual_bytes = 0
        print(f"  Actual size: {actual_bytes} bytes (min: {min_bytes})")

        if actual_bytes < 50:
            print("  Output is near-empty — sub-agent likely failed early")
            print("  Action: re-dispatch with tighter scope")
            recovery_result = 1
        else:
            print("  Output is partial — sub-agent may have been cut off")
            print("  Action: dispatch continuation agent")
            recovery_applied = True
            recovery_result = 2  # signal: needs continuation

    elif symptom == "wrong-format":
        print("Recovery: Wrong format — attempting conversion or re-dispatch")
        print("")

        if not output:
            print("  ERROR: --output required for wrong-format recovery")
            return 2

        # If JSON was expected but got markdown (or vice versa), try conversion
        if fmt == "markdown":
            # Check if it's JSON that should be markdown
            try:
                with open(output) as f:
                    json.load(f)
                is_json = True
            except (OSError, json.JSONDecodeError, ValueError):
                is_json = False
            if is_json:
                print("  Output is JSON, expected markdown")
                print("  Action: re-dispatch with explicit format instruction")
                print("  Or: convert JSON to markdown with a script")
                recovery_result = 1

        if recovery_result == 0:
            print("  Cannot auto-convert — re-dispatch with stronger output contract")
            recovery_result = 1

    elif symptom == "partial-output":
        print("Recovery: Partial output — dispatch continuation agent")
        print("")

        if not output:
            print("  ERROR: --output required for partial-output recovery")
            return 2

        try:
            with open(output) as f:
                lines = f.read().count("\n")
        except OSError:
            lines = 0
        print(f"  Partial output has {lines} lines")
        print("  Action: dispatch continuation agent with:")
        print(f"    - Input: {output} (partial output to continue from)")
        print("    - Instruction: continue from where previous agent left off")
        recovery_applied = True
        recovery_result = 2  # signal: needs continuation dispatch

    elif symptom == "timeout":
        print("Recovery: Timeout — split task or reduce scope")
        print("")

        print("  Action options:")
        print("    1. Split task into smaller sub-tasks (dispatch multiple agents)")
        print("    2. Reduce input size (fewer papers, fewer search groups)")
        print("    3. Increase timeout (if infrastructure allows)")
        print("")
        print("  Recommendation: use scope-guard.py to find optimal split")
        recovery_result = 1

    elif symptom == "loop":
        print("Recovery: Loop detected — tighten scope and add tool-call limit")
        print("")

        print("  Action: re-dispatch with:")
        print("    - Explicit max tool-call limit in prompt")
        print("    - Smaller scope (fewer search groups)")
        print("    - Structured step-by-step instruction (prevents wandering)")
        print("")
        print("  Use: scope-guard.py check --description '...' to validate new scope")
        recovery_result = 1

    elif symptom == "derived-content":
        print("Recovery: Derived content — sub-agent didn't read inputs, made things up")
        print("")

        print("  Root cause: inputs were not accessible (wrong dir, missing files)")
        print("  Action:")
        print("    1. Verify inputs exist: toolchain.py preflight --cwd ... --inputs ...")
        print("    2. Use absolute paths in prompt")
        print("    3. Add explicit instruction: 'READ these files, do not derive content'")
        print("    4. Add post-dispatch verification: toolchain.py verify")
        recovery_result = 1

    else:
        print(f"ERROR: Unknown symptom '{symptom}'")
        print(f"Valid symptoms: {', '.join(VALID_SYMPTOMS)}")
        return 2

    # Summary (reached only by branches that did not return early)
    print("")
    print("=== Recovery Summary ===")
    if recovery_applied:
        print(f"Recovery applied: {symptom}")
        if recovery_result == 2:
            print("Next action: dispatch continuation agent")
    else:
        print(f"Recovery not auto-applicable for: {symptom}")
        print("Next action: manual intervention or re-dispatch")

    return recovery_result


if __name__ == "__main__":
    sys.exit(main())
