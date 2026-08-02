# Task-State File Schema — The Agent's Contract with the Watchdog

Every dispatched agent writes `.scratch/task-state/<TICKET>.json` FIRST (before any
code), heartbeats on every major step, and sets status when done. The watchdog and
the parent read these files; an agent that never writes one is invisible and suspect.

## Schema

```json
{
  "ticket": "TICKET-NAME",
  "stage": "pending | read | design | implement | redteam | verify | review | mark",
  "status": "pending | in_progress | verify_pending | complete | failed | blocked | killed_<reason>",
  "heartbeat": "ISO-8601 with timezone (e.g. 2026-08-02T09:00:00+02:00)",
  "next_action": "what the next agent/parent should do",
  "artifacts": {
    "branch": "fix/ticket-name",
    "commit": "abc1234",
    "report": ".scratch/benchmarks/ticket-name.md",
    "worktree": "worktrees/ticket-name"
  },
  "verification": {
    "build": "PASS/FAIL — detail",
    "run1": "result",
    "gpu_ab": "PENDING/blocked-on"
  },
  "notes": "ground truth, design decisions, deviations from the brief, what to watch",
  "tool_history": ["tool1: purpose", "tool2: purpose"]  // tail only
}
```

## Rules

1. **Write it first.** Before any read/design/code, the agent writes the file with
   `status: in_progress`. A dispatch without a state file is a mis-dispatch.
2. **Heartbeat every major step.** The watchdog flags tickets whose heartbeat is
   stale AND whose state-file mtime is old AND whose worktree has no fresh
   artifacts. One of the three being fresh = alive.
3. **Status is a verdict, not a mood.** `complete` only when deliverables exist.
   `failed` includes the blocker + the attempt. `killed_<reason>` documents a
   kill-criteria firing (e.g. `killed_coherence_gate`).
4. **Grace list for long silent phases.** Long GPU benchmarks get a grace entry in
   `grace.conf` (`TICKET grace_seconds`) so the watchdog doesn't false-flag.
   "Stale state file" ≠ "dead agent" — verify liveness before acting.
5. **The file is the handoff.** The next agent or a new session reads it to resume.
   A well-written state file makes the agent's work durable even if the session
   dies (this mission proved it 3+ times).

## Why this matters (from the source mission)

- A fix committed by a cancelled agent was resumed, not redone: its state file +
  worktree made verification trivial (verify, don't re-implement).
- An agent that skipped its state file looked "dead" to the watchdog for hours
  while actually working — cost a false takeover dispatch.
- The 51-file task-state inventory (`.scratch/task-state/increment1/`) is the
  mission's ground truth; snapshots (`precompaction-*.json`) make session restarts
  seamless.
