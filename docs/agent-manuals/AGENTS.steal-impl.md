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
7. **Build** — build lock, build the correct target (the seam's backend — check the file's dir), release the lock. **Artifact-verify**: nm/strings/disassembly prove the new code is in the built artifact (never trust "Built target"); object mtime > source mtime.
8. **Verdict + close** — IMPL / BANK / KILL with the evidence table. Report FIRST (the project's report path), then ledger entry (the project's numbering convention), then state → complete, then commit + push. Steal-list row update. Lessons field.

## Discipline

- A KILL with falsifying numbers is a legitimate, valuable close. Banked (nothing portable) is too.
- The GPU/measurement A/B is a SEPARATE verify phase — do NOT run it in the steal ticket.
- If the fork's structure diverges mid-application → STOP, document the divergence, HOLD. Do not force a merge.
- Two blocks → state-file blocker + failure report. Do not loop.

## Skills to load

orchestration-dispatch · worktree-guard · gpu-lease (only if a lease is involved) · perf-verification (gate contract) · this class file.
