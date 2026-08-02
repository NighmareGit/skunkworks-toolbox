---
name: orchestration-dispatch
description: >
  Dispatch + orchestration playbook for multi-agent research/implementation campaigns:
  the dispatch-brief anatomy, agent-assignment mapping, resource orchestration
  (locks/leases/serialization), resume-after-kill discipline, and failure lessons.
  Use when: launching agents, writing tickets, dispatching parallel research, running
  a campaign, recovering from cancelled agents, or setting up a new mission.
---

# Orchestration Dispatch

The full generalized playbook lives at **`docs/orchestration-playbook.md`** — read
that first. This skill is the loadable pointer + the two reusable templates.

## Files in this skill

| File | What it is |
|------|-----------|
| `docs/orchestration-playbook.md` (repo docs/) | The canonical, project-neutral playbook (doctrine, loop, 9-part anatomy, assignment map, orchestration rules, resume discipline, kill discipline, session lifecycle, failure lessons) |
| `templates/dispatch-brief.md` | Copy-paste skeleton for every ticket prompt |
| `templates/state-file-schema.md` | The per-ticket state contract every agent writes |

## The 30-second version (full detail in the playbook)

1. **One ticket = one agent = one brief.** The brief is a contract: role, read-first
   list, ground truth, environment, steps in order, the exact change (blast radius),
   a Do-NOT list, kill criteria (numbers), deliverables — plus a failure protocol
   ("blocked twice → write blocker + return") and a call budget.
2. **State file first, always.** Every agent writes its ticket state file before
   touching code; the watchdog reads these; an agent that never writes one is suspect.
3. **Parallelize by resource class, serialize by lock.** Research parallel; build/test
   sequential (build lock); hardware sequential (lease). Locks must be kill-proof
   (stale-holder reaping + self-cleaning trap) — a killed agent must not hang the fleet.
4. **The ledger is the truth.** Every decision/verdict/kill/merge gets a numbered
   entry; summaries derive from it. Verify evidence on disk, don't trust reports.
5. **Death is cheap.** "Cancelled" ≠ "failed" (resume, don't redo); work survives the
   agent (check the worktree before re-dispatching); don't block-wait on agents
   (interrupted waits can cancel them); session kills take agents, not state.
6. **Kill with evidence, name confounds, state re-open conditions.** A documented
   dead end is an asset.
7. **Coherent wrong-output is a pointer bug, not a data problem.** If a system emits
   *fluent* output in the wrong language/mode for a correct input, it's reading a
   valid-but-wrong state — diagnose the pointer, don't blame the data.

## Templates

- `templates/dispatch-brief.md` — the ticket-prompt skeleton
- `templates/state-file-schema.md` — the state-file contract

## Where this came from

Extracted from a hardware-optimization campaign that landed multiple correctness
fixes and a verified unlock (2026-07/08). The generalized pattern is the product;
the mission specifics live in that project's own ledger, not here.
