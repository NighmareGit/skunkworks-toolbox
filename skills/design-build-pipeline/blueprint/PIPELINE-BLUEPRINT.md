# PIPELINE BLUEPRINT — the generic scaffold for a pipeline skill

> Copy this template + fill the placeholders to create a NEW pipeline skill (a different
> component, the same skeleton). The concrete instantiation is
> `design-build-pipeline` (see its SKILL.md) — this is the blank form it was born from.
> **Borrowed structure:** stages with exit gates · seats per stage · cross-cutting rails ·
> a pre-registered convergence criterion. Those four are the invariant skeleton.

---

## 1. Frontmatter

```yaml
---
name: <pipeline-name>            # lowercase-hyphen; e.g. merge-engine-pipeline
description: >
  <2-3 sentences: what the pipeline produces, its first→last stages, the disciplines it
  enforces>. Trigger phrases: <the phrases that should auto-invoke it>, "/<pipeline-name>".
metadata:
  short-description: "<one line>"
---
```

## 2. When to Use

- <the trigger conditions: what gap/component this pipeline exists to deliver>
- <the reproducibility requirement: why a pipeline, not an ad-hoc run>

## 3. The Stages (fill the chain)

```
 MEASURED STATE (<the baseline anchors this pipeline starts from>)
   │
   ▼
[1] <STAGE>  — <what it produces> · gate: <the exit criterion>
[2] <STAGE>  — <what it produces> · gate: <the exit criterion>
[3] …        — (minimum: a design phase, an attack phase, a build phase, a verify phase)
[N] <FINAL>  — <integration + consumption: who consumes the output, how the loop closes>
```

For each stage, name:
- **The gate** (the falsifiable exit criterion — never "feels done")
- **The seat** (which model/role runs it — from the campaign dispatch map)
- **The artifact** (the file/report it produces)

## 4. The Cross-Cutting Rails (adapt, don't drop)

| Rail | Rule |
|------|------|
| **Gates** | every stage exits on its criterion; nothing fires the next stage on vibes |
| **Seats** | plan→frontier judgment · research→general worker/frontier judgment · red-team→frontier judgment · code→general worker · review→independent reviewer · validate→perf-verification |
| **Ticket gate** | every dispatch passes ticket validation (pro-economy justification on costly seats) |
| **Locks** | build lock · source lock · worktree isolation for prototypes |
| **Discipline** | no-narrative-drift (a spec is a prediction, a procedure needs runs); ADR per kill/adopt |
| **Scope governor** | flag when critical-path tickets are unverified |

## 5. The Convergence Criterion (mandatory)

"Loop until done" is only honest with a done-definition:
- The pre-registered KPI from stage [1] — the falsifiable claim the pipeline exists to meet.
- The max-iteration / kill-loud rule (e.g., wayfinder's N loops, each adding a novel vector).

## 6. What NOT to change when scaffolding

The four invariants: (1) stages have exit gates, (2) every stage has a seat, (3) the rails
hold, (4) the convergence criterion is pre-registered. Change the CONTENT of the stages, not
the skeleton — a pipeline without gates or a done-definition is a narrative, not a procedure.
