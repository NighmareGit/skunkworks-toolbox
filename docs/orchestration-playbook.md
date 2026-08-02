# Orchestration Playbook — Running Multi-Agent Campaigns That Land Results

> **What this is:** the generalized, project-neutral operating manual for running
> fleets of sub-agents (research, implementation, measurement, review) under a
> coordinating parent. Distilled from a hardware-optimization campaign that landed
> multiple correctness fixes, an architecture verdict, and a verified unlock —
> but **every rule below is stated in universal terms** so any project can inherit
> it. The mission-specific war stories live in that project's own ledger; this
> file is the pattern.
>
> **Who this is for:** the parent/orchestrator agent in any multi-agent effort —
> and the human who writes its prompts.

---

## 1. The one-paragraph doctrine

A campaign is a **fleet of disposable agents** coordinated by a cheap parent that
specializes in *contracts*. Every ticket is a contract (the dispatch brief), every
agent writes a contract (the state file), every decision is recorded in a contract
(the ledger). Reliability comes from **making agents predictable, not from making
them smart**. When an agent fails, the failure is almost always a broken contract —
a missing "do not" list, a missing kill criterion, a scope that was too monolithic —
so fix the contract, not the agent.

**The parent's only jobs:** (1) write good contracts, (2) read the returns,
(3) decide next moves from evidence. If the parent is doing the work itself, the
system has collapsed into a single agent with extra steps.

---

## 2. The operating loop

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
             (ledger + verdict)   │ grace list  │
                                  └─────────────┘
```

**Loop discipline:** every iteration must produce at least one of — a merged change,
a documented kill, a verified number, or a novel option. If a loop produces none of
these, the campaign is spinning: stop and re-plan before spending more agents.

---

## 3. The dispatch brief — the 9-part anatomy

Every ticket is one agent, one brief. The brief is a **contract**, not a
description. A brief missing any part below produces a proportionally flaky agent.

| # | Part | Why it's load-bearing |
|---|------|----------------------|
| 1 | **Role + ticket** — "You are the X agent for TICKET" | One ticket, one agent; no ambiguity about identity |
| 2 | **Read-first list** — exact file paths to read BEFORE acting | Never let an agent re-derive what a prior agent already wrote down |
| 3 | **Ground truth (verified, do not re-derive)** — what the parent already confirmed | Saves calls; anchors the agent to reality |
| 4 | **Environment** — paths, builds, hardware, credentials, which locks/leases | Without it the agent guesses |
| 5 | **Steps IN ORDER** — numbered, step 1 is always state file + isolation | Code-first agents skip their own bookkeeping |
| 6 | **The change (exactly this)** — precise seams, blast radius, "do NOT re-architect" | Guards against scope creep into working code |
| 7 | **Do NOT list** — explicit prohibitions | The single highest-yield section; most failures are here |
| 8 | **Kill criteria / thresholds** — numbers that decide GO/KILL/CONDITIONAL | The agent reports a verdict, not vibes |
| 9 | **Deliverables** — report path, state file, commit, push targets | An agent is done when deliverables exist, not when it "finishes" |

**Two operational rules in every brief:**
- **Failure protocol:** "if a step blocks you twice, write the blocker + your
  attempt to the state file and return a clear failure report — do not loop."
- **Call budget:** "cap ~N tool calls" — gives the parent a stall signal.

**Reusable template:** `skills/orchestration-dispatch/templates/dispatch-brief.md`

---

## 4. The agent-assignment map (who does what)

| Task category | Agent type | Why |
|---------------|-----------|-----|
| Quick search / symbol lookup | fast search role (small fast model) | Cheap, read-only |
| Codebase exploration | fast explore role | Code-first navigation |
| Spec-compliance check | fast spec-check role | Read-only, code-first |
| Light coding | fast light-code role | Small diffs, fast iteration |
| Deep multi-source research | general-purpose (frontier model) | Synthesis needs reasoning |
| Full code review | reviewer role (frontier model) | Standards + spec axes |
| Implementation | implementer role (frontier model) | Heavy lifting |
| Planning | plan role (frontier model) | Structured plans |
| Debugging | general-purpose + debugging skill | Root-cause reasoning |
| Measurement/verification | general-purpose + verification skill | Gates and numbers |

**Rule of thumb:** fast/cheap models for lookup and small diffs; frontier models for
research, review, implementation, and debugging. Never use a frontier model where a
fast one suffices — and never trust a fast model with a root-cause verdict.

---

## 5. Orchestration rules (the parent's job)

### 5.1 Parallelize by resource class, serialize by lock

- **Read-only research tickets → PARALLEL** (no locks, no shared state).
- **Modify + build + test tickets → SEQUENTIAL** via a build lock; worktree-isolated
  so the source lock is rarely needed.
- **Hardware (GPU/etc.) tickets → SEQUENTIAL** with a per-device lease.
- **Never run two builds concurrently** — shared build dirs corrupt.
- Two tickets that both modify + compile dispatch sequentially, not in parallel;
  a research ticket can always ride alongside.

### 5.2 Locks must be kill-proof

A lock acquired via atomic directory creation is correct, but **must survive its
holder dying**: a killed agent (crash, cancel, session kill) leaves the lock behind,
and every later agent spins on it. Two hardening layers, both non-negotiable:

1. **Stale-holder reaping:** on acquire, if the lock's recorded holder pid is dead,
   reap the lock and retry immediately instead of waiting out the timeout.
2. **Self-cleaning trap:** the holder installs a `trap` so a kill (SIGTERM/EXIT)
   releases the lock. SIGKILL can't be trapped — the reaper covers that case.

Reference implementation: `scripts/lock.sh`.

### 5.3 The state-file contract (anti-context-rot)

Every agent writes a per-ticket state file FIRST (schema:
`skills/orchestration-dispatch/templates/state-file-schema.md`), heartbeats on major
steps, and sets a terminal status. The watchdog reads these. **An agent that never
writes its state file is invisible — treat it as suspect.** Three liveness signals,
any one fresh = alive: heartbeat field, state-file mtime, fresh artifacts in the
ticket's worktree.

### 5.4 Watchdog + grace

A heartbeat watchdog flags stale tickets. Long benchmark phases get a **grace list**
(per-ticket grace seconds) so they aren't false-flagged. **"Stale state file" ≠
"dead agent"** — verify liveness (process, worktree activity) before acting.

### 5.5 The ledger as backbone

Every decision, verdict, kill, and merge gets a numbered entry in an append-only
ledger. It is the truth; summaries and status docs are derived from it. A campaign
without a ledger forgets its own history — and repeats its own mistakes.

### 5.6 Verify evidence, not claims

An agent's report is a claim; the state file + commit + artifact are the evidence.
Verify on disk before believing a verdict ("don't trust state alone"). This is the
cheapest bug-prevention the parent has.

**Close-ritual follow-up sweep (the 'untracked follow-up' plug):** at ticket close,
the parent greps the completed report for out-of-scope markers ("follow-up", "next
step", "out of scope", "recommended") and extracts every one into a ticket or
LEDGER entry before marking done. A follow-up that isn't tracked is a follow-up
that gets lost (source mission: an E-2 recompute-win follow-up sat untracked in a
report until a sweep caught it; two more were caught the same day). The report's
"Follow-ups" section + the state file's `follow_ups[]` are the contract.


An agent's report is a claim; the state file + commit + artifact are the evidence.
Verify on disk before believing a verdict ("don't trust state alone"). This is the
cheapest bug-prevention the parent has.

---

## 6. Resume-after-kill discipline

Agents die. Sessions die. The system must make death cheap:

1. **"Cancelled" ≠ "failed."** A cancelled agent's transcript is preserved; resume it
   (continue from its conversation) instead of re-dispatching fresh.
2. **Work survives the agent.** Before re-dispatching after a kill, check the
   worktree/branch/state file for the agent's partial or committed work. Resume +
   verify beats redo. (A fix that was already committed by a killed agent is done —
   verify it, don't re-implement it.)
3. **Kills orphan processes.** A cancelled agent's background build can survive and
   hold a lock with a dead pid. The hardened lock (5.2) reaps it; check for stale
   lock dirs if agents seem stuck.
4. **Don't block-wait on agents.** Long-timeout waits on an agent that get
   interrupted can cancel the agent itself. Let completion notifications arrive;
   poll briefly, never block long.
5. **Session kills take agents, not state.** Branches, commits, state files, and the
   ledger survive. Re-dispatch from state files, never from memory.

---

## 7. Kill discipline (the hard part)

- Every ticket has kill criteria stated UPFRONT — numbers, not vibes.
- A kill is a **documented verdict** (ledger entry + state file status), not a
  deletion. Failed vectors are valuable.
- **The premise-adjudication rule:** a kill must never rest on an unverified
  architectural premise. When a big idea's viability hinges on a claim, adjudicate
  the claim with a dedicated read-only agent first.
- **Confounds must be named.** If a failing experiment ran on a known-broken path,
  say so — a "kill" that's actually a confound gets a re-run after the fix, and the
  re-run is the real verdict.
- **Conditional verdicts get re-open conditions.** State what would make you revisit.

---

## 8. Session lifecycle

- **Start:** read the project's AGENTS.md → verify ground truth on disk (HEADs,
  live services, state inventory) → read the context doc + ledger tail → resume
  from the next-actions list.
- **Compaction/checkpoint:** write a structured snapshot (state inventory + HEADs +
  next actions) AND a bootstrap prompt that tells the next session to re-read the
  project AGENTS.md first. Both, not either.
- **Kill/restart:** session-scoped agents die; durable state survives. Re-dispatch
  from state files.
- **End of day:** every commit pushed, leases released, locks clean, board + context
  + ledger current. A clean state to walk away from is a feature, not a nicety.

---

## 9. Failure lessons (each cost a real session to learn)

1. **"The output is bad because of the data" is almost always wrong.** When a
   system produces *coherent* output in the wrong language/mode from a correct
   prompt, that is usually a **wrong-address / stale-pointer bug** — the system is
   reading a valid-but-wrong state, not hallucinating from training data. Coherent
   wrong-output is a diagnostic signature, not an excuse. (This one rule saved a
   multi-week detour into "it's the model, not the code.")
2. **A monolithic multi-part agent brief stalls.** "Wire three stubs AND run three
   benchmarks" produced an hour of reading and zero output. Split into
   measurement-only and implementation agents — each was fast and clean.
3. **"Broken in every configuration" ≠ upstream bug.** Differential debugging
   loops can spin for days; a **bisect** (binary search over commits) is the
   ultimate truth-teller — a handful of steps replaces guesswork.
4. **Two independent bugs can share one symptom.** Fixing the first exposes the
   second. Always re-test on the full matrix after a fix, not just the failing case.
5. **Kill with evidence, then write the ADR.** The kill criteria that fired and the
   re-open conditions are the deliverable — the dead end is an asset for the next
   person (or the next mission).

---

## 10. What to copy into a new project

| Artifact | Where it lives | Copy to |
|----------|---------------|---------|
| This playbook | `docs/orchestration-playbook.md` | Your project's docs or AGENTS.md reference |
| Dispatch-brief template | `skills/orchestration-dispatch/templates/dispatch-brief.md` | Your project's `.grok/skills/` or prompts dir |
| State-file schema | `skills/orchestration-dispatch/templates/state-file-schema.md` | Same |
| Lock helper (kill-proof) | `scripts/lock.sh` | Your project's `.scratch/locks/` |
| Watchdog pattern | `skills/agent-monitor/` | Adapt to your state-file layout |
| Ledger pattern | (see your project's research ledger) | Append-only numbered history |

---

*Living document — extend it when a new campaign proves a new pattern, and record
the extension in that campaign's own ledger.*
