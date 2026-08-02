# Orchestration Dispatch Brief — Master Document

> The AGENTS.md-style operating manual for running a multi-agent research/implementation
> campaign. Extracted from the RPC multi-GPU throughput mission (2026-07/08) — the
> pattern that produced 3 correctness fixes, 4+ merges, an architecture verdict, and a
> verified unlock. **This file is the "readme" for a new mission; the linked files are
> the load-bearing parts.**

## 0. The one-paragraph doctrine

A campaign is a **fleet of disposable agents** coordinated by a cheap parent that
specializes in *contracts*: every ticket is a contract (dispatch brief), every agent
writes a contract (state file), every decision is recorded in a contract (LEDGER), and
the parent's only job is writing good contracts and reading the returns. Reliability
comes from **making agents predictable, not from making them smart**. When an agent
fails, the failure is almost always a broken contract (missing Do-NOT list, missing
kill criteria, monolithic scope) — fix the contract, not the agent.

## 1. The operating loop

```
parent writes dispatch brief ──► agent reads brief + state contract
        ▲                                │
        │                          does the work
        │                                │
        │                          writes deliverables
        │                     (report + state file + commit)
        │                                │
        │                         ┌──────▼──────┐
        └── parent evaluates ◄────┤ watchdog +  │
             (LEDGER + verdict)   │ grace list  │
                                  └─────────────┘
```

Every loop iteration must produce at least one of: a banked merge, a documented kill,
a verified number, or a novel attack vector. If a loop produces none of these, the
campaign is spinning — stop and re-plan.

## 2. The contracts (linked files)

| Contract | File | Purpose |
|----------|------|---------|
| Dispatch brief anatomy | `SKILL.md` §"9-part anatomy" | The non-negotiable ticket skeleton |
| Dispatch brief template | `templates/dispatch-brief.md` | Copy-paste skeleton for every ticket |
| State-file schema | `templates/state-file-schema.md` | The agent's contract with the watchdog |
| Agent assignment map | `SKILL.md` §"Agent-assignment mapping" | Who does what (task → agent → model) |
| Orchestration rules | `SKILL.md` §"Orchestration rules" | Parallelize/serialize, locks, LEDGER, resume |
| Failure lessons | `SKILL.md` §"The failure lessons" | Each cost a real session to learn |

## 3. The resource model

- **Locks:** `build` (1 agent), `source` (1 agent), `gpu-N` (1 agent). Atomic `mkdir`
  with **stale-pid reaping** + **self-cleaning trap** (see `lock.sh` in the toolbox —
  commit `9675179`). An agent killed mid-build must not leave a lock that hangs the
  fleet for 600s.
- **Leases:** GPU work requires a lease; never force, wait or record blocked.
- **Serialization rule:** research tickets parallel; modify+build+test sequential
  (build lock); GPU tickets sequential (lease). Two builds never run concurrently.

## 4. The truth layer

| Artifact | Role | Who writes |
|----------|------|-----------|
| `.scratch/research/LEDGER.md` | Append-only numbered history (decisions, verdicts, kills, merges) | Parent, every loop |
| `.scratch/CONTEXT.md` | Living resume point (HEADs, fleet, running agents, next actions) | Parent, every session |
| `.scratch/BUGS.md` | Bug ledger with the bug-hunt contract (6 required fields) | Bug agents + parent |
| `.scratch/task-state/*.json` | Per-ticket ground truth (schema-linked) | Agents (heartbeat) + parent (snapshots) |
| `.scratch/plans/*.md` | Design docs, wayfinder verdicts, ADRs | Design/research agents |

**Rule:** an agent's report is a claim; the state file + commit + artifact are the
evidence. Verify evidence on disk before believing a claim ("don't trust state alone").

## 5. The kill discipline

- Every ticket has kill criteria stated UPFRONT in the brief (numbers, not vibes).
- A kill is a **documented verdict** (LEDGER entry + state file status
  `killed_<reason>`), not a deletion. Failed vectors are valuable.
- The A7 rule: a kill never rests on an unverified topology premise — adjudicate the
  premise with a dedicated read-only agent before killing a DESTINATION-tier idea.
- "Conditional" verdicts get a re-open condition and the confound named (e.g. the
  fabric E3 kill was confounded by a known-broken uid path — re-run after the fix).

## 6. Session lifecycle

- **Start:** read AGENTS.md → verify ground truth (`git rev-parse`, `ps`, `ls
  .scratch/task-state/`) → read CONTEXT.md + LEDGER tail → resume from next actions.
- **Compaction:** write a precompaction snapshot (task-state inventory + HEADs +
  next actions) + a bootstrap prompt with the "re-read AGENTS.md first" step.
- **Kill/restart:** session-scoped agents die; durable state (branches, commits,
  state files, LEDGER) survives. Re-dispatch from state files, never from memory.
- **End:** every commit pushed (gitea + GitHub), leases released, locks clean,
  board + CONTEXT + LEDGER current. Clean state to walk away from.

## 7. Proven outcomes (source mission, 2026-08-02)

- MTP-on-RPC unlocked: 3 correctness fixes (`77f3f3c40` → `d0fff256c` → `da02606b4`),
  good/green scenario default with zero env vars, 100% draft acceptance verified.
- Architecture verdict with evidence: fabric = GET_TENSOR-elimination, not parallel
  compute (adjudication + feasibility + simulator + wire design, 4 agents converging).
- Root-cause wins: GDN thread_local race (bisect, 11 steps), uid collision (BUG-013),
  stale memory-plane binding (BUG-002a M1), each logged with file:line evidence.
- The failure lessons (§5 of SKILL.md) are the real product — they are what a fresh
  mission inherits.

---

*This brief is a living document — extend it when a new mission proves a new pattern,
and record the extension in the source mission's LEDGER.*
