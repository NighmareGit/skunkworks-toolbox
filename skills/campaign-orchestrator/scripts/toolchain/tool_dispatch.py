#!/usr/bin/env python3
"""tool_dispatch.py — single entry point for all sub-agent dispatches (Python port).

Ports dispatch-wrapper.sh (bash) to stdlib-only Python 3.11+. Wires the full
orchestration toolchain:

  Layer 0  idempotency      skip if already done + verified
  Layer  1 preflight        verify environment (cwd, inputs, disk)
  Layer  2 scope-guard      verify task within bounds
  Layer  3 sanitize-prompt  build brief with instruction hierarchy
  Layer  4 contract --write define output contract
  Layer  5 dispatch command (printed for the orchestrator to execute)
  Layer  6 verify           verify outputs exist, size, format, sections
  Layer  7 contract --verify verify outputs match contract
  Layer  8 decision-log     log the dispatch result
  Layer  9 context-budget  record token usage
  ON FAILURE               recovery-playbook — classify and recover

Usage:
  python3 tool_dispatch.py --mode pre --cwd /path --task-id R1 \\
      --inputs "reports/prior.md" --outputs "distillation/notes.md" \\
      --sub-tasks 2 --prompt-file .scratch/prompts/r1.txt \\
      --min-bytes 1000 --format markdown \\
      --sections "Key Insights,Actionable" \\
      --description "R1: read shortlist -> structured notes"

  python3 tool_dispatch.py --mode post --cwd /path --task-id R1 \\
      --outputs "distillation/notes.md" --min-bytes 1000 --format markdown

  python3 tool_dispatch.py --mode post-workflow --cwd /path --task-id R1 \\
      --agent-ids "wf-worker-id,wf-verifier-id" \\
      --verified-count 2 --result-count 2 --note "dispatch-wave: 2/2 verified"

  python3 tool_dispatch.py --mode full --cwd ... (pre + dispatch command + post)
  python3 tool_dispatch.py --mode handoff --cwd /path [--note "..."]
  python3 tool_dispatch.py --mode sabotage  (failure-injection harness)

Modes:
  pre           pre-dispatch checks (layers 0-4). Prints the dispatch command.
  post          post-dispatch verification (layers 6-9).
  full          pre, print dispatch command, then post (manual orchestrator flow).
  post-workflow close the lineage loop for a workflow wave (link + state + log).
  handoff       one-command session handoff (Side A).
  sabotage      run the failure-injection harness in an isolated fixture.

Exit codes:
  0 = all checks passed (pre) / verification passed (post)
  1 = check failed — fix before dispatching (pre) / verification failed (post)
  2 = argument error
  3 = idempotency abort (task already done + verified)
"""

import contextlib
import datetime
import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

# Resolve the toolchain directory ONCE from this file's location (cross-platform,
# never hardcoded). All sibling scripts live here.
TOOLCHAIN_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLCHAIN = os.path.join(TOOLCHAIN_DIR, "toolchain.py")

# M2 anti-path-traversal: same rule as task-state.py. Pivot (handoff) has no
# task id by design and is exempt.
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class _ArgError(Exception):
    """Internal signal: argument error (prints its own message; exit 2)."""


def _run(args, indent=0):
    """Run a subprocess, capture combined stdout+stderr, print indented, return rc.

    Mirrors the bash `tool.sh ... 2>&1 | sed 's/^/  /'`. The returncode is the
    tool's exit code (the layer's contract). Missing executables / launch errors
    surface as a clean error + rc 2, never a traceback.
    """
    try:
        res = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
    except FileNotFoundError:
        print(f"ERROR: executable not found: {args[0]}")
        return 2
    except Exception as e:
        print(f"ERROR: {e}")
        return 2
    _print_indented(res.stdout or "", indent)
    return res.returncode


def _run_capture(args):
    """Run a subprocess, capture combined stdout+stderr. Return (rc, text).

    Used when the wrapper needs the tool's stdout (mint, handoff readout,
    sanitize). Mirrors `OUT=$(tool.sh ... 2>&1)`.
    """
    try:
        res = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
    except FileNotFoundError:
        return 2, ""
    except Exception:
        return 2, ""
    return res.returncode, res.stdout or ""


def _print_indented(text, indent):
    """Print text with every line prefixed by `indent` spaces (sed 's/^/  /')."""
    if not text:
        return
    pad = " " * indent
    for line in text.splitlines(keepends=True):
        sys.stdout.write(pad + line)


def _local_mint():
    """Fallback DISPATCH_ID mint (uuid7, dc_<32-hex>) if dispatch-trace.py is
    unavailable. Mirrors dispatch-trace.uuid7_hex()."""
    ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    rand = random.getrandbits(74)
    value = (
        (ms << 80)
        | (0x7 << 76)
        | (((rand >> 62) & 0x0FFF) << 64)
        | (0x2 << 62)
        | (rand & ((1 << 62) - 1))
    )
    return f"dc_{value:032x}"


def main(argv=None) -> int:
    """Run the dispatch wrapper. Standalone (`python3 tool_dispatch.py ...`) or
    importable by toolchain.py as the `dispatch` subcommand (toolchain.py
    calls main(argv) and propagates the returncode)."""
    if argv is None:
        argv = sys.argv[1:]

    # -----------------------------------------------------------------------+
    # Manual arg parser — mirrors the bash while-loop/case exactly. No argparse.|
    # -----------------------------------------------------------------------+
    mode = ""
    cwd = ""
    task_id = ""
    inputs = ""
    outputs = ""
    sub_tasks = 1
    prompt_file = ""
    min_bytes = 100
    format_ = "any"
    sections = ""
    description = ""
    max_tool_calls = 20
    max_sub_tasks = 3
    tokens = 0
    agent_ids = ""
    verified_count = ""
    result_count = ""
    wf_status = ""
    wf_note = ""
    no_settle = False
    skip_idempotency = False

    i = 0
    while i < len(argv):
        a = argv[i]

        def take_value():
            """Fetch the value for a --flag; a missing value is an arg error."""
            nonlocal i
            if i + 1 >= len(argv):
                raise _ArgError(f"ERROR: {a} requires a value")
            v = argv[i + 1]
            i += 2
            return v

        try:
            if a == "--mode":
                mode = take_value()
            elif a == "--cwd":
                cwd = take_value()
            elif a == "--task-id":
                task_id = take_value()
            elif a == "--inputs":
                inputs = take_value()
            elif a == "--outputs":
                outputs = take_value()
            elif a == "--sub-tasks":
                sub_tasks = take_value()
            elif a == "--prompt-file":
                prompt_file = take_value()
            elif a == "--min-bytes":
                min_bytes = take_value()
            elif a == "--format":
                format_ = take_value()
            elif a == "--sections":
                sections = take_value()
            elif a == "--description":
                description = take_value()
            elif a == "--max-tool-calls":
                max_tool_calls = take_value()
            elif a == "--max-sub-tasks":
                max_sub_tasks = take_value()
            elif a == "--tokens":
                tokens = take_value()
            elif a == "--agent-ids":
                agent_ids = take_value()
            elif a == "--verified-count":
                verified_count = take_value()
            elif a == "--result-count":
                result_count = take_value()
            elif a == "--status":
                wf_status = take_value()
            elif a == "--note":
                wf_note = take_value()
            elif a == "--no-settle":
                no_settle = True; i += 1
            elif a == "--skip-idempotency":
                skip_idempotency = True; i += 1
            else:
                print(f"ERROR: Unknown arg: {a}")
                return 2
        except _ArgError as e:
            print(e)
            return 2

    # Coerce numeric fields (defaults are ints; parsed values are strings).
    # Garbage (e.g. --min-bytes abc) is an arg error, never a traceback —
    # the bash silently degraded garbage to 0; a clean error is strictly safer.
    try:
        sub_tasks = int(sub_tasks)
        min_bytes = int(min_bytes)
        max_tool_calls = int(max_tool_calls)
        max_sub_tasks = int(max_sub_tasks)
        tokens = int(tokens)
    except ValueError:
        print("ERROR: numeric flag value must be an integer "
              f"(got '{sub_tasks}'/'{min_bytes}'/'{max_tool_calls}'/'{max_sub_tasks}'/'{tokens}')")
        return 2

    # -----------------------------------------------------------------------+
    # Validation (order mirrors the bash exactly).                            |
    # -----------------------------------------------------------------------+
    if not mode:
        print("ERROR: --mode required")
        return 2
    if not task_id and mode != "handoff":
        print("ERROR: --task-id required (all modes except handoff)")
        return 2
    if mode != "handoff" and not TASK_ID_RE.match(task_id):
        print(f"ERROR: invalid task_id '{task_id}'")
        print("  Must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ (no slashes, no '..', no NUL)")
        return 2

    # CWD POLICY (F6): resolve against --cwd ONCE. Every downstream layer gets
    # ABSOLUTE paths so a wrapper invoked from a different cwd cannot re-introduce
    # the wrong-directory bug.
    if cwd:
        try:
            cwd_abs = os.path.realpath(cwd)
        except Exception:
            cwd_abs = os.path.abspath(cwd)
    else:
        cwd_abs = os.getcwd()

    def absolutize_list(lst):
        """Comma-separated relative paths -> absolute against cwd_abs. R8: strip
        per element, no shell re-parsing."""
        out = []
        for p in lst.split(","):
            p = p.strip()
            if not p:
                continue
            if not os.path.isabs(p):
                p = os.path.join(cwd_abs, p)
            out.append(p)
        return ",".join(out)

    if inputs:
        inputs = absolutize_list(inputs)
    if outputs:
        outputs = absolutize_list(outputs)
    if prompt_file and not os.path.isabs(prompt_file):
        prompt_file = os.path.join(cwd_abs, prompt_file)

    # -----------------------------------------------------------------------+
    # DISPATCH_ID (D1/D5): campaign-owned lineage root. pre/full mint a fresh   |
    # dc_<uuidv7>; post reuses the one persisted in the brief registry so the   |
    # whole chain (pre -> spawn -> post) shares a single id.                   |
    # -----------------------------------------------------------------------+
    dispatch_id = ""
    brief_json_path = os.path.join(
        cwd_abs, ".scratch", "dispatch-briefs", task_id, "brief.json"
    )
    if os.path.isfile(brief_json_path):
        try:
            with open(brief_json_path) as f:
                dispatch_id = json.load(f).get("dispatch_id", "")
        except Exception:
            dispatch_id = ""
    if not dispatch_id:
        rc, minted = _run_capture(
            [sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-trace.py"), "mint"]
        )
        dispatch_id = (minted or "").strip()
        if not dispatch_id:
            # dispatch-trace.py unavailable — fall back to a local mint so the run
            # proceeds with a valid id instead of crashing.
            dispatch_id = _local_mint()

    # Header block.
    print("========================================")
    print(f"  Dispatch Wrapper — {mode}")
    print(f"  Task: {task_id}")
    print(f"  Description: {description or task_id}")
    print(f"  CWD (abs): {cwd_abs}")
    print("========================================")
    print()

    overall = 0

    # -----------------------------------------------------------------------+
    # Layer functions — closures over the shared state above (mirrors the     |
    # bash's dynamic scoping of the wrapper's variables).                     |
    # -----------------------------------------------------------------------+
    def layer0_idempotency():
        if skip_idempotency:
            if os.environ.get("ALLOW_REDISPATCH") != "1":
                print("── Layer 0: Idempotency ── REFUSED")
                print("  --skip-idempotency requires ALLOW_REDISPATCH=1 (safety: this bypasses")
                print("  the only duplicate-work guard). Set the env var to force a re-dispatch.")
                print()
                return 3
            print("── Layer 0: Idempotency ── SKIP (--skip-idempotency + ALLOW_REDISPATCH=1) ⚠️")
            print()
            return 0

        print("── Layer 0: Idempotency Check ──")
        if not outputs:
            print("  SKIP: no outputs specified")
            print()
            return 0

        # R3 (portable ledger): TASKS_LEDGER env pins it; else the reference
        # project's research ledger if present; else .scratch/task-state.
        ledger = os.environ.get("TASKS_LEDGER", "")
        if not ledger:
            ref = os.path.join(
                cwd_abs, "docs", "research",
                "task-atomization-low-cap-agents", "TASKS.json",
            )
            if os.path.isfile(ref):
                ledger = ref
            else:
                ledger = os.path.join(
                    cwd_abs, ".scratch", "task-state", "TASKS.json"
                )

        rc = _run(
            [sys.executable, TOOLCHAIN, "idempotency",
             "--task-id", task_id, "--outputs", outputs,
             "--min-bytes", str(min_bytes), "--ledger", ledger]
        )
        if rc == 0:
            print()
            print("  ✅ Task not done — proceeding")
            print()
            return 0
        if rc == 1:
            print()
            print("  ✅ Task ALREADY DONE + VERIFIED — ABORTING dispatch")
            print("  (idempotency: outputs exist and meet size threshold)")
            print("  To force re-dispatch: delete outputs, or set ALLOW_REDISPATCH=1")
            print()
            return 3
        if rc == 2:
            print()
            print("  ⚠️  Outputs exist but UNVERIFIED — run post-dispatch verification first")
            print()
            return 1
        return 0

    def layer1_preflight():
        print("── Layer 1: Pre-Flight Environment Check ──")
        args = [sys.executable, TOOLCHAIN, "preflight",
                "--cwd", cwd_abs, "--min-disk-mb", "100"]
        if inputs:
            args += ["--inputs", inputs]
        rc = _run(args)
        if rc == 0:
            print()
            print("  ✅ Environment validated")
            print()
            return 0
        print()
        print("  ❌ Environment check FAILED — fix before dispatching")
        print()
        return 1

    def layer2_scope():
        print("── Layer 2: Scope Guard ──")
        args = [sys.executable, os.path.join(TOOLCHAIN_DIR, "scope-guard.py"),
                "check", "--sub-tasks", str(sub_tasks),
                "--max-sub-tasks", str(max_sub_tasks),
                "--max-tool-calls", str(max_tool_calls)]
        if description:
            args += ["--description", description]
        rc = _run(args)
        if rc == 0:
            print()
            print("  ✅ Within scope bounds")
            print()
            return 0
        print()
        print("  ❌ Scope exceeds bounds — decompose or tighten")
        print(f"  Run: python3 scope-guard.py decompose --sub-tasks {sub_tasks}")
        print()
        return 1

    def layer3_sanitize():
        print("── Layer 3: Prompt Sanitization + Brief Registry ──")
        brief_dir = os.path.join(cwd_abs, ".scratch", "dispatch-briefs", task_id)
        os.makedirs(brief_dir, exist_ok=True)

        sanitized = ""
        if prompt_file:
            if not os.path.isfile(prompt_file):
                print(f"  WARN: prompt file not found: {prompt_file}")
                print("  Orchestrators should construct prompt inline")
                print()
                return 0
            _rc, sanitized = _run_capture(
                [sys.executable, os.path.join(TOOLCHAIN_DIR, "sanitize-prompt.py"),
                 "-f", prompt_file]
            )
            if _rc != 0:
                # Mirror the bash's errexit on this assignment: a sanitize
                # failure is a real gate failure, never a silent success.
                print(f"  ❌ Prompt sanitization FAILED (exit {_rc}) — aborting pre-dispatch")
                print("  Fix the prompt file or sanitize-prompt.py, then re-run.")
                return 1
            sanitized = sanitized.strip()
            print(f"  ✅ Prompt sanitized from file: {prompt_file}")
            print(f"  Length: {len(sanitized)} chars (JSON-safe)")
        else:
            print("   NOTE: no --prompt-file — orchestrator constructs prompt inline.")
            print("  (For longcat roles, build the brief with sanitize-prompt.py --brief)")

        brief_sha = ""
        if sanitized:
            # sanitize-prompt.py prints a JSON string; unquote it (F2/D1).
            try:
                brief_text = json.loads(sanitized)
            except (json.JSONDecodeError, ValueError):
                brief_text = sanitized
            brief_md = os.path.join(brief_dir, "brief.md")
            try:
                with open(brief_md, "w") as f:
                    f.write(brief_text)
                with open(brief_md, "rb") as f:
                    brief_sha = hashlib.sha256(f.read()).hexdigest()
            except OSError as e:
                print(f"  ❌ Cannot write brief: {brief_md}: {e}")
                return 1

        # M2: build brief.json via json.dump (never string interpolation).
        created = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        brief = {
            "task_id": task_id,
            "dispatch_id": dispatch_id,
            "role": "unknown",
            "cwd": cwd_abs,
            "prompt_file": prompt_file or "",
            "brief_sha256": brief_sha,
            "outputs": outputs or "",
            "min_bytes": int(min_bytes),
            "format": format_,
            "created": created,
        }
        try:
            with open(os.path.join(brief_dir, "brief.json"), "w") as f:
                json.dump(brief, f, indent=2)
        except OSError as e:
            print(f"  ❌ Cannot write brief.json: {e}")
            return 1

        print(f"  🪪  DISPATCH_ID: {dispatch_id}")
        print('  → Orchestrator: include "dispatch=$DISPATCH_ID" in the subagent\'s')
        print("    description, then link the agent id after spawn:")
        print(f"    dispatch-trace.py link --dispatch-id {dispatch_id} --agent-id <harness-id>")
        # State machine: pre-dispatch mints -> pending_spawn (non-fatal, silent —
        # mirrors bash `>/dev/null 2>&1 || true`).
        _run_capture([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-state.py"),
                      "transition", "--dispatch-id", dispatch_id, "--to", "pending_spawn",
                      "--cwd", cwd_abs])
        if brief_sha:
            print(f"  📝 Brief written: {brief_dir}/brief.md")
            print(f"  📝 Registry:      {brief_dir}/brief.json (sha256: {brief_sha})")
        else:
            print(f"  📝 Registry:      {brief_dir}/brief.json (no prompt file — inline prompt)")
        print()
        return 0

    def layer4_contract_write():
        print("── Layer 4: Output Contract (write) ──")
        contract_file = os.path.join(
            cwd_abs, ".scratch", "task-state", "output-contracts.json"
        )
        if not outputs:
            print("  SKIP: no outputs specified")
            print()
            return 0
        for output in outputs.split(","):
            output = output.strip()
            args = [sys.executable, TOOLCHAIN, "contract", "--write",
                    "--output", output, "--min-bytes", str(min_bytes),
                    "--format", format_, "--contract-file", contract_file]
            if sections:
                args += ["--sections", sections]
            _run(args, indent=2)  # non-fatal
        print(f"  ✅ Output contract(s) written → {contract_file}")
        print()
        return 0

    def layer5_dispatch():
        print("── Layer 5: Dispatch Command ──")
        print("  ┌─────────────────────────────────────────────")
        print("  │  Execute this spawn_subagent tool call:")
        print("  │")
        print("  │  spawn_subagent(")
        print(f"  │    cwd=\"{cwd_abs}\",")
        print("  │    background=true,")
        print("  │    prompt=<constructed from prompt file or inline>,")
        print("  │    ...")
        print("  │  )")
        print("  │")
        print("  │  After sub-agent completes, run:")
        print(f"  │    toolchain.py dispatch --mode post --task-id {task_id} ...")
        if outputs:
            print("  │")
            print("  │  Expected outputs:")
            for output in outputs.split(","):
                output = output.strip()
                if os.path.isabs(output):
                    print(f"  │    - {output}")
                else:
                    print(f"  │    - {cwd_abs}/{output}")
        print("  └─────────────────────────────────────────────")
        print()

    def layer6_verify():
        print("── Layer 6: Post-Dispatch Verification ──")
        if not outputs:
            print("  SKIP: no outputs specified")
            print()
            return 0
        verify_failed = False
        for output in outputs.split(","):
            output = output.strip()
            args = [sys.executable, TOOLCHAIN, "verify", output,
                    "--min-bytes", str(min_bytes), "--format", format_,
                    "--cwd", cwd_abs]
            if sections:
                args += ["--sections", sections]
            print(f"  Verifying: {output}")
            rc = _run(args, indent=4)
            if rc == 0:
                print(f"  ✅ Verified: {output}")
            else:
                print(f"  ❌ Verification failed: {output}")
                verify_failed = True
            print()
        if verify_failed:
            print("  ❌ One or more outputs failed verification")
            print()
            return 1
        print("  ✅ All outputs verified")
        print()
        return 0

    def layer7_contract_verify():
        print("── Layer 7: Output Contract (verify) ──")
        contract_file = os.path.join(
            cwd_abs, ".scratch", "task-state", "output-contracts.json"
        )
        if not outputs:
            print("  SKIP: no outputs specified")
            print()
            return 0
        contract_ok = True
        for output in outputs.split(","):
            output = output.strip()
            rc = _run([sys.executable, TOOLCHAIN, "contract", "--verify",
                       "--output", output, "--contract-file", contract_file],
                      indent=2)
            if rc != 0:
                contract_ok = False
        print()
        if contract_ok:
            return 0
        return 1

    def layer8_decision_log(result, note, outcome):
        print("── Layer 8: Decision Log ──")
        log_file = os.path.join(
            cwd_abs, ".scratch", "task-state", "DECISIONS.md"
        )
        # RT-D4: resolve the log against --cwd, never the process cwd.
        rationale = note if note else f"Dispatch wrapper {mode} for {task_id}"
        real_outcome = outcome if outcome else "unknown"
        _run([sys.executable, TOOLCHAIN, "decision-log",
              "--task-id", task_id, "--dispatch-id", dispatch_id,
              "--decision", result, "--rationale", rationale,
              "--outcome", real_outcome, "--log-file", log_file], indent=2)
        print()
        return 0

    def layer9_budget():
        print("── Layer 9: Context Budget ──")
        campaign = os.environ.get("CAMPAIGN_ID", "")
        if not campaign:
            print("  SKIP: no CAMPAIGN_ID env set (project-specific)")
        elif tokens > 0:
            # R1: campaign id from CAMPAIGN_ID env, never hardcoded.
            _run([sys.executable, os.path.join(TOOLCHAIN_DIR, "context-budget.py"),
                  "--campaign", campaign, "record", "--task-id", task_id,
                  "--tokens", str(tokens)], indent=2)
        else:
            print("  SKIP: no --tokens specified")
        print()
        return 0

    def do_recovery(failed_layer):
        print(f"── Recovery: failure at layer {failed_layer} ──")
        symptom_map = {1: "wrong-dir", 2: "loop", 6: "missing-output"}
        symptom = symptom_map.get(failed_layer, "partial-output")
        args = [sys.executable, TOOLCHAIN, "recovery",
                "--task-id", task_id, "--symptom", symptom]
        if cwd_abs:
            args += ["--cwd", cwd_abs]
        if outputs:
            first = outputs.split(",")[0].strip()
            args += ["--expected-output", first]
        _run(args, indent=2)  # non-fatal
        print()

    # -----------------------------------------------------------------------+
    # Mode dispatch — mirrors the bash case statement. Exit codes are the     |
    # contract and are asserted by the suite.                                 |
    # -----------------------------------------------------------------------+
    if mode == "pre":
        print("=== PRE-DISPATCH CHECKLIST ===")
        print()
        l0 = layer0_idempotency()
        if l0 == 3:
            print("=== PRE-DISPATCH: SKIPPED (idempotency) ===")
            return 3
        if l0 != 0:
            overall = 1
            do_recovery(0)
        if overall == 0:
            if layer1_preflight() != 0:
                overall = 1
                do_recovery(1)
        if overall == 0:
            if layer2_scope() != 0:
                overall = 1
                do_recovery(2)
        if overall == 0:
            if layer3_sanitize() != 0:
                # sanitize/brief-write failure is a gate failure (bash errexit
                # killed the run there); the rest of layer3 stays non-fatal.
                overall = 1
        if overall == 0:
            layer4_contract_write()
        if overall == 0:
            layer5_dispatch()
        if overall == 0:
            print("=== PRE-DISPATCH: ALL CHECKS PASSED ===")
            print("Ready to dispatch. Execute the spawn_subagent call above.")
        else:
            print("=== PRE-DISPATCH: FAILED ===")
            print("Fix the issues above before dispatching.")

    elif mode == "post":
        print("=== POST-DISPATCH VERIFICATION ===")
        print()
        if layer6_verify() != 0:
            overall = 1
            do_recovery(6)
        # Layer 7 MUST gate: a failed contract verification fails the run.
        if overall == 0:
            if layer7_contract_verify() != 0:
                overall = 1
                # (no recovery for L7 — mirrors the bash)
        if overall == 0:
            layer8_decision_log(
                "verified", "post-dispatch verification passed",
                "verification passed (all gates green)")
            _run_capture([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-state.py"),
                          "transition", "--dispatch-id", dispatch_id, "--to", "verified",
                          "--cwd", cwd_abs])
        else:
            layer8_decision_log(
                "verification-failed",
                "post-dispatch verification failed; recovery/re-dispatch needed",
                "verification FAILED — recovery/re-dispatch required")
            _run_capture([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-state.py"),
                          "transition", "--dispatch-id", dispatch_id, "--to", "failed",
                          "--cwd", cwd_abs])
        if overall == 0:
            layer9_budget()
        if overall == 0:
            print("=== POST-DISPATCH: ALL CHECKS PASSED ===")
            print(f"Task {task_id} complete and verified.")
        else:
            print("=== POST-DISPATCH: VERIFICATION FAILED ===")
            print("Run recovery or re-dispatch.")

    elif mode == "post-workflow":
        print("=== POST-WORKFLOW LINEAGE CEREMONY ===")
        print()
        status = wf_status if wf_status else "verified"
        note = wf_note if wf_note else "workflow wave complete"

        # 1. Link every harness agent id (comma/space separated) into the brief.
        if agent_ids:
            # normalize spaces -> commas, collapse repeats, strip edge commas.
            ids = agent_ids.replace(" ", ",")
            while ",," in ids:
                ids = ids.replace(",,", ",")
            ids = ids.strip(",")
            rc = _run([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-trace.py"),
                       "link", "--dispatch-id", dispatch_id, "--agent-id", ids,
                       "--cwd", cwd_abs], indent=2)
            if rc != 0:
                print("  ❌ link failed — lineage incomplete (brief write may still have succeeded)")
        else:
            print("  ℹ️  no --agent-ids given — skipping link (lineage will be incomplete)")

        # 2. State machine: spawned -> verified|failed -> done (silent, non-fatal).
        if status == "failed":
            _run_capture([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-state.py"),
                          "transition", "--dispatch-id", dispatch_id, "--to", "failed",
                          "--cwd", cwd_abs])
        else:
            _run_capture([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-state.py"),
                          "transition", "--dispatch-id", dispatch_id, "--to", "verified",
                          "--cwd", cwd_abs])
            _run_capture([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-state.py"),
                          "transition", "--dispatch-id", dispatch_id, "--to", "done",
                          "--cwd", cwd_abs])

        # 3. Decision log (real outcome, never hardcoded).
        if status == "failed":
            layer8_decision_log(
                "verification-failed", note,
                "workflow wave FAILED — recovery/re-dispatch required")
        else:
            vtxt = ""
            if verified_count and result_count:
                vtxt = f"; {verified_count}/{result_count} independently verified"
            layer8_decision_log("verified", note, f"workflow wave complete{vtxt}")

        # 4. Budget record.
        layer9_budget()

        # 5. Show the chain.
        _run([sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-trace.py"),
              "trace", "--dispatch-id", dispatch_id, "--cwd", cwd_abs], indent=2)

        if status != "failed":
            print("=== POST-WORKFLOW: DONE ===")
            print(f"Task {task_id} linked, verified, and closed. next-action is clean.")
        else:
            print("=== POST-WORKFLOW: FAILED (recorded) ===")
            print("Recovery path: re-dispatch the wave under a fresh dispatch id.")

    elif mode == "handoff":
        print("=== HANDOFF: ONE-COMMAND SESSION HANDOFF ===")
        print()
        settle_args = [] if no_settle else ["--settle"]
        rc, handoff_out = _run_capture(
            [sys.executable, os.path.join(TOOLCHAIN_DIR, "dispatch-state.py"),
             "handoff"] + settle_args + ["--cwd", cwd_abs]
        )
        print(handoff_out, end="")
        if rc != 0:
            overall = 1

        if overall == 0:
            log_file = os.path.join(
                cwd_abs, ".scratch", "task-state", "DECISIONS.md"
            )
            _run([sys.executable, TOOLCHAIN, "decision-log",
                  "--task-id", "PIVOT",
                  "--decision", "HANDOFF: session handed off",
                  "--rationale", wf_note if wf_note else "session handoff — fresh session resumes via next-action",
                  "--outcome", "resume: dispatch-state.py next-action on boot",
                  "--log-file", log_file], indent=2)

            resume_file = os.path.join(
                cwd_abs, ".scratch", "task-state", "RESUME.md"
            )
            created = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            dispatch_state_path = os.path.join(TOOLCHAIN_DIR, "dispatch-state.py")
            memo = wf_note if wf_note else "—"
            try:
                with open(resume_file, "w") as f:
                    f.write("# Session Handoff — resume instructions\n\n")
                    f.write(f"- **Handed off:** {created}\n")
                    f.write(f"- **Project:** {cwd_abs}\n")
                    f.write(f'- **Resume command:** python3 {dispatch_state_path} next-action --cwd "{cwd_abs}"\n')
                    f.write("\n## What the fresh session does (boot readout)\n")
                    for line in handoff_out.splitlines():
                        f.write(f"- {line}\n")
                    f.write("\n## Memo from the previous session\n")
                    f.write(f"{memo}\n\n")
            except OSError as e:
                # Mirrors bash `> "$resume_file" 2>/dev/null || true` — a resume
                # memo write failure must not fail the handoff.
                print(f"  ⚠️  Could not write resume memo: {resume_file}: {e}")
                overall = 0
            else:
                print()
                print(f"  📄 Resume memo written: {resume_file}")

        print()
        if overall == 0:
            print("=== HANDOFF: DONE — hand off and boot ===")
            print("Tell the fresh session: resume (RESUME.md has the exact instruction —")
            print("the new session reads agents.md, finds RESUME.md, and boots next-action).")
        else:
            print("=== HANDOFF: ERROR (see above) ===")

    elif mode == "full":
        print("=== FULL DISPATCH FLOW ===")
        print()
        l0 = layer0_idempotency()
        if l0 == 3:
            print("=== FULL DISPATCH: SKIPPED (idempotency) ===")
            return 3
        if l0 != 0:
            overall = 1
            do_recovery(0)
        if overall == 0:
            if layer1_preflight() != 0:
                overall = 1
                do_recovery(1)
        if overall == 0:
            if layer2_scope() != 0:
                overall = 1
                do_recovery(2)
        if overall == 0:
            if layer3_sanitize() != 0:
                overall = 1
        if overall == 0:
            layer4_contract_write()
        if overall == 0:
            layer5_dispatch()

        if overall == 0:
            print()
            print("  ⏸️  PAUSE: Execute the spawn_subagent call, then run:")
            print(f"  toolchain.py dispatch --mode post --task-id {task_id}"
                  f" --cwd {cwd_abs} --outputs {outputs}"
                  f" --min-bytes {min_bytes} --format {format_}")
            print()
            layer8_decision_log(
                "dispatched", description,
                "dispatched — verification pending (run --mode post)")
        else:
            print("=== FULL DISPATCH: PRE-CHECK FAILED ===")

    elif mode == "sabotage":
        # SABOTAGE MODE (fireplace B1): failure-injection harness. Replays the
        # META-ANALYSIS failure modes and asserts each gate catches them. Runs
        # ONLY in an isolated fixture dir — never real state (RT-D3: clean up).
        print("=== SABOTAGE: Failure-Injection Harness ===")
        print("Isolated fixture only — no real campaign state touched.")
        print()
        sab_dir = tempfile.mkdtemp(prefix="sabotage.")
        spass = 0
        sfail = 0

        def run_case(name, args):
            """Run one case via the module's OWN main() in-process (captured
            return). A case PASSES when the gate returns NONZERO."""
            nonlocal spass, sfail
            buf = io.StringIO()
            rc = 0
            with contextlib.redirect_stdout(buf):
                try:
                    rc = main(args)
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            if rc != 0:
                spass += 1
                print(f"  ✅ gate caught: {name} (exit {rc})")
            else:
                sfail += 1
                print(f"  ❌ gate MISSED: {name} (exit 0 — sabotage slipped through)")
                for line in buf.getvalue().splitlines()[:6]:
                    print(f"       {line}")

        try:
            wrong = os.path.join(sab_dir, "wrong")
            right = os.path.join(sab_dir, "right")
            os.makedirs(wrong)
            os.makedirs(right)

            # A: sub-agent writes output to the WRONG directory (FM1).
            with open(os.path.join(wrong, "out.md"), "w") as f:
                f.write("# H\n" + "x" * 300)
            run_case("wrong-dir write detected",
                     ["--mode", "post", "--cwd", right, "--task-id", "S1",
                      "--outputs", "out.md", "--min-bytes", "100",
                      "--format", "markdown"])

            # B: sub-agent reports DONE but wrote nothing (FM3 false-done).
            run_case("false-done (no output) detected",
                     ["--mode", "post", "--cwd", right, "--task-id", "S2",
                      "--outputs", "ghost.md", "--min-bytes", "100",
                      "--format", "markdown"])

            # C: empty output below contract minimum (FM2 contract).
            with open(os.path.join(right, "tiny.md"), "w") as f:
                f.write("# H")
            run_case("too-small output detected",
                     ["--mode", "post", "--cwd", right, "--task-id", "S3",
                      "--outputs", "tiny.md", "--min-bytes", "500",
                      "--format", "markdown"])

            # D: wrong format (raw JSON where markdown expected) (FM2 format).
            with open(os.path.join(right, "raw.md"), "w") as f:
                f.write('{"raw":"json"}')
            run_case("wrong-format output detected",
                     ["--mode", "post", "--cwd", right, "--task-id", "S4",
                      "--outputs", "raw.md", "--min-bytes", "5",
                      "--format", "markdown"])

            # E: missing required section (contract FM2 sections).
            with open(os.path.join(right, "nosect.md"), "w") as f:
                f.write("# H\n" + "x" * 300)
            run_case("missing required section detected",
                     ["--mode", "post", "--cwd", right, "--task-id", "S5",
                      "--outputs", "nosect.md", "--min-bytes", "100",
                      "--format", "markdown", "--sections", "MandatorySection"])

            # F: duplicate dispatch prevented by idempotency (FM3/L8).
            with open(os.path.join(right, "dup.md"), "w") as f:
                f.write("# H\n" + "x" * 300)
            run_case("duplicate dispatch aborted (idempotency)",
                     ["--mode", "pre", "--cwd", right, "--task-id", "S6",
                      "--outputs", "dup.md", "--min-bytes", "100",
                      "--format", "markdown"])

            # G: preflight catches missing input (FM1).
            run_case("missing input caught by preflight",
                     ["--mode", "pre", "--cwd", right, "--task-id", "S7",
                      "--inputs", "does-not-exist.md", "--outputs", "out.md",
                      "--min-bytes", "100", "--format", "markdown"])

            # H (POSITIVE CONTROL, RT-D1): a CORRECT output MUST pass.
            with open(os.path.join(right, "good.md"), "w") as f:
                f.write("# H\n" + "x" * 300)
            buf = io.StringIO()
            rc = 0
            with contextlib.redirect_stdout(buf):
                try:
                    rc = main(["--mode", "post", "--cwd", right,
                               "--task-id", "S8", "--outputs", "good.md",
                               "--min-bytes", "100", "--format", "markdown"])
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            if rc == 0:
                spass += 1
                print("  ✅ positive control: good output passes all gates (exit 0)")
            else:
                sfail += 1
                print("  ❌ positive control FAILED: good output rejected — gates over-strict/broken")
        finally:
            shutil.rmtree(sab_dir, ignore_errors=True)

        print()
        print(f"=== SABOTAGE RESULTS: {spass} caught, {sfail} missed ===")
        if sfail > 0:
            print(f"FAIL: {sfail} sabotage cases slipped through the gates")
            return 1
        print("ALL GATES HOLD — every replayable failure mode was caught")
        return 0

    else:
        print(f"ERROR: Unknown mode '{mode}'. Use: pre, post, full, post-workflow, handoff, sabotage")
        return 2

    return overall


if __name__ == "__main__":
    sys.exit(main())
