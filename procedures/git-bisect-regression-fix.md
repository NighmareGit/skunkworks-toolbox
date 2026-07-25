# Procedure: Git Bisect → Root Cause → Minimal Fix

**Date:** 2026-07-25  
**Domain:** GDN GPU corruption (HIP/ROCm)  
**Outcome:** FIXED — -3/+2 lines after 382-commit bisect

---

## 1. Problem Framing

### Symptoms
- Qwen3.5 Gated Delta Net (GDN) models produce garbled `?` output on GPU
- Same model works on CPU (ngl=0) — confirms the bug is GPU-backend-specific
- 9B MoE model is affected, not just 122B — eliminates model-size theories
- **Key discriminator:** Use `llama-server` (not `llama-cli`) — CLI's `>` loop is a CLI artifact, not a GDN bug. Server gives clean JSON with actual token content.

### Preconditions for Bisect
Before bisecting, confirm:
1. You have a **reliably GOOD commit** (GDN produces text)
2. You have a **reliably BAD commit** (GDN produces garbage)
3. The test case is **deterministic** (temperature=0, fixed seed)
4. The test can run **unattended** and return a clear pass/fail

### Our Anchors
| Anchor | Commit | GDN Output |
|--------|--------|-----------|
| GOOD | `2e68087aa` (Gemma4 MTP merge) | "Thinking Process:..." |
| BAD | `6f56b74c8` (HEAD) | "????????" |

---

## 2. Test Script Design

### The Critical Rule
> **Your test script IS the bisect.** A buggy test = a wrong result. Invest the time to get it right.

### v1 Failure Mode (What Went Wrong)
Our first automated bisect returned `a16cce81d` ("ngram: reduce noisy logs") as the first bad commit — a 2-line logging change that couldn't possibly break GDN. Root cause: **the test marked every commit BAD** because:

1. **Stale builds**: cmake didn't recompile when `git bisect` changed commits
2. **Port conflicts**: fixed port (9995) stayed busy from prior test's lingering server
3. **Python stdin parsing bug**: `json.load(sys.stdin)` inside `$()` had pipe exit-code issues
4. **Wrong response field**: checking `reasoning_content` only; model might use `content`

### v2 Design (What Worked)

```bash
#!/bin/bash
# Key design decisions:

# 1. FORCE rebuild: rm binary + cmake reconfigure each step
rm -f bin/llama-server
cmake .. -DGGML_HIPBLAS=ON ...   # reconfigure for THIS commit's cmake

# 2. Random port to avoid conflicts
PORT=$((19950 + RANDOM % 1000))
fuser -k $PORT/tcp 2>/dev/null

# 3. Kill ALL servers before starting
pkill -f "llama-server" 2>/dev/null
sleep 2

# 4. Server health check before testing
if ! kill -0 $SERVER_PID 2>/dev/null; then
    exit 125  # skip untestable commit
fi

# 5. Check BOTH response fields
text = msg.get('reasoning_content', '') or msg.get('content', '')

# 6. Robust Python with clear exit codes
if any(c.isalpha() for c in text):
    sys.exit(0)   # GOOD
else:
    sys.exit(1)   # BAD
```

### Exit Code Semantics
| Code | Meaning | When |
|------|---------|------|
| 0 | GOOD | GDN produces alphabetic text |
| 1 | BAD | GDN produces garbled output |
| 125 | SKIP | Build fails, server dies, can't test |

---

## 3. Build System Pitfalls

### The Stale Object Problem
`git bisect` changes source files, but cmake may not detect the change if:
- Object files are newer than restored source files (git sets mtime to checkout time)
- cmake dependency tracking uses content hashing, not timestamps
- Library archives (.a) aren't invalidated when constituent .o files change

**Fix:** Always delete these before rebuilding:
```bash
rm -f build/.../ggml-backend.cpp.o       # the specific .o
rm -f build/.../libggml-base.a            # the archive
rm -f build/bin/libggml-base.so           # the shared lib
```

Then reconfigure cmake to regenerate Makefiles:
```bash
cmake .. -DGGML_HIPBLAS=ON -DGGML_HIP_UMA=ON -DCMAKE_HIP_ARCHITECTURES=gfx1100
```

### Cross-Platform Compilation Trap
Our HIP build compiles `ggml-cuda.cu` (CUDA source via HIPIFY). The object file lives in:
```
build/ggml/src/ggml-hip/CMakeFiles/ggml-hip.dir/__/ggml-cuda/ggml-cuda.cu.o
```
Not where you'd expect. Always `find` the object before deleting.

---

## 4. Running the Bisect

```bash
cd project
git bisect start HEAD <GOOD_COMMIT>
git bisect run bash /path/to/test-script.sh
```

### What to Expect
- ~8-12 steps for 300-400 commits
- ~90-120s per step (build + server startup + test)
- Total: 12-24 minutes
- Build failures (exit 125) are fine — bisect skips them

### Real-Time Monitoring
The bisect prints each step's result. Watch for:
- All GOOD or all BAD → test script is broken
- BUILD FAILED on too many commits → anchors too far apart, narrow range
- First bad commit is implausible → test script bug (see v1 failure)

---

## 5. Root Cause Analysis

### Step 1: Read the Full Diff
```bash
git show <BAD_COMMIT> -p
```

Look for changes that are:
- **NOT gated by feature flags** (e.g., `if (ggml_backend_is_rpc(...))`)
- **Affecting your test configuration** (single-GPU HIP in our case)
- **Subtle synchronization changes** (async→sync, event_wait→event_synchronize)

### Step 2: Binary-Search Within the Commit
If the commit touches multiple files, test each file independently:

```bash
# Revert only file A, keep file B at BAD commit
git show <GOOD_COMMIT>:path/to/file_a.cpp > path/to/file_a.cpp
# Build and test
# If FIXED → the bug is in file_a
# If still BAD → bug is in file_b (or both)

# Then binary-search within the file:
# Revert only function X, keep function Y at BAD
```

### Step 3: Identify the Mechanism
Once you find the specific function change, trace the data flow:

```
Where does the data come from?
   ↓
What stream/thread does it travel on?
   ↓
Where is synchronization enforced?
   ↓
Where could a race occur?
```

### Our Root Cause
`ggml_cuda_issue_pinned_h2d_async()` uses a `thread_local` pinned staging buffer:

```
set_tensor_async() ──┐
                      ├─→ shared thread_local buffer ──→ GPU
cpy_tensor_async() ──┘
```

When both are called on the same thread during MoE model inference, the second call overwrites the staging buffer before the first H2D completes on the GPU. Result: corrupted expert weights → wrong expert selection → garbled output.

### Step 4: Confirm the Hypothesis
Don't guess. Verify by:
1. Reverting ONLY the suspected change
2. Keeping everything else at the BAD commit
3. Building and testing
4. If FIXED → confirmed. If not → keep searching.

---

## 6. Extracting the Minimal Fix

### Principle: Touch as Little as Possible
The goal is NOT to revert the entire commit. The goal is to fix the bug while preserving any perf optimizations or other changes that aren't broken.

### Our Minimal Fix
```
ggml/src/ggml-cuda/ggml-cuda.cu:
  -3 lines  (remove pinned staging + early return)
  +2 lines  (direct cudaMemcpyAsync on main stream)
```

`cpy_tensor_async()` keeps using pinned staging — these are never called concurrently for the same tensor.

### What We Preserved
- RPC prefetch at split start (ggml-backend.cpp)
- Gather drain at split entry (ggml-backend.cpp)
- MoE ids RPC download flush (ggml-backend.cpp)
- `cpy_tensor_async` pinned H2D optimization (ggml-cuda.cu)
- All B+15 throughput improvements

---

## 7. Verification Gate

Before calling it done:

| Check | How |
|-------|-----|
| **GDN output coherent** | Check `reasoning_content` has alphabetic text, not `?` |
| **No regression** | Test non-GDN model if available |
| **Builds clean** | Full rebuild from scratch |
| **Patch applies to HEAD** | Test at latest commit, not just the bisect commit |
| **Patch is minimal** | Review: are there any unnecessary changes? |

---

## 8. Lessons Learned

### The Bisect Methodology
1. **Automated test script is everything.** Spend 50% of time getting it right.
2. **Force rebuilds.** Don't trust cmake's dependency tracking across bisect steps.
3. **Random ports, kill all servers.** Clean state for every test.
4. **Binary-search within commits.** The bisect finds the commit; then bisect within the commit's diff.
5. **Verify anchors manually before automating.** Run GOOD and BAD commits by hand with your test script.

### The Analysis Methodology
1. **Filter by execution path.** On single-GPU, RPC-gated code can't be the cause. Eliminate it.
2. **Trace data flow.** Follow the bytes from source to destination — where do they cross synchronization boundaries?
3. **Shared mutable state is a red flag.** `thread_local` buffer shared between two functions? That's where bugs hide.
4. **One change at a time.** When testing within a commit, revert one function/file at a time to isolate.

### Tooling
- `llama-server` > `llama-cli` for output inspection (CLI artifacts are misleading)
- `python3 -c` with `sys.exit()` for test scripts (clear exit codes)
- `cmake --build` is NOT sufficient after git checkout — force reconfigure

---

## 9. Deliverables

| Item | Location |
|------|----------|
| **Patch** | `.scratch/patches/gdn-fix-thread-local-pinned-staging.patch` |
| **Report** | `.scratch/research/gdn-bisect-fix.md` |
| **Test script** | `/tmp/gdn-bisect-v2.sh` (reference) |
| **Commit** | `42e4e603b` on `fix/gdn-thread-local-pinned-staging` |
| **Tag** | `v8-gdn-fix` |
| **Branches ported** | `good-prototype`, `v0-row-split-fix` |

---

## Appendix: Quick Reference

```bash
# Start bisect
git bisect start HEAD <GOOD_COMMIT>

# Run automated
git bisect run bash test-script.sh

# Manual step (for debugging)
git bisect good   # or: git bisect bad

# When done
git bisect reset

# Show the breaking commit
git bisect log

# Binary-search within a commit
git show <GOOD>:path/to/file > path/to/file  # revert one file
# Build, test, repeat for each file/function

# Force clean rebuild after checkout
rm -f build/path/to/specific.o build/path/to/lib.a
cmake .. <FLAGS> && cmake --build . --target binary -j$(nproc)

# Save patch
git diff -- path/to/file > fix.patch
```
