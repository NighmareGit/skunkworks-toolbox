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
7. **TDD → Prototype → Verification** — correctness first, then performance. Use the project's verification gate. Prefer `implement` when the ticket is fully specified.
8. **Debug loop** on failure (do not advance). Use `diagnosing-bugs` for hard cases.
9. **Code-review** on green → re-verify.
10. **Failure handling** — if the approach cannot deliver the ticket goal, document the failure mode in `.scratch/adrs/`, commit on the feature branch, notify parent.
11. **Parent evaluation** — incorporate results, kill dead vectors, promote survivors, regenerate Wayfinder plan.

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
