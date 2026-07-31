---
name: wayfinder-assembly-chain
description: Goal-driven multi-agent assembly chain with Wayfinder attack-vector planning, parallel research, isolated worktrees, TDD/prototype loops, verification gates, and parent re-evaluation. Use when running systematic multi-agent campaigns that must scale, measure, kill failed vectors, and converge on a hard performance or correctness goal.
---

# Wayfinder Assembly Chain

Orchestrate multi-agent work as a closed feedback loop: Goal → Wayfinder (attack vectors) → parallel research → tickets → isolated implementation → verification → parent re-evaluation. Failed vectors become documented knowledge. Success is measured, never claimed.

## Core Loop (immutable order)

1. **Goal** — single immutable primary objective with explicit success metrics.
2. **Wayfinder** — produces coarse slices / attack vectors. Max N loops (default 10). Each loop must introduce at least one novel vector.
3. **Parallel Research Wave** — one focused research agent per coarse slice (`research`).
4. **Grill-with-docs** — per-slice deep dive informed by research.
5. **to-spec → to-tickets** — turn validated vectors into a spec (when needed) then into concrete, independently measurable tickets with blocking edges. Tiny vectors may go straight to tickets.
6. **Isolated execution** — one git branch + one worktree per ticket.
7. **TDD → Prototype** — implement the ticket (correctness first, then performance). Prefer `implement` when the ticket is fully specified.
8. **Red-team BEFORE verify/review (critical enhancement)** — adversarial review of the implemented ticket AND its spec. A code review runs *against* the spec and cannot catch spec-level flaws (protocol gaps, measurability holes, merge-order errors — cf. the Increment-1 F1–F8 findings). If the red-team finds issues: **adapt the spec → re-ticket → re-run steps 7–8** (do NOT hot-fix the code while the ticket is wrong). Bound: max 3 red-team → spec-adapt → re-execute iterations, then escalate to the parent.
9. **Debug loop** on red/verification failure (do not advance). Use `diagnosing-bugs` for hard cases.
10. **Verify** — run the project's verification gate on the red-team-passed implementation (perf-verification: clean output diffing, throughput, baseline comparison). Never advance on grep-only gates.
11. **Code-review** on green → re-verify.
12. **Failure handling** — if the approach cannot deliver the ticket goal, document the failure mode in `.scratch/adrs/`, commit on the feature branch, notify parent.
13. **Parent evaluation** — incorporate results, kill dead vectors, promote survivors, regenerate Wayfinder plan.

## Resumability (interruption-safe execution)

- **The scaffold is the system's memory; agents are expendable.** Durable state (specs, tickets, ACs, ledger, task-state) must let ANY agent resume ANY ticket from an interruption.
- **Per-agent task-state files** (use the `task-state` skill): before/after each stage, write `<ticket-id>.<stage>.state.json` — stage, status (pending/in_progress/done/failed), artifacts, next-action. If an agent dies, a replacement reads the state file and continues from the exact stage.
- **Verify-already-done on restart (do not trust state alone):** before resuming or redoing a stage, verify the ground truth — does the ticket's worktree/branch exist? does the merge sit at the expected commit? did the AC gate actually pass (re-run the check)? Then mark done or continue. Never redo verified work; never skip unverified work.
- **One state file per ticket** at `.scratch/task-state/<campaign>/<ticket-id>.json`; the parent aggregates them into the living CONTEXT.md.

## Wayfinder Rules

- Attack vectors must be independently measurable vertical slices where possible.
- Every vector has explicit kill criteria.
- Parent kills, promotes, or defers. Never leave vectors in limbo.
- Living context lives in `.scratch/CONTEXT.md` and the current Wayfinder plan file.
- Research findings go under `.scratch/research/`. Benchmarks under `.scratch/benchmarks/`.

## Resource Discipline (non-negotiable)

All exclusive-resource access is governed by the **resource-locks** skill.

- GPU + VRAM, build directories, and source modifications are exclusive.
- Agents must acquire the appropriate lock/lease before use and release afterwards.
- Research (read-only) may run fully parallel.
- Worktree isolation can remove the need for the source lock, but never removes the need for the GPU lease.
- Parent must sequence tickets so exclusive-resource claims do not overlap.

See `resource-locks` for the full protocol, lock table, and failure behaviour.

## Verification Gate

A ticket is done only when the verification step reports:
- Clean functional result (no correctness regressions)
- Required performance / scaling metrics recorded
- Comparison against the stated baseline
- Scaling behaviour documented or explicitly marked "not yet measurable"

Never merge or declare success without passing the gate.

## Scratch & Documentation Policy

- Durable state → project `.scratch/`
- Ephemeral per-agent notes → `/tmp/agent-<id>-<timestamp>.scratch.md`
- Failed attack vectors are valuable — write ADRs in `.scratch/adrs/`
- Use conventional commits on feature branches
- Prefer vertical slices that can be measured independently

## Parent / Orchestrator Constraints

The parent must **not** perform research, implementation, benchmarking, or debugging itself. All concrete work is delegated to sub-agents. The parent only:
- Maintains the Goal and Wayfinder plan
- Dispatches and sequences work under the constraints of `resource-locks`
- Evaluates results and decides kill / promote / re-loop
- Updates living context and documentation

## When to Stop or Pivot

- Max Wayfinder loops reached with no positive progress on the primary metric → document asymptote and stop.
- A vector is proven structurally impossible → ADR + kill.
- New evidence shows the original Goal formulation is wrong → parent may rewrite the Goal (rare, explicit decision).

## Minimal Scaffold to Start a Campaign

```
.scratch/
  CONTEXT.md          # living status
  plans/              # wayfinder plans
  research/           # research reports
  benchmarks/         # measurement artifacts
  adrs/               # failed / decided vectors
  locks/              # lock.sh + lock dirs (see resource-locks)
  BUGS.md             # known issues ledger
```
