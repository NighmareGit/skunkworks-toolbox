#!/usr/bin/env python3
"""
scope-guard.py — Scope limit enforcer (FM4: Scope Explosion fix)

Validates that a task is within acceptable bounds BEFORE dispatching.
Enforces: max tool calls, max sub-tasks, max depth, max time.
Also provides task decomposition recommendations.

Usage:
    python3 scope-guard.py check --sub-tasks 3 --max-sub-tasks 3 --tool-calls 15 --max-tool-calls 20
    python3 scope-guard.py decompose --sub-tasks 8 --max-sub-tasks 3
    python3 scope-guard.py estimate --description "Search 6 groups, read 84 papers, write synthesis"

Exit codes:
    0 = within bounds (safe to dispatch)
    1 = exceeds bounds (decompose or tighten scope)
    2 = argument error
"""

import sys
import argparse
import json
import re
from datetime import datetime, timezone


# Default limits — calibrated for low-cap sub-agents
DEFAULTS = {
    "max_sub_tasks": 3,
    "max_tool_calls": 20,
    "max_depth": 2,  # levels of nested reasoning
    "max_time_seconds": 600,  # 10 minutes
    "max_input_files": 5,
    "max_output_files": 3,
    "max_search_groups": 3,
}


def estimate_tool_calls(description: str) -> int:
    """Heuristic: estimate tool calls from task description."""
    calls = 0

    # Count explicit search/read/write operations
    patterns = {
        r'\bsearch\b': 2,  # each search = ~2 calls (query + retrieve)
        r'\bfind\b': 2,
        r'\bread\b': 1,
        r'\bopen\b': 1,
        r'\bwrite\b': 1,
        r'\bcreate\b': 1,
        r'\banalyze\b': 2,
        r'\bscreen\b': 2,
        r'\bscore\b': 1,
        r'\bmerge\b': 1,
        r'\bdedup\b': 1,
        r'\bsynthesize\b': 3,
        r'\bcategorize\b': 2,
        r'\bextract\b': 2,
        r'\bcompare\b': 2,
        r'\bevaluat\b': 2,
    }

    desc_lower = description.lower()
    for pattern, cost in patterns.items():
        matches = len(re.findall(pattern, desc_lower))
        calls += matches * cost

    # Scale by group/file counts mentioned
    group_match = re.search(r'(\d+)\s*(search\s*)?groups?', desc_lower)
    if group_match:
        calls += int(group_match.group(1)) * 3

    paper_match = re.search(r'(\d+)\s*papers?', desc_lower)
    if paper_match:
        calls += int(paper_match.group(1)) * 0.5  # skim = 0.5 each

    return int(calls)


def estimate_time(tool_calls: int) -> int:
    """Estimate time in seconds from tool calls (assume ~15s/call for low-cap)."""
    return tool_calls * 15


def check_bounds(sub_tasks, max_sub_tasks, tool_calls, max_tool_calls,
                 max_depth=None, max_time=None, description=None):
    """Check if task is within bounds. Returns (passed, violations, recommendations)."""
    violations = []
    recommendations = []

    # Use estimates if explicit values not provided
    if tool_calls is None and description:
        tool_calls = estimate_tool_calls(description)
        print(f"  Estimated tool calls from description: {tool_calls}")
    elif tool_calls is None:
        # No tool-calls and no description: this is a violation, not a crash.
        # Report clearly so the caller adds a description or explicit budget.
        violations.append(
            "No tool-call estimate possible: neither --tool-calls nor --description given"
        )
        recommendations.append(
            "Pass --description (auto-estimate) or --tool-calls <N> (explicit budget)"
        )
        tool_calls = 0  # avoid None comparisons below

    estimated_time = estimate_time(tool_calls) if tool_calls else 0

    # Check sub-tasks
    if sub_tasks > max_sub_tasks:
        violations.append(
            f"Sub-tasks ({sub_tasks}) exceeds limit ({max_sub_tasks})"
        )
        recommendations.append(
            f"Decompose into {sub_tasks // max_sub_tasks + 1} parallel sub-agents"
        )

    # Check tool calls
    if tool_calls > max_tool_calls:
        violations.append(
            f"Tool calls ({tool_calls}) exceeds limit ({max_tool_calls})"
        )
        recommendations.append(
            f"Reduce scope: fewer search groups, smaller input set, or split into sub-agents"
        )

    # Check time
    if estimated_time > max_time:
        violations.append(
            f"Estimated time ({estimated_time}s) exceeds limit ({max_time}s)"
        )
        recommendations.append(
            f"Tighten scope to fit {max_time}s budget (~{max_time // 15} tool calls max)"
        )

    # Check depth
    if max_depth is not None and max_depth > DEFAULTS["max_depth"]:
        violations.append(
            f"Reasoning depth ({max_depth}) exceeds limit ({DEFAULTS['max_depth']})"
        )
        recommendations.append(
            f"Flatten: break into sequential shallow tasks instead of nested reasoning"
        )

    passed = len(violations) == 0
    return passed, violations, recommendations, tool_calls, estimated_time


def decompose(sub_tasks, max_sub_tasks):
    """Recommend decomposition for an over-scoped task.

    Produces CONTIGUOUS, non-overlapping ranges: e.g. 8 tasks / 3 per agent
    → A:1-3, B:4-6, C:7-8 (not the old overlapping 1-3/3-5/5-7).
    """
    if sub_tasks <= 0:
        return []
    if max_sub_tasks <= 0:
        max_sub_tasks = 1
    n_agents = (sub_tasks + max_sub_tasks - 1) // max_sub_tasks
    tasks_per_agent = sub_tasks // n_agents
    remainder = sub_tasks % n_agents

    decomposition = []
    start = 1
    for i in range(n_agents):
        count = tasks_per_agent + (1 if i < remainder else 0)
        end = start + count - 1
        decomposition.append({
            "agent": f"Sub-Agent {chr(65 + i)}",  # A, B, C...
            "sub_tasks": count,
            "scope": f"Tasks {start}-{end}",
        })
        start = end + 1

    return decomposition


def main():
    parser = argparse.ArgumentParser(description="Scope limit enforcer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # check command
    check_parser = subparsers.add_parser("check", help="Check if task within bounds")
    check_parser.add_argument("--sub-tasks", type=int, default=1, help="Number of sub-tasks")
    check_parser.add_argument("--max-sub-tasks", type=int, default=DEFAULTS["max_sub_tasks"])
    check_parser.add_argument("--tool-calls", type=int, default=None, help="Estimated tool calls (or auto-estimate from description)")
    check_parser.add_argument("--max-tool-calls", type=int, default=DEFAULTS["max_tool_calls"])
    check_parser.add_argument("--max-depth", type=int, default=None, help="Reasoning depth levels")
    check_parser.add_argument("--max-time", type=int, default=DEFAULTS["max_time_seconds"], help="Max time in seconds")
    check_parser.add_argument("--description", type=str, default=None, help="Task description (for auto-estimation)")

    # decompose command
    decomp_parser = subparsers.add_parser("decompose", help="Recommend decomposition")
    decomp_parser.add_argument("--sub-tasks", type=int, required=True, help="Total sub-tasks")
    decomp_parser.add_argument("--max-sub-tasks", type=int, default=DEFAULTS["max_sub_tasks"])

    # estimate command
    est_parser = subparsers.add_parser("estimate", help="Estimate tool calls and time")
    est_parser.add_argument("--description", type=str, required=True, help="Task description")

    args = parser.parse_args()

    if args.command == "check":
        passed, violations, recommendations, tool_calls, estimated_time = check_bounds(
            sub_tasks=args.sub_tasks,
            max_sub_tasks=args.max_sub_tasks,
            tool_calls=args.tool_calls,
            max_tool_calls=args.max_tool_calls,
            max_depth=args.max_depth,
            max_time=args.max_time,
            description=args.description,
        )

        print("=== Scope Guard Check ===")
        print(f"Sub-tasks: {args.sub_tasks} (limit: {args.max_sub_tasks})")
        print(f"Tool calls: {tool_calls} (limit: {args.max_tool_calls})")
        print(f"Est. time: {estimated_time}s (limit: {args.max_time}s)")
        print()

        if violations:
            print("VIOLATIONS:")
            for v in violations:
                print(f"  ✗ {v}")
            print()

        if recommendations:
            print("RECOMMENDATIONS:")
            for r in recommendations:
                print(f"  → {r}")
            print()

        if passed:
            print("RESULT: PASS — within bounds, safe to dispatch")
            sys.exit(0)
        else:
            print("RESULT: FAIL — exceeds bounds, decompose or tighten scope")
            sys.exit(1)

    elif args.command == "decompose":
        decomposition = decompose(args.sub_tasks, args.max_sub_tasks)
        print("=== Decomposition Recommendation ===")
        print(f"Total sub-tasks: {args.sub_tasks}")
        print(f"Max per agent: {args.max_sub_tasks}")
        print(f"Recommended agents: {len(decomposition)}")
        print()
        for agent in decomposition:
            print(f"  {agent['agent']}: {agent['sub_tasks']} sub-tasks ({agent['scope']})")
        print()
        print(json.dumps(decomposition, indent=2))

    elif args.command == "estimate":
        tool_calls = estimate_tool_calls(args.description)
        estimated_time = estimate_time(tool_calls)
        print("=== Scope Estimate ===")
        print(f"Description: {args.description}")
        print(f"Estimated tool calls: {tool_calls}")
        print(f"Estimated time: {estimated_time}s ({estimated_time/60:.1f} min)")
        print()

        if tool_calls > DEFAULTS["max_tool_calls"]:
            print(f"WARNING: Exceeds default limit ({DEFAULTS['max_tool_calls']} calls)")
            decomposition = decompose(tool_calls, DEFAULTS["max_tool_calls"])
            print(f"Recommendation: Split into {len(decomposition)} sub-agents")
            sys.exit(1)
        else:
            print("Within default limits")
            sys.exit(0)


if __name__ == "__main__":
    main()
