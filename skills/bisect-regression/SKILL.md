---
name: bisect-regression
description: Use when a regression appeared between two known git commits and you need to find the exact breaking change, extract a minimal fix, and understand the root cause. Triggered by phrases like "bisect this", "find what broke", "regression between X and Y", "when did this start failing?", or "what commit broke this?"
---

# Bisect Regression

## Overview

When a regression has a **deterministic pass/fail signal** and you know a GOOD and BAD commit, `git bisect` automation finds the exact breaking change in log(N) steps. The non-obvious part is writing a **reliable automated test script** — that's 80% of the work.

**Core principle:** A buggy test script = a wrong bisect result. Invest half your time in the test script before starting the bisect.

## When to Use

- ✅ Reproducible regression with deterministic pass/fail
- ✅ Known GOOD commit (before the bug) and BAD commit (after the bug)
- ✅ Test can run unattended (no human judgment needed)
- ✅ Project builds from command line

## When NOT to Use

- ❌ Non-deterministic / flaky failures (bisect needs deterministic signal)
- ❌ No known GOOD commit (can't anchor the search)
- ❌ Bug requires visual inspection or human judgment per step
- ❌ Build takes >5 minutes per commit (bisect becomes impractical)

## Preconditions Checklist

Before running bisect, verify ALL of these manually:

- [ ] **GOOD commit confirmed:** Checkout GOOD, build, test — verify passes
- [ ] **BAD commit confirmed:** Checkout BAD, build, test — verify fails
- [ ] **Test is deterministic:** Run GOOD 3 times — all pass. Run BAD 3 times — all fail.
- [ ] **Model/input fixed:** Same model file, same prompt, temperature=0, fixed seed
- [ ] **No external state:** Kill all lingering servers, use random ports, clean temp files

## Test Script Design Pattern

### Exit Code Contract

| Exit | Meaning | When |
|------|---------|------|
| 0 | GOOD | Regression does NOT manifest |
| 1 | BAD | Regression DOES manifest |
| 125 | SKIP | Cannot test (build fails, server dies, config broken) |

### Minimum Viable Test Script

```bash
#!/bin/bash
set -e

# 1. FORCE clean state
pkill -f "my-server" 2>/dev/null || true
sleep 2
PORT=$((19950 + RANDOM % 1000))
fuser -k $PORT/tcp 2>/dev/null || true
sleep 1

# 2. FORCE rebuild (see Build System Pitfalls below)
cd "$BUILD_DIR"
rm -f bin/my-binary                          # force relink
cmake .. -D<FLAGS> > /dev/null 2>&1 || exit 125  # reconfigure
cmake --build . --target my-binary -j$(nproc) > /tmp/build.log 2>&1 || exit 125

# 3. Start and health-check
./bin/my-binary --port $PORT > /dev/null 2>&1 &
SERVER_PID=$!
sleep 5
kill -0 $SERVER_PID 2>/dev/null || exit 125

# 4. Test
RESPONSE=$(curl -s --max-time 30 "http://localhost:$PORT/test")
kill $SERVER_PID 2>/dev/null; wait 2>/dev/null

# 5. Evaluate — use sys.exit() for clear exit codes
echo "$RESPONSE" | python3 -c "
import sys
# ... check for pass/fail signal ...
if passes:
    sys.exit(0)   # GOOD
else:
    sys.exit(1)   # BAD
"
```

## Build System Pitfalls

**The #1 failure mode:** cmake doesn't recompile after `git bisect` changes source files.

**Why:** Git sets file mtimes to checkout time. If cmake's dependency tracking uses content hashing or if .a archives aren't invalidated, stale objects get linked.

**Fix — always do this in your test script:**

```bash
# Delete specific object files, archives, and shared libs
rm -f build/path/to/changed_file.cpp.o
rm -f build/path/to/libarchive.a
rm -f build/bin/libshared.so

# Reconfigure cmake (regenerates Makefiles for this commit)
cmake .. -D<FLAGS> > /dev/null 2>&1

# Now rebuild
cmake --build . --target binary -j$(nproc)
```

**Finding the right .o file:** Build systems may place objects in unexpected directories (e.g., HIP builds compile CUDA sources into a HIP subdirectory). Use `find build -name "*.o" | grep <filename>` to locate them.

## Running the Bisect

```bash
cd project
git bisect start HEAD <GOOD_COMMIT>
git bisect run bash /path/to/test-script.sh
```

**Expect:** ~8-12 steps for 300-400 commits, ~1-2 minutes per step, 10-25 minutes total.

**While it runs, watch for:**
- All steps returning the same result → test script broken
- Many BUILD FAILED (exit 125) → range too wide, narrow anchors
- First bad commit is implausible (e.g., a logging change) → test script bug

**If the bisect finishes with a suspect commit, don't trust it yet.** Manually verify:
```bash
git checkout <SUSPECT_COMMIT>~1  # parent — should be GOOD
# build, test → verify GOOD
git checkout <SUSPECT_COMMIT>     # the commit — should be BAD
# build, test → verify BAD
```

## Root Cause Analysis

### Step 1: Read the Diff

```bash
git show <BAD_COMMIT> -p
```

Filter out noise:
- Changes gated by feature flags your test doesn't use (e.g., `if (is_rpc_backend)` on single-GPU)
- Trace/logging changes
- Comment-only changes

### Step 2: Binary-Search Within the Commit

If the commit touches multiple files, isolate which file:

```bash
# Revert only file A to GOOD version
git show <GOOD_COMMIT>:path/to/file_a.cpp > path/to/file_a.cpp
# Build, test → if FIXED, bug is in file_a
# If still BAD, revert file B, etc.
```

If the commit touches multiple functions in one file, isolate which function:

```bash
# Revert only function X (copy-paste from GOOD commit)
# Build, test → if FIXED, bug is in function X
```

### Step 3: Trace Data Flow

Once you find the specific change, trace the data:

```
Where does the data come from?
   ↓
What thread/stream does it travel on?
   ↓
Where is synchronization enforced?
   ↓
Where could a race occur?
```

**Red flags to look for:**
- Shared mutable state (`thread_local`, `static`, global buffers)
- Synchronization primitives changed (event_wait → event_synchronize, async → sync)
- Ordering dependencies removed (early returns, skipped queue ops)
- Multiple writers to the same buffer without locking

### Step 4: Confirm by Targeted Revert

Revert ONLY the suspected change, keeping everything else at BAD:
```bash
# Edit the file: revert the specific function/block
# Build, test
# If FIXED → confirmed
# If still BAD → keep searching
```

## Extracting the Minimal Fix

**Principle: Touch as little as possible.** The goal is NOT to revert the entire breaking commit. Preserve any perf optimizations or unrelated changes that don't cause the bug.

**Checklist for the fix:**
- [ ] Only changes code related to the root cause
- [ ] Preserves unrelated changes from the breaking commit
- [ ] Builds cleanly
- [ ] Passes the regression test
- [ ] Applied to HEAD (not just the bisect commit)
- [ ] Can be explained in one sentence

## Verification Gate

Before calling it done:

| Check | How |
|-------|-----|
| Fix works at HEAD | Apply patch to latest commit, build, test |
| Fix works at breaking commit | Verify the bisect commit with fix applied |
| No regression | Test non-affected models/configurations |
| Patch is minimal | `git diff --stat` — should be single file, few lines |
| Root cause documented | Write `.scratch/research/<ticket>-bisect-fix.md` |

## Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Stale build objects | Every commit tests the same (GOOD or BAD) | Delete .o files, force cmake reconfigure |
| Port conflict | Server fails to start, exit 125 | Use random ports, kill all servers first |
| Wrong response field | Test marks all GOOD or all BAD | Check both `content` and `reasoning_content` |
| CLI output artifacts | `>` loop looks like GDN bug | Use server API, not CLI tools |
| Not checking both fields | Model uses different field than expected | `msg.get('reasoning_content') or msg.get('content')` |
| Fixing at bisect commit only | Fix doesn't apply to HEAD | Always port and test at HEAD |
| Reverting entire commit | Loses perf improvements | Binary-search within the commit's diff |

## Quick Reference

```bash
# Start bisect
git bisect start HEAD <GOOD_COMMIT>
git bisect run bash test.sh

# Manual step
git bisect good | bad | skip

# Show log
git bisect log

# Reset when done
git bisect reset

# Save breaking commit's diff
git show <BAD_COMMIT> -p

# Revert one file to GOOD version
git show <GOOD_COMMIT>:path/to/file > path/to/file

# Force rebuild after checkout
rm -f build/path/to/file.o build/path/to/lib.a
cmake .. && cmake --build . -j$(nproc)

# Save minimal patch
git diff -- path/to/file > fix.patch
```

## Real-World Impact

**GDN GPU corruption (2026-07-25):** Bisected 382 commits to find `590597110` (B+15 RPC prefetch). Root cause: `thread_local` pinned staging buffer shared between `set_tensor_async` and `cpy_tensor_async` — second call overwrites buffer before first H2D completes. Fix: -3/+2 lines. Tag: `v8-gdn-fix`.

Full procedure: `.scratch/procedures/git-bisect-regression-fix.md`
