# Role Registry — the Orchestrator's Dispatch Front-Door

> Single curated table the orchestrator resolves through when dispatching: task type →
> role → model → capability → prompt → rails. Every dispatch should be a LOOKUP, not
> hand-assembly. `config-consistency.py --registry` validates this table against
> `~/.grok/config.toml` (role exists, model matches, prompt file exists) so the registry
> cannot drift from the live config.
> Applies to: `~/.grok/config.toml` + `~/.grok/prompts/*.md`. Companion: `ROLE-ARCHITECTURE.md`.

## The Registry

| Role | Model | Capability | Prompt file | Rails | When to dispatch to this role |
|------|-------|------------|-------------|-------|-------------------------------|
| `orchestrator` | `deepseek-v4-flash` | all | prompts/orchestrator.md | dispatch discipline | Coordination: state machine, dispatch, verify, recover, log. Never for deep execution. |
| `researcher` | `longcat` | read-only | prompts/researcher.md | R1-R9 + no-derivation | Heavy reading + synthesis: papers, source, docs. 256K context is the asset. |
| `implementer` | `longcat` | all | prompts/implementer.md | R1-R9 + scope-creep | Code changes, test-running, toolchain edits. Deep work. |
| `general` | `longcat` | all | prompts/general.md | R1-R9 + single-goal | Well-scoped execution tasks that don't fit a specialist (prefer a specialist when one exists). |
| `planner` | `longcat` | read-only | prompts/planner.md | R1-R9 + planner-doesn't-execute | Architecture/planning that reads lots of files. Produces plans, never executes. Renamed from `plan` — the built-in `plan` type cannot be shadowed at user scope (verified in discovery.rs). |
| `verifier` | `deepseek-v4-flash` | read-only | prompts/verifier.md | independent check, no repair | Contract checking, output verification, review. MUST be a different model than the implementer. |
| `math-enforcer` | `deepseek-v4-flash` | execute | prompts/math_enforcer.md | Python-tool enforcement | Numerical/validation tasks. Cheap mechanical checks. |
| `explore` | `local-gemma-4-e4b` | read-only | (built-in) | rails inline | Codebase recon, fast read/grep/list, free local AI. NO math, no deep reading (re-verify output). Read-only TOOLSET (no shell), not a sandbox — read_file/grep accept absolute paths, so scope it via the paths you hand it and re-verify outputs. |
| `(fork)` | `deepseek-v4-flash` | — | — | — | Session forks inherit the orchestrator model (`fork_secondary_model`). |

## Dispatch rules (the front-door contract)

1. **Every dispatch resolves through this table** — never spawn ad-hoc without a role, model, and rails.
2. **Prefer the specialist**: researcher for reading, implementer for code, verifier for checks, explore for recon. `general` is the fallback, not the default.
3. **Verifier ≠ implementer model** (correlated-error protection): longcat implements, ds-4-flash verifies.
4. **Longcat roles loop without rails** — every longcat brief embeds the rail core (`prompts/longcat-rails.md`): single goal, tool budget, numbered steps, stop-and-report, definition of done.
5. **Workflows**: when dispatching a wave, `agent()` calls carry `agent_type` (resolved via the type registry → model + capability + rails) — reference this table when choosing the type, don't hand-assemble `model`/`capability_mode` per call. `dispatch-wave.rhai` enforces a `KNOWN_TYPES` allowlist (validated by `config-consistency.py` D2c).
6. **Lineage**: every dispatch gets a `dc_` DISPATCH_ID (see dispatch-trace.py) — include `dispatch=<id>` in the subagent description, link the agent id after spawn, stamp the decision log.

## Curation workflow

To add or change a role: (1) edit `~/.grok/config.toml` `[subagents.roles.*]` + prompt file, (2) update this table, (3) run `config-consistency.py` — it must report CONFIG-CONSISTENT before the role is used.

## Spawnable types (the routing layer)

Every registry role except `explore`/`(fork)` is also a **real spawnable subagent type** via
an agent definition in `~/.grok/agents/<role>.md` (verified against the grok-build source:
`xai-grok-agent` discovery scans `.grok/agents/` from cwd to repo root, then `~/.grok/agents/`).
The definition front-matter (`model`, `capability_mode`) + body (rails) make
`spawn_subagent(subagent_type="researcher")` resolve to model=longcat, read-only, rails —
no per-spawn hand-assembly. `config-consistency.py` validates each definition exists AND
parses (D2b) and that the workflow's `agent_type` references resolve (D2c).

> Builtin-name caveat (verified in discovery.rs): user-scope definitions whose name collides
> with a built-in subagent (`plan`, `explore`, `general-purpose`) are skipped — the built-in
> wins. That is why the planning type is named `planner`, not `plan`.

| Definition | Type | Model | Capability |
|-----------|------|-------|------------|
| `~/.grok/agents/researcher.md` | `researcher` | longcat | read-only |
| `~/.grok/agents/implementer.md` | `implementer` | longcat | all |
| `~/.grok/agents/general.md` | `general` | longcat | all |
| `~/.grok/agents/planner.md` | `planner` | longcat | read-only (renamed from `plan` — the built-in plan cannot be shadowed at user scope, so the rails body lives under a non-builtin name) |
| `~/.grok/agents/verifier.md` | `verifier` | deepseek-v4-flash | read-only |
| `~/.grok/agents/math-enforcer.md` | `math-enforcer` | deepseek-v4-flash | execute |
| `~/.grok/agents/orchestrator.md` | `orchestrator` | deepseek-v4-flash | all |

`explore` and the fork are builtin — no definition file needed.

*Generated: 2026-08-08 · informed by grok-build source investigation (D4).*
