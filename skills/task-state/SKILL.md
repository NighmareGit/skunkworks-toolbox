---
name: task-state
description: Anti-context-rot state persistence for sub-agents and pipelines. Checkpoint intermediate progress to disk so agents can resume after compaction or crash. Use at the start and end of every sub-agent task, and before any long-running operation. Triggers: "save state", "checkpoint", "resume from", "pick up where I left off".
---

# Task State

Prevent context rot by checkpointing agent state to disk. Solves three problems:

1. **Context compaction** — Grok compacts at 85% window. State written before compaction survives.
2. **Pipeline crash recovery** — if a sub-agent dies mid-stage, the next agent resumes from the last checkpoint.
3. **Multi-agent handoff** — parent dispatches sub-agent; sub-agent reads state from previous stage.

## State File

```
.scratch/task-state/<task-id>.json
```

Standard JSON schema:

```json
{
  "task_id": "bug-003",
  "pipeline": "bug-hunt",
  "stage": "diagnose",
  "iteration": 2,
  "status": "in_progress",
  "last_checkpoint": "2026-07-26T15:30:00Z",
  "worktree": "worktrees/bug-003/",
  "branch": "fix/bug-003",
  "gpu_leased": "ROCm0",
  "findings": {
    "root_cause": "thread_local buffer race in ggml-cuda.cu",
    "target_file": "ggml/src/ggml-cuda/ggml-cuda.cu",
    "target_line": 3488,
    "hypotheses_tested": ["buffer-overlap", "stream-sync"],
    "hypothesis_confirmed": "buffer-overlap"
  },
  "artifacts": {
    "debug_log": ".scratch/research/bug-003-debug.md",
    "bisect_result": ".scratch/research/bug-003-bisect.md",
    "prototype_patch": ".scratch/patches/bug-003-fix.patch"
  },
  "metrics": {
    "tokens_used": 45000,
    "time_elapsed_s": 340,
    "builds_run": 3,
    "tests_run": 2
  },
  "next_steps": ["apply fix to ggml-cuda.cu:3488", "build and test with 9B ngl=1"]
}
```

## Operations

### Checkpoint (save state)

Called by an agent to persist its current state. Safe to call multiple times — last write wins.

```
/task-state checkpoint --task-id bug-003 --stage diagnose --findings '{"root_cause":"...","target_file":"..."}'
```

The orchestrator merges provided fields with existing state. Only provided fields are updated; all others persist.

**When to checkpoint:**
- At the start of every stage (mark `status: in_progress`)
- Before any long-running operation (build, benchmark, bisect)
- After any significant finding (root cause confirmed, hypothesis falsified)
- At the end of every stage (mark `status: done`)
- On compaction warning (save immediately, mark `needs_resume: true`)

### Resume (load state)

Called by a new agent to pick up where the previous one left off.

```
/task-state resume --task-id bug-003
```

Returns the full state JSON. The agent reads `stage`, `status`, `findings`, `next_steps`, and `artifacts` to understand what was done and what remains.

**Resume protocol:**
1. Load state file
2. If `status: in_progress` — previous agent died mid-stage. Re-run that stage.
3. If `status: done` — advance to next stage.
4. If `needs_resume: true` — context was compacted, agent must rebuild context from `findings` and `artifacts`.
5. If file doesn't exist — fresh start, initialize state.

### List (all task states)

```
/task-state list                     # all active tasks
/task-state list --pipeline bug-hunt # filter by pipeline
```

### Prune (cleanup completed tasks)

```
/task-state prune --older-than 7d   # remove states older than 7 days
/task-state prune --task-id bug-003  # remove specific task
```

## Integration Points

### With bug-hunt

```
Stage 0 (Triage)    → task-state checkpoint --stage triage --status done
Stage 1 (Diagnose)  → task-state resume --task-id bug-003
                       ... diagnose work ...
                       task-state checkpoint --stage diagnose --findings '{...}' --status done
Stage 2 (Bisect)     → task-state resume → ... → checkpoint
...
Stage 7 (Mark)       → task-state checkpoint --status resolved
                       task-state prune --task-id bug-003  (cleanup)
```

### With worktree-guard

Worktree path and branch name are persisted in task state. On resume, `worktree-guard` reads the state file instead of creating a new worktree.

### With context compaction

When Grok warns about compaction, the agent should:
1. Call `task-state checkpoint` immediately with current findings
2. Set `needs_resume: true`
3. After compaction, call `task-state resume` to rebuild context

## Anti-Context-Rot Pattern

The core pattern is: **write state, not just code.** An agent should treat its state file as its external memory.

```
// BAD — context lost on compaction
"I've confirmed the root cause is the buffer race. Next I'll fix ggml-cuda.cu line 3488."
[compaction happens — agent forgets everything]

// GOOD — state survives compaction
task-state checkpoint --findings '{"root_cause":"buffer race","target_line":3488}'
[compaction happens]
task-state resume  // → "Ah yes, buffer race at line 3488, now I'll fix it"
```

## Rules

1. **Checkpoint before long ops.** Build, benchmark, bisect — save state first.
2. **Checkpoint on findings.** Every significant discovery goes to disk immediately.
3. **Resume, don't restart.** Always check for existing state before starting fresh.
4. **Prune resolved.** Clean up state files for completed tasks so the directory doesn't bloat.
5. **One state file per task.** Don't scatter state across multiple files — one JSON per task ID.
