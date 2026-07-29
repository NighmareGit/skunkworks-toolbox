---
name: optimization-blueprint
description: >
  Closed-loop optimization with meta-cognitive scaffolding: goal definition →
  triage → Wayfinder (parallel research + dynamic Rhai workflow for
  spec→prototype→review→red-team) → goal check → framework-failure detection →
  skill architect for self-extending scaffolding. Max 3 iterations.
  Use when: "optimize", "parallelize", "speed up", "make faster", "concurrent",
  "async", "throughput", "pipeline optimization", "/optimization-blueprint".
metadata:
  short-description: "Self-extending optimization: goal → triage → Wayfinder → skill architect → loop (max 3)"
---

# Optimization Blueprint (Closed-Loop with Meta-Cognitive Scaffolding)

A closed-loop optimization system that can recognize when the current
approach framework is insufficient and dynamically build new skills or
workflows to extend itself. Three loop paths:

| Path | Trigger | Action |
|------|---------|--------|
| **Deepen** | Solution failed, framework is fine | Brainstorming → Deep Research → rebuild workflow |
| **Extend** | Framework itself is insufficient | Skill Architect → scaffold new skill/workflow → run it |
| **Converge** | Goals met OR max loops reached | Done |

```
Phase 0: Goal Definition ──→ Phase 1: Triage ──→ Phase W: Wayfinder
                                                       │
                                          ┌────────────┤
                                          ▼            ▼
                                   Parallel Research  Build Rhai Workflow
                                          │            │
                                          └────────────┘
                                               │
                                               ▼
                                          Phases 3-6
                                          (via workflow tool)
                                               │
                                               ▼
Phase G: Goal Check ──→ PASS? ────→ Done
     │                        │
     │ NO (< 3 loops)         │ YES
     ▼                        │
Framework Failure Detector    │
     │                        │
     ├── Solution failure ──→ Deep Research → loop to Phase W
     │                        │
     └── Framework failure ──→ Skill Architect → build new
                               skill/workflow → run it → loop
```

---

## Phase 0 — Goal Definition

Define what success looks like. Use the scaffold below; prompt the user
if they haven't specified:

```yaml
GOAL: <one-line description>
SUCCESS_METRICS:
  - <measurable criterion 1>
  - <measurable criterion 2>
  - all existing tests still pass
CONSTRAINTS:
  - <what must NOT change>
  - <boundary condition>
LOOP_LIMIT: 3
```

**How:** Present the scaffold to the user. Fill defaults from the codebase
(e.g., current test count from `python3 -m pytest engines/ -q --tb=short`).

---

## Phase 1 — Triage

Break the optimization request into discrete, independent topics.
Each topic = one scoped change to one file or module.

**Output:** structured list with TOPIC, WHAT, FILES, RISK, EFFORT, DEPS.

**How:** Read relevant source code. Spawn a triage sub-agent.

---

## Phase W — Wayfinder

The Wayfinder orchestrates parallel research, dynamically builds a Rhai
workflow for the build phases, and executes it. It also includes a
**framework-failure detector** that decides whether the problem is solvable
within the current approach or needs entirely new scaffolding.

### W1 — Framework Assessment (New)

Before investing in full research, assess whether the current scaffolding
(workflow template, skills, tooling) is adequate for the optimization:

- Are there existing tools/skills that cover this kind of optimization?
- Does the problem fit the existing `.rhai` workflow template?
- Are there missing capabilities (e.g., no skill for a specific technique)?

**Output:** A flag: `framework_adequate: true/false`.

If `false`, skip to W4 (Skill Architect) instead of W2.

### W2 — Parallel Research

For each triaged topic, spawn a **research sub-agent** in parallel. Each
reads the relevant code and recommends the best approach. Output per topic:
- Approach recommendation (with rationale)
- Code sketch
- Performance estimate (current vs optimized)
- Risk assessment

**How:** Use `spawn_subagent` with `background: true` per topic.
Collect all results.

### W3 — Dynamic Rhai Workflow

Build a `.rhai` workflow file that wraps phases 3-6 (spec → prototype →
code review → red-team) into a single runnable unit. The workflow is
**dynamically constructed** from the research results and goal definition.

The generated workflow must include:
- **Phase 3 (Spec):** synthesize research into a unified implementation plan
- **Phase 4 (Prototype):** implement the spec, one topic at a time
- **Phase 5 (Code Review):** review against standards + spec
- **Phase 6 (Red-team):** adversarial attack-vector review

Write the file to `.grok/workflows/optimization-<slug>.rhai`.
Use the existing `.grok/workflows/parallelize-pipeline.rhai` as a template
for the Rhai syntax (backtick string literals, `let result = agent(...)`,
`print()` for progress).

**Critical rules:**
- Each phase is a single `agent()` call
- Pass context between phases via `${variable}` string interpolation
- Include success metrics in the workflow comments
- Name the file with a slug from the optimization topic

### W4 — Skill Architect

When the framework assessment or multiple failed loops indicates that the
existing scaffolding is insufficient, **delegate to the `skill-architect` skill**.

The `skill-architect` skill (at `.grok/skills/skill-architect/SKILL.md`) handles
the full process:
1. **Reusability Gate** — is this pattern needed in 1 place or 2+?
2. **Stage 1 (reusable)** — build a generic skill at `.grok/skills/<name>/SKILL.md`
3. **Stage 2 (instantiate)** — apply the generic skill to the specific case
4. **One-off short circuit** — build a workflow/script directly if not reusable
5. **Validate** — ensure the new scaffolding compiles and runs

**How:** Invoke the skill by describing the gap. Example prompt:

```
/skill-architect

GAP:
  name: parallel-subprocess
  what_is_missing: Run N subprocess calls in parallel with batching and timeouts
  where_needed: run_live_pipeline.py data fetch block
  reusability_check:
    appears_in_n_places: 3
    other_places: [IBKR fetch, options fetch, sentiment fetch]
  preferred_form: skill
```

The skill will build the scaffolding and report back. Resume the optimization
loop once the new capability is available.

---

## Phase G — Goal Check

After the Wayfinder workflow completes, check results against success
metrics from Phase 0.

**Checklist:**
- [ ] `python3 -m pytest engines/ -q --tb=short` — 0 failures?
- [ ] Run optimized path: `python3 run_live_pipeline.py --physical-only --dry-run`
- [ ] Measure against SUCCESS_METRICS
- [ ] Verify CONSTRAINTS not violated
- [ ] Check for regressions in the sequential path

### Framework Failure Detector

If metrics are not met, diagnose WHY. Run a diagnostic sub-agent:

```
Given:
- Goal: <goal>
- Metrics failed: <which ones>
- Approach tried: <what the Wayfinder built>
- Loop count: <N>
- Constraints: <list>

Diagnose: Is this a solution failure (wrong implementation of the right
approach) or a framework failure (the approach itself cannot work within
current tooling/scaffolding)?

If framework failure: what capability is missing? What skill or workflow
would need to exist for this optimization to succeed?
```

**Output:** one of:
- `SOLUTION_FAILURE` — the same approach can work with different parameters
- `FRAMEWORK_FAILURE` — need new scaffolding before this can work

### Branching

| Condition | Action |
|-----------|--------|
| All metrics met | ✅ **Complete** — report results, offer to commit |
| SOLUTION_FAILURE, loops < LOOP_LIMIT | 🔄 **Deepen** — brainstorming → deep research → loop to Phase W |
| FRAMEWORK_FAILURE, loops < LOOP_LIMIT | 🔧 **Extend** — Skill Architect (W4) → build new scaffolding → loop to Phase W |
| loops >= LOOP_LIMIT | ⛔ **Converge** — document what was tried, what remains, what scaffolding was built |

---

## Loop-Back Paths

### Path A: Deepen (Solution Failure)

When the framework is fine but the solution needs work:

1. **Brainstorming** — use the `brainstorming` or `fireplace` skill to
   generate alternative implementations. Prompt: "The current approach
   [describe] failed to meet [which metric]. Brainstorm alternatives."
2. **Deep Research** — take the brainstorming output and run a focused
   research sub-agent on the most promising alternative.
3. **Loop** — pass deep research back to Phase W (W2), rebuild workflow.

### Path B: Extend (Framework Failure)

When the tooling/scaffolding itself is insufficient:

1. **Skill Architect (W4)** — design and build the missing capability
2. **Validate** — run the new skill/workflow to ensure it works
3. **Loop** — resume Phase W with the new capability available

### Path C: Converge

When max loops reached, produce a final report documenting:
- What was tried (each loop's approach)
- What succeeded (new skills/workflows built, even if goals weren't met)
- What remains (unmet metrics for future work)
- Recommendation (which approach came closest and should be the starting
  point for the next campaign)

---

## Goal Scaffold Template

When the user hasn't specified goals, present this:

```
GOAL: <one-line description>
SUCCESS_METRICS:
  - <metric 1>
  - <metric 2>
  - all existing tests pass
CONSTRAINTS:
  - <constraint 1>
  - <constraint 2>
LOOP_LIMIT: 3

Current test count: NNN passing
```

---

## File Reference

| File | Purpose |
|------|---------|
| `.grok/workflows/parallelize-pipeline.rhai` | Template for dynamically generated workflows |
| `.grok/skills/optimization-blueprint/SKILL.md` | This skill |
| `engines/` | Test suite: `python3 -m pytest engines/ -q --tb=short` |
