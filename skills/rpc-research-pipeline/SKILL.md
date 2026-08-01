---
name: rpc-research-pipeline
description: >
  The RPC multi-GPU flavored research pipeline: BASELINE (both GPUs, µs/token) →
  FIREPLACE → RESEARCH WAVE → TRIAGE → WAYFINDER → DEEP RESEARCH → to-PRD →
  RED-TEAM → SCAFFOLDING → DECIDE, with the research LEDGER as the durable backbone.
  Use for RPC/llama.cpp throughput questions: "which RPC fix is best", "should we
  build A7", "is vector X viable", "what's the verdict on the recompute architecture".
  Trigger phrases: "run the rpc research pipeline", "baseline both gpus", "triage the
  rpc findings", "rpc wayfinder". Slash command: /rpc-research-pipeline.
---

# RPC Research Pipeline — Idea → Evidence → Decision (RPC multi-GPU flavor)

This is the **specialized** variant of `research-pipeline` for this project's RPC
multi-GPU fork (atomic-llama-cpp-turboquant). The generic pipeline's order, ledger,
kill discipline, and adjudication rules all apply verbatim — read that skill first.
What differs here: **Stage 0 is pre-specified** (this domain's anchor is known and
measured), the **scoring rubric is fixed**, and the **vector vocabulary + artifact
paths are the project's own** (A1–A8, NW1–4, BUG-011 lineage). You do NOT re-derive
the baseline or the vocabulary — you work against them.

## Stage 0 — Baseline (pre-specified, do not re-derive)

The comparison anchor is **already measured** at `.scratch/benchmarks/rpc-baseline-cost.md`:

| Metric | Anchor value |
|--------|--------------|
| Per-token blocking RPC | ~5,300 µs/token (2-GPU layer-split 9B MTP, TCP) |
| GRAPH_COMPUTE | ~4,390 µs (82.8%), 2.8 calls/token — MTP-churn-inflated |
| GET_TENSOR | ~808 µs (15.2%), ~4.7 calls/token |
| GET_DEVICE_MEMORY | ~33 µs (0.6%) — V1a cache working |
| GRAPH_RECOMPUTE | ~0 µs (async) — already optimal |
| 1-GPU tg ceiling | ~98 t/s = 7900 XTX 10.2ms/token decode (head-bound floor) |
| Scaling | 2-GPU 35B 80.89 tg64 · 3-GPU 80B 84.21 · 5-GPU 80B 70.19 t/s |

**Acceptance threshold (default):** any claim must beat the anchor in the anchor's
own units (µs/token or t/s), measured via the S0 diffing harness — never prose.
The V2 "+56%" claim was a mirage precisely because it was scored against nothing;
every vector in this domain is scored against this table.

**Hardware/method context (already known):** 5 GPUs (7900 XTX ROCm, 5060 Ti, 3090,
3070, 3060 Ti Docker RPC); layer-split + row-split modes; TCP default with
`GGML_RPC_UDP=1` behind a reliability gate (BUG-011/T2e); MTP speculation.

## The Loop (immutable order — same as generic)

```
⓪ BASELINE ─▶ ① FIREPLACE ─▶ ② RESEARCH WAVE ─▶ ③ TRIAGE ─▶ ④ WAYFINDER ─▶ ⑤ DEEP RESEARCH
   (done)        (divergent)    (parallel)        (vectors)   (refine)      (chosen vector)

⑥ to-PRD ─▶ ⑦ RED-TEAM ─▶ ⑧ TECHNICAL SCAFFOLDING ─▶ ⑨ COLLECT SPECS → DECIDE
   (spec)       (attack)     (implementation spec)      (gate when all in)
```

## The scoring rubric (fixed for this domain — locked at Stage 0)

| Criterion | Measure |
|-----------|---------|
| Per-token RPC cost | µs/token at N=1,2,3,5 (GRAPH_RECOMPUTE + GET_TENSOR + events) |
| RPC share of decode | % of token time in RPC, before vs after |
| N-backend stability | connection churn → no recompute misses; failure isolation; cache growth bounded; heterogeneous nodes (ROCm+CUDA) |
| Rollback cost (speculative vectors) | mispredict penalty vs pipeline depth; must beat the round-trip it hides |
| Change size / risk | lines, hot-path exposure, regression surface |
| Kill criteria | per vector — stated in the wayfinder brief, honored at the ⑨ gate |

## The vector vocabulary (the project's own — reuse, don't reinvent)

**Correctness stack (BUG-011 lineage):** B0 (TCP-only control, CARRY) · A1 (shared
store only, KILL — fails by construction) · A2/A2′ (shared server + session,
SHORTLIST → **built**: T2b/T2c) · A4 (versioned store + UDP seq, CARRY/alternative).

**Network-stall stack:** NW1 (uid stability — #1 lever, T3a-c in campaign, projected
+42/84/97%) · NW2 (payload analysis: 244KB is 98.2% metadata) · NW3 (async
GRAPH_COMPUTE, +5–15%, queued) · NW4 (GET_TENSOR batch / same-host shmem /
GRAPH_COMPUTE_ALL, queued).

**Topology / beyond-floor:** A7 (RPC-to-RPC chain — adjudicated, see below) ·
A5 (MTP-on-RPC, CARRY/DEFER — acceptance gate) · A6 (router prediction, KILL with
re-open condition) · A8/Path-E Hydra (DESTINATION) · E/F/G + GETpipe + R2reorder
(CARRY/research) · GRAPHPIPE (KILL).

**Kill criteria already honored:** A1 (BUG-011b by construction) · A6 (3 criteria:
no window / nothing to hide / <1% economics) · GRAPHPIPE (autoregressive-bound) ·
T-B1 double-buffer (flip test, ADR-005).

## Stage-by-stage contract (same as generic; artifact paths pre-bound)

| # | Stage | Agent | Read-only? | Deliverable |
|---|-------|-------|-----------|-------------|
| ⓪ | Baseline | measurement (lease) | ❌ | `.scratch/benchmarks/rpc-baseline-cost.md` — DONE (refresh if stale) |
| ① | Fireplace | 1 (divergent) | ✅ | `.scratch/research/fireplace-rpc-architecture.md` |
| ② | Research wave | 3–5 parallel | ✅ | `.scratch/research/rpc-research-<axis>.md` (upstream, transport, concurrency, nbackends, speculative, nw1-4, a6, a7-*) |
| ③ | Triage | parent | ✅ | findings → named vectors in LEDGER entry (A1..An, NWn) |
| ④ | Wayfinder | plan agent | ✅ | `.scratch/plans/rpc-architecture-vectors.md` → `rpc-architecture-final.md` |
| ⑤ | Deep research | 1–2 per vector | ✅ | e.g. `rpc-research-speculative.md` (R5/A4), `rpc-research-a6-router-prediction.md` |
| ⑥ | to-PRD | to-prd skill | ✅ | `.scratch/specs/PRD-rpc-<topic>.md` |
| ⑦ | Red-team | 1–2 adversarial | ✅ | `.scratch/specs/PRD-rpc-<topic>-redteam.md` (SHIP / SHIP-WITH-FIXES / REJECT) |
| ⑧ | Scaffolding | parent/plan | ✅ | `.scratch/specs/scaffold-rpc-<topic>.md` — slices, blocking edges, merge order |
| ⑨ | Decide | parent + user | — | ADR (`.scratch/adrs/ADR-NNN-…`) + verdict doc + LEDGER final entry |

## Conflict adjudication — the A7 precedent (load-bearing)

The A7 research wave produced a NO-GO resting on **"the starfish parallelizes
compute (per-token = max(t_i)); the chain serializes it (Σt_i)."** The scheduler
(`ggml_backend_sched_compute_splits` in ggml-backend.cpp) and the measured V6
scaling (adding weak GPUs *decreases* throughput — the serial signature) contradicted
that premise. Instead of picking a winner: a dedicated **adjudication agent**
re-derived the comparison against the source + baseline before any kill was accepted.
**Rule: in this domain, the starfish-vs-chain serial/parallel question (and any
equivalent load-bearing topology premise) MUST go through adjudication, not
intuition.** Kill decisions never rest on an unverified premise.

## Known traps (domain-specific — check before declaring victory)

1. **The kill-criteria trap:** recompute hit-rate >99% after NW1 ≠ done — the
   steady-state GET_TENSOR tax (~800µs/backend, O(N)) remains. Measure the gap.
2. **The mirage:** any "+UDP" or throughput claim must be re-validated against the
   S0 diffing harness (output coherence), not llama-bench time-only (BUG-011 lesson).
3. **Heterogeneity:** adding weak GPUs to a layer pipeline can regress throughput
   (V6: 84→72→70 t/s). Balance by compute time, not weight count.
4. **Rollback economics:** speculative vectors need p > ~0.70 break-even AND
   T_rollback < 2×T_compute; RPC acceptance (0.33–0.647) is below both.
5. **Merge order (F8):** correctness (A2′/T2) lands before throughput (NW1/T3) —
   a throughput change without the uid-verify underneath is a correctness regression.

## Handoff

At DECIDE, implementation goes to `wayfinder-assembly-chain` (the Increment-1
campaign is the live example). Handoff carries: ACs anchored to the baseline table
above, the F8 merge order, and the red-team's SHIP-WITH-FIXES list.

## Resumability

Same as generic: read the LEDGER stage-status table → verify artifacts on disk →
resume the earliest incomplete stage. Agents are expendable; the ledger + specs
are the memory.
