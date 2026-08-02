# Pattern Recognition — The Judgment Layer (Generalized)

> **What this is:** the calibration a runbook doesn't transfer — the
> pattern-recognition a parent orchestrator accumulates by watching agents live.
> Project-neutral: every pattern is stated universally, without war stories.
> The project-flavored version (with the source mission's incidents) lives in that
> project's `.scratch/docs/orchestration/pattern-recognition.md`.
>
> **How to use:** read BEFORE dispatching anything. This is the judgment layer on
> top of the dispatch anatomy (skills/orchestration-dispatch) and the playbook
> (docs/orchestration-playbook.md). When a pattern fires, consult the matching
> section.

---

## 1. Reading agent health — the triage table

| Signal | Healthy | Stall (intervene) | Dead (kill + resume) |
|--------|---------|-------------------|----------------------|
| Tool-call rate | Steady, purposeful | Climbs slowly (~1/10min) or flat | Frozen 10+ min |
| File writes | State file + artifacts advancing | Zero writes anywhere (workspace + tmp) | Zero writes + no process |
| Errors | < 5% of calls | Climbing, same call retried | Errors + no progress |
| Token consumption | < ~30% ctx | Ballooning (> 40% ctx) on analysis | — |
| Build/GPU processes | Present when expected | Zombie survives cancel (holds lock) | Process gone |

**The three classic misreads, each calibrated by a real incident:**
- **The long reader** — many calls, high token use, ZERO writes for ~1h. Looks
  like deep analysis; is usually a stall from an over-scoped brief. Split the
  scope; the halves are fast.
- **The zombie build** — an agent was cancelled, but its detached background
  build survived and holds a lock with a dead pid → every later agent spins.
  Check lock dirs + processes before blaming slowness.
- **The false death** — a stale state-file heartbeat while the agent is actively
  working (it just never writes its state file). Verify liveness before
  dispatching a redundant takeover.

## 2. Signature diagnostics (output tells you the bug class)

| Signature | What it actually is | How to confirm |
|-----------|--------------------|----------------|
| Fluent wrong-language output | Wrong-epoch/right-state read — system reads a *valid* but misaligned memory | "Coherent" = state is valid, pointer is wrong |
| Repetition loops | Wrong cached object replayed (identity collision) | Compare identities/keys between the two phases |
| Garbage tokens → hard error | Same bug, escalated after a fix removed a masking failure | It's progress (one bug fixed) exposing the next |
| Identical output with/without a mechanism | Mechanism is inert OR the real bug is elsewhere | Flip ON/OFF under identical conditions |
| Same symptom, two independent bugs | Fix #1 exposes #2 | Always re-test the FULL matrix after a fix |

**The meta-rule:** *coherent wrong-output is a pointer bug, not a data problem.*
If the output is *fluent*, the system is fine — the state it's reading is wrong.
Diagnose the pointer.

## 3. Brief-writing calibration

- **Ground truth: over-supply it.** Every verified fact saves the agent 1-3 calls.
  Include HEADs, live services, existing commits, and "do NOT re-derive" markers.
- **Read-first: point at the artifact, not the topic.** "Read `spec.md` §5-6"
  beats "understand the problem." Named sections save loops.
- **Do-NOT list: name the *actual* failure mode.** "Do NOT use transport X — it
  crashes service Y" prevents a real incident; "be careful" prevents nothing.
- **Kill criteria: numbers + a verdict mapping.** "> 80 = GO, < 79 = KILL, 79-80 =
  CONDITIONAL (re-run after fix)" — the agent returns a verdict, not a dump.
- **Over-specification warning:** specifying *how* when the agent should decide
  *what* produces a typist, not an engineer. Specify the *seam* and the
  *constraint*, let the agent implement.

## 4. The confound detector (when a kill isn't a kill)

A failing experiment is a kill ONLY if the failure isn't explained by a known-bad
condition. If it ran on a path known to be broken, the re-run after the fix is the
real verdict, not the first run.

| Question | Kill it | Re-run it |
|----------|---------|-----------|
| Ran on a path known to be broken? | No | **Yes — confound, re-run after fix** |
| Premise adjudicated (A7 rule)? | Yes, with evidence | No — adjudicate first |
| Failure explained by the mechanism under test? | Yes | No — something else is wrong |
| Baseline fair (same hardware/build)? | Yes | No — different setup |

## 5. The resume-vs-redo decision

When an agent is cancelled/killed, before re-dispatching:
1. **Check for committed work** — `git log` on its branch, `git status` in its
   worktree. Committed work by a cancelled agent is a real deliverable: resume +
   verify, never re-implement.
2. **Check the build** — was the change actually compiled into the artifact?
3. **Check the state file** — did it record blockers/attempts?
4. **Resume with the verified facts** — state what the parent confirmed so the
   agent skips ground-truth re-discovery.

If the agent was in a failure loop (errors climbing, same call retried, zero
writes) → **fresh dispatch** with the lesson applied (usually: split the scope).

## 6. The three dispatch archetypes (with skeleton exemplars)

### Implementation brief (the fix is designed; build + verify it)

> You are the [ROLE] agent for [TICKET] — [ONE-SENTENCE GOAL].
> **Read first:** [design doc §5-6], [prior test matrix], [bug ledger].
> **Step 0 [optional probe]:** [diagnostic gate BEFORE the fix, if M1/M2-style
> discrimination matters].
> **Step 1:** [the change — file:line seam + constraint; "throwaway quality,
> compile-clean is the bar"]. Worktree-isolated off [base], build lock, [device]
> lease.
> **Step 2 — Verify:** [named gate run] must [pass condition] — THE gate. [regress
> runs] no-regression. [UDP/env variant] off for all runs.
> **Deliverables:** [report path], [state file], [commit + push], [ledger entry].
> **Do NOT:** modify beyond [scoped files]; [the real failure mode]; fight over
> [device] (lease first); spend >N calls — if blocked twice, write the blocker
> and return.

### Measurement-only brief (a number is needed; nothing to build)

> You are the measurement agent for [TICKET]. Measurement-ONLY: no code changes.
> Keep it FAST (< 15 calls, < 25 min).
> **Context:** [repo @ HEAD], [build dir fresh?], [devices + services], [model],
> acquire [device] lease first.
> **Run 1:** [EXACT command — flags, ports, so the number is reproducible].
> **Run 2:** [variant]. Record [metric] + [coherence gate].
> **Deliverables:** report [path] (runs, configs, numbers, exact commands), state
> file [path] status=complete. If [service] is down: record "blocked" and return.
> **Do NOT:** modify code; attempt [out-of-scope]; fight over the device; run
> [forbidden variant].

### Read-only research brief (a mechanism/verdict needs evidence)

> You are a **design research agent** (read-only, no code, no builds, no GPU) for
> [QUESTION]. Produce a concrete, source-verified [deliverable].
> **Investigate (source-truth everything):** [files with the mechanism], [prior
> diagnosis — may not exist, say so], [bug ledger].
> **Questions (with code evidence):** (1) [mechanism + WHERE], (2) [why the
> single-node path is immune], (3) [fix candidates with effort/risk/cost],
> (4) [composition with in-flight work], (5) [cost per option].
> **Deliverables:** [design doc with file:line trace + candidate table +
> recommendation + impl checklist], [ledger entry], [bug ledger update], [state
> file].
> **Do NOT:** modify source; build; use hardware; acquire locks beyond reading.
> Cite file:line for every claim — if a file doesn't exist, say so explicitly.

### The ordering rule (seeding protocol)

In a fresh session: dispatch a **measurement** ticket first (calibrates your read
on agent health), then **read-only research** in parallel, then **implementation**
once the design is evidence-backed.

**Executable form:** the source project's specialized copy carries a literal
`first-3-loops-checklist.md` (real paths + commands) — ground-truth verification →
read the judgment layer → one measurement calibration dispatch → close one ticket
end-to-end. Replicate that pattern in any new project: 4 loops, each with explicit
pass criteria, before trusting your read on implementation tickets.

---

*Living document — every new campaign pattern gets a row here (generalized) +
a row in the source project's specialized copy (with the war story).*
