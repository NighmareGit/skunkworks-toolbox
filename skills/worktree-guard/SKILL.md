---
name: worktree-guard
description: Pre-flight guard that ensures isolated worktree/branch before any code-modifying sub-agent runs. Creates worktree if needed, reports path, cleans up after, and bootstraps the build (copy configured build dirs from a prior ticket, repoint CMAKE_HOME_DIRECTORY, guard against the stale build.make silent-skip hazard). Use as pre-condition for prototype, implement, bug-hunt, to-ticket, or any destructive code work.
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

### Build Bootstrap (reuse configured build dirs)

If a previous ticket's worktree has configured build dirs (e.g. `build-rocm-native`,
`build-cuda-b`), **copy them instead of re-running cmake configure** — saves ~20 min
per ticket:

```bash
# From the repo root (worktrees/ lives there)
cp -r worktrees/<prev-task>/build-rocm-native worktrees/<task-id>/build-rocm-native
cp -r worktrees/<prev-task>/build-cuda-b      worktrees/<task-id>/build-cuda-b
```

Then **repoint the source path** in every copied `CMakeCache.txt` — the cache still
points at the previous worktree:

```bash
cd worktrees/<task-id>
sed -i 's|/path/to/worktrees/<prev-task>|/path/to/worktrees/<task-id>|g' \
    build-rocm-native/CMakeCache.txt build-cuda-b/CMakeCache.txt
grep -m1 CMAKE_HOME_DIRECTORY build-rocm-native/CMakeCache.txt  # verify
```

Sanity-build before dispatching the sub-agent:

```bash
cmake --build build-rocm-native --target rpc-server -j$(nproc)   # or the ticket's target
```

#### ⚠️ The stale build.make hazard (silent skip)

Per-target `build.make` files under `CMakeFiles/<target>.dir/` may still reference
the **old worktree's source path**. `cmake --build` then reports `[100%] Built target`
("up to date") and **silently skips recompiling your edits** — the agent thinks its
changes are built when they aren't. Symptoms: gate fails with old behavior, or the
new symbol is absent from the binary.

Fix: remove the stale per-target dir and re-configure:

```bash
rm -rf build-rocm-native/CMakeFiles/ggml-rpc.dir    # the edited target's dir
cmake -S . -B build-rocm-native                      # re-configure (fixes build.make)
cmake --build build-rocm-native --target rpc-server -j$(nproc)
```

**Verify the build actually took your edits** — never trust "Built target" alone:

```bash
nm -C build-rocm-native/bin/rpc-server | grep <new-symbol>   # must be present
# or, for a .so transport lib:
nm -C build-rocm-native/bin/libggml-rpc.so | grep <new-symbol>
```

Rule: after ANY build-bootstrap, confirm the new symbol/lines are in the artifact
before the sub-agent runs its gate. A "clean" build that skipped your code is a
silent false-green.


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
