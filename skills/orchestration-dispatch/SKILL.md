---
name: orchestration-dispatch
description: >
  Project-bolted dispatch + orchestration playbook for THIS campaign (RPC multi-GPU
  throughput). Specialized from the generalized toolbox playbook
  (docs/orchestration-playbook.md): the dispatch-brief anatomy, agent-assignment
  map, resource orchestration, resume-after-kill discipline, and failure lessons —
  wired to this project's actual artifacts (LEDGER, BUGS.md, AGENTS.md, state files,
  real commit history). Use when: launching agents in this campaign, writing
  tickets, dispatching research, recovering from cancelled agents, or onboarding a
  new orchestrator to this project.
---

# Orchestration Dispatch — Project-Bolted (RPC Multi-GPU Campaign)

> **This is the campaign-specialized version.** The generalized pattern lives in the
> toolbox (`skunkworks-toolbox/docs/orchestration-playbook.md`); this file bolts the
> pattern to THIS project — real artifact paths, real dispatch examples, real commit
> history, real lessons with their war stories. If a rule here conflicts with the
> toolbox version, the project version wins (it reflects what actually worked here).

## The core doctrine (as proven in this campaign)

A campaign is a **fleet of disposable agents** coordinated by a cheap parent that
writes contracts. Every ticket is a contract (dispatch brief), every agent writes a
contract (state file), every decision lands in a contract (LEDGER). When an agent
fails, the failure is almost always a broken contract — fix the contract, not the
agent.

**Proof (this campaign, 2026-07/08):** 3 correctness fixes banked back-to-back
(T3a-c `77f3f3c40` → E-1 `d0fff256c` → stable-uid flip `da02606b4`), an
architecture verdict with 4-agent converging evidence, and the MTP-on-RPC unlock —
each produced by a single-agent ticket following this playbook.

## Where everything lives (project map)

| Artifact | Path | Role |
|----------|------|------|
| Campaign context | `.scratch/CONTEXT.md` | Living resume point (HEADs, fleet, running agents, next actions) |
| The ledger | `.scratch/research/LEDGER.md` | Append-only numbered truth (#48–65 and counting) |
| Bug ledger | `.scratch/BUGS.md` | BUG-013 (fixed-by-default), BUG-014 (open), BUG-002a (VERIFIED-FIXED) |
| Ticket state | `.scratch/task-state/increment1/*.json` | Per-ticket ground truth + heartbeat (51 files) |
| Wayfinder verdicts | `.scratch/plans/rpc-3fires-vectors.md` | The attack-vector shortlist/kills |
| Design docs | `.scratch/plans/*.md` | e.g. `bug-002a-deep-fix-design.md` (M1 root cause) |
| Dispatch templates | `.grok/skills/orchestration-dispatch/templates/` | Copy-paste skeletons |
| The fork | `atomic-llama-cpp-turboquant/` | `good-prototype` = `da02606b4` (all fixes merged) |
| Toolbox (general) | `skunkworks-toolbox/docs/orchestration-playbook.md` | The generalized pattern |

## The 9-part dispatch anatomy (campaign flavor)

1. **Role + ticket** — "You are the X agent for TICKET-NAME." One ticket, one agent.
2. **Read-first list** — exact `.scratch/` paths (reports, design docs, prior state).
   Never let an agent re-derive what a prior agent wrote down.
3. **Ground truth (verified, do not re-derive)** — the parent states HEADs, live
   servers (3060 Ti RPC at 127.0.0.1:50051), existing commits, which builds are
   fresh. Saves the agent 10-20 calls of re-discovery.
4. **Environment** — fork path, build dirs (`build-rocm-native`, `build-cuda-b-bin`),
   GPU topology (7900 XTX + 3060 Ti), which locks/leases to take.
5. **Steps IN ORDER** — step 1 is ALWAYS: write the state file
   (`.scratch/task-state/increment1/<TICKET>.json`) + worktree isolation
   (worktree-guard). Never code first.
6. **The change (exactly this)** — precise seams with file:line (e.g.
   `ggml-backend.cpp:2060-2080`), and "do NOT re-architect X — it's correct for
   reasons in [ref]". Blast radius stated.
7. **Do NOT list** — explicit prohibitions: other files, other branches, UDP
   variants (`GGML_RPC_UDP=0` — BUG-014), GPU fighting, scope creep.
8. **Kill criteria / thresholds** — numbers (e.g. fabric E3: `tg64 > 80.89 = GO`,
   `hop >= 800 µs = KILL`). The agent reports a verdict, not vibes.
9. **Deliverables** — report to `.scratch/benchmarks/<ticket>.md`, state file with
   terminal status, commit + push (gitea + GitHub), LEDGER entry if a decision.

**Operational rules baked into every brief:**
- **Failure protocol:** "if a step blocks you twice, write the blocker + your
  attempt to the state file and return a clear failure report — do not loop."
- **Call budget:** "cap ~N tool calls" (research 15-30, implementation 30-45,
  measurement 15-25).

## Agent-assignment map (this campaign's proven routing)

| Task | Agent | Model | Why |
|------|-------|-------|-----|
| Quick search / symbol lookup | jupiter-search | jupiter-gemma-4 | Fast, read-only, cheap |
| Codebase exploration | jupiter-explore | jupiter-gemma-4 | Code-first navigation |
| Spec compliance | jupiter-spec-check | jupiter-gemma-4 | Read-only code-first |
| Light coding | implementer role | ds-v4-flash | Code tasks grow context → jupiter decode collapses with KV depth (08-02: 150→5-11 t/s at 69K). Frontier owns ALL code |
| Deep multi-source research | general-purpose | longcat-2 | Frontier synthesis |
| Full code review | reviewer role | ds-v4-flash | Standards + spec axes |
| Implementation | implementer role | ds-v4-flash | Heavy lifting |
| Planning | plan role | ds-v4-flash | Structured plans |
| Debugging | general-purpose + diagnosing-bugs | ds-v4-flash | Root-cause reasoning |
| Measurement/verification | general-purpose + perf-verification | ds-v4-flash | Gates + numbers |

### Jupiter eligibility gate (constraint-aligned allocation — 2026-08-02)

Jupiter (MidnightCoder-30B, 5070 Ti 16 GB, **1 slot**) is a this-session, single-lane, short-horizon LAN token buffer. A task may be dispatched to jupiter ONLY if **ALL** hold:

1. **Read-only** — no code modification, no builds, no GPU work.
2. **Short horizon** — ≤ 3 turns (≤ ~30K context, fast-decode zone); no deep multi-file dives, no long reports.
3. **Small outputs** — readable with grep/head, not full-file dumps; terse report.
4. **Single-lane** — one jupiter agent at a time; never shared across grok sessions (interleaved sessions thrash the KV — zero reuse).
5. **Not latency-critical** — a 100%-GPU generation at depth is acceptable (background buffer).

If any criterion fails → frontier (longcat / ds-v4-flash). Measured basis 08-02: decode 150 t/s at short context, 5-11 t/s at ~69K KV depth (code tasks inherently grow context → not useful); `id_task` in this server build is decode-linked (16-token request advanced it +74) so raw task-id churn is NOT a flood signal — watchdog v4 uses rate+progress-aware signatures (zombie-rate churn ≥50 ids/10s sustained, wedged-slot = frozen id + no decode progress).

## Orchestration rules (what actually worked)

### Parallelize by resource class, serialize by lock
- Read-only research → **PARALLEL** (no locks).
- Modify+build+test → **SEQUENTIAL** (build lock), worktree-isolated.
- GPU tickets → **SEQUENTIAL** with `gpu-N` lease (gpu-lease skill).
- Never two concurrent builds. Two modify+compile tickets dispatch sequentially;
  research rides alongside.

### Locks must be kill-proof (this campaign paid for this lesson)
`lock.sh` (fork `.scratch/locks/` + workspace root) is hardened:
- **Stale-holder reaping:** dead holder pid → reap instantly on acquire.
- **Self-cleaning trap:** `trap EXIT INT TERM` releases on kill.
- Why: a cancelled agent's orphaned build held `build.lock` with a dead pid for
  600s spins — the "session hang" that cost an hour of investigation. If agents
  seem stuck: `find . -name "*.lock" -type d` and check for stale dirs.

### State-file contract
Every agent writes `.scratch/task-state/increment1/<TICKET>.json` FIRST (schema:
`templates/state-file-schema.md`), heartbeats on major steps, sets terminal status.
Watchdog reads these. **An agent that never writes its state file is invisible —
treat it as suspect.** Three liveness signals, any fresh = alive: heartbeat field,
file mtime, worktree artifacts. Grace list (`task-state/grace.conf`) covers long
benchmarks. "Stale state file" ≠ "dead agent" — verify liveness first (this
campaign false-flagged T3a and dispatched a redundant takeover).

### The LEDGER is the backbone
Every decision/verdict/kill/merge gets a numbered entry (currently #48–65).
CONTEXT.md and AGENTS.md derive from it. A campaign without a ledger repeats its
mistakes.

### Verify evidence, not claims
An agent's report is a claim; state file + commit + artifact are the evidence.
Verify on disk before believing a verdict ("don't trust state alone" — this
campaign's ground-truth checks caught a stale HEAD reference and 7 un-tracked
state files).

## Resume-after-kill discipline (learned from 4 session kills)

1. **"Cancelled" ≠ "failed."** A cancelled agent's transcript is preserved — resume
   it (`resume_from`) instead of re-dispatching fresh. (3 of this campaign's
   "failed" agents were actually cancelled; resume worked.)
2. **Work survives the agent.** Before re-dispatching after a kill, check the
   worktree/branch/state file. **The E-1 fix was committed by a cancelled agent**
   (`d0fff256c`); we resumed, verified, and merged — we did NOT re-implement.
3. **Kills orphan processes.** A cancelled agent's background build can survive and
   hold a lock with a dead pid. Hardened lock.sh reaps it.
4. **Don't block-wait on agents.** Long-timeout waits that get interrupted CANCEL
   the subagent (the repeated agent-kill pattern this session). Let completion
   notifications arrive; poll briefly, never block long.
5. **Session kills take agents, not state.** Branches, commits, state files, LEDGER
   survive. Re-dispatch from state files, never from memory.

## Kill discipline (campaign-tested)

- Kill criteria stated UPFRONT — numbers, not vibes.
- A kill is a **documented verdict** (LEDGER + state file `killed_<reason>`), not a
  deletion. Failed vectors are valuable.
- **Premise-adjudication rule (A7):** a kill never rests on an unverified topology
  premise — adjudicate with a dedicated read-only agent first. (The fabric verdict
  survived because we adjudicated chain-vs-fanout before building.)
- **Name the confound.** The fabric E3 "kill" ran on the default-uid path corrupted
  by BUG-013/002a — a confound, so it gets a clean re-run after the fix, not a
  burial.
- **Conditional verdicts get re-open conditions** (e.g. fabric parallel-compute
  re-opens only at >1.02 ms/layer or InfiniBand).

## The campaign's signature lessons (with war stories)

1. **Coherent wrong-output is a pointer bug, not a data problem.** "The model
   outputs Chinese because it's trained on Chinese" was wrong three times over:
   the GDN thread_local race, the uid collision (BUG-013), and the stale
   memory-plane binding (BUG-002a M1) all produced *fluent, correctly-translatable
   Chinese* — the model was reading a valid-but-wrong-epoch state, not
   hallucinating from data. **Coherent translatable wrong-language output =
   diagnostic signature of a stale pointer.** (Now a footnote in
   `plans/bug-002a-deep-fix-design.md` §3.)
2. **A monolithic multi-part agent brief stalls.** "Wire 3 stubs AND run 3
   benchmarks" produced 62 min of reading and zero output. Split into
   measurement-only + implementation agents; each was fast and clean.
3. **"Broken on all backends" ≠ upstream bug.** The GDN race broke single-GPU too.
   Bisect (11 steps, 382 commits) beat 2 loops of differential guesswork.
4. **Two independent bugs can share one symptom.** BUG-013 (uid collision) + BUG-002a
   (stale binding) both garbled; fixing one exposed the other. Always re-test the
   full matrix after a fix.
5. **Kill with evidence, then write the ADR.** The fabric verdict, the UDS transport
   kill (0.3%), the sidecar residual kill (<5% threshold) — each documented with the
   criteria that fired and the re-open conditions.

## Templates (project-wired)

- `templates/dispatch-brief.md` — the implementation-ticket skeleton (campaign paths)
- `templates/verification-brief.md` — the measurement-only skeleton (pre-specified command, hard budget, BUG-014-safe)
- `templates/state-file-schema.md` — the state-file contract (real examples)

## Relationship to the toolbox

- **Toolbox (generalized, public):** `skunkworks-toolbox/docs/orchestration-playbook.md`
  + `skills/orchestration-dispatch/` — the pattern, project-neutral, sanitized.
- **This project copy (specialized, private):** this file — the pattern bolted to
  the campaign's real artifacts. When the campaign proves a new pattern, generalize
  it into the toolbox (per the toolbox AGENTS.md hygiene contract) and record the
  extension in the LEDGER.
