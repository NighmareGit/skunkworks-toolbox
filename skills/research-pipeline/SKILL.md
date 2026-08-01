---
name: research-pipeline
description: >
  Run the project's idea→evidence→decision pipeline for architecture, performance,
  or design questions: BASELINE → FIREPLACE → RESEARCH WAVE → TRIAGE → WAYFINDER →
  DEEP RESEARCH → to-PRD → RED-TEAM → SCAFFOLDING → DECIDE, with a research LEDGER
  as the durable backbone. Use when a question needs divergent exploration, evidence
  from primary sources, vector triage, and a defensible verdict (e.g. "which fix is
  best", "should we build X", "is idea Y viable"). The issuer must spec the comparison
  baseline up front. Trigger phrases: "run the research pipeline", "fireplace loop",
  "research wave", "triage the findings", "what's the verdict on X". Slash command:
  /research-pipeline.
---

# Research Pipeline — Idea → Evidence → Decision

Turn a fuzzy idea into a defensible verdict, with every stage tracked in a research
LEDGER so the pipeline is resumable and nothing falls through. Success = a decision
(GO / KILL / DEFER / CONDITIONAL-GO) backed by source-cited evidence and recorded
in the ledger + ADR — never a claim without measurement.

This skill is **general-purpose**: it applies to any question with a measurable
comparison. Where a stage needs specifics (what to measure, which criteria score a
verdict), the **issuer supplies them** — the pipeline never hard-codes a domain.
A worked example (the RPC multi-GPU fork) appears at the end to show the shape,
not to prescribe it.

## The Loop (immutable order)

```
⓪ BASELINE ─▶ ① FIREPLACE ─▶ ② RESEARCH WAVE ─▶ ③ TRIAGE ─▶ ④ WAYFINDER ─▶ ⑤ DEEP RESEARCH
   (issuer-      (divergent)    (parallel)        (vectors)   (refine)      (chosen vector)
    speced)

⑥ to-PRD ─▶ ⑦ RED-TEAM ─▶ ⑧ TECHNICAL SCAFFOLDING ─▶ ⑨ COLLECT SPECS → DECIDE
   (spec)       (attack)     (implementation spec)      (gate when all in)
```

## Stage 0 — Baseline (always first; issuer-specified)

**The issuer MUST spec two things in the kickoff prompt:**
- **The comparison anchor** — the "before" / control / current-best that every claim is scored against (e.g. "current per-token RPC cost on the 2-GPU layer-split path")
- **The acceptance threshold** — what counts as a win (e.g. "≥ 20% lower blocking RPC per token, no correctness regression")

*For a better outcome, also give the pipeline what to measure and how* (the metric and the measurement method — e.g. "µs per token via the S0 harness, both GPUs, TCP and UDP"). The more the issuer specifies, the sharper the whole pipeline gets — but anchor + threshold are the only required pieces.

The baseline stage then produces `.scratch/benchmarks/<topic>-baseline.md` capturing
what was measured. **Every later claim in the pipeline is scored against the anchor,
in the baseline's own units — not against prose.** If the issuer gave no anchor, the
pipeline's first action is to ask for one; never start theorizing without it (the
"+56% mirage" lesson: a claim measured against nothing is worthless).

## Stage-by-stage contract

| # | Stage | Agent | Read-only? | Deliverable | Gate to advance |
|---|-------|-------|-----------|-------------|-----------------|
| ⓪ | Baseline | measurement agent (lease if needed) | ❌ (may need resources) | `.scratch/benchmarks/<topic>-baseline.md` — anchor + threshold recorded | anchor + threshold recorded; claims anchorable |
| ① | Fireplace | 1 (divergent) | ✅ | `.scratch/research/fireplace-<topic>.md` — ≥8 perspectives, cluster/contrast, 2–5 survivors | ≥8 perspectives rotated; survivors explicit |
| ② | Research wave | 3–5 parallel | ✅ | `.scratch/research/<topic>-<axis>.md` per agent, primary sources, cited | each report cites primary source; no claim without ref |
| ③ | Triage | parent | ✅ | findings sorted into named vectors (A1..An) in LEDGER entry | every finding lands in exactly one vector or is dropped with reason |
| ④ | Wayfinder | plan agent | ✅ | `.scratch/plans/<topic>-vectors.md` — per-vector: mechanism, evidence, expected effect vs baseline, N-behavior, change size, risk, **kill criteria**, verdict (KILL/CARRY/SHORTLIST/DESTINATION/DEFER) | every vector has kill criteria; no limbo |
| ⑤ | Deep research | 1–2 per chosen vector | ✅ | deep-dive report on the surviving vector — "deserves its own" | chosen vector fully specified; open questions closed or deferred explicitly |
| ⑥ | to-PRD | to-prd skill | ✅ | `.scratch/specs/PRD-<topic>.md` (or tracker issue) | PRD has measurable acceptance criteria anchored to the Stage-0 baseline |
| ⑦ | Red-team | 1–2 adversarial | ✅ | `.scratch/specs/PRD-<topic>-redteam.md` — attack assumptions, kill-criteria traps, merge-order, measurability holes | verdict: SHIP / SHIP-WITH-FIXES / REJECT; fixes folded back |
| ⑧ | Scaffolding | parent/plan | ✅ | `.scratch/specs/scaffold-<topic>.md` — slices/tickets with blocking edges, effort, file-collision map, per-slice verify recipe | every ticket has AC + verify recipe; merge order explicit |
| ⑨ | Decide | parent + user | — | ADR + verdict doc in `.scratch/specs/` + LEDGER final entry | all specs collected; user decision recorded |

**Issuer may override any stage's deliverable path or agent count** — the contract is
a default, not a straitjacket. What is NOT negotiable: the order, the ledger, the
baseline anchor, and kill criteria.

## The Ledger (the backbone — never optional)

`.scratch/research/LEDGER.md` is the pipeline's memory. It MUST contain:
- Header: purpose, pipeline stage-status table (each stage: status + artifact path)
- Numbered entries (1..n), one per major finding/decision, each with: what, evidence/source, verdict, report path, date
- A **Paused topics** section for deferred/blocked items with a re-evaluation trigger
- The **scoring rubric** (locked at Stage 0 — derived from the issuer's baseline +
  any issuer-supplied decision criteria, e.g. N-stability, rollback cost, change size)

Every stage appends to the ledger BEFORE moving on. If the pipeline is interrupted,
the ledger + stage-status table are the resume point (verify ground truth on disk,
don't trust state alone).

## Conflict adjudication (baked in from the A7 wave)

When two research reports contradict on a **load-bearing premise** (e.g. one report's
verdict rests on "X parallelizes" while the primary source and measured data say
"X serializes"), do NOT pick a winner by intuition:
1. Isolate the exact premise the verdict hinges on.
2. Dispatch a dedicated **adjudication agent** (read-only) to test it against
   primary sources + the Stage-0 baseline, and re-derive the conclusion.
3. Kill decisions never rest on an unverified premise. The adjudicator's report
   becomes part of the ledger.

This is the pipeline's built-in premise-check — the difference between killing a
DESTINATION-tier idea on a wrong model vs. on evidence.

## Kill discipline

- Every KILL gets an ADR (`.scratch/adrs/ADR-NNN-<topic>-killed.md`) documenting:
  what was tried, the falsify/evidence that killed it, and the **re-open condition**.
- Before/after isn't proof — a mechanism must survive the **flip test** (a candidate
  that passed before/after can still die on an ON/OFF falsify).
- Kill criteria are honored at the gate, not after (wayfinder briefs state them;
  the ⑨ gate checks them).

## Verification & handoff

The pipeline ends at DECIDE. Implementation uses the project's implementation
pipeline (here: wayfinder-assembly-chain). The handoff must include: ACs anchored
to the baseline, the merge order, and the red-team's SHIP-WITH-FIXES list — so
implementation starts from the pipeline's findings, not from scratch.

## Resource discipline

- Stages ①–⑧ are **read-only** → fully parallel-safe, no locks.
- Stage ⓪ (baseline) and any verification may need exclusive resources (GPU, build,
  devices) → acquire the project's lease/locks, run sequentially.
- Research artifacts go where the project keeps such notes (here: the ROOT repo's
  tracked `.scratch/`, not the fork's gitignored `.scratch`).

## Resumability

If interrupted at any stage: read the LEDGER stage-status table → verify the
artifact exists on disk → resume the earliest incomplete stage → continue the
gates in order. Agents are expendable; the ledger + specs are the memory.

---

## Worked example (for shape only — RPC multi-GPU fork)

- **⓪ Baseline**: issuer speced "per-token RPC cost in µs, both GPUs, layer-split, TCP+UDP, failure signature, N-node extrapolation" → `rpc-baseline-cost.md`. (This is the specialized sibling skill's home turf — see `rpc-research-pipeline` for the full recipe.)
- **①–②**: fireplace + 5 research agents (upstream, transport, concurrency, N-backend, speculative).
- **③–④**: triage → vectors A1–A4 etc.; wayfinder with per-vector kill criteria → `rpc-architecture-vectors.md`.
- **⑤**: deep research on the speculative engine (A4/R5).
- **⑥–⑧**: PRD → red-team (SHIP-WITH-FIXES F1–F8) → scaffold (slices S0–S3, merge order F8).
- **⑨**: ADR-004 + verdict; campaign launch.
- **Adjudication in action**: A7 research produced a NO-GO resting on "the starfish
  parallelizes compute"; the scheduler code + measured scaling said serial →
  dedicated adjudicator re-derived the comparison before any kill was accepted.
