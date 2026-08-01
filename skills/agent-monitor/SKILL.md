---
name: agent-monitor
description: >
  Watchdog + heartbeat monitoring for multi-agent campaigns. Watches per-ticket
  state files (heartbeat, status, tool_history), classifies anomalies
  (STUCK / DEAD / LOOPING / BAD OUTPUT / RESOURCE), and alerts the parent —
  read-only, never kills. Includes the heartbeat protocol agents must follow,
  the liveness-check rule (staleness alone ≠ death), and the health-check
  status-line emitter. Use when running any multi-agent workflow that needs to
  detect dead, stuck, looping, or resource-blocked agents. Trigger phrases:
  "watch the agents", "monitor the campaign", "heartbeat", "is an agent stuck",
  "agent monitor", "dead or looping". Slash command: /agent-monitor.
---

# Agent Monitor — Watchdog + Heartbeat for Multi-Agent Work

Detect when an agent is dead, stuck, looping, or blocked — and tell the parent,
**without ever killing anything yourself**. The monitor is the campaign's immune
system: it watches, classifies, and alerts; the parent decides and acts.

## The heartbeat protocol (what agents must do)

Every ticket/work-item has a state file (JSON) that agents update. The monitor
reads these files — it does NOT trust process liveness alone.

```json
{
  "ticket": "T2b",
  "stage": "implement",
  "status": "in_progress",
  "heartbeat": "2026-08-01T03:15:24+02:00",
  "next_action": "finish the extraction; then write state+heartbeat",
  "tool_history": ["cmake --build ...", "git diff --stat", "..."],
  "artifacts": ["worktrees/increment1-T2b/"]
}
```

**Mandatory agent rules:**
- Update `heartbeat` **before and after every tool-heavy stage** (build, GPU run, ssh, long fetch).
- `heartbeat` MUST be the actual runtime timestamp at write time — `datetime.now(timezone.utc).isoformat()` (or local with offset). **NEVER a placeholder/epoch** (`2026-08-01T00:00:00Z`, `1970-01-01T00:00:00Z`, a fixed string). A placeholder heartbeat is a protocol violation: the monitor computes a huge stale age and raises a FALSE STALE alarm even though the agent is alive (observed 2026-08-01: ACADEMIC-A1/A2 wrote `00:00:00Z` and triggered alarms while actively working).
- Append to `tool_history` (tail ~10) so the loop detector has data.
- Flip `status` to `done`/`failed` on completion — **this is what prevents false alarms**.

**Monitor-side fallback (defense in depth):** the watchdog treats the state file's **own mtime** as a liveness signal — a file modified within the last 15 min means the agent is alive regardless of the heartbeat field's content. This absorbs placeholder-timestamp bugs without losing the staleness alarm for genuinely dead agents.

## Anomaly classification (the taxonomy)

| Signal | Class | Parent action |
|--------|-------|---------------|
| heartbeat stale + process alive | **STUCK** (hung on ssh/docker/pull) | SIGTERM → diagnose |
| process gone + status=in_progress | **DEAD** | respawn from state file |
| heartbeat fresh + state stale + repeated identical commands | **LOOPING** | kill → diagnose → re-ticket |
| harness/checker flags garbage output | **BAD OUTPUT** (silent corruption) | kill → diagnose |
| disk < threshold / GPU contention / container died | **RESOURCE** | clean / re-lease / restart |

## The critical rule: staleness alone ≠ death

A stale heartbeat is **not** proof an agent died. Two legitimate causes:
1. **Long build/GPU run** — a 45-min CUDA build with a 15-min stale heartbeat is normal.
2. **Agent finished but never flipped status** — the #1 false-alarm source (T0, T2b).

**The liveness check:** before alerting on a stale heartbeat, look for *artifact
advancement* — any file under the ticket's worktree modified in the last N
minutes. If artifacts are advancing, the agent is alive; update your tolerance
and keep watching. Only alert when BOTH heartbeat is stale AND no artifact moved.

**Build-phase tolerance:** use a longer stale window during build phases
(~45 min) than during pure research/read phases (~15 min).

## The watchdog loop (silent unless FAILED)

For a long-running monitor (cron or background), emit **nothing on success** —
only `FAILED: <details>` lines on anomalies. This keeps the parent's signal
channel clean (monitor-compatible: every stdout line is an event).

```bash
while true; do
  # 1. system checks first (disk, GPU, container)
  # 2. for each state file with status=in_progress:
  #      - compute heartbeat age (python ISO-8601 parse — robust to tz)
  #      - if age > tolerance AND no artifact advanced recently:
  #          emit "FAILED: <ticket> heartbeat stale <age>s, no artifact activity"
  # 3. sleep interval
done
```

Key properties:
- **Skips** `done`/`pending` tickets — only `in_progress` can be anomalous.
- **Artifact liveness** = newest file under the ticket worktree.
- **Disk check** exits hard on < threshold (a full disk kills everything).
- **Python heartbeat parsing** (ISO-8601 with tz) beats `date -d` portability issues.

## Health-check (one status line per ticket)

For a human/agent-facing snapshot, emit per-ticket status lines:

```
system: disk=54% (120G free) | leases=1 | locks: build | container=up
T2b: running, heartbeat 30s ago, state=implement, artifacts advancing ✓
T0: done
T2c: STUCK (heartbeat 20min stale, no artifact movement)
```

Exit 0 = all healthy; exit 1 = at least one anomaly (usable in CI/gates).

## Authority (non-negotiable)

**The watchdog is read-only + ALERT. It never kills agents, deletes state, or
modifies files.** A false positive on a long CUDA build is worse than the loop
it catches — so the monitor *reports*, and the parent *decides*. Exceptions:
hard resource failures (disk full) may exit loudly, but even then the parent
acts.

## Loop-detection heuristic

Identical command strings re-executed >N times with no state change = loop.
Compare the ticket's `tool_history` tail: if the last ~5 entries are the same
command (or a cycle of the same 2–3) AND `stage` never changed AND heartbeat is
fresh → LOOPING. Fresh heartbeat is what distinguishes a loop from a dead agent
(a looper is busy; a dead agent isn't).

## Wiring into a campaign

1. **Agents** follow the heartbeat protocol (state file per ticket).
2. **Monitor** runs the watchdog loop (background or cron, silent-unless-FAILED).
3. **Parent** receives `FAILED:` lines, reads the classification, decides
   (kill/respawn/re-ticket/re-lease), and updates the state file.
4. **On restart**, the parent reads state files to rebuild campaign state —
   the monitor's data IS the resumability layer.

## Parameters (issuer-specified)

| Param | Default | Meaning |
|-------|---------|---------|
| state dir | project `.scratch/task-state/<campaign>/` | where ticket JSON lives |
| worktree root | project `worktrees/` | where artifact liveness is checked |
| stale tolerance | 15 min (45 min build-phase) | heartbeat age before suspicion |
| disk threshold | 40 GB free | hard RESOURCE alert |
| loop threshold | 5 identical tail commands | LOOPING trigger |
| sleep interval | 300 s | monitor poll rate |

## Worked example (the real one)

The Increment-1 RPC campaign ran this exactly:
- `task-state.py` — atomic heartbeat/status writes (mkdir lock + .tmp + rename).
- `watchdog.sh` — the loop above; caught the T2b "stale heartbeat" storm, which
  turned out to be an agent that *finished but never flipped status* — the
  liveness check (worktree file advancing) is what kept it from being a false
  kill.
- `health-check.sh` — per-ticket status lines for the parent.

Same pattern applies to ANY multi-agent campaign: same state schema, same
taxonomy, same authority rule, different ticket names.
