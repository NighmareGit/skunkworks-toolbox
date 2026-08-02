# CONCEPT — Grok Harness Upgrades (system-design discoveries + structural patches, upstreamable)

**Purpose:** a durable ledger of the grok-harness system-design issues this campaign discovered
and the structural patches we applied to work around them — organized so they can be shared
back with x.ai (design doc / issue / PR) to harden grok for everyone, humans and AIs alike.

**Thesis:** grok's harness defaults to *goodwill-driven agents* — one parent-centric AGENTS.md
auto-loaded into every subagent, skills as opt-in discovery, and no per-role instruction
channel. This campaign patched that structurally (layered instruction stack, mandatory
Skills-to-load, compaction-safe placement, a trust layer). The patches are our-side tooling,
but the *design lessons* are upstreamable: x.ai can build the rails INTO grok so no project
has to bolt them on.

---

## The entries (issue → impact → our patch → upstream-ability)

### 1. THE PER-ROLE INSTRUCTION GAP (the flagship)
- **Issue:** the harness auto-loads ONE parent-centric AGENTS.md into every subagent (compacted).
  It carries orchestration doctrine (dispatch tables, delegation rules) — written for the
  PARENT, not the worker. Dispatched agents get no role-specific rails: how to behave as a
  steal-impl / verify / research / bug-fix / review agent is left to model goodwill.
- **Impact:** agents improvise process; conventions drift; the parent must re-encode the same
  discipline into every brief; a model that doesn't "feel like it" follows nothing.
- **Patch (our-side):** a three-layer instruction stack — machine-wide universal class manuals
  (`~/.grok/agents/AGENTS.<class>.md`) → project-bolted addendum (`.grok/agents/CAMPAIGN.md`)
  → brief wiring (mandatory Skills-to-load). Plus an auto-load pointer at the TOP of AGENTS.md.
  Procedure-not-persona: sequences, checks, decision rules, kill criteria — no role-play fluff.
- **Upstreamable:** a native **per-role instruction channel** in the harness: the dispatch
  API takes a `class`/`role` field and auto-attaches the matching instruction file (from a
  machine-wide registry), like the auto-load does for AGENTS.md. The parent then can't forget
  to instrument; the rails are in the context by construction.

### 2. SKILLS ARE OPT-IN DISCOVERY
- **Issue:** subagents see a skills *inventory* (from AGENTS.md) but nothing makes them READ a
  skill. Discovery ≠ application; a model may improvise instead of loading the procedure.
- **Patch:** the dispatch-brief template's "Skills to load" is now a MANDATORY section (paths +
  read-confirmation in the final summary). "If a skill file is missing, say so — do not improvise."
- **Upstreamable:** a `skills: []` field on the dispatch that the harness PRE-LOADS into the
  subagent's context (not opt-in), or at least an auto-read of named skills before the first turn.

### 3. COMPACTION TAIL-LOSS
- **Issue:** the auto-loaded AGENTS.md is *compacted* — tail sections can drop. The most
  important content (agent-facing contract) sat deep in the file; it could vanish for agents.
- **Patch:** the agent-facing section is placed at the TOP of AGENTS.md (before Primary Goal)
  so compaction preserves it. The 10-point spine is duplicated with the class files
  (cheap redundancy for compaction resilience).
- **Upstreamable:** stable section-pinning for the auto-load (mark sections as
  compaction-pinned), or a size budget with a warning when the instruction file exceeds it.

### 4. WORKFLOW RUNTIME REDUCED SURFACE
- **Issue:** the Rhai workflow runtime rejects STANDARD Rhai functions: `args.get(key, default)`
  (3-arg) and `join(array, str)` both fail with "Function not found" — while `contains`+index,
  `for`+string-concat, `type_of`, `.len()` work. Session-tree-dependent (G1's open question).
  Silent defaulting (the `args.get` 3-arg pattern cited in a shipped example workflow) would
  have rendered missing args as "()" — a latent failure mode.
- **Patch:** the parent's `validate_only` gate caught both defects pre-launch; templates now use
  only the empirically-confirmed surface (contains+index, for+concat) + a LOUD required-keys
  guard (`pause("verification", ...)` on missing keys — silent defaults forbidden).
- **Upstreamable:** (a) document the actual supported Rhai surface in the workflow tool docs
  (or ship the standard string/array lib — `join` and `args.get` 3-arg are standard Rhai and
  were likely stripped by a minimal build); (b) a compile-time lint that flags
  "function-not-found" BEFORE launch (validate_only already does — advertise it).

### 5. VALIDATE_ONLY IS SINGLE-PATH SMOKE
- **Issue:** the workflow dry-run ("smoke check") executes ONE canned path — it proved both
  defects here, but it is not a correctness proof (it can't cover every branch).
- **Patch (discipline):** validate_only is a GATE, not a proof — templates changed → validate →
  the report says "smoke, not proof" (a captured lesson).
- **Upstreamable:** multi-path dry-run (execute every class branch with canned hosts), or a
  branch-coverage report from validate_only.

### 6. AGENT_BUDGET = LAUNCHES, NOT TOOL CALLS
- **Issue:** the workflow `agent_budget` counts child-agent LAUNCHES; the campaign's early
  registry treated it as a tool-call budget (5-16× mismatch). The contract is under-documented.
- **Patch:** budget-as-data (`declared_max_slots` in the manifest → `round_up(slots×2,4)` at
  render); unit confusion resolved from 3 independent sources.
- **Upstreamable:** document the unit in the tool contract (one sentence) + a runtime warning
  when a workflow exceeds N launches mid-run.

### 7. BLOCK-WAITING CANCELS SUBAGENTS
- **Issue:** long `get_command_or_subagent_output` waits, when interrupted, CANCELLED subagents
  (this campaign's repeated agent-kill pattern: VVRAM ×2, fix agent). The wait/notify semantics
  make an interrupted wait destructive.
- **Patch (discipline):** never block-wait on agent outputs — dispatch and let completion
  notifications arrive (a hard rule now in the auto-load spine).
- **Upstreamable:** make interrupted waits NON-destructive (the subagent keeps running; the wait
  just detaches), or a "detach" affordance that guarantees no cancel-on-interrupt.

### 8. ENV BAKED AT PROCESS START
- **Issue:** the model key resolution (`env_key`) reads the env at process start — swapping to a
  new API key required a FULL GROK RESTART (the longcat quota-dead-key incident, this session).
- **Patch:** inline `api_key` in `[model.<name>]` wins over `env_key` (documented resolution
  order) — but the running session may still cache config.
- **Upstreamable:** per-model key re-resolution on use (read the env at call time, not process
  start), or a `/reload-config` command that refreshes models+keys without restart.

### 9. MONITORS DON'T SURVIVE COMPACTION / SESSION RESTART
- **Issue:** a background monitor (watchdog) did not survive a session restart — the session
  boundary silently drops watch state.
- **Patch:** re-arm monitors after restart from the checkpoint (documented in the handoff).
- **Upstreamable:** persist monitor registrations across session boundaries (or a documented
  "monitors are session-scoped" contract).

### 10. SCHEDULER OWNERSHIP GAP
- **Issue:** scheduled tasks fire only when a session is up — no session for N weeks = silent
  backlog (the lessons-sweep red-team's L4).
- **Patch:** stale-marker startup hook + delta caps + chunked processing.
- **Upstreamable:** scheduler backfill semantics (fire missed runs on next session) or a
  documented fail-open contract.

---

## The layered instruction stack (the flagship patch, detailed)

```
Agent spawn
  └─ auto-load: AGENTS.md (compaction-safe: agent-facing contract at TOP)
       └─ pointer: ~/.grok/agents/AGENTS.<class>.md   (machine-wide, universal)
       └─ 10-point spine (the standing behavior contract)
  └─ brief: Skills-to-load #1 = class manual · #1b = project-bolted CAMPAIGN.md
  └─ class manual: the procedural depth (falsify-first 3-checks, gate tables, signatures)
  └─ trust layer: independent review (different model) + verify-on-disk — rails guide, distrust proves
```

## Upstream-ability map

| # | Entry | x.ai can change IN grok | ours is tooling-only |
|---|-------|------------------------|----------------------|
| 1 | Per-role instruction channel | ✅ native `role`/`class` field on dispatch | the stack itself |
| 2 | Skills pre-load | ✅ `skills: []` pre-loaded into context | mandatory Skills-to-load |
| 3 | Compaction pinning | ✅ pinned sections | top-placement discipline |
| 4 | Rhai surface | ✅ ship standard lib / document surface | contains+index templates |
| 5 | validate_only | ✅ multi-path smoke + coverage report | gate discipline |
| 6 | agent_budget unit | ✅ doc the contract | budget-as-data manifest |
| 7 | Wait semantics | ✅ non-destructive interrupt | don't-block rule |
| 8 | Key re-resolution | ✅ per-use env read / reload-config | inline api_key |
| 9 | Monitor persistence | ✅ persist across sessions | re-arm discipline |
| 10 | Scheduler backfill | ✅ fire missed runs | stale-marker hooks |

## The spirit

Structure over goodwill. Procedure rails the agent, distrust verifies the output, and the
harness should carry the rails natively — so every project (and every model) gets them, and
"better grok for all of us (humans and AI)" stops being a per-project bolt-on.
