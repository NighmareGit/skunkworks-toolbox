# Agent Instruction Files — Machine-Wide (for dispatched subagents, ANY project)

> Agent-facing operating manuals for the agents a parent dispatches to tickets. Installed
> machine-wide at `~/.grok/agents/` (next to `~/.grok/skills/`) because agent→model→skill→task
> mapping and "how agents get fed instructions" is a MACHINE-wide pattern, not a per-project one.
> Canonical backup: skunkworks-toolbox `docs/agent-manuals/`. Project-bolted pointers live in
> each project's auto-loaded AGENTS.md + dispatch-brief template.

## The set

| File | For | When |
|------|-----|------|
| `AGENTS.steal-impl.md` | Port/steal agents | Porting a proven change from an upstream repo into the fork |
| `AGENTS.verify.md` | Verification agents | Running a pre-specified recipe + gate table + verdict |
| `AGENTS.research.md` | Research agents | Read-only research — citations, verdict-on-research |
| `AGENTS.bug-fix.md` | Bug-hunt agents | Repro → diagnose → minimal fix → verify |
| `AGENTS.review.md` | Reviewer agents | Independent review — standards + spec + verify-on-disk |

## How the parent wires them

1. Every brief's "Skills to load" lists `~/.grok/agents/AGENTS.<class>.md` FIRST.
2. The auto-loaded project AGENTS.md carries an "Agent-Facing Instructions" section pointing here.
3. The agent MUST read its class file before acting and confirm in the final summary.
4. The class file overrides nothing in the brief; conflict → the brief wins, flag the conflict.

## The shared spine (each class file assumes it; the parent enforces it)

1. **Read-first** — the feedstock is the source of truth; do NOT re-derive.
2. **State-first** — heartbeat the state file (real ISO timestamp, your id); NEVER replace it.
3. **Evidence over claims** — cite file:line; verify on disk; never trust "Built target".
4. **Report-first, NO-OVERWRITE** — the report file is the first deliverable; append-only.
5. **Ledger discipline** — the project's entry numbering convention, computed at write time.
6. **Lessons field** — the project's close-ritual lessons line (0-3, evidence-cited).
7. **Hold vs blind-patch** — new root cause → document + HOLD; never re-architect.
8. **Don't loop** — two blocks on a step → state-file blocker + clear failure report.
9. **Resource discipline** — GPU lease (never force), build lock (build only), worktree isolation.
10. **Kill criteria** — every ticket has them; a KILL with falsifying numbers is a valid close.
