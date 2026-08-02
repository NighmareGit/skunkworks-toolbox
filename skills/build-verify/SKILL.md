---
name: build-verify
description: >
  Loadable build-stage procedure for steal-impl / bug-fix tickets. Use when
  the agent must compile a ported change and prove the artifact is real,
  fresh, and traceable to THIS worktree's build of THIS commit. Covers:
  seam→target routing (ggml-cuda/*.cu compiles under BOTH CUDA and HIP),
  self-check cascade (grep compile_commands.json / build.make for the seam),
  provenance contract (artifact inside worktree-local build dir, object mtime
  > source, nm symbol proof, second-build no-op), dual-tree cleanliness
  (worktree AND main tree git status clean), and the revert trigger. Invoked
  by AGENTS.steal-impl.md §7 and the frontier-impl.rhai s5 stage. Slash:
  /build-verify. Trigger phrases: "build-verify", "compile-verify",
  "artifact provenance", "build discipline", "seam→target", "self-check build".
---

# Build-Verify Procedure

The build stage is not "run cmake and report success." It is a **provenance
protocol**: the artifact must be proven to be THIS worktree's build of THIS
commit, fresh against the seam, and clean on both trees. Every claim below is
verifiable on disk — never trust "Built target."

## 1. Seam→Target Map (which build dir(s) to build)

The seam's file path decides the backend build dir(s). Build **every** backend
that compiles the seam file. The "CUDA-only" excuse is **banned** — it is
factually wrong for any file under `ggml-cuda/`.

| Seam file pattern | Required build dir(s) | Why |
|-------------------|-----------------------|-----|
| `ggml/src/ggml-cuda/*.cu` | `build-cuda` AND `build-rocm-native` (ggml-hip target) | The same `.cu` files are compiled by both `ggml-cuda` (CUDA) and `ggml-hip` (HIP) targets. `ggml-hip/CMakeLists.txt:63` GLOBs `../ggml-cuda/*.cu` into `ggml-hip`'s sources. **This is the load-bearing case.** |
| `ggml/src/ggml-hip/*` | `build-rocm-native` only | HIP shim |
| `ggml/src/ggml-rpc/*.cpp` | Any `GGML_RPC=ON` build | Pure C++, backend-agnostic |
| `ggml/src/ggml-cpu/*` | Any build (CPU default ON) | Always compiled |
| `ggml/src/ggml-base/*`, `ggml.c`, `gguf.cpp` | Any build | Core, always compiled |
| `src/models/*.cpp`, `src/llama.cpp`, `src/llama-*.cpp` | Any build | Always compiled as part of `llama` lib |

**Corollary:** A seam in `ggml-cuda.cu` MUST be built in BOTH a CUDA build AND a
HIP build. Skipping either leaves a backend unverified.

## 2. Self-Check Cascade (before building)

Verify the chosen target actually compiles the seam file. A target that does
not compile the seam is the **wrong target** — no excuse accepted.

```
1. Determine seam's backend category from §1.
2. Confirm the candidate build has the backend enabled:
     grep -E "GGML_(CUDA|HIP|RPC):BOOL=ON|UNINITIALIZED=ON" <build>/CMakeCache.txt
3. Confirm the seam file is in the build's compiled set (cascade):
     a. grep -q "<seam-file>" <build>/compile_commands.json    # CMake ground truth
     b. grep -q "<seam-file>" <build>/ggml/src/ggml-<backend>/CMakeFiles/ggml-<backend>.dir/build.make
     c. test -f <build>/ggml/src/ggml-<backend>/CMakeFiles/ggml-<backend>.dir/<dir>/<seam-file>.o
4. If any check fails → WRONG TARGET. Pick a different build dir.
```

**The "CUDA-only" killer:** For `ggml-cuda.cu`, step 3a on `build-rocm-native`
returns a match (the file IS compiled under ROCm as `ggml-hip`). The excuse is
falsified by the build system's own dependency data.

## 3. Build + Artifact Verification

Acquire the build lock (`atomic-llama-cpp-turboquant/.scratch/locks/lock.sh`),
build, release. Then prove:

| Check | Command | Proves |
|-------|---------|--------|
| Object mtime > source mtime | `stat -c '%y' <obj.o>` > `stat -c '%y' <src.cu>` | Artifact reflects current source |
| New symbol in object | `nm -C <obj.o> \| grep <new-symbol>` | The new code was compiled |
| New symbol in shared lib | `nm -C <lib.so> \| grep <new-symbol>` | The new code linked into the artifact |
| Second-build no-op | Re-run `cmake --build` → "Built target X" with nothing to do | The first build did real work (not a silent skip) |

**Stale-build guard:** Before building, force a clean reconfigure
(`cmake -E rm -rf CMakeCache.txt CMakeFiles/` in the build dir) to eliminate
the stale-cache hazard (cache says backend OFF but artifacts were built with ON).

## 4. Provenance Contract (P1–P6)

The artifact proof is valid **iff** ALL six properties are evidenced:

| # | Property | Evidence |
|---|----------|----------|
| P1 | Commit binding | Artifact built from the worktree's HEAD commit (the build ran in the worktree at the reported commit) |
| P2 | Worktree binding | `realpath(<artifact>)` starts with `realpath(<worktree>)` — artifact is INSIDE the worktree-local build dir |
| P3 | Build recency | Object mtime > source mtime |
| P4 | Symbol presence | nm/strings/disassembly shows the new code in the artifact |
| P5 | Build run proof | Second-build no-op confirms the first build performed the actual recompile |
| P6 | Pre-build cleanliness | `git status --porcelain` was clean BEFORE the build (the build matches the committed state) |

**Borrowed evidence = FAILURE.** If the artifact path is outside the worktree,
points to another arm's build, or the commit binding fails → the build is
unverified → STOP, do not claim "build-clean."

## 5. Dual-Tree Cleanliness

Before close, BOTH trees must be clean:

```
( cd <worktree> && git status --porcelain --untracked-files=no )
( cd <main-tree> && git status --porcelain --untracked-files=no )
```

- Worktree clean: expected (build artifacts are gitignored).
- Main tree clean: **mandatory.** Any dirty tracked file is yours to revert
  (`git checkout -- <file>`) or explain in the report. A dirty main tree =
  PASS-WITH-FIXES at best, not CLEAN-PASS.

## 6. Revert Trigger

The build-marker wrapper (`tools/scripts/steal-build-marker.sh`, Axis B's
deferred structural backstop) is **un-deferred** (implemented) if the next
steal ticket's build-stage report shows ANY of:

- Borrowed artifacts (artifact path outside the worktree-local build dir).
- An artifact path pointing to a sibling arm's build dir.
- The self-check grep (§2 step 3) was skipped or its output omitted.
- The main tree is left dirty without a revert.

When the trigger fires, implement the wrapper from
`build-disc-axis-b-provenance.md §4a` and re-run the build stage through it.

## 7. Report Template

The build-stage report MUST include:

```
## Build Verification

Seam: <file:line>
Target(s): <build-dir(s)> + <target-name(s)>
Self-check: grep <seam-file> <build>/compile_commands.json → MATCH / MISSING
Artifact: <worktree>/<build-dir>/<path>.o (realpath inside worktree: YES/NO)
Provenance:
  P1 commit binding: HEAD = <sha>
  P2 worktree binding: artifact realpath starts with worktree realpath
  P3 object mtime <timestamp> > source mtime <timestamp>
  P4 symbol <name> in .o: YES/NO; in .so: YES/NO
  P5 second-build no-op: YES (first build did real work)
  P6 pre-build cleanliness: git status clean at build time
Cleanliness:
  worktree git status: CLEAN / DIRTY (<files>)
  main tree git status: CLEAN / DIRTY (<files>, reverted: YES/NO)
```
