---
name: alpha-wayfinder
description: Evolved Wayfinder pipeline with dependency-mapped vectors, three-tier gates, confidence accumulation, toolbox dispatch (parallel-subprocess, model-pipeline-queue, optimization-blueprint, skill-architect), checkpoint protocol, multi-campaign nesting, and convergence-based termination. The successor to beta-wayfinder. Use when running systematic campaigns where vectors have ordering constraints, partial wins matter, and you need to decide when to stop.
---

# Alpha Wayfinder — Evolved Systematic Campaign Pipeline

The successor to beta-wayfinder. Inherits all 8 original enhancements (dependency-mapped vectors, three-tier gates, confidence accumulation, convergence-based termination, portfolio-aware kill criteria, resource budgeting, auto-lock wrapper, re-validation schedule) and adds 5 new enhancements focused on skill integration, agent reliability, and multi-campaign orchestration.

---

## Inherited Enhancements (from beta-wayfinder)

The following are preserved from beta-wayfinder. See `beta-wayfinder/SKILL.md` for full details on each:

| # | Enhancement | Summary |
|---|-------------|---------|
| E1 | Dependency-Mapped Vectors | Every vector declares `depends_on` and `blocks`. Parent builds DAG, never dispatches before dependencies resolved. |
| E2 | Three-Tier Verification Gate | PASS / PARTIAL / FAIL verdicts. PARTIAL is not failure — ensemble of partials can meet the goal. |
| E3 | Confidence Accumulation | Per-vector confidence bands: Hypothesis (5-15%) → Post-research (25-45%) → Post-prototype (50-70%) → Verified (75-95%) → Production (95%+). |
| E4 | Convergence-Based Termination | Stop when 3 consecutive loops produce 0 novel vectors that survive grill. |
| E5 | Portfolio/Diversification-Aware Kill | Kill only if Sharpe < threshold AND correlation > 0.7 AND Sharpe < surviving − 0.3. |
| E6 | Per-Vector Resource Budgeting | Data cost, compute cost, engineering effort declared upfront. |
| E7 | Auto-Lock Wrapper | `.scratch/scripts/with-lock.sh` for all data-fetch and backtest commands. |
| E8 | Data Freshness / Re-Validation | Every killed/partial vector carries a re-validate field with trigger conditions. |

---

## Enhancement 9: Toolbox Dispatch

Not every vector follows the same implementation path. The parent selects the appropriate skill toolbox per vector based on its profile:

| Vector Profile | Toolbox | When |
|---------------|---------|------|
| Pure computation / logic | `tdd` → `prototype` → `code-review` → verify | Most vectors |
| N-way data parallelism | `parallel-subprocess` → `tdd` → verify | Concurrent data fetches, options chain processing, universe screening |
| Model pipelining | `model-pipeline-queue` → `tdd` → verify | LLM call chaining (e.g., 9B → 35B screening-to-context) |
| Performance bottleneck | `optimization-blueprint` (sub-campaign) | Any vector found too slow after initial verification |
| Missing capability | `skill-architect` → build → integrate | When no existing skill covers the needed pattern |

### parallel-subprocess integration

For any vector that fetches or computes data for multiple tickers/symbols:

```python
# Agent pattern:
# "Using the parallel-subprocess skill at .grok/skills/parallel-subprocess/SKILL.md,
#  fetch options chains for the active candidates in batches of 25 with 120s
#  timeout per batch. Aggregate results and pass to the next stage."
```

The skill provides configurable batch sizing, per-batch timeouts, error handling, and result merging. See `.grok/skills/parallel-subprocess/SKILL.md`.

### model-pipeline-queue integration

For any vector that chains LLM calls where downstream processing should start as soon as each upstream result arrives:

```python
# Agent pattern:
# "Using the model-pipeline-queue skill at .grok/skills/model-pipeline-queue/SKILL.md,
#  set up a producer-consumer queue. Producers: T1 9B screening calls.
#  Consumers: T4 35B execution context calls. Each T1 result triggers its own
#  T4 call without waiting for all T1 results to complete."
```

The skill provides thread-safe queue management, configurable worker counts, and error isolation per pipeline item. See `.grok/skills/model-pipeline-queue/SKILL.md`.

### optimization-blueprint delegation

If a vector passes verification but fails a performance constraint (e.g., prediction latency > threshold, throughput below target), the parent spawns a sub-campaign:

```yaml
# Parent dispatches:
# "optimization-blueprint sub-campaign on M6 micro-prediction.
#  GOAL: Reduce prediction latency from 250ms to <100ms.
#  SUCCESS_METRICS:
#    - 5-min prediction latency < 100ms (p95)
#    - Direction accuracy maintained >= 55%
#  CONSTRAINTS:
#    - Must not regress accuracy below 53%
#    - No external API dependency introduced
#  LOOP_LIMIT: 2"
```

The sub-campaign runs in isolation (its own worktree) and reports PASS / PARTIAL / FAIL back. The vector's confidence is updated post-optimization.

### skill-architect delegation

If triage reveals that no existing skill covers what a vector needs, and the pattern appears in 2+ places (reusability gate), delegate to skill-architect:

```yaml
# Parent dispatches:
# "skill-architect
#  GAP:
#    name: concurrent-options-greeks
#    what_is_missing: Compute options greeks (delta, gamma, vega) for 20+
#      tickers concurrently with IBKR API batching
#    where_needed: M5 skew, M7 put/call skew, M8 VIX skew (3 places)
#    reusability_check: appears_in_n_places: 3
#    preferred_form: skill"
```

The skill-architect builds the generic capability, validates it, then the vector implementation uses it. See `.grok/skills/skill-architect/SKILL.md`.

---

## Enhancement 10: Checkpoint Protocol (via task-state)

Every agent dispatched by alpha-wayfinder MUST checkpoint its state using the `task-state` skill. This is mandatory — it is how the system survives compaction and multi-agent handoffs.

### Checkpoint Points (Mandatory)

| Point | When | Format |
|-------|------|--------|
| Agent start | Immediately on dispatch | `.scratch/task-state/<vector-id>.json` with `status: in_progress` |
| Pre-long-op | Before any operation >30s (download, model training, parallel fetch) | Update with `current_step` and `progress` |
| Phase complete | After research, prototype, test phase finishes | Update with `current_phase`, `findings` |
| Agent end | On completion or error | `status: completed` / `status: failed` with `error_detail` |

### Resume Pattern

```
Resume vector M6 — read .scratch/task-state/m6-micro-prediction.json
Last checkpoint: prototype built, 3/6 tests passing, current_phase: test
Next: fix 3 failing tests, re-run pytest, continue to verification
```

### Parent State Tracking

The parent maintains its own session state at `.scratch/task-state/session-main.json`. On resume, the parent reads this file first, then checks each running agent's checkpoint to rebuild the campaign state.

See `.grok/skills/task-state/SKILL.md` for the full protocol.

---

## Enhancement 11: Multi-Campaign Nesting

Alpha-wayfinder can nest campaigns. A vector that is itself a multi-module system (e.g., Harrier with 20 sub-modules) is dispatched as a **nested alpha-wayfinder campaign**:

```
Parent (uprunner): alpha-wayfinder campaign
  Goal: Build Harrier intraday prediction engine
  Vectors: one per Harrier module group (Infrastructure, Signal Engines, etc.)
  
  └── Nested campaign on Signal Engines (M5-M9):
      Goal: Build all signal engine modules with cross-module consistency
      Vectors: M5 (Skew Z-Score), M6 (Micro-Prediction), M7 (PC Skew),
               M8 (VIX Skew), M9 (Sentiment)
      DAG: M5/M6/M9 in parallel → M7 (depends on M5) → ensemble verify
```

### Nesting Rules

- The nested campaign inherits the parent's goal, success metrics, and loop limits
- A nested campaign reports a single PASS / PARTIAL / FAIL verdict back to the parent
- Nested campaigns run in their own worktree (isolated from parent)
- Max nesting depth: 2 levels (parent → child)
- A nested campaign that fails → parent kills the parent vector, writes ADR

---

## Enhancement 12: Module Scaffolding Input

Alpha-wayfinder can read module scaffolding files (like `.harrier/modules/m*/SPEC.md`) as native input. Instead of manually declaring vectors, the parent reads the scaffolding directory and auto-generates vectors from the SPEC files:

```
Input: .harrier/modules/  (20 SPEC.md files)
Output: 20 vectors, each with:
  - depends_on, blocks (parsed from SPEC.md tables)
  - confidence (parsed from SPEC.md)
  - kill criteria (parsed from SPEC.md)
  - re-validate (parsed from SPEC.md)
  - resource cost (parsed from SPEC.md)
  - toolbox recommendation (derived from module type)
```

The parent then resolves the DAG from the combined dependency graph and dispatches in the same wave order defined in the scaffolding.

This means HARRIER.md (or any module-scaffolding project) becomes a direct-executable campaign plan — no manual vector declaration needed.

---

## Updated Full Loop

```
1.  GOAL — immutable primary objective + success metrics
2.  INPUT PARSE — if .harrier/modules/ or similar scaffolding exists, auto-generate vectors;
    otherwise run WAYFINDER to produce vectors manually
3.  DAG RESOLUTION — order vectors by dependency, identify parallelizable work
4.  TOOLBOX SELECTION — per-vector: tdd/prototype, parallel-subprocess, model-pipeline-queue,
    optimization-blueprint sub-campaign, or skill-architect delegation
5.  RESEARCH WAVE (parallel, respects depends_on tiers)
6.  GRILL — per-slice deep dive
7.  VECTOR REVIEW — update confidence, decide promote/kill/partial/defer
8.  TICKETS — one per promoted vector, each with assigned toolbox
9.  ISOLATED EXECUTION — worktree per ticket, checkpoint (task-state) on every phase
10. IMPLEMENTATION — TDD → PROTOTYPE → VERIFICATION (PASS / PARTIAL / FAIL),
    with toolbox-specific variations per Enhancement 9
11. FRAMEWORK CHECK — if implementation hits a missing capability →
    skill-architect → build scaffolding → resume vector
12. ENSEMBLE UPDATE — recompute correlation matrix, re-weight
13. CONVERGENCE CHECK — 3 consecutive loops with 0 novel survivors?
    → Yes: stop, write ADR
    → No: loop back to step 3 (re-resolve DAG with updated confidences)
14. RE-VALIDATION SCHEDULER — check stale vectors, re-evaluate if trigger fired
```

---

## Toolbox Reference

All skills referenced by alpha-wayfinder:

| Skill | Path | Use |
|-------|------|-----|
| `task-state` | `.grok/skills/task-state/SKILL.md` | Checkpoint agent state (mandatory for all agents) |
| `parallel-subprocess` | `.grok/skills/parallel-subprocess/SKILL.md` | N-way concurrent data fetch/computation |
| `model-pipeline-queue` | `.grok/skills/model-pipeline-queue/SKILL.md` | Producer-consumer model call pipelining |
| `optimization-blueprint` | `.grok/skills/optimization-blueprint/SKILL.md` | Performance optimization sub-campaigns |
| `skill-architect` | `.grok/skills/skill-architect/SKILL.md` | Build new skills for missing capabilities |
| `tdd` | `.grok/skills/tdd/SKILL.md` | Test-driven development |
| `prototype` | `.grok/skills/prototype/SKILL.md` | Throwaway prototype to validate design |
| `code-review` | `.grok/skills/code-review/SKILL.md` | Standards + spec review |
| `research` | `.grok/skills/research/SKILL.md` | Deep investigation against primary sources |
| `red-team` | `.grok/skills/red-team/SKILL.md` | Adversarial review of plans/implementations |
| `diagnosing-bugs` | `.grok/skills/diagnosing-bugs/SKILL.md` | Hard bug diagnosis loop |
| `worktree-guard` | `.grok/skills/worktree-guard/SKILL.md` | Isolated worktree per ticket |

---

## Scaffold

Same as `beta-wayfinder`, plus:

```
.harrier/
  modules/            # module scaffolding (SPEC.md + .rhai per module) —
                      # alpha-wayfinder reads this as auto-generated vector input

.scratch/
  plans/              # wayfinder plans
  research/           # research reports
  benchmarks/         # measurement artifacts
  adrs/               # failed / decided vectors
  locks/              # lock.sh + lock dirs
  task-state/         # agent checkpoints (task-state skill)
  scripts/
    with-lock.sh      # auto-lock wrapper
    correlation-matrix.sh  # recompute vector correlation
  BUGS.md             # known issues ledger
  SCHEDULE.md         # re-validation schedule for killed/partial vectors

.grok/
  skills/             # skills available to agents (including those built by skill-architect)
  workflows/          # Rhai workflows for dynamic campaign execution

data/
  harrier/            # Harrier-specific data (feeds, decisions, attribution, benchmarks)
```

---

## When to Use Alpha vs Beta

| Scenario | Use |
|----------|-----|
| Campaign with sub-100 vectors, no parallel data-fetch or model pipelining needed | `beta-wayfinder` is sufficient |
| Campaign with complex DAG, parallel data processing, or model call chains | `alpha-wayfinder` |
| Building a multi-module system from `.harrier/` or similar scaffolding | `alpha-wayfinder` |
| Campaign where agents frequently hit context limits (compaction-prone) | `alpha-wayfinder` (checkpoint protocol) |
| Campaign where the current tooling may be insufficient (need skill-architect) | `alpha-wayfinder` |
| Performance-critical sub-component needs dedicated optimization pass | `alpha-wayfinder` (optimization-blueprint delegation) |

In practice: beta-wayfinder was sufficient for the uprunner signal research campaign (6 vectors, no parallel data processing, no model pipelining). Alpha-wayfinder is required for Harrier (20 modules, parallel options chain processing, model pipelining for micro-prediction, checkpoint-critical due to multi-day build).
