#!/usr/bin/env python3
"""tool_contract.py — Output contract schema + verifier (FM2: Contract Ambiguity fix).

Defines what "done" means for a task, then verifies outputs match the contract.
Contracts are stored as JSON alongside the task for auditability.

Usage:
  tool_contract.py --write --output <path> --min-bytes <n> --format <fmt> [--sections <s1,s2>] [--contract-file <path>]
  tool_contract.py --verify --contract-file <path>
  tool_contract.py --verify --output <path> --min-bytes <n> --format <fmt> [--sections <s1,s2>]

Formats: markdown, json, yaml, text, any

Exit codes:
  0 = contract written or verification passed
  1 = verification failed (with details)
  2 = argument error
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


def write_contract(output, min_bytes, fmt, sections, contract_file):
    if not output:
        print("ERROR: --output required for --write")
        return 2

    parent = os.path.dirname(contract_file)
    if parent:
        os.makedirs(parent, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    sections_list = []
    if sections:
        sections_list = [s.strip() for s in sections.split(",") if s.strip()]

    contract = {
        "output": output,
        "min_bytes": min_bytes,
        "format": fmt,
        "required_sections": sections_list,
        "created": timestamp,
        "verified": False,
        "verified_at": None,
    }

    if os.path.exists(contract_file):
        try:
            with open(contract_file) as f:
                contracts = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError):
            contracts = {}
    else:
        contracts = {}

    contracts[output] = contract

    with open(contract_file, "w") as f:
        json.dump(contracts, f, indent=2)

    print(f"Contract written: {output}")
    print(f"  min_bytes: {min_bytes}")
    print(f"  format: {fmt}")
    print(f"  required_sections: {sections.replace(',', ' ')}")
    print(f"  contract_file: {contract_file}")
    return 0


def verify_contract(output, min_bytes, fmt, sections, contract_file, explicit_args):
    verify_output = output
    verify_min_bytes = min_bytes
    verify_format = fmt
    verify_sections = sections

    # If contract file exists and has entry for this output, use stored values
    if os.path.isfile(contract_file) and output:
        stored = None
        try:
            with open(contract_file) as f:
                contracts = json.load(f)
            if output in contracts:
                stored = contracts[output]
        except (json.JSONDecodeError, ValueError, OSError):
            stored = None

        if stored:
            verify_min_bytes = stored.get("min_bytes", 100)
            verify_format = stored.get("format", "any")
            verify_sections = ",".join(stored.get("required_sections", []))
        elif explicit_args:
            # Caller supplied explicit contract args — honor them (self-contained mode)
            pass
        else:
            # F10 fix: a MISSING stored contract with no explicit args is a
            # violation, not a silent downgrade to defaults. If a contract was
            # written for this output and it vanished (lost update / wrong dir),
            # verification must fail loudly rather than pass on weaker defaults.
            print(f"VIOLATION: contract file exists but has no entry for: {output}")
            print("  (contract was lost or never written — do NOT verify against defaults)")
            print("  Fix: pass explicit --min-bytes/--format/--sections, or re-run --write")
            return 1

    if not verify_output:
        print("ERROR: --output required for --verify")
        return 2

    pass_ = 0
    fail = 0

    print("=== Output Contract Verification ===")
    print(f"Output: {verify_output}")
    print(f"Contract: min_bytes={verify_min_bytes}, format={verify_format}")
    print("")

    # Check 1: File exists
    if not os.path.isfile(verify_output):
        print(f"FAIL: File does not exist: {verify_output}")

        # Check wrong directory (R1 — portable sibling search)
        # NOTE: output-contract.sh has no --cwd flag; CWD is always empty, so the
        # pattern below is `== "/*"` and only matches absolute output paths.
        # Preserved verbatim from the source for behavioral fidelity.
        cwd = ""
        if verify_output.startswith(cwd + "/"):
            parent = os.path.dirname(cwd)
            rel = verify_output[len(cwd) + 1:]
            if os.path.isdir(parent):
                for name in sorted(os.listdir(parent)):
                    cand_dir = os.path.join(parent, name)
                    if not os.path.isdir(cand_dir):
                        continue
                    if os.path.normpath(cand_dir) == os.path.normpath(cwd):
                        continue
                    cand = os.path.join(cand_dir, rel)
                    if os.path.isfile(cand):
                        print(f"  FOUND in wrong dir: {cand}")
                        break
        return 1

    print("PASS: File exists")
    pass_ += 1

    # Read file content once for the checks below
    with open(verify_output, errors="replace") as f:
        content = f.read()
    lines = content.splitlines()

    # Check 2: Min bytes
    actual_bytes = os.path.getsize(verify_output)
    if actual_bytes < verify_min_bytes:
        print(f"FAIL: Too small ({actual_bytes} bytes < {verify_min_bytes} min)")
        fail += 1
    else:
        print(f"PASS: Size OK ({actual_bytes} bytes >= {verify_min_bytes})")
        pass_ += 1

    # Check 3: Format
    if verify_format == "markdown":
        first5 = lines[:5]
        if any(line.startswith("#") for line in first5):
            print("PASS: Markdown format (has # header)")
            pass_ += 1
        else:
            print("FAIL: No markdown header found in first 5 lines")
            fail += 1
    elif verify_format == "json":
        try:
            json.loads(content)
            print("PASS: Valid JSON")
            pass_ += 1
        except Exception:
            print("FAIL: Not valid JSON")
            fail += 1
    elif verify_format == "yaml":
        try:
            import yaml
        except ImportError:
            # Best-effort: PyYAML unavailable -> skip (per the port contract,
            # replicate the source's `import yaml` probe; on ImportError fall
            # back to SKIP behavior rather than a hard FAIL).
            print(f"SKIP: No format check for '{verify_format}'")
        else:
            try:
                yaml.safe_load(content)
                print("PASS: Valid YAML")
                pass_ += 1
            except Exception:
                print("FAIL: Not valid YAML")
                fail += 1
    elif verify_format in ("any", "text"):
        print(f"SKIP: No format check for '{verify_format}'")
    else:
        print(f"WARN: Unknown format '{verify_format}'")

    # Check 4: Required sections
    if verify_sections:
        for section in verify_sections.split(","):
            # Case-insensitive fixed-string match, with a word-boundary fallback
            # (mirrors the source's dual `grep -qiF` + `grep -qiE` checks). The
            # section is treated as a fixed string (escaped), never as regex.
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
                fail += 1

    # Update contract file with verification result (non-fatal)
    if os.path.isfile(contract_file):
        try:
            with open(contract_file) as f:
                contracts = json.load(f)
            if verify_output in contracts:
                contracts[verify_output]["verified"] = fail == 0
                contracts[verify_output]["verified_at"] = datetime.now(timezone.utc).isoformat()
                contracts[verify_output]["actual_bytes"] = actual_bytes
                with open(contract_file, "w") as f:
                    json.dump(contracts, f, indent=2)
        except Exception:
            pass

    print("")
    print("=== Contract Verification Summary ===")
    print(f"Passed: {pass_} | Failed: {fail}")

    if fail > 0:
        print("RESULT: FAIL — output does not meet contract")
        return 1

    print("RESULT: PASS — output meets contract")
    return 0


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", default=False)
    ap.add_argument("--verify", action="store_true", default=False)
    ap.add_argument("--output", default=None)
    # Defaults mirror the bash; None sentinel tracks explicit overrides (M5 fix).
    ap.add_argument("--min-bytes", type=int, default=None)
    ap.add_argument("--format", default=None)
    ap.add_argument("--sections", default=None)
    ap.add_argument("--contract-file", default=None)

    args, unknown = ap.parse_known_args(argv)
    if unknown:
        print(f"ERROR: Unknown arg: {unknown[0]}")
        return 2

    mode = None
    if args.write:
        mode = "write"
    elif args.verify:
        mode = "verify"

    if mode is None:
        print("ERROR: --write or --verify required")
        return 2

    # Default contract file path
    contract_file = args.contract_file
    if contract_file is None:
        contract_file = ".scratch/task-state/output-contracts.json"

    # Resolve explicit overrides (M5): a missing flag keeps its default value but
    # is NOT counted as an explicit override.
    min_bytes = args.min_bytes if args.min_bytes is not None else 100
    fmt = args.format if args.format is not None else "any"
    sections = args.sections if args.sections is not None else ""
    explicit_args = (
        args.min_bytes is not None
        or args.format is not None
        or args.sections is not None
    )

    if mode == "write":
        return write_contract(args.output, min_bytes, fmt, sections, contract_file)
    else:
        return verify_contract(args.output, min_bytes, fmt, sections, contract_file, explicit_args)


if __name__ == "__main__":
    sys.exit(main())
