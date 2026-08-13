#!/usr/bin/env python3
"""toolchain.py — consolidated cross-platform orchestration toolchain.

The bash leaf tools of the campaign toolchain, ported to stdlib Python and
dispatched from one entry point. Each port also ships as a standalone
tool_<name>.py module (same directory) and is imported LAZILY here, so one
broken module only breaks its own subcommand.

Subcommands (name  ->  module  ->  source it ports):
  preflight      tool_preflight    preflight-check.sh   environment validator
  verify         tool_verify       verify-output.sh     post-dispatch output verification
  contract       tool_contract     output-contract.sh   output contract write/verify
  idempotency    tool_idempotency  idempotency-check.sh duplicate-work guard
  decision-log   tool_decisionlog  decision-log.sh      append-only decision audit trail
  adr-log        tool_adrlog       adr-log.sh           architecture decision records
  recovery       tool_recovery     recovery-playbook.sh failure recovery procedures
  fix-workdir    tool_fixworkdir   fix-workdir.sh       move wrong-dir artifacts

Pure stdlib (argparse, pathlib, json, re, shutil). Runs identically on
Linux/macOS/Windows — no bash, no shell=True anywhere.

Usage:
  python3 toolchain.py preflight --cwd <dir> --inputs <files>
  python3 toolchain.py verify <path> --min-bytes 100 --format markdown
  python3 toolchain.py decision-log --decision "..." --rationale "..." --log-file <path>
  ... (each subcommand mirrors its source tool's CLI + exit codes exactly)
"""

import importlib
import sys

SUBCOMMANDS = {
    "preflight": "tool_preflight",
    "verify": "tool_verify",
    "contract": "tool_contract",
    "idempotency": "tool_idempotency",
    "decision-log": "tool_decisionlog",
    "adr-log": "tool_adrlog",
    "recovery": "tool_recovery",
    "fix-workdir": "tool_fixworkdir",
    "dispatch": "tool_dispatch",
}


def main(argv: list | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("toolchain.py — consolidated cross-platform orchestration toolchain")
        print(f"subcommands: {', '.join(sorted(SUBCOMMANDS))}")
        print("Each subcommand mirrors the source tool's CLI + exit codes exactly "
              "(see tool_<name>.py docstrings).")
        return 0
    name = argv[0]
    if name not in SUBCOMMANDS:
        print(f"ERROR: unknown subcommand '{name}' "
              f"(use: {', '.join(sorted(SUBCOMMANDS))})", file=sys.stderr)
        return 2
    try:
        mod = importlib.import_module(SUBCOMMANDS[name])
    except Exception as e:
        # Any module-load failure (ImportError, SyntaxError, import-time bug)
        # must surface as a clean error, not a raw traceback. One broken module
        # only breaks its own subcommand.
        print(f"ERROR: subcommand module '{SUBCOMMANDS[name]}' failed to load: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2
    try:
        return mod.main(argv[1:])
    except SystemExit as e:
        # Tools with their own -h/argparse handling may sys.exit(); propagate
        # the code (0 for help, their arg-error code otherwise).
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        # A runtime crash inside a subcommand must be a clean error, never a
        # raw traceback escaping the dispatcher.
        print(f"ERROR: subcommand '{name}' crashed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
