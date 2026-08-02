# Dispatch Brief Template — Copy-Paste Skeleton

> Fill the bracketed fields. Every section is load-bearing; do not delete sections to
> save tokens — a brief missing its Do-NOT list or kill criteria is how agents fail.

## Prompt

You are the **[ROLE]** agent for **[TICKET-NAME]** — **[ONE-SENTENCE GOAL]**.
[CONTEXT: what this unlocks / why it matters / what prior work it builds on.]

### Read first (before any action)

1. `[path/to/spec.md]` — [what it defines] (PRIMARY SPEC)
2. `[path/to/report.md]` — [prior findings to reuse, do not re-derive]
3. `[path/to/design.md]` — [the mechanism/plan]
4. `[path/to/state.json]` — [ticket state if resuming]

### Ground truth (verified by the parent — trust, re-check only if it smells)

- Repo/HEAD: `[fork]` @ `[commit]` (branch `[branch]`)
- Build: `[build-dir]` (fresh/stale — verify with `[probe command]`)
- Hardware/services: `[which devices, which remote services/endpoints, ports, env requirements]`
- Model: `[path]`
- Existing work: `[branch/commit/worktree with prior partial work]`

### Required steps (IN ORDER — step 1 is always state + isolation)

1. **State file FIRST:** write `.scratch/task-state/<TICKET>.json` (schema:
   ticket, stage, status=in_progress, heartbeat ISO, next_action, artifacts,
   tool_history). Update heartbeat on every major step.
2. **Worktree isolation** (worktree-guard): create `worktrees/<ticket>/` off
   `[base]`, branch `[branch-name]`. Never touch the main checkout. Confirm with
   `git worktree list`.
3. [Step 3+ — the actual work, numbered, with precise seams: file:line]
4. [Verification steps with the exact commands]
5. **Commit + report:** conventional message (`[type]([scope]): [subject]`),
   report to `[path]`, state file → status=complete/verify_pending, push to
   `[remotes]`.

### The change (exactly this — blast radius)

- File: `[path]`, function `[name]` (line ~NNN)
- Do: `[precise description]`
- Do NOT: [re-architect X / touch Y / change Z — the current code is correct for
  reasons described in [ref]]

### Do NOT

- Do NOT modify anything beyond [scoped files]
- Do NOT [run UDP variants / use the GPU without a lease / run concurrent builds /
  attempt out-of-scope work]
- Do NOT spend more than ~[N] tool calls grinding one failure — if a step blocks
  you twice, write the blocker + your attempt to the state file and return a
  clear failure report instead of looping.

### Kill criteria / thresholds

| Criterion | Threshold | Source |
|-----------|-----------|--------|
| [metric] | [GO number] | [ref] |
| [metric] | [KILL number] | [ref] |


> **Follow-ups:** the report MUST end with a "Follow-ups" section listing every
> out-of-scope next step (one line each); the state file carries them in
> `follow_ups[]`. A report that says "follow-up needed" without a follow_ups[]
> entry is incomplete - the parent extracts them at ticket close.

### Deliverables (report-first + self-verify)

> Rule: for study/research tickets, the report file is the FIRST deliverable —
> write it BEFORE the LEDGER/state entries (which reference it), and verify it on
> disk (`ls`/`grep`) before returning. A completion summary with no file on disk
> is a claim, not a deliverable.

- Commit: `[branch]` @ `[expected message]`, pushed to `[remotes]`
- Report: `[path]` — [what it must contain]
- State file: `[path]` — status=complete with verdict
- [LEDGER/BUGS.md/AGENTS.md update if applicable]
- Crisp summary: "the fix/verdict is X because Y" — one paragraph, not a dump

## Orchestration notes for the parent

- **Budgets are stall signals, not caps:** research 15-30 calls; implementation
  30-45; measurement 15-25. An overrun with deliverables + evidence is fine; an
  overrun with zero writes / repeated identical calls = loop. Trust the harness
  count, not the agent's self-report.
  A stalled agent shows ~0 writes and tool-call count climbing slowly — check
  `ps` for zombie builds and `.scratch/locks/` for stale locks before killing.
- **First-dispatch vs resume:** if a prior dispatch was cancelled, check for its
  uncommitted/committed work FIRST (worktree, branch, state file). Resume with
  `resume_from` if the transcript is valuable; re-dispatch fresh with this
  template if it was a failure loop.
- **One ticket = one agent.** If the brief has "and then run the benchmark," split
  it. Measure-only tickets are fast and rarely stall.
