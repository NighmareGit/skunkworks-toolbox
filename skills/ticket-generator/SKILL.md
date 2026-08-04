---
name: ticket-generator
description: >
  The governor's mechanized chore: turn a need / signal / gap into a machine-ready,
  MPR-validated, claimed dispatcher ticket in one command. Wraps the producer chain
  (source JSON → rhai-builder --manifest → validate-ticket MPR → ticket-claim) so the
  dispatcher's queue fills without hand-tokening the mechanics. Trigger phrases:
  "create a ticket", "ticket this", "generate a ticket for", "emit a ticket",
  "/ticket-generator".
metadata:
  short-description: "One-command need → machine-ready dispatcher ticket (the South Star chore)"
---

# Ticket Generator — the need → ticket chore

The dispatcher's job is to hold machine-ready tickets; the governor's job is to fill the
queue from needs. This chore mechanizes the filling: **need → source JSON → rhai-builder →
MPR validate → claim → queued ticket**, one command, no hand-written ceremony.

## When to Use

- A signal/gap/need lands (from the reflection machine, a review, a sweep, a user ask) and
  it must become a dispatchable ticket.
- You just wrote a pipeline stage by hand and realized it should have been a ticket (the
  2026-08-04 lesson: the merger pipeline's tickets were hand-assembled — this chore exists
  so that never needs to happen again).

## The Chain (what the chore wraps)

```
need (title + class + deliverable + rails) 
   → render source JSON  (the 4 rails: seam / discriminator / kill / commands)
   → rhai-builder.py --manifest <source.json> --dispatches-dir prepped
        (emits <ticket>.args.json + <ticket>.phase2-ticket.json + the manifest)
   → validate-ticket.py <phase2-ticket.json>   (the MPR gate — FAIL = fix the source, re-emit)
   → ticket-claim.sh claim <ticket> --owner <owner>   (the queue reservation)
   → report: the ticket path + the dispatch command
```

## The Argument Contract (the source JSON's required fields)

| Field | What it is | Required |
|-------|-----------|----------|
| `ticket` | the ID (UPPER-KEBAB) | yes |
| `class` | research / steal-impl / CPU-mechanical / CPU-analysis / GPU-* | yes |
| `state_path` | the increment2 state file (for the kernel/watchdog) | yes |
| `resource` | none / build-lock / source-lock / gpu-* | yes |
| `feedstock` | the inputs (file paths + one-line what each provides) | yes |
| `deliverable` | the output file the gate checks | yes |
| `evidence_only` | true for research/read-only tickets | yes |
| `task` | `{method, analyze, deliverables}` — the work contract | yes |
| `seams` | the artifacts the discriminator checks | yes |
| `discriminator` | the falsifiable PASS criterion | yes |
| `kill` | the kill criterion (never silent) | yes |
| `commands` | `{seat, model, method_steps, report_path}` | yes |

## The One Command

```bash
python3 .scratch/scripts/ticket-generator.py \
  --need <need.json> --dispatches-dir .scratch/dispatches/prepped \
  --owner parent [--claim] [--no-validate]
```

`need.json` is the source JSON minus the generated fields (schema, template, budget —
rhai-builder fills those). The chore renders, emits, MPR-validates (fail-loud), and (with
`--claim`) reserves the ticket. Output: the ticket path + the dispatch command to fire it.

## The Rails Discipline (what the chore enforces, not just does)

1. **No ticket without the 4 rails** — a source JSON missing seam/discriminator/kill/commands
   fails the completeness assertion before emission.
2. **No ticket that fails MPR** — validate-ticket is the gate; a FAIL is a source problem,
   never a force-through.
3. **No silent queue** — every emitted ticket is recorded (the bridge) and claimed (the
   claim protocol); the queue's state is visible.
4. **Prerequisites are named** — if a ticket fires only after another lands, the feedstock/
   state carries the dependency; the queue holds it until the gate opens.
5. **The #187 discipline** — a generated ticket is a prediction; its verdict comes from the
   run, never from the generation.

## References

- The producer: `.scratch/scripts/rhai-builder.py`
- The MPR gate: `.scratch/scripts/validate-ticket.py`
- The claim protocol: `.scratch/scripts/ticket-claim.sh`
- The machinery skill: `dispatcher-engine` (the generalized engine this chore drives)
- The specialized instance: `south-star-collect.py` / `south-star-reflect.sh` (the reflection
  machine — this chore generalizes its emit step to any need)
