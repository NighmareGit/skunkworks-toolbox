# {{PROJECT_NAME}} — Agents & Workflows

## Context Budget Note

> A fresh session has ~256K context. Reading all linked docs costs ~50K. If resuming an active campaign, read only: `agents.md` (Session Startup section + Context Budget Note) → `CAMPAIGN.json` → `MISSION.md` → `DECISIONS.md` (last 10 ## entries) → `tasks/<first_ready_task>.json` → task instruction file → `ORCHESTRATOR.md` (if exists) → run `health-snapshot.py`. This keeps orientation under 20K context.

## The Agent Orientation Point

> **This is your main entry point for working with agents, workflows, and the {{PROJECT_NAME}} system.** All other docs fold into this concept hub.

---

## Quick Reference

| Concept | Link |
|---------|------|
| Project Mission | [README.md](README.md) |
| Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Testing Guide | [TESTING.md](TESTING.md) |
| Repository Structure | [project-map.md](project-map.md) |
| Secrets Management | [`{{SECRETS_PATH}}`]({{SECRETS_PATH}}) |

---

## Session Startup

> **Startup-Critical Sections:** For session startup, read only the Session Startup section and the Context Budget Note. Skip the rest until needed.

When starting any session in this project, do these steps IN ORDER:

1. **Read this file** (`agents.md`) — you're already here.
2. **Check for active campaigns:**
   ```bash
   ls .scratch/campaigns/
   ```
   If multiple campaigns exist, prioritize by: (1) tasks in `in_progress`, (2) campaign `status:in_progress`, (3) `needs_human:true`, (4) `status:pending`. Report all campaigns to the user with a recommendation.
2.5. **Smoke-test the dispatch toolchain** (mandatory after any toolchain change, recommended at every session start):
   ```bash
   python3 tests/run_toolchain_tests.py                          # model-free tests
   python3 .scratch/scripts/toolchain.py dispatch --mode sabotage --task-id S0   # failure injection
   ```
   If either fails, STOP and report — the dispatch gates you are about to rely on do not hold.
2.5b. **Handoff resume check** — if `.scratch/task-state/RESUME.md` exists, read it FIRST.
   A previous session handed off and left the exact resume command + its memo there; a
   fresh session needs no other instruction (the human only said "resume").
2.6. **Boot the state machine** (stateless interpreter — the resume-from-files guarantee):
   ```bash
   python3 .scratch/scripts/dispatch-state.py next-action --cwd "$PWD"
   ```
   It reads all dispatch records and emits THE next command in priority order
   (VERIFY in-flight → DISPATCH ready → ADVANCE verified → RECOVER failed). Do what it
   says, then re-run. Stop anywhere, boot anywhere, same trajectory.
2.7. **Handoff** (BEFORE ending a session — trigger: the user says "we need a new
   session" / hand over / handoff / takeover): ONE command:
   ```bash
   python3 .scratch/scripts/toolchain.py dispatch --mode handoff --cwd "$PWD" --note "what I did, what's next"
   ```
   It settles the mechanical state (`verified → done`), stamps the handoff line in
   `DECISIONS.md`, writes `RESUME.md` (the exact boot command + your memo), and prints
   what the fresh session will do on boot. Then "resume" is all the fresh session needs.
   Never end a session without running this if the user asked for one.
3. **If campaigns exist:**
   a. Read the campaign's `CAMPAIGN.json` (task graph + statuses).
      - If `CAMPAIGN.json` is not valid JSON, report corruption to the user with the file path and stop. Do not proceed with a corrupt task graph.
      - If campaign `status` is `pending` and `created` >24h ago, flag to the user.
   a.5. Read the campaign's `MISSION.md` (path from `mission_ref` field in `CAMPAIGN.json`) to understand WHAT the campaign is about.
   b. Read the campaign's `DECISIONS.md` — last 10 ## entries (read from bottom; entries are delimited by `## <timestamp>` headers). If fewer than 10 exist, read the whole file.
   c. Run `health-snapshot.py` from within the campaign folder: `cd .scratch/campaigns/<id> && python3 health-snapshot.py`.
   d. Read the campaign's `ORCHESTRATOR.md` if it exists (role definition; skip if missing).
   e. Read `tasks/<first_ready_task>.json` for inputs, outputs, budget, and timeout. A "ready" task has `status:pending` and all `depends_on` tasks have `status:done`.
   f. Read the task instruction file (from the task's `file` field) for the first ready task.
   g. If the first ready task has `sub_agents`, read `agents/<agent_id>.json` for each to understand their role and `output_file`.
4. **If no campaigns exist:** read the project's mission/control file for planned work.
5. **Report status to the user** before acting on anything.

   Status report format:
   ```
   ## Campaign Status: <campaign_id>
   - Mission: <one-line from MISSION.md>
   - Status: <status> | Updated: <updated>
   - Tasks: <count> total (<done> done, <pending> pending, <in_progress> running, <failed> failed, <needs_human> escalated)
   - First ready task: <task_id or "none">
   - Recommended next action: <specific action with task ID if applicable>
   ```

   Based on campaign state, recommend one of: [dispatch first ready task / ask user for direction / wait for running agents to complete / report completion].

---

## North-Star Mission

> **{{MISSION}}**

---

## Environment Setup (Linux)

```bash
# Ensure Cargo/toolchain binaries are on PATH
export PATH="$HOME/.cargo/bin:$PATH"
cd <project-root>

# Verify local model server (loopback)
curl -s {{MODEL_SERVER_URL}}/health && echo

# Verify secrets keyfile
test -f {{SECRETS_PATH}} && echo "secrets OK"
```

---

## Repository Layout

{{REPO_LAYOUT}}

---

## Campaign Orchestration

When coordinating multi-task efforts with parallel sub-agents, use the
[`campaign-orchestrator`](~/.grok/skills/campaign-orchestrator/SKILL.md) skill
to set up the coordination layer.

It provides:

- **Task graph + status tracking** (`CAMPAIGN.json`) — dependency-aware scheduling
- **Per-task state** (`tasks/TX.json`) — inputs, outputs, retries, resume points
- **Sub-agent heartbeats** (`agents/TXx.json`) — health monitoring for parallel workers
- **Decision audit trail** (`DECISIONS.md`) — append-only log of why decisions were made
- **Health readout** (`health-snapshot.py`) — one-glance campaign status

### When to Use

Invoke `campaign-orchestrator` when:
- A mission splits into 3+ tasks with dependency ordering
- Any task fans out to parallel sub-agents (concurrent searches, dispatches)
- The work must survive crashes / context compaction and resume cleanly
- You need an audit trail of orchestration decisions

### Active Campaign Check

**Before creating new campaigns, always check `.scratch/campaigns/` for in-progress work.**
`CAMPAIGN.json` is the source of truth for active work. Read it first.

To see all active campaigns:
```bash
for c in .scratch/campaigns/*/; do
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(f\"{d.get('campaign_id','?')}: {d.get('status','?')} ({len(d.get('tasks',{}))} tasks)\")" "$c/CAMPAIGN.json"
done
```

### Quick Setup

```bash
# 1. Scaffold the coordination layer
python3 ~/.grok/skills/campaign-orchestrator/scripts/scaffold-campaign.py \
    --id <campaign-slug> \
    --mission <path-to-MISSION.md> \
    --target .scratch/campaigns

# 2. Populate CAMPAIGN.json with your task graph
# 3. Create tasks/TX.json per task (inputs, outputs, sub_agents)
# 4. Create agents/TXx.json per sub-agent (role, output_file)
# 5. Run health-snapshot.py anytime for a status readout
```

### Dispatch Toolchain (`.scratch/scripts/`)

Every sub-agent dispatch MUST flow through the dispatch toolchain — it mechanizes the
fixes for the project's historical failure modes (wrong directory, missing inputs,
scope explosions, verification vacuum). Single entry point:
`python3 .scratch/scripts/toolchain.py dispatch`.
The whole toolchain is **Python** (`toolchain.py preflight|verify|contract|idempotency|
decision-log|adr-log|recovery|fix-workdir|dispatch` — cross-platform, no bash).

```bash
# Pre-dispatch (layers 0-4: idempotency, preflight, scope, sanitize, contract)
python3 .scratch/scripts/toolchain.py dispatch --mode pre \
    --cwd "$PWD" --task-id R1 \
    --inputs "reports/prioritized-shortlist.md" \
    --outputs "distillation/shortlist-notes.md" \
    --min-bytes 1000 --format markdown \
    --description "R1: read shortlist → structured notes"

# Post-dispatch (layers 6-9: verify, contract, decision log, budget)
python3 .scratch/scripts/toolchain.py dispatch --mode post \
    --cwd "$PWD" --task-id R1 \
    --outputs "distillation/shortlist-notes.md" \
    --min-bytes 1000 --format markdown

# Workflow waves (dispatch-wave.rhai delivers STRUCTURED results, not files):
# close the lineage loop with post-workflow, which links worker/verifier agent
# ids, moves the state machine to done, and stamps the decision log.
python3 .scratch/scripts/toolchain.py dispatch --mode post-workflow \
    --cwd "$PWD" --task-id R1 \
    --agent-ids "<worker-id>,<verifier-id>" \
    --verified-count 2 --result-count 2

# Session handoff (before ending a session — see Session Startup step 2.7)
python3 .scratch/scripts/toolchain.py dispatch --mode handoff --cwd "$PWD" --note "what I did, what's next"
```

**Regression net** (run after ANY change to `.scratch/scripts/`, and at session start):

```bash
python3 tests/run_toolchain_tests.py                                 # model-free tests
python3 .scratch/scripts/toolchain.py dispatch --mode sabotage --task-id S0   # failure injection: proves the gates gate
```

### Role Routing

Sub-agent work is routed to roles defined in `~/.grok/config.toml` (`[subagents.roles.*]`).
Full model-role matrix: `~/.grok/ROLE-ARCHITECTURE.md`. Quick map:

| Work type | `subagent_type` | Model |
|-----------|----------------|-------|
| Coordination, forks, verification | `orchestrator` / `verifier` | `deepseek-v4-flash` (cheap, mechanical) |
| Research, implementation, planning | `researcher` / `implementer` / `general` / `planner` | `longcat` (deep work, 256K ctx — needs R1-R9 rails) |
| Codebase recon | `explore` | `local-gemma-4-e4b` (free local AI at {{MODEL_SERVER_URL}}; no math, re-verify output) |

Longcat roles loop without rails — every longcat brief MUST include the rail core
(`~/.grok/prompts/longcat-rails.md`): single goal, tool budget, numbered steps,
stop-and-report, definition of done. Use `sanitize-prompt.py --brief` to build the brief.

### Multiple Active Campaigns

If multiple campaigns are active, prioritize by:
1. Campaigns with tasks in `in_progress` (mid-execution, highest priority)
2. Campaigns with `status: in_progress` (overall)
3. Campaigns with `needs_human: true` (escalation needed)
4. Campaigns with `status: pending` (not yet started)

Report all active campaigns to the user and ask which to focus on.

### Emergency Stop

To pause a campaign immediately:
1. Note the current task ID and agent ID
2. Kill the sub-agent process (if identifiable)
3. Set the task `status: failed`, `needs_resume: true`
4. Log the pause in DECISIONS.md with rationale
5. Run `python3 health-snapshot.py` to confirm state

To resume: read the paused task's `next_action` from its task state file and re-dispatch.

### Resume Protocol

**Primary mechanism — the stateless interpreter:** run `dispatch-state.py next-action`
(Session Startup step 2.6). It computes THE next command from files alone — a session
resumes from files, not from memory. The steps below are the task-file layer for
interrupted sub-agents.

When resuming a paused or interrupted campaign:

1. **Identify interrupted tasks:** run `python3 health-snapshot.py` — look for `needs_resume: true` or `needs_human: true`.
2. **Read task state:** `tasks/TX.json` → check `next_action` for where to continue.
3. **Read agent state:** `agents/TXx.json` → check `output_file` for partial progress.
4. **Decide action:**
   - If partial output exists: dispatch new agent with context of what was done.
   - If no output: retry from scratch with the same brief.
   - If `needs_human: true`: report to the user with diagnosis.
5. **Log the resume decision** in DECISIONS.md.
6. **Dispatch** using the standard dispatch protocol.

### Orchestrator Delegation Rule

When acting as orchestrator, **never execute task work directly**. Dispatch
sub-agents for all execution, planning, and review. Reserve your context for
coordination, decisions, and monitoring.

| Orchestrator Does | Orchestrator Delegates |
|-------------------|------------------------|
| State machine advancement | Research & data collection |
| Health monitoring | Screening & scoring |
| Output verification | Synthesis & writing |
| Escalation decisions | Planning & decomposition |
| Decision logging | Quality review |
| Budget tracking | Code generation |

---

## State Verification

Before trusting campaign state, verify:

- [ ] `CAMPAIGN.json` is valid JSON (not corrupt)
- [ ] Every task with `status: done` has outputs on disk
- [ ] Every output file meets `output_contract.min_size_bytes`
- [ ] No tasks stuck in `in_progress` with stale heartbeats (>15min)
- [ ] `DECISIONS.md` is append-only (no rewritten history)

Run `python3 health-snapshot.py` — it performs output verification automatically.
Tasks with `status: done` that fail verification are flagged.

---

*This document is the main orientation point. All other docs cross-reference this file.*
