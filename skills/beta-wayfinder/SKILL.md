---
name: beta-wayfinder
description: Enhanced Wayfinder pipeline with dependency mapping, partial-pass gates, confidence accumulation, portfolio thinking, and convergence-based termination. Predecessor to alpha-wayfinder. Use when running systematic campaigns where vectors have ordering constraints, partial wins matter, and you need to decide when to stop optimizing.
---

# Alpha Wayfinder — Enhanced Systematic Campaign Pipeline

An evolution of `wayfinder-assembly-chain` with 8 specific optimizations. All the original rules apply (resource discipline, verification gate, parent-orchestrator constraints), plus the enhancements below.

---

## Enhancement 1: Dependency-Mapped Vectors

Every vector declares its `depends_on` and `blocks` edges. The parent uses this to build a DAG and never dispatches a vector before its dependencies are resolved.

### Vector format

```markdown
### V3 — [Name]
- **Depends on:** V1, V2 (must be PASS or PARTIAL before V3 starts)
- **Blocks:** V4 (V3 result is input to V4)
- **Hypothesis:** ...
- **Kill criteria:** ...
```

The parent enforces this ordering. If V1 is killed, V3's dependency is unmet — V3 either becomes independent (its hypothesis doesn't need V1) or is killed too.

---

## Enhancement 2: Three-Tier Verification Gate

Instead of binary pass/fail, every ticket reports one of:

| Verdict | Meaning | Action |
|---------|---------|--------|
| **PASS** | Meets all kill-reversal criteria (Sharpe >= 1.5, etc.) | Promote to ensemble, lock in |
| **PARTIAL** | Clear improvement (+40% throughput, +0.4 Sharpe) but below full target | Keep in pipeline, iterate with reduced priority, re-evaluate next loop |
| **FAIL** | Below kill threshold or structurally impossible | Kill, write ADR |

**PARTIAL verdicts are not failures.** They are acknowledged improvements that may compound when combined with other PARTIAL vectors. The ensemble of several PARTIAL vectors can meet the goal even when no single one does.

---

## Enhancement 3: Confidence Accumulation

Each vector carries a live confidence score that increases as evidence accumulates:

| Stage | Confidence Band | Meaning |
|-------|----------------|---------|
| Hypothesis | 5–15% | Gut feeling, no data |
| Post-research | 25–45% | Data supports plausibility |
| Post-prototype | 50–70% | Working prototype, limited out-of-sample |
| Verified | 75–95% | Full walk-forward, transaction-cost-aware |
| In production | 95%+ | Live results match backtest |

The parent uses confidence to:
- Decide kill vs. iterate (a vector at 40% confidence with cheap iteration cost is worth another loop)
- Weight the vector in the ensemble (higher confidence = higher weight)
- Identify where uncertainty is highest and target research there

---

## Enhancement 4: Convergence-Based Termination

Instead of a fixed loop cap (10), use this rule:

> **Stop when 3 consecutive Wayfinder loops produce 0 novel vectors that survive the grill stage.**

Rationale: If you've searched the entire vector space and nothing new survives scrutiny, you've converged. A fixed cap either stops too early (you'd have found V1a at loop 11) or too late (you keep spinning on dead ends).

The parent still documents the convergence decision in an ADR:
```
ADR-007: Campaign convergence at loop 14
- 3 consecutive loops with 0 novel survivors
- Search space appears exhausted for current data regime
- Recommend re-evaluation when new data sources become available
```

---

## Enhancement 5: Portfolio/Diversification-Aware Kill Criteria

A vector that scores below the absolute kill threshold may still be worth keeping if it provides **diversification**:

> Kill vector X only if: `Sharpe(X) < threshold` **AND** `max_correlation(X, surviving_vector) > 0.7` **AND** `Sharpe(X) < Sharpe(surviving_vector) - 0.3`

In other words: a weak but decorrelated signal is more valuable than a moderately strong but highly correlated one.

The parent maintains a **correlation matrix** of all surviving vectors and checks new vectors against it before killing.

---

## Enhancement 6: Per-Vector Resource Budgeting

Every ticket declares its resource cost upfront:

```markdown
### V3 — Sentiment Microstructure
- **Data cost:** $0/month (free Polygon tier)
- **Compute cost:** ~2 CPU-hours per backtest
- **Engineering effort:** 3–5 days
- **Data feed lead time:** 0 days (data already in Polygon)
```

This lets the parent decide: "V3 costs $0 and 3 days — worth trying even at 20% confidence" vs. "V6 costs $200/mo in data feeds and 2 weeks — wait until confidence > 50%."

---

## Enhancement 7: Auto-Lock Wrapper

Sub-agents should NOT manually acquire/release locks. Instead, dispatch work through a wrapper:

```bash
# Instead of:
source .scratch/locks/lock.sh
acquire_lock data-feed 120
python fetch_data.py
release_lock data-feed

# Use:
.scratch/scripts/with-lock.sh data-feed 120 python fetch_data.py
```

The wrapper acquires the lock, runs the command, and releases the lock — even if the command crashes. Implemented in the project's `.scratch/scripts/with-lock.sh`.

---

## Enhancement 8: Data Freshness / Re-Validation

Every killed or partial vector carries a `re-validate` field:

```markdown
### V2 — IV Skew (PARTIAL, Sharpe 0.9)
- **Killed:** 2026-08-15
- **Re-validate:** 2026-11-15 (3 months)
- **Re-validation trigger:** New VIX regime, new options data source, or new ML technique
```

The parent schedules re-validation checks. When the trigger fires, the vector is re-evaluated with current data. This prevents permanent loss of a signal that was killed in an unfavorable regime.

---

## Full Enhanced Loop

```
1. GOAL — immutable primary objective + success metrics
2. WAYFINDER — produce vectors with depends_on, blocks, kill criteria, confidence, resource budget
3. DAG RESOLUTION — order vectors by dependency, identify parallelizable work
4. RESEARCH WAVE (parallel, respects depends_on tiers)
5. GRILL — per-slice deep dive
6. VECTOR REVIEW — update confidence, decide promote/kill/partial/defer
7. TICKETS — one per promoted vector
8. ISOLATED EXECUTION — worktree per ticket
9. TDD → PROTOTYPE → VERIFICATION (PASS / PARTIAL / FAIL)
10. ENSEMBLE UPDATE — recompute correlation matrix, re-weight
11. CONVERGENCE CHECK — 3 consecutive loops with 0 novel survivors?
    → Yes: stop, write ADR
    → No: loop back to step 2
12. RE-VALIDATION SCHEDULER — check stale vectors, re-evaluate if trigger fired
```

---

## Scaffold

Same as `wayfinder-assembly-chain`, plus:

```
.scratch/
  plans/              # wayfinder plans
  research/           # research reports
  benchmarks/         # measurement artifacts
  adrs/               # failed / decided vectors
  locks/              # lock.sh + lock dirs
  scripts/
    with-lock.sh      # auto-lock wrapper
    correlation-matrix.sh  # recompute vector correlation
  BUGS.md             # known issues ledger
  SCHEDULE.md         # re-validation schedule for killed/partial vectors
```
