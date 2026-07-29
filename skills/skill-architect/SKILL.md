---
name: skill-architect
description: >
  Design and build new skills or workflows when the current scaffolding is
  insufficient for a task. Diagnoses the missing capability, decides whether
  it's a reusable pattern (build a generic skill) or a one-off (build a
  workflow/script), then scaffolds and validates the result.
  Use when: "framework failure", "missing capability", "need a skill for",
  "this needs its own tool", "reusable pattern", "/skill-architect",
  or the optimization-blueprint skill delegates a FRAMEWORK_FAILURE here.
metadata:
  short-description: "Build new skills and workflows on the fly when existing scaffolding isn't enough"
---

# Skill Architect

When a task hits a **framework failure** — the existing skills, tools, and
workflows don't have the capability needed — the Skill Architect designs and
builds the missing scaffolding. It operates in two stages with a reusability
gate.

```
FRAMEWORK FAILURE: capability X is missing
         │
         ▼
┌─────────────────────────────────┐
│ Reusability Gate                │
│                                 │
│ "Would another part of the      │
│  codebase benefit from this?"   │
└──────┬──────────────┬───────────┘
       │              │
     YES              NO
       │              │
       ▼              ▼
  Stage 1:         One-off short circuit
  Generic skill    → build a workflow or
  → then           script directly, no
  instantiate      generic skill needed
```

---

## Input

The Skill Architect requires a **gap diagnosis**. This can come from:
- A framework assessment (e.g., Phase W1 in optimization-blueprint)
- Direct user request ("we need a way to X")
- A failed optimization loop that identified missing scaffolding

The diagnosis should describe:

```yaml
GAP:
  name: "<short name, e.g. parallel-subprocess>"
  what_is_missing: "<what capability isn't available>"
  where_needed: "<which files/contexts need this>"
  reusability_check:
    appears_in_n_places: <1 or 2+>
    other_places: ["<list of other contexts that would benefit>"]
  preferred_form: skill | workflow | script
```

---

## Step 1: Reusability Gate

Ask one question: **"Would another part of the codebase benefit from this same capability?"**

| Pattern appears in | Build | Example |
|-------------------|-------|---------|
| **1 place** (one-off) | Direct workflow or script | A specific concurrency test for one tool |
| **2+ places** (reusable) | Generic skill first, then instantiate | Parallel subprocess pattern used by IBKR, options, sentiment |

**How to determine this:**
- Read the codebase for similar patterns
- Check if the same approach would apply to other tools
- If you're not sure, default to one-off (skills can be generalized later)

---

## Step 2a: Build a Generic Skill (Reusable Path)

When the pattern appears in 2+ places, build a generic skill that captures it.

### Design the skill

Identify:
- **Inputs** — what parameters make it generic? (batch_size, timeout, command, etc.)
- **Outputs** — what does it produce? (merged dict, success/failure counts, errors)
- **Pattern essence** — what is the core algorithm or process?
- **Worked example** — how does a specific case map onto the generic parameters?

### Scaffold the skill

Create the file at `.grok/skills/<pattern-name>/SKILL.md`.

Required structure:

```markdown
---
name: <kebab-case-name>
description: >
  <one-sentence description with trigger phrases>
metadata:
  short-description: "<10-word summary>"
---

# <Title>

<2-3 sentence explanation of what this skill does and when to use it>

## Inputs

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|

## Outputs

| Field | Type | Description |
|-------|------|-------------|

## How to Use

<step-by-step instructions with code blocks>

## Worked Example

<a concrete example showing the pattern instantiated for a real case>

## When to Use vs Alternatives

| Use this | If |
|----------|----|
| ... | ... |
```

### Rules for good skills:
- **Concrete** — include runnable code blocks, not just prose
- **Parameterized** — inputs and outputs are explicitly defined
- **One job** — a single skill does one thing well
- **Self-contained** — doesn't depend on other skills (though it can reference them)
- **Trigger phrases** — the `description` field should match when it should auto-invoke
- The skill directory is `<project>/.grok/skills/<name>/` or `~/.grok/skills/<name>/` for user-wide

---

## Step 2b: Build a One-Off (Non-Reusable Path)

When the pattern appears in only 1 place, build the specific tool directly.

Options (pick the simplest that works):

| Form | When | Output |
|------|------|--------|
| **Rhai workflow** | Multi-phase process with agent calls | `.grok/workflows/<name>.rhai` |
| **Standalone script** | Single subprocess or computation | `tools/<name>/tool.py` |
| **Inline code change** | Small change to an existing file | Edit in place |
| **Shell alias/fn** | Quick one-liner | Document in the relevant file |

---

## Step 3: Validate

Regardless of path taken, validate the new scaffolding:

### For skills:
- [ ] File exists at the correct path
- [ ] YAML frontmatter is valid (name, description, metadata)
- [ ] Skill appears in `/skills` list (it auto-loads when files change on disk)
- [ ] Skill can be invoked (test with a dry-run prompt)

### For workflows:
- [ ] File exists at `.grok/workflows/<name>.rhai`
- [ ] `workflow <name> validate_only=true` passes
- [ ] Workflow has `let meta = #{ name, description }` header

### For scripts:
- [ ] `python3 -m py_compile <file>` passes
- [ ] `--help` or `--dry-run` works

---

## Step 4: Hand back

Report to the caller:
- What was built (path + summary)
- Whether it's a generic skill or one-off
- How to use it
- Any limitations or future generalization opportunities

---

## Examples

### Example A: Parallel subprocess (reusable)

```
GAP: "Run N subprocess calls in parallel with batching and error handling"
     Needed by: IBKR fetch, options fetch, sentiment fetch (3 places)

Result: generic skill at .grok/skills/parallel-subprocess/SKILL.md
        + usage in run_live_pipeline.py for each data source
```

### Example B: Concurrency benchmark (one-off)

```
GAP: "Benchmark different thread counts for the data fetch pipeline"
     Needed by: one debugging session, not a recurring need

Result: .grok/workflows/benchmark-concurrency.rhai (run once, discard)
```

### Example C: Stale chain detection (reusable)

```
GAP: "Detect stale yfinance options chains"
     Needed by: V1 engine, V2 engine, backtest runner (3 places)

Result: generic skill at .grok/skills/stale-chain-detection/SKILL.md
        + reference from each consuming engine
```
