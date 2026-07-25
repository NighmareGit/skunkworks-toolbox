name: perf-verification
description: Mandatory gate before a ticket can be marked done. Checks generation quality (no garbling/looping) and records tokens/s + GPU utilization + scaling notes.
---

# Performance + Correctness Verification

## Correctness
- Run a fixed set of prompts that previously exposed garbling or looping.
- Output must be clean. Any garbling, repetition, or correctness bug → FAIL.

## Performance
- Run `llama-bench` (or the fork's equivalent) under the leased GPUs.
- Record: prompt processing t/s, token generation t/s, GPU util, power, memory.
- Compare against the baseline stored in `.scratch/benchmarks/baseline.json` (create if missing).
- Explicitly state whether this change moves the scaling curve in the positive direction.

## Output
Write a report to `.scratch/benchmarks/<ticket-id>.md` and return a clear PASS / FAIL + reason.
A ticket may only be marked done on PASS (or on explicit "documented failure — approach cannot achieve goal").