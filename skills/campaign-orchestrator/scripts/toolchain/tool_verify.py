#!/usr/bin/env python3
"""tool_verify.py — Post-dispatch output verification (FM3: Verification Vacuum fix).

Independently verifies sub-agent outputs. Does NOT trust self-report.
Checks: file exists (with wrong-dir detection), min bytes, format (markdown/json/yaml),
required sections, and line count.

Usage:
  tool_verify.py <expected_path> [options]

Options:
  --min-bytes <n>        Minimum file size (default: 100)
  --format <fmt>         markdown|json|yaml|any (default: any)
  --sections <s1,s2>     Required section headers (case-insensitive match)
  --min-lines <n>        Minimum line count (default: 0 = skip)
  --max-lines <n>        Maximum line count (default: 0 = skip)
  --contains <text>      File must contain this text
  --not-contains <text>  File must NOT contain this text
  --cwd <dir>            Project root for wrong-dir detection

Exit codes:
  0 = all checks passed
  1 = one or more checks failed
  2 = argument error
"""

import argparse
import os
import re
import sys


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-bytes", type=int, default=100)
    ap.add_argument("--format", default="any")
    ap.add_argument("--sections", default="")
    ap.add_argument("--min-lines", type=int, default=0)
    ap.add_argument("--max-lines", type=int, default=0)
    ap.add_argument("--contains", default="")
    ap.add_argument("--not-contains", default="")
    ap.add_argument("--cwd", default="")

    # First positional arg is the path (mirrors the bash: only if not a flag)
    rest = list(argv)
    expected_path = None
    if rest and not rest[0].startswith("--"):
        expected_path = rest[0]
        rest = rest[1:]

    args, unknown = ap.parse_known_args(rest)
    if unknown:
        print(f"ERROR: Unknown arg: {unknown[0]}")
        return 2

    if expected_path is None:
        print("ERROR: expected_path required")
        print("Usage: toolchain.py verify <path> [--min-bytes n] [--format fmt] [--sections s1,s2] [--min-lines n]")
        return 2

    min_bytes = args.min_bytes
    fmt = args.format
    sections = args.sections
    min_lines = args.min_lines
    max_lines = args.max_lines
    contains = args.contains
    not_contains = args.not_contains
    cwd = args.cwd

    # Resolve to absolute path if relative
    if not os.path.isabs(expected_path):
        expected_path = os.path.join(os.getcwd(), expected_path)

    pass_ = 0
    fail = 0
    checks = 0

    print("=== Output Verification ===")
    print(f"Path: {expected_path}")
    print(f"Contract: min_bytes={min_bytes}, format={fmt}")
    print("")

    # Check 1: File exists
    checks += 1
    if not os.path.isfile(expected_path):
        print("FAIL: File does not exist")

        # Diagnose: check wrong directory (R1 — portable sibling search)
        if cwd and expected_path.startswith(cwd + os.sep) and expected_path != cwd:
            parent = os.path.dirname(cwd)
            rel = expected_path[len(cwd) + 1:]
            if os.path.isdir(parent):
                for name in sorted(os.listdir(parent)):
                    if name.startswith("."):
                        continue
                    cand_dir = os.path.join(parent, name)
                    if not os.path.isdir(cand_dir):
                        continue
                    if os.path.normpath(cand_dir) == os.path.normpath(cwd):
                        continue
                    cand = os.path.join(cand_dir, rel)
                    if os.path.isfile(cand):
                        wrong = cand.rstrip("/")
                        print(f"  FOUND in wrong directory: {wrong}")
                        print(f"  Fix: mv '{wrong}' '{expected_path}'")
                        print(f"  Or:  python3 .scratch/scripts/toolchain.py fix-workdir")
                        break

        # Check for partial output (.tmp)
        if os.path.isfile(expected_path + ".tmp"):
            print(f"  FOUND partial output: {expected_path}.tmp (sub-agent interrupted)")

        print("")
        print(f"=== VERIFICATION FAILED ({fail} failures) ===")
        return 1

    print("PASS: File exists")
    pass_ += 1

    # Read file content once for the checks below
    with open(expected_path, errors="replace") as f:
        content = f.read()
    lines = content.splitlines()

    # Check 2: File size
    checks += 1
    actual_bytes = os.path.getsize(expected_path)
    if actual_bytes < min_bytes:
        print(f"FAIL: File too small ({actual_bytes} bytes < {min_bytes} min)")
        print("  Possible causes: partial output, derived content, or early termination")
        fail += 1
    else:
        print(f"PASS: File size OK ({actual_bytes} bytes >= {min_bytes})")
        pass_ += 1

    # Check 3: Format validation
    checks += 1
    if fmt == "markdown":
        first10 = lines[:10]
        if any(line.startswith("#") for line in first10):
            print("PASS: Markdown format (has # header)")
            pass_ += 1
        else:
            print("FAIL: No markdown header found in first 10 lines")
            print(f"  First line: {lines[0] if lines else ''}")
            fail += 1
    elif fmt == "json":
        import json
        try:
            json.loads(content)
            print("PASS: Valid JSON")
            pass_ += 1
        except Exception:
            print("FAIL: Not valid JSON")
            fail += 1
    elif fmt == "yaml":
        try:
            import yaml
        except ImportError:
            # Best-effort: PyYAML unavailable -> skip (consistent with the
            # source's failure path of shelling out to `python3 -c "import yaml"`).
            print(f"SKIP: No format check for '{fmt}'")
            pass_ += 1
        else:
            try:
                yaml.safe_load(content)
                print("PASS: Valid YAML")
                pass_ += 1
            except Exception:
                print("FAIL: Not valid YAML")
                fail += 1
    elif fmt in ("any", "text"):
        print(f"SKIP: No format check for '{fmt}'")
        pass_ += 1
    else:
        print(f"WARN: Unknown format '{fmt}', skipping")
        pass_ += 1

    # Check 4: Required sections
    if sections:
        for section in sections.split(","):
            section = section.strip()
            checks += 1
            # Match section as a fixed string (no regex interpretation). Primary
            # check: case-insensitive fixed-string "# <section>". Fallback:
            # word-boundary header match (section escaped -> fixed string).
            target = "# " + section
            found = target.lower() in content.lower()
            if not found:
                pat = r"^#.*\s" + re.escape(section) + r"(\s|$)"
                try:
                    found = any(re.search(pat, ln, re.IGNORECASE) for ln in lines)
                except re.error:
                    found = False
            if found:
                print(f"PASS: Section found → {section}")
                pass_ += 1
            else:
                print(f"FAIL: Section missing → {section}")
                print(f"  Expected a markdown header like: ## {section}")
                fail += 1

    # Check 5: Line count
    actual_lines = content.count("\n")
    if min_lines > 0:
        checks += 1
        if actual_lines >= min_lines:
            print(f"PASS: Line count OK ({actual_lines} >= {min_lines})")
            pass_ += 1
        else:
            print(f"FAIL: Too few lines ({actual_lines} < {min_lines})")
            fail += 1
    if max_lines > 0:
        checks += 1
        if actual_lines <= max_lines:
            print(f"PASS: Line count OK ({actual_lines} <= {max_lines})")
            pass_ += 1
        else:
            print(f"FAIL: Too many lines ({actual_lines} > {max_lines})")
            fail += 1

    # Check 6: Contains text
    if contains:
        checks += 1
        try:
            found = re.search(contains, content) is not None
        except re.error:
            found = False
        if found:
            print(f"PASS: Contains expected text '{contains}'")
            pass_ += 1
        else:
            print(f"FAIL: Missing expected text '{contains}'")
            fail += 1

    # Check 7: Does not contain text
    if not_contains:
        checks += 1
        try:
            found = re.search(not_contains, content) is not None
        except re.error:
            found = False
        if found:
            print(f"FAIL: Contains forbidden text '{not_contains}'")
            fail += 1
        else:
            print(f"PASS: Does not contain forbidden text '{not_contains}'")
            pass_ += 1

    # Summary
    print("")
    print("=== Verification Summary ===")
    print(f"Checks: {checks} | Passed: {pass_} | Failed: {fail}")
    print(f"File: {actual_bytes} bytes, {actual_lines} lines")

    if fail > 0:
        print("")
        print("RESULT: FAIL — output does not meet contract")
        print("")
        print("Recovery options:")
        print("  1. Re-dispatch with tighter scope")
        print("  2. Check .scratch/scripts/toolchain.py recovery")
        print("  3. If wrong dir: python3 .scratch/scripts/toolchain.py fix-workdir")
        return 1

    print("")
    print("RESULT: PASS — output verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
