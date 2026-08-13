#!/usr/bin/env python3
"""
health-snapshot.py — Campaign health readout for campaign-orchestrator.

Emits one status line per task + sub-agent for quick orchestrator resume.
Run from the campaign folder or pass --campaign <path>.

Includes output verification (not just status, but actual file checks).

Usage (one-shot):
    python3 health-snapshot.py --campaign .scratch/campaigns/my-campaign
    cd .scratch/campaigns/my-campaign && python3 health-snapshot.py

Usage (monitor loop — silent unless anomaly/change):
    python3 health-snapshot.py --watch --interval 30
    python3 health-snapshot.py --campaign .scratch/campaigns/my-campaign --interval 60

Output is ASCII-safe for Windows consoles.
"""

import argparse
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import campaign as camp


def format_snapshot(campaign_dir: Path, campaign: dict, stale_threshold: int = 900) -> list[str]:
    """Generate snapshot output lines. Returns list of strings."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append(f" Campaign : {campaign.get('campaign_id', '?')}")
    lines.append(f" Status   : {campaign.get('status', '?')}")
    lines.append(f" Mission  : {campaign.get('mission_ref', '?')}")
    lines.append(f" Updated  : {camp.iso_or_none(campaign.get('updated'))}")
    lines.append("=" * 60)
    lines.append("")

    tasks = campaign.get("tasks", {})
    task_dir = campaign_dir / "tasks"
    agent_dir = campaign_dir / "agents"

    for task_id, task_meta in tasks.items():
        status = task_meta.get("status", "?")
        depends = ", ".join(task_meta.get("depends_on", [])) or "none"

        indicators = {
            "done":       "[DONE] ",
            "in_progress": "[RUN ] ",
            "failed":     "[FAIL] ",
            "pending":    "[PEND] ",
        }
        indicator = indicators.get(status, "[????] ")

        lines.append(f"  {indicator} {task_id}  (depends: {depends})")

        # Load full task state if available
        task_state = camp.read_json(task_dir / f"{task_id}.json")
        if task_state:
            retries = task_state.get("retry_count", 0)
            needs_resume = task_state.get("needs_resume", False)
            needs_human = task_state.get("needs_human", False)
            timeout = task_state.get("timeout_seconds", 600)

            if retries > 0:
                lines.append(f"           retries: {retries}")
            if needs_resume:
                next_steps = task_state.get("next_steps", [])
                lines.append(f"           NEEDS RESUME: {next_steps[0] if next_steps else 'see task file'}")
            if needs_human:
                lines.append(f"           !!! NEEDS HUMAN: escalation threshold reached")

            # Output verification (not just status)
            if status == "done":
                verification = camp.verify_task_output(task_state, campaign_dir)
                if verification["all_ok"]:
                    lines.append(f"           outputs: verified ok ({len(verification['outputs'])} files)")
                else:
                    lines.append(f"           outputs: VERIFICATION FAILED")
                    for issue in verification["issues"][:3]:
                        lines.append(f"              ! {issue}")

            # Token budget check
            token_budget = task_state.get("token_budget", {})
            max_tokens = token_budget.get("max_tokens")
            tokens_used = token_budget.get("tokens_consumed", 0)
            if max_tokens:
                pct = (tokens_used / max_tokens) * 100 if max_tokens > 0 else 0
                over = " OVER BUDGET" if pct > 100 else ""
                lines.append(f"           tokens: {tokens_used}/{max_tokens} ({pct:.0f}%){over}")

        # Sub-agent details
        sub_agents = task_meta.get("sub_agents", [])
        if sub_agents:
            for agent_id in sub_agents:
                agent_state = camp.read_json(agent_dir / f"{agent_id}.json")
                if agent_state:
                    hb = camp.iso_or_none(agent_state.get("heartbeat"))
                    astat = agent_state.get("status", "?")
                    role = agent_state.get("role", "")
                    confidence = agent_state.get("confidence")
                    lines.append(f"           +-- {agent_id}: {astat} (hb: {hb})")
                    if role:
                        lines.append(f"                role: {role[:60]}")
                    if confidence is not None:
                        conf_str = f"{confidence:.0%}" if isinstance(confidence, float) else str(confidence)
                        lines.append(f"                confidence: {conf_str}")

                    # Anomaly: stale heartbeat check
                    if astat == "in_progress" and agent_state.get("heartbeat"):
                        age = camp.heartbeat_age_seconds(agent_state["heartbeat"])
                        if age is not None and age > stale_threshold:
                            newest_art = 0.0
                            for art in agent_state.get("artifacts", []):
                                p = camp.resolve_output_path(campaign_dir, art)
                                if p.exists():
                                    newest_art = max(newest_art, p.stat().st_mtime)
                            output_file = agent_state.get("output_file")
                            if output_file:
                                p = camp.resolve_output_path(campaign_dir, output_file)
                                if p.exists():
                                    newest_art = max(newest_art, p.stat().st_mtime)
                            if newest_art > 0:
                                art_age = time.time() - newest_art
                                if art_age > stale_threshold:
                                    lines.append(f"           !!! STUCK: hb {age:.0f}s stale, no artifacts {art_age:.0f}s")
                                else:
                                    lines.append(f"           (hb stale but artifacts advancing)")
                            else:
                                lines.append(f"           !!! STUCK: hb {age:.0f}s stale, no artifacts")
                else:
                    lines.append(f"           +-- {agent_id}: no state file yet")

    # Decision log summary
    decisions_file = campaign_dir / "DECISIONS.md"
    if decisions_file.exists():
        content = decisions_file.read_text(encoding="utf-8")
        entries = content.count("\n## ")
        last_ts = ""
        for line in content.split("\n"):
            if line.startswith("## "):
                last_ts = line[3:].strip()[:30]
        lines.append("")
        lines.append(f"  Decisions: {entries} entries | last: {last_ts or 'none'}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    return lines


def detect_changes(prev_lines: list[str] | None, curr_lines: list[str]) -> bool:
    """Return True if snapshot changed meaningfully since last check."""
    if prev_lines is None:
        return True
    return prev_lines != curr_lines


def run_watch(campaign_dir: Path, interval: int, stale_threshold: int):
    """Monitor loop — prints only on change or anomaly."""
    print(f"[WATCH] Monitoring {campaign_dir} every {interval}s (stale threshold: {stale_threshold}s)")
    print(f"[WATCH] Ctrl+C to stop. Printing only on change or anomaly.")
    print()

    prev_lines = None
    try:
        while True:
            campaign = camp.read_json(campaign_dir / "CAMPAIGN.json")
            if not campaign:
                print(f"[FAIL] No CAMPAIGN.json in {campaign_dir}", file=sys.stderr)
                sys.exit(1)

            curr_lines = format_snapshot(campaign_dir, campaign, stale_threshold)

            if detect_changes(prev_lines, curr_lines):
                ts = camp.now_iso()[:19].replace("T", " ")
                print(f"--- {ts} ---")
                for line in curr_lines:
                    print(line)
                prev_lines = curr_lines

            time.sleep(interval)
    except KeyboardInterrupt:
        print()
        print("[WATCH] Stopped.")
        sys.exit(0)


def run_once(campaign_dir: Path, stale_threshold: int):
    """One-shot snapshot."""
    campaign = camp.read_json(campaign_dir / "CAMPAIGN.json")
    if not campaign:
        print(f"[FAIL] No CAMPAIGN.json found in {campaign_dir}", file=sys.stderr)
        sys.exit(1)

    lines = format_snapshot(campaign_dir, campaign, stale_threshold)
    for line in lines:
        print(line)


def main():
    parser = argparse.ArgumentParser(description="Campaign health snapshot")
    parser.add_argument("--campaign", "-c", default=".", help="Path to campaign folder")
    parser.add_argument("--watch", "-w", action="store_true", help="Monitor loop — print only on change/anomaly")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Watch loop interval in seconds (default: 30)")
    parser.add_argument("--stale", "-s", type=int, default=900, help="Heartbeat stale threshold in seconds (default: 900 = 15min)")
    args = parser.parse_args()

    campaign_dir = Path(args.campaign).resolve()

    if args.watch:
        run_watch(campaign_dir, args.interval, args.stale)
    else:
        run_once(campaign_dir, args.stale)


if __name__ == "__main__":
    main()
