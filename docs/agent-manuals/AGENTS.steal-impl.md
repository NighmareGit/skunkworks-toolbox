# AGENTS.steal-impl.md — Operating Manual for Steal/Port Agents (universal)

You are the implementation agent for a STEAL ticket: port a proven performance/correctness
idea from an upstream repo into this project's fork. The parent orchestrates; you execute one
ticket end-to-end. Your verdict decides whether the idea is PORTED, BANKED, or KILLED — with evidence.

## Sequence (in order)

1. **Read-first** — the feedstock (steal-list row, seam report, prior doability study, state file). The seam report is the arg-packer's output: trust its PORT-AS-IS / ADAPT / KILL read, but FALSIFY it against the real code.
2. **State-first** — heartbeat the state file (real ISO timestamp, your id); NEVER replace it.
3. **Worktree** — worktree-guard: create `worktrees/<ticket>/` off the base, branch `steal/<id>`. Never touch the main checkout.
4. **Fetch** — fetch the upstream diff (git fetch / curl the .patch). Read it fully; truncate only the noisy middle.
5. **Falsify-first** — does the change apply to this fork? Check THREE things before any edit:
   - **Functional redundancy** — does the fork already achieve this (a different path to the same effect)? If yes → KILL (redundant) with the evidence.
   - **File existence** — do the patch's target files/dirs exist in the fork? If a target is absent, estimate the divergence — KILL or ADAPT with evidence.
   - **Structural fit** — do the function names, variable names, and surrounding logic match the patch target?
6. **Apply EXACTLY** — the delta (the seam report's precise change). Blast radius = the seam only. No re-architecting, no porting hardware-bound parts, no scope creep.
7. **Build** — build lock, build the correct target(s) from the seam's file path (the seam→target map below: build EVERY backend that compiles the seam; a seam under ggml/src/ggml-cuda/* is compiled under BOTH the CUDA build dir and the ROCm/HIP build dir — the "CUDA-only" excuse is BANNED), release the lock.
   ```
   seam path pattern             → backend build dir(s) to build
   ggml/src/ggml-cuda/*.cu (*)   → build-cuda  AND  build-rocm-native (ggml-hip)
   ggml/src/ggml-hip/*           → build-rocm-native only
   ggml/src/ggml-cpu/*           → build-cpu / the CPU base lib
   ggml/src/ggml-base/*          → every backend (verify against the seam's primary)
   src/*.cpp, src/llama.cpp     → the frontend lib of the seam's backend
   (*) ggml-cuda.cu is HIP-compiled too: ggml-hip/CMakeLists.txt:64 GLOBs
   ../ggml-cuda/*.cu into ggml-hip's sources (proven empirically — the F2 snake-fusion
   fix compiled under build-rocm-native, .o under ggml-hip.dir). This is the load-bearing
   case: never skip the HIP build for a ggml-cuda/*.cu seam.
   ```
   **Self-check**: the chosen target must actually compile the seam file — the seam's .o must appear in the build dir (grep compile_commands.json / the CMake target sources for the seam filename); a target that does not compile the seam is the WRONG target. **Artifact-verify**: nm/strings/disassembly prove the new code is in the built artifact (never trust "Built target"); object mtime > source mtime. **Provenance**: evidence must trace to THIS worktree's build of HEAD — artifact path inside the worktree-local build dir; borrowed evidence (another worktree's build, a sibling arm's artifact) is a FAILURE. **Cleanliness**: worktree AND main tree git status clean before close — any dirty tracked file is yours to revert or explain in the report.
   **Revert trigger**: B1 is KILLED (and the build-marker wrapper un-deferred) if the next steal ticket's build-stage report shows borrowed artifacts, an artifact path outside the worktree-local build dir, or the self-check grep skipped.
8. **Verdict + close** — IMPL / BANK / KILL with the evidence table. Report FIRST (the project's report path), then ledger entry (the project's numbering convention), then state → complete, then commit + push. Steal-list row update. Lessons field.

## Discipline

- A KILL with falsifying numbers is a legitimate, valuable close. Banked (nothing portable) is too.
- The GPU/measurement A/B is a SEPARATE verify phase — do NOT run it in the steal ticket.
- If the fork's structure diverges mid-application → STOP, document the divergence, HOLD. Do not force a merge.
- Two blocks → state-file blocker + failure report. Do not loop.

## Skills to load

orchestration-dispatch · worktree-guard · gpu-lease (only if a lease is involved) · perf-verification (gate contract) · this class file.
