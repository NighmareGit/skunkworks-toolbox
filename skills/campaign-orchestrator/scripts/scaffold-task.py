#!/usr/bin/env python3
"""
scaffold-task.py — Generate task + agent state JSON stubs for campaign-orchestrator.

Creates the tasks/TX.json file and agents/TXx.json files for sub-agents.
Optionally updates CAMPAIGN.json with the task entry.

Uses campaign.py for atomic writes and safe paths.
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import campaign as camp


def parse_agent_spec(spec: str) -> tuple[str, str]:
    """Parse 'T1A:Primary search' into (agent_id, role)."""
    if ":" in spec:
        agent_id, role = spec.split(":", 1)
        return agent_id.strip(), role.strip()
    return spec.strip(), ""


def comma_list(value: str) -> list[str]:
    """Split comma-separated string, strip whitespace, drop empties."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main():
    parser = argparse.ArgumentParser(description="Scaffold task + agent state files")
    parser.add_argument("--campaign", "-c", required=True, help="Path to campaign folder")
    parser.add_argument("--task", "-t", required=True, help="Task ID (e.g. T1)")
    parser.add_argument("--file", "-f", required=True, help="Path to task instruction file")
    parser.add_argument("--inputs", default="", help="Comma-separated input paths")
    parser.add_argument("--outputs", default="", help="Comma-separated output paths")
    parser.add_argument("--agents", default="", help="Comma-separated agent specs (ID:role)")
    parser.add_argument("--depends-on", default="", help="Comma-separated task IDs this depends on")
    parser.add_argument("--timeout", type=int, default=600, help="Task timeout in seconds (default: 600)")
    parser.add_argument("--max-tokens", type=int, default=None, help="Token budget for this task")
    parser.add_argument("--update-campaign", action="store_true", help="Also update CAMPAIGN.json")
    args = parser.parse_args()

    campaign_dir = Path(args.campaign).resolve()
    if not campaign_dir.exists():
        print(f"[FAIL] Campaign folder not found: {campaign_dir}", file=sys.stderr)
        sys.exit(1)

    task_id = args.task
    task_file = Path(args.file).resolve()
    inputs = comma_list(args.inputs)
    outputs = comma_list(args.outputs)
    depends_on = comma_list(args.depends_on)
    agent_specs = comma_list(args.agents)

    # Parse agent specs
    agents = []
    agent_data = []
    for spec in agent_specs:
        agent_id, role = parse_agent_spec(spec)
        agents.append(agent_id)
        agent_data.append({
            "agent_id": agent_id,
            "role": role,
            "output_file": ""  # Will be assigned below
        })

    # Assign output files to agents
    # If exactly one output per agent, assign directly
    # If one output total, assign to first agent only
    # If multiple outputs, assign by index
    if len(outputs) == 1 and len(agent_data) >= 1:
        agent_data[0]["output_file"] = outputs[0]
    elif len(outputs) == len(agent_data):
        for i, ad in enumerate(agent_data):
            ad["output_file"] = outputs[i]
    else:
        # Assign by index, extras get empty string
        for i, ad in enumerate(agent_data):
            if i < len(outputs):
                ad["output_file"] = outputs[i]

    # Create tasks/TX.json
    tasks_dir = campaign_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_state = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "campaign_id": campaign_dir.name,
        "file": camp.safe_relative_to(task_file, Path.cwd().resolve()),
        "status": "pending",
        "depends_on": depends_on,
        "inputs": inputs,
        "outputs": outputs,
        "sub_agents": agents,
        "started": None,
        "completed": None,
        "retry_count": 0,
        "needs_resume": False,
        "needs_human": False,
        "token_budget": {"max_tokens": args.max_tokens, "tokens_consumed": 0},
        "timeout_seconds": args.timeout,
        "retry_policy": {"max_retries": 2, "max_fresh_agents": 1, "backoff_seconds": 30},
        "output_contract": {"min_size_bytes": 100, "required_sections": []},
        "findings": {},
        "artifacts": {}
    }

    camp.atomic_write_json(tasks_dir / f"{task_id}.json", task_state)
    print(f"[OK] Created tasks/{task_id}.json")

    # Create agents/TXx.json
    agents_dir = campaign_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    for ad in agent_data:
        agent_state = {
            "schema_version": "1.0.0",
            "agent_id": ad["agent_id"],
            "task_id": task_id,
            "campaign_id": campaign_dir.name,
            "role": ad["role"],
            "status": "pending",
            "heartbeat": None,
            "next_action": None,
            "tool_history": [],
            "output_file": ad["output_file"],
            "tokens_consumed": 0,
            "confidence": None,
            "artifacts": []
        }
        camp.atomic_write_json(agents_dir / f"{ad['agent_id']}.json", agent_state)
        print(f"[OK] Created agents/{ad['agent_id']}.json")

    # Optionally update CAMPAIGN.json
    if args.update_campaign:
        campaign_file = campaign_dir / "CAMPAIGN.json"
        campaign_obj = camp.read_json(campaign_file)

        if campaign_obj is None:
            print(f"[WARN] No CAMPAIGN.json found, skipping update")
        else:
            if "tasks" not in campaign_obj:
                campaign_obj["tasks"] = []
            campaign_obj["tasks"][task_id] = {
                "file": camp.safe_relative_to(task_file, Path.cwd().resolve()),
                "status": "pending",
                "depends_on": depends_on,
                "sub_agents": agents
            }
            campaign_obj["updated"] = camp.now_iso()
            camp.atomic_write_json(campaign_file, campaign_obj)
            print(f"[OK] Updated CAMPAIGN.json with {task_id}")

    print()
    print(f"  Task {task_id} scaffolded: {len(inputs)} inputs, {len(outputs)} outputs, {len(agents)} agents")
    if depends_on:
        print(f"  Depends on: {', '.join(depends_on)}")


if __name__ == "__main__":
    main()
