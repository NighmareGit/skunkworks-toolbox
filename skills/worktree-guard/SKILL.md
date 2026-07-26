---
name: worktree-guard
description: Pre-flight guard that ensures isolated worktree/branch before any code-modifying sub-agent runs. Creates worktree if needed, reports path, cleans up after. Use as pre-condition for prototype, implement, bug-hunt, to-ticket, or any destructive code work.
---

# Worktree Guard

Ensure code-modifying sub-agents run in isolation. Three phases: **pre-flight** (ensure worktree exists), **during** (report path for sub-agent use), **post-flight** (cleanup or persist).

## Pre-Flight (before any code change)

Delegate creation to `using-git-worktrees` if a worktree doesn't already exist. Provide the task identifier so the branch/worktree is named predictably.

```
Task ID → worktree path:     worktrees/<task-id>/
Task ID → branch name:       fix/<task-id>
```

**If worktree already exists** (resuming a crashed pipeline): verify it's valid, report path, skip creation.

**If no worktree:** call `using-git-worktrees` with branch name `fix/<task-id>`, path `worktrees/<task-id>/`.

### GPU Lease Association

If the task requires a GPU, acquire the lease AFTER worktree creation and BEFORE any build/run. Associate the lease with the worktree path so cleanup can release it.

```
Worktree:  worktrees/bug-001/
GPU:       ROCm0 (leased until stage complete)
```

## During (report for sub-agent use)

Output to the calling pipeline:

```json
{
  "worktree_path": "/path/to/worktrees/bug-001/",
  "branch": "fix/bug-001",
  "gpu_leased": "ROCm0",
  "lease_expires": "2026-07-26T15:30:00Z"
}
```

The sub-agent `cd`s into `worktree_path` and works there. All builds, tests, and file modifications happen inside the worktree.

## Post-Flight (after sub-agent completes)

Two modes, controlled by the caller:

### Mode: cleanup (default for bug-hunt)

```bash
# Release GPU lease first
gpu-lease release <lease-id>

# Remove worktree
git worktree remove worktrees/<task-id>/ --force

# Delete branch
git branch -D fix/<task-id>
```

Use when the fix is committed to the main repo (bug-hunt Stage 7 Mark). The worktree is disposable — the commit history is in the main repo.

### Mode: persist (for review or manual merge)

```bash
# Release GPU lease
gpu-lease release <lease-id>

# Leave worktree in place, report path
echo "Worktree preserved at worktrees/<task-id>/"
echo "Branch: fix/<task-id>"
```

Use when the user wants to inspect, manually merge, or iterate further. Caller is responsible for eventual cleanup.

## Crash Recovery

If the pipeline crashes mid-stage, the worktree and GPU lease persist. On resume:
1. Pre-flight detects existing worktree → skip creation
2. GPU lease may have expired → re-acquire if needed
3. Sub-agent continues from where it left off

State is tracked in `.scratch/bug-hunt-state.json` (or task-specific equivalent).

## Integration Points

| Caller Skill | Task ID Pattern | Mode |
|-------------|----------------|------|
| `bug-hunt` | `bug-<id>` | cleanup after Stage 7 Mark |
| `prototype` | `proto-<timestamp>` | persist (user reviews) |
| `implement` | `feat-<name>` | persist (user merges) |
| `to-ticket` | `ticket-<id>` | cleanup after verification |
| `gdn-fix-pipeline` | `gdn-loop-<n>` | cleanup after verify |

## Quick Start for Sub-Agents

```
# Pre-flight
/worktree-guard pre-flight --task-id bug-003

# Work in worktree
cd worktrees/bug-003/
# ... diagnose, prototype, verify ...

# Post-flight (on success)
/worktree-guard post-flight --task-id bug-003 --mode cleanup
```

## Rules

1. **Never modify code outside a worktree.** Pre-flight must pass before any `search_replace` or `write` call.
2. **Release GPU before removing worktree.** Lease release first, then `git worktree remove`.
3. **Clean up on success, persist on failure.** Let the user inspect failed attempts.
4. **Re-entrant.** Running pre-flight twice with the same task ID is safe (idempotent).
