# Wayfinder Family — Competence Comparison

**Date:** 2026-08-01
**Purpose:** Durable answer to "which wayfinder do I use, and why?" — so an agent
arriving at the toolbox can pick the right campaign harness without reading all
four skills. Written from the skills' own content, not reputation.

---

## The four claimants

| | **wayfinder-assembly-chain** | **beta-wayfinder** | **alpha-wayfinder** | **research-pipeline** |
|---|---|---|---|---|
| **Lineage** | The original | Predecessor tier | Successor tier (beta + 5) | Companion, not successor |
| **Core competence** | Closed-loop campaign **execution**: goal → vectors → parallel research → isolated worktrees → verify → parent re-eval | Campaign **economics**: when to stop, what to keep | Campaign **orchestration**: dispatch, checkpoints, nesting, scaffolding | Idea→**decision**: what to build at all, before any campaign |
| **Stopping rule** | Fixed max 10 loops | **Convergence**: 3 loops, 0 novel survivors | Same convergence + re-validation scheduler | Gate: all specs collected |
| **Verdict model** | Binary pass/fail | **3-tier** PASS/PARTIAL/FAIL + confidence bands (5→95%) | 3-tier + **spec-compliance sub-gate** (test suite → spec check → kill criteria) | GO / KILL / DEFER / CONDITIONAL-GO |
| **Uniqueness** | Red-team-before-verify, F8 merge discipline, watchdog | Portfolio kill (correlation-aware), resource budgeting, re-validation triggers | Toolbox dispatch (5 skills), checkpoint protocol, multi-campaign nesting, module-scaffold auto-parse | **Conflict adjudication**, baseline-anchored scoring, ADR + flip-test kill discipline |
| **Weakness** | No stopping economics; loops until capped | No toolbox routing; no checkpoints | **Heavy** — built for Harrier-scale (20 modules); overkill for ≤6-vector campaigns | Ends at DECIDE — no execution leg (hands off) |

---

## Where each one wins (measured, not asserted)

### wayfinder-assembly-chain — execution teeth
The only one with red-team-BEFORE-verify (a code review cannot catch spec-level
flaws), merge-order discipline (the F8 rule: correctness lands before throughput),
and a watchdog for looping/dead agents. **This is what the Increment-1 RPC
campaign actually runs on.** If you're implementing decided work with gates, this
is the harness.

### beta-wayfinder — the 80/20
Inherits the original + 8 enhancements, all aimed at **campaign economics**: when
to stop (convergence, not a cap), what to keep (portfolio-aware kill — a weak but
decorrelated vector outlives a strong correlated one), and how much a vector costs
(resource budgeting). The docs admit it: *"beta was sufficient for the uprunner
signal research campaign (6 vectors)."* For small/medium campaigns it's the
right-sized choice — alpha's toolbox routing would be ceremony.

### alpha-wayfinder — the apex of the campaign tier
alpha ⊇ beta (inherits all 8) + 5: toolbox dispatch (parallel-subprocess,
model-pipeline-queue, optimization-blueprint sub-campaigns, skill-architect
delegation), mandatory task-state checkpoints, multi-campaign nesting (max depth
2), module-scaffold auto-parse (`.harrier/modules/` → 20 vectors from SPEC.md),
and the spec-compliance gate (E13: test suite → spec compliance → kill criteria;
a MISSING/WRONG requirement blocks PASS). **Required for Harrier-scale builds**:
20 modules, parallel options processing, model call pipelining, multi-day
checkpoint-critical work.

### research-pipeline — the upstream decider
Neither beta nor alpha answers **"should we even run a campaign on this?"** — they
assume a goal and produce vectors. research-pipeline (generic) /
rpc-research-pipeline (RPC flavor) run the idea→evidence→decision funnel: baseline
(issuer specs anchor + threshold) → fireplace → parallel research wave → triage →
wayfinder → deep research → to-PRD → red-team → scaffold → decide. Its two
load-bearing rules:
1. **Conflict adjudication** — when two reports contradict on a load-bearing
   premise, dispatch a dedicated adjudicator before any kill. (The A7 NO-GO was
   overturned this way: the "starfish parallelizes compute" premise was false —
   scheduler + measured scaling prove it serial.)
2. **Kill discipline** — every kill gets an ADR with a re-open condition; a
   mechanism must survive the flip test, not just before/after.

---

## The honest verdict

- **Most competent overall:** `alpha-wayfinder` — for its domain (large, parallel,
  checkpoint-heavy builds). It is the apex of the campaign tier.
- **Most competent per unit of complexity:** `beta-wayfinder` — the 80/20.
- **The load-bearing ones for *current* work:** `wayfinder-assembly-chain`
  (execution) + `research-pipeline` (decisions) — the running Increment-1 RPC
  campaign is the assembly chain's; the A7 verdict was the research pipeline's.
- **Alpha's blind spot:** its spec-compliance gate checks *implementation against
  spec* — it would NOT catch a *spec built on a wrong model* (exactly the A7
  failure). Adopting adjudication-before-kill (research-pipeline) and
  red-team-before-verify (assembly-chain) would make alpha the single canonical
  harness. Right now the younger, smaller skill holds a lesson the apex lacks.

---

## When to use which (decision table)

| Scenario | Use |
|----------|-----|
| "Should we build X? Which fix is best? Is idea Y viable?" | `research-pipeline` / `rpc-research-pipeline` |
| Decided work with verification gates, ≤10 vectors | `wayfinder-assembly-chain` |
| Small/medium campaign, want convergence + kill economics | `beta-wayfinder` |
| Large campaign: DAG, parallel data-fetch, model pipelining, compaction-prone | `alpha-wayfinder` |
| Multi-module system from scaffolding (`.harrier/`, SPEC.md) | `alpha-wayfinder` (module auto-parse) |
| Performance-critical sub-component needs a dedicated pass | `alpha-wayfinder` → `optimization-blueprint` |
| Missing capability appears in 2+ places | `skill-architect` (from alpha's toolbox dispatch) |
| A kill is proposed on a load-bearing premise | `research-pipeline` adjudication, regardless of harness |
