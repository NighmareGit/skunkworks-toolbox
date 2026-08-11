#!/usr/bin/env python3
"""
context-budget.py — Context usage tracker (BS1/BS8: Context Budget + Coordination Ratio fix)

Tracks context/token usage across sub-agents and the orchestrator.
Alerts when orchestration exceeds 20% of total campaign cost.
Enables data-driven delegation decisions.

Usage:
    python3 context-budget.py init --campaign <id>
    python3 context-budget.py record --task-id <id> --tokens <n> --agent <agent_id>
    python3 context-budget.py record-orchestrator --tokens <n> --note "verification"
    python3 context-budget.py report
    python3 context-budget.py ratio
    python3 context-budget.py alert

Exit codes:
    0 = success / ratio OK
    1 = ratio exceeds threshold (orarg parse error)
    2 = argument error
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DEFAULTS = {
    "orchestration_threshold": 0.20,  # 20% max orchestration ratio
    "state_dir": ".scratch/task-state",
    "context_window": 128000,  # default context window size
}


def budget_path(campaign_id: str) -> Path:
    return Path(DEFAULTS["state_dir"]) / f"budget-{campaign_id}.json"


def init_budget(campaign_id: str):
    """Initialize a new budget tracker."""
    path = budget_path(campaign_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "schema_version": "1.0.0",
        "campaign_id": campaign_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "updated": datetime.now(timezone.utc).isoformat(),
        "orchestrator_tokens": 0,
        "sub_agent_tokens": {},
        "orchestrator_log": [],
        "sub_agent_log": [],
        "context_window": DEFAULTS["context_window"],
        "alerts": [],
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Budget tracker initialized: {path}")
    print(f"  Campaign: {campaign_id}")
    print(f"  Context window: {DEFAULTS['context_window']:,} tokens")
    print(f"  Orchestration threshold: {DEFAULTS['orchestration_threshold']*100:.0f}%")


def load_budget(campaign_id: str) -> dict:
    path = budget_path(campaign_id)
    if not path.exists():
        print(f"Budget not found: {path}. Run 'init' first.", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def save_budget(budget: dict):
    budget["updated"] = datetime.now(timezone.utc).isoformat()
    path = budget_path(budget["campaign_id"])
    with open(path, "w") as f:
        json.dump(budget, f, indent=2)


def record_task(campaign_id: str, task_id: str, tokens: int, agent: str = None):
    """Record token usage for a sub-agent task."""
    budget = load_budget(campaign_id)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "tokens": tokens,
        "agent": agent or task_id,
    }

    budget["sub_agent_log"].append(entry)
    budget["sub_agent_tokens"][agent or task_id] = (
        budget["sub_agent_tokens"].get(agent or task_id, 0) + tokens
    )

    save_budget(budget)
    print(f"Recorded: {task_id} = {tokens:,} tokens (agent: {agent or task_id})")

    # Check ratio after recording
    check_ratio(budget)


def record_orchestrator(campaign_id: str, tokens: int, note: str = ""):
    """Record orchestrator token usage."""
    budget = load_budget(campaign_id)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tokens": tokens,
        "note": note,
    }

    budget["orchestrator_log"].append(entry)
    budget["orchestrator_tokens"] += tokens

    save_budget(budget)
    print(f"Recorded orchestrator: {tokens:,} tokens ({note})")

    # Check ratio after recording
    check_ratio(budget)


def find_signals_json(session_id: str) -> Path | None:
    """Locate a sub-agent's signals.json by session id in ~/.grok/sessions/.

    Every session (including subagents) writes signals.json with real telemetry:
    contextTokensUsed, toolCallCount, modelsUsed. We search the session tree by
    the subagent session id (which spawn_subagent returns as the agent id).
    """
    sessions_root = Path.home() / ".grok" / "sessions"
    if not sessions_root.exists():
        return None
    # Subagent sessions are nested under the parent session dir; a direct
    # top-level search by id catches the common layout. We walk a bounded depth.
    for candidate in sessions_root.rglob("signals.json"):
        if session_id in str(candidate):
            return candidate
    return None


def harvest_session(campaign_id: str, session_id: str, task_id: str = None,
                    agent: str = None, require: bool = False):
    """Harvest real token/tool-call telemetry from a session's signals.json.

    Returns True if real numbers were recorded. When `require` is True, missing
    telemetry is an error (fail closed) — the caller can escape with
    --no-telemetry.
    """
    signals = find_signals_json(session_id)
    if signals is None:
        msg = f"No signals.json found for session {session_id} (telemetry unavailable)"
        if require:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"WARN: {msg}")
        return False

    try:
        data = json.loads(signals.read_text())
    except (json.JSONDecodeError, OSError) as e:
        msg = f"signals.json unreadable: {signals} ({e})"
        if require:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"WARN: {msg}")
        return False

    tokens = data.get("contextTokensUsed")
    tool_calls = data.get("toolCallCount", 0)
    if tokens is None:
        msg = f"signals.json has no contextTokensUsed: {signals}"
        if require:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"WARN: {msg}")
        return False

    budget = load_budget(campaign_id)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "task_id": task_id or session_id,
        "tokens": tokens,
        "tool_calls": tool_calls,
        "source": "signals.json",
        "signals_path": str(signals),
    }
    agent_key = agent or task_id or session_id
    budget["sub_agent_log"].append(entry)
    budget["sub_agent_tokens"][agent_key] = tokens  # measured, not cumulative guess
    save_budget(budget)

    print(f"Harvested: {agent_key} = {tokens:,} tokens, {tool_calls} tool calls")
    print(f"  (source: {signals})")
    check_ratio(budget)
    return True


def compute_ratio(budget: dict) -> float:
    """Compute orchestration ratio. Returns 0.0 if no sub-agent tokens yet."""
    sub_total = sum(budget["sub_agent_tokens"].values())
    total = budget["orchestrator_tokens"] + sub_total
    if total == 0:
        return 0.0
    return budget["orchestrator_tokens"] / total


def check_ratio(budget: dict, verbose: bool = True):
    """Check if orchestration ratio exceeds threshold."""
    ratio = compute_ratio(budget)
    sub_total = sum(budget["sub_agent_tokens"].values())
    total = budget["orchestrator_tokens"] + sub_total

    if verbose:
        print(f"\n  Current ratio: {ratio*100:.1f}% orchestration")
        print(f"  Orchestrator: {budget['orchestrator_tokens']:,} tokens")
        print(f"  Sub-agents: {sub_total:,} tokens ({len(budget['sub_agent_tokens'])} agents)")
        print(f"  Total: {total:,} tokens")

    threshold = DEFAULTS["orchestration_threshold"]
    if ratio > threshold and sub_total > 0:
        alert_msg = (
            f"ALERT: Orchestration ratio {ratio*100:.1f}% exceeds "
            f"{threshold*100:.0f}% threshold"
        )
        if verbose:
            print(f"\n  ⚠️  {alert_msg}")
            print(f"  Recommendation: delegate more work to sub-agents")
            print(f"  (but not at the cost of quality — verify outputs)")
        budget["alerts"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ratio": ratio,
            "message": alert_msg,
        })
        save_budget(budget)
        return False
    return True


def generate_report(campaign_id: str):
    """Generate a full budget report."""
    budget = load_budget(campaign_id)
    ratio = compute_ratio(budget)
    sub_total = sum(budget["sub_agent_tokens"].values())
    total = budget["orchestrator_tokens"] + sub_total

    print("=" * 50)
    print(f"Context Budget Report — {campaign_id}")
    print("=" * 50)
    print(f"Created: {budget['created']}")
    print(f"Updated: {budget['updated']}")
    print()

    print("Token Usage:")
    print(f"  Orchestrator:  {budget['orchestrator_tokens']:>10,} tokens")
    print(f"  Sub-agents:    {sub_total:>10,} tokens ({len(budget['sub_agent_tokens'])} agents)")
    print(f"  Total:         {total:>10,} tokens")
    print()

    print(f"Orchestration Ratio: {ratio*100:.1f}%")
    threshold = DEFAULTS["orchestration_threshold"]
    status = "✅ OK" if ratio <= threshold else "⚠️ EXCEEDS THRESHOLD"
    print(f"  Threshold: {threshold*100:.0f}%  [{status}]")
    print()

    if budget["sub_agent_tokens"]:
        print("Per-Agent Breakdown:")
        for agent, tokens in sorted(budget["sub_agent_tokens"].items(),
                                     key=lambda x: x[1], reverse=True):
            pct = (tokens / total * 100) if total > 0 else 0
            print(f"  {agent:20s} {tokens:>10,} tokens ({pct:5.1f}%)")
        print()

    if budget["alerts"]:
        print(f"Alerts ({len(budget['alerts'])}):")
        for alert in budget["alerts"][-5:]:
            print(f"  {alert['timestamp']}: {alert['message']}")
        print()

    # Context window utilization
    if budget.get("context_window"):
        max_usage = max(
            budget["orchestrator_tokens"],
            max(budget["sub_agent_tokens"].values()) if budget["sub_agent_tokens"] else 0,
            0,
        )
        utilization = max_usage / budget["context_window"] * 100
        print(f"Context Window Utilization: {utilization:.1f}%")
        print(f"  Window size: {budget['context_window']:,} tokens")
        print(f"  Peak usage: {max_usage:,} tokens")


def main():
    parser = argparse.ArgumentParser(description="Context budget tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize budget tracker")
    init_parser.add_argument("--campaign", required=True, help="Campaign ID")

    # record (sub-agent)
    record_parser = subparsers.add_parser("record", help="Record sub-agent token usage")
    record_parser.add_argument("--campaign", required=True)
    record_parser.add_argument("--task-id", required=True)
    record_parser.add_argument("--tokens", type=int, required=True)
    record_parser.add_argument("--agent", default=None)

    # record-orchestrator
    orch_parser = subparsers.add_parser("record-orchestrator", help="Record orchestrator tokens")
    orch_parser.add_argument("--campaign", required=True)
    orch_parser.add_argument("--tokens", type=int, required=True)
    orch_parser.add_argument("--note", default="")

    # report
    report_parser = subparsers.add_parser("report", help="Generate budget report")
    report_parser.add_argument("--campaign", required=True)

    # ratio
    ratio_parser = subparsers.add_parser("ratio", help="Check orchestration ratio")
    ratio_parser.add_argument("--campaign", required=True)

    # alert
    alert_parser = subparsers.add_parser("alert", help="Alert if ratio exceeds threshold")
    alert_parser.add_argument("--campaign", required=True)

    # harvest (real telemetry from signals.json)
    harvest_parser = subparsers.add_parser(
        "harvest", help="Harvest real tokens/tool-calls from a session's signals.json"
    )
    harvest_parser.add_argument("--campaign", required=True)
    harvest_parser.add_argument("--session-id", required=True, help="Sub-agent session id")
    harvest_parser.add_argument("--task-id", default=None)
    harvest_parser.add_argument("--agent", default=None)
    harvest_parser.add_argument("--require", action="store_true",
                                help="Fail closed when telemetry is missing")

    args = parser.parse_args()

    if args.command == "init":
        init_budget(args.campaign)
    elif args.command == "record":
        record_task(args.campaign, args.task_id, args.tokens, args.agent)
    elif args.command == "record-orchestrator":
        record_orchestrator(args.campaign, args.tokens, args.note)
    elif args.command == "report":
        generate_report(args.campaign)
    elif args.command == "harvest":
        harvest_session(args.campaign, args.session_id, args.task_id, args.agent, args.require)
    elif args.command == "ratio":
        budget = load_budget(args.campaign)
        ok = check_ratio(budget)
        sys.exit(0 if ok else 1)
    elif args.command == "alert":
        budget = load_budget(args.campaign)
        ok = check_ratio(budget, verbose=False)
        ratio = compute_ratio(budget)
        if not ok:
            print(f"ALERT: Orchestration ratio {ratio*100:.1f}% exceeds threshold")
            sys.exit(1)
        print(f"OK: Orchestration ratio {ratio*100:.1f}% within threshold")
        sys.exit(0)


if __name__ == "__main__":
    main()
