---
name: orchestration-dispatch
description: >
  Battle-tested dispatch + orchestration playbook for multi-agent research/implementation
  campaigns (extracted from the RPC multi-GPU throughput mission, 2026-07/08). Covers the
  exact dispatch-brief anatomy that worked, the agent-assignment mapping, resource
  orchestration (locks/leases/serialization), resume-after-kill discipline, and the
  failure lessons that cost real sessions to learn. Use when: launching agents, writing
  tickets, dispatching parallel research, running a campaign, recovering from cancelled
  agents, or building a new mission's AGENTS.md.
---

# Orchestration Dispatch — The Operating System of a Successful Campaign

**Source mission:** RPC multi-GPU throughput campaign (`hunter/prototype-auto`, 2026-07/08).
This is the *operating system* that produced 3 correctness fixes, 4+ banked merges, an
architecture verdict, and a verified unlock — distilled so the next mission starts at
lesson-20 instead of lesson-1.

## What this skill contains

| File | What it is |
|------|-----------|
| `SKILL.md` (this) | The playbook: dispatch anatomy, assignment map, orchestration rules, lessons |
| `templates/dispatch-brief.md` | The reusable ticket-prompt skeleton (copy-paste) |
| `templates/state-file-schema.md` | The task-state contract every agent must write |
| `DISPATCH-BRIEF.md` | The AGENTS.md-style master brief with linked references (this skill's "readme" for a new mission) |

## The core insight

A campaign's reliability comes from **making the parent cheap and the agents predictable**.
Every ticket that succeeded had the same anatomy; every agent that failed was missing one
of the parts below. The dispatch brief is a *contract*, not a description.

## The 9-part dispatch anatomy (the non-negotiable skeleton)

1. **Role + ticket** — "You are the X agent for TICKET-NAME." One ticket, one agent.
2. **Read-first list** — exact file paths the agent must read BEFORE acting. Never let an
   agent re-derive what a prior agent already wrote down.
3. **Ground truth (verified, do not re-derive)** — the parent states what it already
   verified (HEADs, live servers, existing commits), so the agent doesn't waste calls
   re-discovering it.
4. **Environment** — paths, builds, GPU topology, credentials, which locks/leases to take.
5. **Required steps IN ORDER** — numbered, with the *first* step always being the state
   file + worktree isolation (never code first).
6. **The change (exactly this)** — precise seams with file:line, or "do NOT re-architect"
   guardrails. The agent must know the blast radius.
7. **Do NOT list** — explicit prohibitions (other files, other branches, UDP variants,
   GPU fighting, scope creep). This is where most agent failures happen.
8. **Kill criteria / thresholds** — the numbers that decide GO/KILL/CONDITIONAL, stated
   upfront so the agent reports a verdict, not vibes.
9. **Deliverables** — report path, state file path, LEDGER entry, commit message, push
   targets. An agent is done when the deliverables exist, not when it "finishes."

Plus two operational rules baked into every brief:
- **Failure protocol:** "if a step blocks you twice, write the blocker + your attempt to
  the state file and return a clear failure report — do not loop." (Caps grinding.)
- **Call budget:** "cap ~N tool calls" — gives the parent a watchdog signal.

## Agent-assignment mapping (who does what)

| Task category | Agent type | Why |
|---------------|-----------|-----|
| Quick search / symbol lookup | jupiter-search (jupiter-gemma-4) | Fast, read-only, cheap |
| Codebase exploration | jupiter-explore | Fast, code-first |
| Spec compliance check | jupiter-spec-check | Read-only, code-first |
| Light coding | jupiter-light-code | Fast, read-write, small diffs |
| Deep multi-source research | general-purpose (longcat-2) | Frontier reasoning for synthesis |
| Full code review | reviewer (ds-v4-flash) | Standards + spec axes, needs frontier |
| Implementation | implementer (ds-v4-flash) | Heavy lifting |
| Planning | plan (ds-v4-flash) | Structured plans |
| Debugging | general-purpose + diagnosing-bugs skill | Complex root-cause |
| Measurement/verification | general-purpose + perf-verification skill | GPU/benchmark gates |

## Orchestration rules (the parent's job)

### Parallelize by resource class, serialize by lock
- Read-only research tickets → **PARALLEL** (no locks).
- Modify+build+test tickets → **SEQUENTIAL** via `build` lock; worktree-isolated so
  `source` lock is rarely needed.
- GPU tickets → **SEQUENTIAL** with `gpu-N` lease on top.
- Never run two builds concurrently (shared build dir corruption).

### The state-file contract (anti-context-rot)
Every agent writes `.scratch/task-state/<TICKET>.json` FIRST (schema in
`templates/state-file-schema.md`), heartbeats on every major step. The watchdog reads
these. An agent that never writes its state file is invisible — treat it as suspect.

### Watchdog + grace
A heartbeat watchdog flags stale tickets. Long GPU benchmarks get a **grace list**
(`grace.conf`) so they aren't false-flagged. "Stale state file" ≠ "dead agent" — verify
liveness before killing.

### The LEDGER as backbone
Every session decision, verdict, kill, and merge gets a numbered LEDGER entry
(`.scratch/research/LEDGER.md`). It is the append-only truth; AGENTS.md/CONTEXT.md are
derived summaries. A campaign without a LEDGER forgets its own history.

### Resume-after-kill discipline (learned the hard way — 4 kills this mission)
- **"Cancelled" ≠ "failed"** — a cancelled agent's *transcript is preserved*; resume it
  with `resume_from` instead of re-dispatching fresh.
- **Work survives the agent** — check the worktree/branch for the agent's commit BEFORE
  re-dispatching. (This mission: the E-1 fix was committed by a cancelled agent; we
  resumed and verified it, didn't redo it.)
- **Session kills orphan processes** — a cancelled agent's background build can survive
  and hold `build.lock` with a dead pid. The hardened lock.sh reaps dead-pid locks; check
  `find . -name "*.lock" -type d` if agents seem stuck.
- **Do NOT block-wait on agents** — long-timeout `get_command_or_subagent_output` waits
  that get interrupted CANCEL the subagent. Let completion notifications arrive; poll
  short, never block long.

## The failure lessons (each cost a real session)

1. **"Garbled output = training data" is almost always wrong.** Coherent *translatable*
   Chinese from an English prompt was the diagnostic signature of a stale memory-plane
   binding — the model was reading a valid-but-wrong-epoch state. Wrong-address glitches
   that produce *coherent* output in another language are pointer bugs, not data.
2. **A monolithic multi-part agent brief stalls.** "Wire 3 stubs AND run 3 benchmarks"
   produced 62 min of reading and zero output. Split into measurement-only and
   implementation agents; each was fast and clean.
3. **"Broken on all backends" ≠ upstream bug.** The GDN race broke single-GPU too — bisect
   is the ultimate truth-teller (11 steps replaced 2 loops of differential guesswork).
4. **Two independent bugs can share one symptom.** The uid-collision (BUG-013) and the
   stale-binding (BUG-002a) both produced garbling; fixing one exposed the other. Always
   re-test after a fix, on the full matrix.
5. **Kill with evidence, then write the ADR.** Failed vectors are valuable — document the
   kill criteria that fired and the re-open conditions.

## Where this lives

- **Canonical:** `skunkworks-toolbox/skills/orchestration-dispatch/` (gitea + GitHub)
- **Campaign copy:** `prototype-auto/.grok/skills/orchestration-dispatch/` (active use)
- **Master brief:** `DISPATCH-BRIEF.md` — the AGENTS.md-style doc linking all of this
- **Source mission docs:** `hunter/prototype-auto/.scratch/` — LEDGER, CONTEXT, BUGS.md,
  plans/ (the living proof this playbook works)
