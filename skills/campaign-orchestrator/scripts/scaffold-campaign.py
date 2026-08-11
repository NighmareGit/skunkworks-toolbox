#!/usr/bin/env python3
"""
scaffold-campaign.py — Create the campaign-orchestrator coordination layer.

Two modes:
  Manual mode (default): creates empty templates, agent populates the graph.
  Auto-wire mode (--auto-wire): parses MISSION.md + task files, generates full graph.

Uses campaign.py for atomic writes, safe paths, and decision logging.
"""

import argparse
import json
import sys
from pathlib import Path

# Import core library
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import campaign as camp


# ── Parsing (auto-wire mode) ────────────────────────────────────────────────


def parse_mission_task_table(mission_path: Path) -> list[dict]:
    """Parse the task pipeline table from MISSION.md."""
    content = mission_path.read_text(encoding="utf-8")
    tasks = []
    lines = content.split("\n")
    in_table = False
    header_cols = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and "Task" in stripped and "File" in stripped:
            header_cols = [c.strip() for c in stripped.split("|")[1:-1]]
            in_table = True
            continue
        if in_table and stripped.startswith("|") and "---" in stripped:
            continue
        if in_table and stripped.startswith("|"):
            cols = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cols) >= len(header_cols):
                row = dict(zip(header_cols, cols))
                tasks.append(row)
        elif in_table and not stripped.startswith("|"):
            break

    return tasks


def extract_task_id(task_name: str) -> str:
    """Extract 'T1' from 'T1 — Collect'. Raises ValueError if not found."""
    import re
    match = re.match(r"(T\d+)", task_name.strip())
    if match:
        return match.group(1)
    raise ValueError(f"Cannot extract task ID from: {task_name!r}")


def extract_depends_on(depends_str: str) -> list[str]:
    """Extract dependency task IDs."""
    import re
    depends_str = depends_str.strip()
    if depends_str in ("—", "-", "none", ""):
        return []
    return re.findall(r"T\d+", depends_str)


def extract_file_link(file_cell: str) -> str:
    """Extract path from markdown link."""
    import re
    match = re.search(r"\]\(([^)]+)\)", file_cell)
    if match:
        return match.group(1)
    return file_cell.strip().strip("[]()")


def parse_task_file(task_path: Path) -> dict:
    """Parse a task instruction file for inputs, outputs, sub-agents."""
    content = task_path.read_text(encoding="utf-8")
    result = {"inputs": [], "outputs": [], "sub_agents": []}

    # Parse Inputs table
    in_inputs = False
    in_inputs_table = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Inputs"):
            in_inputs = True
            continue
        if in_inputs and stripped.startswith("|") and "Source" in stripped:
            in_inputs_table = True
            continue
        if in_inputs and in_inputs_table and stripped.startswith("|") and "---" not in stripped:
            cols = [c.strip().strip("`").strip() for c in stripped.split("|")[1:-1]]
            if len(cols) >= 2:
                result["inputs"].append(cols[1])
        if in_inputs and in_inputs_table and not stripped.startswith("|"):
            in_inputs = False
            in_inputs_table = False

    # Parse Output section — detect paths with multiple extensions
    in_output = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Output"):
            in_output = True
            continue
        if in_output and stripped.startswith("```"):
            continue
        if in_output and stripped.startswith("##"):
            in_output = False
            continue
        if in_output and "." in stripped and not stripped.startswith("#"):
            # Extract path-like tokens (contains / or \ and has an extension)
            import re
            paths = re.findall(r"[\w./\\-]+\.\w{1,10}", stripped)
            for p in paths:
                p = p.strip("`").strip()
                if "/" in p or "\\" in p:
                    result["outputs"].append(p)

    # Parse Execution Model / Sub-agents table
    in_exec = False
    in_exec_table = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Execution Model"):
            in_exec = True
            continue
        if in_exec and stripped.startswith("|") and "Sub-Agent" in stripped:
            in_exec_table = True
            continue
        if in_exec and in_exec_table and stripped.startswith("|") and "---" not in stripped:
            cols = [c.strip().strip("`").strip() for c in stripped.split("|")[1:-1]]
            if len(cols) >= 2:
                agent_id = cols[0].strip()
                role = cols[1].strip() if len(cols) > 1 else ""
                output = cols[2].strip() if len(cols) > 2 else ""
                if agent_id and not agent_id.startswith("--"):
                    result["sub_agents"].append({
                        "id": agent_id,
                        "role": role,
                        "output_file": output
                    })
        if in_exec and in_exec_table and not stripped.startswith("|"):
            in_exec = False
            in_exec_table = False

    return result


# ── Auto-wire ────────────────────────────────────────────────────────────────


def auto_wire(mission_path: Path, campaign_dir: Path) -> tuple[int, int]:
    """Parse MISSION.md + task files, generate full coordination layer."""
    mission_dir = mission_path.parent
    task_rows = parse_mission_task_table(mission_path)
    if not task_rows:
        print(f"[FAIL] No task table found in {mission_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Found {len(task_rows)} tasks in MISSION.md")

    tasks_graph = {}
    all_task_states = {}
    all_agent_states = {}

    for row in task_rows:
        task_name = row.get("Task", "")
        task_id = extract_task_id(task_name)
        file_link = row.get("File", "")
        phase = row.get("Phase", "")
        depends_str = row.get("Depends On", "")
        depends_on = extract_depends_on(depends_str)

        task_file_name = extract_file_link(file_link)
        task_file_path = mission_dir / task_file_name

        print(f"  Parsing {task_id}: {task_file_name}")

        if task_file_path.exists():
            parsed = parse_task_file(task_file_path)
        else:
            print(f"  [WARN] Task file not found: {task_file_path}")
            parsed = {"inputs": [], "outputs": [], "sub_agents": []}

        # Build sub-agent IDs
        sub_agent_ids = []
        for sa in parsed["sub_agents"]:
            sa_id = sa["id"]
            import re
            if re.match(r"^[A-Z]$", sa_id):
                sa_id = f"{task_id}{sa_id}"
                sa["id"] = sa_id
            sub_agent_ids.append(sa_id)

        tasks_graph[task_id] = {
            "file": camp.safe_relative_to(task_file_path, Path.cwd().resolve()),
            "status": "pending",
            "depends_on": depends_on,
            "sub_agents": sub_agent_ids
        }

        # Task state with new fields
        all_task_states[task_id] = {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "campaign_id": campaign_dir.name,
            "file": camp.safe_relative_to(task_file_path, Path.cwd().resolve()),
            "status": "pending",
            "depends_on": depends_on,
            "inputs": parsed["inputs"],
            "outputs": parsed["outputs"],
            "sub_agents": sub_agent_ids,
            "started": None,
            "completed": None,
            "retry_count": 0,
            "needs_resume": False,
            "needs_human": False,
            "token_budget": {"max_tokens": None, "tokens_consumed": 0},
            "timeout_seconds": 600,
            "retry_policy": {"max_retries": 2, "max_fresh_agents": 1, "backoff_seconds": 30},
            "output_contract": {"min_size_bytes": 100, "required_sections": []},
            "findings": {},
            "artifacts": {}
        }

        # Agent states with new fields
        for sa in parsed["sub_agents"]:
            sa_id = sa["id"]
            all_agent_states[sa_id] = {
                "schema_version": "1.0.0",
                "agent_id": sa_id,
                "task_id": task_id,
                "campaign_id": campaign_dir.name,
                "role": sa["role"],
                "status": "pending",
                "heartbeat": None,
                "next_action": None,
                "tool_history": [],
                "output_file": sa["output_file"],
                "tokens_consumed": 0,
                "confidence": None,
                "artifacts": []
            }

    # Write CAMPAIGN.json atomically
    campaign_obj = {
        "schema_version": "1.0.0",
        "campaign_id": campaign_dir.name,
        "mission_ref": camp.safe_relative_to(mission_path, Path.cwd().resolve()),
        "status": "pending",
        "created": camp.now_iso(),
        "updated": camp.now_iso(),
        "tasks": tasks_graph
    }
    camp.atomic_write_json(campaign_dir / "CAMPAIGN.json", campaign_obj)

    # Write task states atomically
    for task_id, state in all_task_states.items():
        camp.atomic_write_json(campaign_dir / "tasks" / f"{task_id}.json", state)

    # Write agent states atomically
    for agent_id, state in all_agent_states.items():
        camp.atomic_write_json(campaign_dir / "agents" / f"{agent_id}.json", state)

    print(f"[OK] Auto-wired {len(tasks_graph)} tasks, {len(all_agent_states)} agents")
    return len(tasks_graph), len(all_agent_states)


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Scaffold a campaign coordination layer")
    parser.add_argument("--id", help="Campaign ID (slug)")
    parser.add_argument("--mission", required=True, help="Relative path to MISSION.md")
    parser.add_argument("--target", default=".scratch/campaigns", help="Parent directory for campaign folders")
    parser.add_argument("--auto-wire", action="store_true", help="Parse MISSION.md + task files, generate full graph")
    args = parser.parse_args()

    mission_path = Path(args.mission).resolve()
    if not mission_path.exists():
        print(f"[FAIL] Mission file not found: {mission_path}", file=sys.stderr)
        sys.exit(1)

    if args.auto_wire:
        campaign_id = mission_path.parent.name
    elif args.id:
        campaign_id = args.id
    else:
        print("[FAIL] Provide --id or use --auto-wire", file=sys.stderr)
        sys.exit(1)

    campaign_dir = Path(args.target).resolve() / campaign_id

    # Create folder structure
    for d in [campaign_dir / "tasks", campaign_dir / "agents"]:
        d.mkdir(parents=True, exist_ok=True)

    if args.auto_wire:
        task_count, agent_count = auto_wire(mission_path, campaign_dir)
    else:
        campaign_obj = {
            "schema_version": "1.0.0",
            "campaign_id": campaign_id,
            "mission_ref": camp.safe_relative_to(mission_path, Path.cwd().resolve()),
            "status": "pending",
            "created": camp.now_iso(),
            "updated": camp.now_iso(),
            "tasks": {}
        }
        camp.atomic_write_json(campaign_dir / "CAMPAIGN.json", campaign_obj)
        task_count = 0
        agent_count = 0

    # DECISIONS.md — header only
    decisions_content = f"# Decision Log — {campaign_id} Campaign\n\nAppend-only audit trail. Every orchestration decision gets an entry.\nFormat: `## <timestamp> — <what happened>` followed by rationale.\n\n---\n\n## {camp.now_iso()[:10]} T+00:00 — Campaign scaffolded\n- Mission: {camp.safe_relative_to(mission_path, Path.cwd().resolve())}\n- Mode: {'auto-wire' if args.auto_wire else 'manual'}\n- Rationale: campaign-orchestrator skill invoked\n"
    (campaign_dir / "DECISIONS.md").write_text(decisions_content, encoding="utf-8")

    # Copy health-snapshot.py + campaign.py into campaign folder
    # (health-snapshot.py does `import campaign as camp` with SCRIPT_DIR on
    # sys.path, so campaign.py MUST be present beside it — a broken scaffold
    # otherwise. Fixed 2026-08-10.)
    import shutil
    for script_name in ("health-snapshot.py", "campaign.py"):
        script_src = SCRIPT_DIR / script_name
        script_dst = campaign_dir / script_name
        if script_src.exists():
            shutil.copy2(script_src, script_dst)

    # README.md
    readme = f"""# Campaign Coordination Layer — {campaign_id}

Orchestration backbone. Tracks task state, sub-agent health, decisions, and artifacts.

## Quick Commands

```bash
# Health readout
python3 health-snapshot.py

# Monitor loop (silent unless anomaly/change)
python3 health-snapshot.py --watch --interval 30

# Scaffold a new task's state file
python3 ~/.grok/skills/campaign-orchestrator/scripts/scaffold-task.py --campaign . --task T1
```

## File Layout

```
{campaign_dir.name}/
  CAMPAIGN.json          # task graph + statuses
  DECISIONS.md           # append-only decision audit trail
  health-snapshot.py     # health readout (+ watch mode)
  tasks/                 # per-task state (TX.json)
  agents/                # sub-agent heartbeats (TXx.json)
```

## Re-Run Discipline

Each task file is self-contained. Before running a task:
1. Check if all outputs in `tasks/TX.json` exist on disk.
2. Verify output size meets `output_contract.min_size_bytes`.
3. If all outputs fresh AND no inputs changed → skip (idempotent).
4. If any output missing or input changed → execute.
"""
    (campaign_dir / "README.md").write_text(readme, encoding="utf-8")

    print(f"[OK] Campaign scaffolded: {campaign_dir}")
    if args.auto_wire:
        print(f"     Tasks: {task_count} | Agents: {agent_count}")
    else:
        print(f"     Next: populate CAMPAIGN.json with your task graph")


if __name__ == "__main__":
    main()
