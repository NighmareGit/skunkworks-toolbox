---
name: task-state
description: >
  Persist and resume agent state across compaction, crashes, and multi-agent handoffs.
  Uses atomic file operations (mkdir lock, .tmp + rename, fsync) to prevent data loss.
  Includes a helper script at .scratch/scripts/task-state.py for all operations.
  AUTO-LOADED by every agent at session startup via AGENTS.md Step 1.
  Trigger phrases: "save state", "checkpoint", "resume from", "pick up where I left off",
  "compaction needed", "before compaction", "/task-state", "stage complete",
  "stage done", "significant finding", "long operation", "multi-agent handoff",
  "context rot", "state persistence".
---

# Task State — Anti-Context-Rot (Hardened)

Prevent context loss by checkpointing agent state to disk. Uses atomic file
operations: `mkdir` for advisory locking, `.tmp` + `rename` for atomic writes,
`fsync` for durability.

## Helper Script

```bash
.scratch/scripts/task-state.py <command> [args]
```

All operations go through this script. It handles:
- **Atomic writes** — write to `.tmp`, `os.rename()` (atomic on POSIX), `os.fsync()`
- **Locking** — `mkdir`-based advisory lock with 5s timeout and 50ms retry
- **Error recovery** — malformed JSON → recovered state object, never crashes
- **Schema versioning** — every state file includes `schema_version: "2.0.0"`
- **Task-ID discovery** — `CURRENT` file + `CURRENT_TASK_ID` env var

## Commands

### Save (checkpoint)

```bash
# Set entire state (first-time save)
python3 .scratch/scripts/task-state.py save --task-id session-main --set '{"status":"in_progress","findings":{}}'

# Merge fields into existing state (update only what changed)
python3 .scratch/scripts/task-state.py save --task-id session-main --merge '{"findings":{"root_cause":"alpha_floor"}}'

# Set needs_resume on compaction warning
python3 .scratch/scripts/task-state.py save --task-id session-main --merge '{"needs_resume":true,"next_steps":["do X","do Y"]}'
```

The lock file prevents two agents from writing simultaneously. Lock timeout
is 5 seconds — if another agent holds the lock longer, the caller fails
loudly rather than silently overwriting data.

### Read (resume)

```bash
# Full state
python3 .scratch/scripts/task-state.py read --task-id session-main

# Specific field (returns JSON value or exits 1)
python3 .scratch/scripts/task-state.py read --task-id session-main --field findings.root_cause

# Current task ID (if no --task-id, reads from CURRENT file or CURRENT_TASK_ID env)
python3 .scratch/scripts/task-state.py read
```

### List

```bash
python3 .scratch/scripts/task-state.py list
```

Shows all state files with: task_id, status, stage, last_checkpoint, needs_resume flag.

### Prune

```bash
# Dry run
python3 .scratch/scripts/task-state.py prune --older-than 7d

# Actually delete
python3 .scratch/scripts/task-state.py prune --older-than 7d --force
```

### Current Task ID

```bash
# Print current
python3 .scratch/scripts/task-state.py current

# Set current (done automatically by save)
python3 .scratch/scripts/task-state.py current --set session-main
```

## Resume Protocol

```python
# Step 1: Load state
import subprocess, json
def load_state(task_id="session-main"):
    result = subprocess.run(
        ["python3", ".scratch/scripts/task-state.py", "read", "--task-id", task_id],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None  # Fresh start
    return json.loads(result.stdout)

state = load_state()

# Step 2: Interpret status
if state is None:
    # Fresh start — initialize new state
    ...
elif state.get("status") == "in_progress" or state.get("needs_resume"):
    # Previous agent died or context was compacted
    # Rebuild from state["findings"] and state["artifacts"]
    # Execute next_steps[0]
    ...
elif state.get("status") == "done":
    # Advance to next stage
    ...
```

## Schema

```json
{
  "schema_version": "2.0.0",
  "task_id": "session-main",
  "stage": "scaffolding-approved",
  "iteration": 3,
  "status": "in_progress",
  "needs_resume": false,
  "last_checkpoint": "2026-07-29T00:35:00Z",
  "findings": {},
  "artifacts": {},
  "next_steps": [],
  "recovered": false,
  "recovery_note": null
}
```

## When to Checkpoint

- **Agent start:** save with `status: in_progress`
- **Before long ops** (>30s): save with current findings
- **On significant finding:** merge finding into state
- **On compaction warning:** save with `needs_resume: true`, commit, push
- **Agent end:** save with `status: done`

## Compaction Protocol

```
1. python3 .scratch/scripts/task-state.py save --task-id <id> --merge '{"needs_resume":true}'
2. git add .scratch/task-state/<id>.json
3. git commit -m "checkpoint: pre-compaction"
4. git push   # best-effort, state is safe on disk from step 1
```

State is safe on disk the moment the save command returns. Git push is
best-effort for cross-machine recovery — not a critical path.

## Directory Structure

```
.scratch/task-state/
├── CURRENT              # Contains current task ID (e.g. "session-main")
├── session-main.json    # State file
├── session-main.lock    # Lock directory (mkdir-based)
├── session-main.tmp     # Temp file (written atomically, then renamed)
└── bug-003.json         # Another task's state
```
