#!/usr/bin/env python3
"""ticket-generator.py — the governor's mechanized chore: need → machine-ready dispatcher ticket.

Wraps the producer chain so the dispatcher's queue fills without hand-tokening the mechanics:
    need (source JSON minus generated fields)
      → render <ticket>.source.json
      → rhai-builder --manifest   (emits args.json + phase2-ticket.json + manifest)
      → validate-ticket           (the MPR gate — FAIL = source problem, never a force-through)
      → ticket-claim (optional)   (the queue reservation)
      → report: the ticket path + the dispatch command

Usage:
    ticket-generator.py --need <need.json> [--dispatches-dir DIR] [--owner NAME] [--claim]
    ticket-generator.py --help
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, ".scratch", "scripts")
DEFAULT_DISPATCHES = os.path.join(ROOT, ".scratch", "dispatches", "prepped")

# Fields rhai-builder fills at emission (the need JSON must NOT carry them).
GENERATED_FIELDS = {"schema", "template", "template_sha256", "status", "gates",
                    "estimated_cost", "stall_soft", "agent_budget", "budget_derivation",
                    "renderings", "generated_by", "generated_at", "provenance"}
REQUIRED_FIELDS = ["ticket", "class", "state_path", "resource", "feedstock",
                   "deliverable", "task", "seams", "discriminator", "kill", "commands"]


def die(msg, code=1):
    print(f"ticket-generator: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd, label):
    print(f"── {label}: {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip()[-1200:])
    if r.returncode != 0:
        print(f"ticket-generator: {label} FAILED ({r.returncode})", file=sys.stderr)
        if r.stderr.strip():
            print(r.stderr.strip()[-800:], file=sys.stderr)
        sys.exit(r.returncode)
    return r


def main():
    ap = argparse.ArgumentParser(description="need → machine-ready dispatcher ticket")
    ap.add_argument("--need", required=True, help="the source JSON (minus generated fields)")
    ap.add_argument("--dispatches-dir", default=DEFAULT_DISPATCHES)
    ap.add_argument("--owner", default="parent")
    ap.add_argument("--claim", action="store_true", help="reserve the ticket via ticket-claim.sh")
    ap.add_argument("--no-validate", action="store_true", help="skip the MPR gate (debug only)")
    args = ap.parse_args()

    # 1. Load + validate the need.
    try:
        with open(args.need) as f:
            need = json.load(f)
    except Exception as e:
        die(f"cannot read --need: {e}")
    missing = [f for f in REQUIRED_FIELDS if f not in need]
    if missing:
        die(f"need missing required fields: {missing} (the 4 rails + the contract)")
    stray = [f for f in GENERATED_FIELDS if f in need]
    if stray:
        die(f"need carries generated fields (rhai-builder fills them): {stray}")
    ticket_id = need["ticket"]
    if ticket_id != ticket_id.upper().replace(" ", "-"):
        die(f"ticket id must be UPPER-KEBAB: '{ticket_id}'")

    # 2. Render the source JSON.
    os.makedirs(args.dispatches_dir, exist_ok=True)
    source_path = os.path.join(args.dispatches_dir, f"{ticket_id}.source.json".lower())
    with open(source_path, "w") as f:
        json.dump(need, f, indent=2)
    print(f"── rendered source: {source_path}")

    # 3. The producer chain.
    rhai = os.path.join(SCRIPTS, "rhai-builder.py")
    run([sys.executable, rhai, "--manifest", source_path, "--dispatches-dir", args.dispatches_dir],
        "rhai-builder (emits the phase2 ticket + manifest)")

    ticket_path = os.path.join(args.dispatches_dir, "tickets", f"{ticket_id}.phase2-ticket.json")
    if not os.path.exists(ticket_path):
        die(f"emission produced no ticket at {ticket_path}")

    # 4. The MPR gate.
    if not args.no_validate:
        vt = os.path.join(SCRIPTS, "validate-ticket.py")
        run([sys.executable, vt, ticket_path], "MPR gate (validate-ticket)")

    # 5. The queue reservation.
    if args.claim:
        tc = os.path.join(SCRIPTS, "ticket-claim.sh")
        run(["bash", tc, "claim", ticket_id, "--owner", args.owner], "claim")

    # 6. The report.
    print("\nticket-generator: TICKET READY")
    print(f"  ticket   : {ticket_id}")
    print(f"  path     : {ticket_path}")
    print(f"  state    : {need['state_path']}")
    print(f"  class    : {need['class']} | resource: {need['resource']} | evidence_only: {need.get('evidence_only', False)}")
    print(f"  seat     : {need.get('commands', {}).get('seat', '?')}")
    print(f"  dispatch : spawn_subagent with the ticket at {ticket_path}")


if __name__ == "__main__":
    main()
