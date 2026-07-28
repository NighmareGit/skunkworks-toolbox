---
name: systematic-campaign
description: >
  Run a multi-target systematic campaign: triage missed metrics → wayfinder per target → parallel research → grill + red-team → spec + implement → verify → code-review → integrate. Uses a Rhai workflow under the hood. Includes model routing: local models for code, frontier for strategy, web_search for research. Trigger phrases: "run a campaign", "systematic fix", "multi-target loop", "fix the misses", "/systematic-campaign", "/campaign".
---

# Systematic Campaign

Orchestrate a complete fix-it campaign for N measurable targets. Each target goes through the full pipeline independently; results are re-measured and committed at the end.

## When to Use

- You have walk-forward / benchmark results with clear missed targets
- Each target has a quantified gap (e.g., "Win rate 54.6% < 60%")
- You need a reproducible, documented process that can be reviewed

## The Loop (per target)

```
for each target:
  1. Triage       — quantify the gap, hypothesize root cause, propose 3-5 vectors
  2. Wayfinder    — expand vectors with code-level specifics, kill criteria, expected delta
  3. Research     — codebase search + optional web_search for academic/industry approaches
  4. Grill        — stress-test the recommended vector from all angles
  5. Red-team     — adversarial review (what assumptions could be wrong?)
  6. Spec         — write SPEC.md: problem, solution, files, test plan, rollback
  7. Implement    — make changes, run tests, fix failures
  8. Verify       — re-run measurement, compare vs baseline
```

After all targets: code-review → commit → pipeline run.

## Model Routing

Not all agents have internet access. Route tasks correctly:

| Task Type | Tools | Model |
|-----------|-------|-------|
| **Code reading / analysis** | `read_file`, `grep`, `python3` | Any (local or frontier) |
| **Implementation** | `search_replace`, `write`, `read_file` | Any (local or frontier) |
| **Strategy / architecture** | All tools | Frontier preferred |
| **Web research** | `web_search` (uses searxng MCP) | Must have internet access — use frontier or instruct local agent to report back |
| **Red-team / grill** | All tools | Frontier or deep-reasoning model |

**Rule:** If an agent doesn't have internet access and needs it, it signals the parent with `NEED_ONLINE: <query>`. The parent dispatches a web-search sub-agent and returns the results.

## Creating the Workflow

1. Write a Rhai workflow script with the following phases:

```
Phase 0: Triage all targets
Phase 1: Wayfinder per target (loop)
Phase 2: Research per target (loop)
Phase 3: Grill + Red-team per target (loop)
Phase 4: Spec + Implement per target (loop)
Phase 5: Verify (re-run measurement)
Phase 6: Code review + Commit
Phase 7: Pipeline run (optional)
```

Each phase's `agent()` prompt must include a `MODEL ROUTING:` section that tells the agent which tools to use.

2. Save to `~/.grok/workflows/<campaign-name>.rhai`
3. Validate: `workflow(name="<campaign-name>", validate_only=true)`
4. Run: `workflow(name="<campaign-name>", agent_budget=256)`

See `references/workflow-template.rhai` for a complete template.

## Artifact Structure

```
.scratch/
  research/<campaign-slug>/       # triage, research, grill reports
    triage-{ID}.md
    research-{ID}.md
    grill-{ID}.md
  plans/<campaign-slug>/          # wayfinder, spec, implementation notes
    wayfinder-{ID}.md
    spec-{ID}.md
    implement-{ID}.md
  benchmarks/
    post-fix-comparison.md        # baseline vs post-fix metrics
    post-fix-walkforward.md       # full walk-forward report
    post-fix-code-review.md       # code review of all changes
    post-fix-pipeline-run.md      # live pipeline output
```

## Files to Create per Run

```bash
mkdir -p .scratch/research/<campaign-slug>
mkdir -p .scratch/plans/<campaign-slug>
```

## Success Criteria

The campaign is complete when:
1. All targets have been through the full loop
2. Walk-forward shows measurable improvement (or honest documentation of why not)
3. All tests pass (existing + new)
4. Changes are committed and pushed
5. Code review is archived in `.scratch/benchmarks/`
