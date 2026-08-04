---
name: design-build-pipeline
description: >
  Run the full design→build→integrate pipeline for a machine component or feature: measure →
  wayfinder → fireplace → research → triage → spec → red-team → to-PRD (seams checkpoint) →
  plan → tdd → prototype → code-review → validate → loop until done → integrate. Each stage
  carries its gate, its seat, and the campaign's disciplines (falsification probes, echo-rejected
  validation, the deliverable gate, ADRs, no-narrative-drift). Trigger phrases: "run the
  pipeline", "design and build", "full chain", "/design-build-pipeline", "wayfinder through
  integrate".
metadata:
  short-description: "The full design→build→integrate chain with per-stage gates and seats"
---

# Design-Build Pipeline

The end-to-end chain for turning a measured gap or a new component into an integrated, tested,
reviewed deliverable. **Run it by this file, not from memory** — each stage has an exit gate;
nothing fires the next stage until the previous one passes.

## When to Use

- A new machine component needs the full treatment (design → spec → PRD → build → verify → integrate)
- A measured gap needs a systematic fix with a defensible verdict
- You need the chain reproducible and reviewable, with a decision record at every kill/adopt

## The Pipeline

```
 MEASURED STATE (baseline anchors: prior verdicts, sealed corpora, the archive)
   │
   ▼
[1] BASELINE  — anchor to the measured state; name the gaps and the falsifiable claim
[2] WAYFINDER — vectors with kill criteria + expected delta (the alpha/beta-wayfinder skill)
[3] FIREPLACE — diverge: 6+ frames before converging (the fireplace skill)
[4] RESEARCH  — evidence wave, parallel seats (the research-pipeline skill; academic/primary sources)
[5] TRIAGE    — kill / keep / defer each vector with an ADR for the kills
[6] to-SPEC   — the technical design; EVERY decision carries its falsification probe
[7] RED-TEAM  — attack the spec BEFORE the build (the red-team skill); blockers fold back into [6]
[8] to-PRD    — the /to-prd skill: PRD (problem/solution/user stories/impl+testing decisions)
                 + the ONE highest seam + USER SEAMS-CHECKPOINT + publish ready-for-agent
[9] PLAN      — the build plan (plan seat)
[10] TDD      — red-green-refactor (longcat; the tdd skill)
[11] PROTOTYPE— worktree-isolated (worktree-guard; longcat)
[12] CODE-REVIEW — standards + spec axes (reviewer seat / ds-v4-flash)
[13] VALIDATE — perf-verification contract + echo-rejected scoring + the deliverable gate
[14] LOOP     — until the convergence criterion (the KPI / done-definition) is met
[15] INTEGRATE— merge to main + ADR + the CONSUMPTION contract (who consumes it, loop closure)
```

## The Cross-Cutting Rails (every stage)

| Rail | Rule |
|------|------|
| **Gates** | each stage exits on its gate: falsification probes at [6], blockers at [7], seams-checkpoint at [8], perf-verification + deliverable-gate at [13] |
| **Seats** | plan→ds-v4-flash · research→longcat/ds-v4-flash · red-team→ds-v4-flash · tdd/code→longcat · review→reviewer (ds-v4-flash) · validate→perf-verification |
| **MPR gate** | every dispatch passes the MPR validation (pro-economy justification on costly seats) |
| **Locks** | build lock before builds; source lock for shared-file edits; worktree isolation for prototypes |
| **Discipline** | #187 no-narrative-drift (a spec is a prediction, a procedure needs runs); falsification over vibes; ADR for every kill/adopt |
| **Scope governor** | flag when North Star tickets are unverified (>2 → WARN before new South Star builds) |

## The Convergence Criterion

"Loop until done" needs a done-definition: the [14] loop exits only when [13] passes AND the
pre-registered KPI (the [1] falsifiable claim) is met. If the loop exceeds the wayfinder's max
iterations without convergence, the pipeline kills loudly with the falsifying number + ADR.

## Blueprint

The generic scaffold lives in `blueprint/PIPELINE-BLUEPRINT.md` — copy it + fill the
placeholders to spin up a future pipeline skill (different component, same skeleton).
