# Verification-Brief Template — Measurement-Only Tickets

> The sibling of `dispatch-brief.md`: for tickets that produce a NUMBER, a PASS/FAIL
> verdict, or a measurement — nothing to build. These are the safest dispatches in a
> campaign (they never stall: no scope to wander, a hard budget, a pre-specified
> command) and the recommended **first dispatch of a fresh session** (calibrates the
> parent's read on agent health).
>
> Anatomy difference vs implementation briefs: the **exact command is pre-specified**
> (so the number is reproducible and comparable), the budget is **hard and small**
> (< 15 calls, < 25 min), and there is a legitimate **"record blocked and return"**
> exit (a down service is not the agent's failure).

## Prompt

You are the measurement agent for **[TICKET]** — **[ONE-SENTENCE GOAL: a number or
verdict is needed; nothing to build]**. Measurement-ONLY: no code changes, no
wiring. Keep it FAST (target < [N] tool calls, < [N] min).

### Context

- Repo: `[fork]` @ `[HEAD]` (branch `[branch]`)
- Build: `[build-dir]` — verify fresh with `[probe command]`; rebuild (build lock)
  only if stale
- Devices/services: `[which GPU/device, which remote service + port, env
  requirements]` — verify up before starting
- Model/input: `[path]`
- **Acquire the [device] lease first** (lease skill). Release when done.

### The run(s)

- **[Run 1]:** `[EXACT command — full flags, ports, model path, so the number is
  reproducible and comparable to prior baselines]`
- Measure `[metric]` + run the coherence gate: `[probe — e.g. curl a fixed prompt at
  temperature 0, judge coherent vs garbled]`
- **[Run 2 variant]:** `[same with the one changed flag]` → record `[metric]` +
  coherence

### Deliverables

- Report `[path]`: both runs (config, numbers, output, coherence verdict), the
  EXACT commands used, and a note on what baseline this compares to
- State file `[path]` status=complete
- If `[service/device]` is down: try `[recovery step]`, else record "blocked" in
  the state file and return — a down service is not your failure

### Do NOT

- Do NOT modify any code (measurement only)
- Do NOT attempt `[out-of-scope items]` (separate tickets)
- Do NOT fight over the device (lease first, release after)
- Do NOT run `[forbidden variant — e.g. a transport that crashes this setup]`

## Orchestration notes

- **Budget:** < 15 calls, < 25 min is the norm. A measurement ticket that takes
  longer is either blocked (check the service) or mis-scoped (it became an
  investigation — split it).
- **Comparability:** the pre-specified command is what makes the number mean
  something. Never let a measurement agent improvise the harness; state the
  baseline it must match (same build, same flags, same hardware).
- **Coherence gate:** always require output-quality judgment (coherent/garbled),
  not just timing — a fast number on garbage output is a trap.
- **Verdict, not dump:** give the threshold or the comparison ("vs 80.89 baseline")
  so the agent returns a verdict, not a number with no frame.
