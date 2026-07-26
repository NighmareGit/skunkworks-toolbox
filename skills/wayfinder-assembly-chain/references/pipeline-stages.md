# Pipeline Stages Reference

## 1. Wayfinder
Produces the current set of coarse slices / attack vectors.
Output: updated plan file under `.scratch/plans/` + living CONTEXT.md.

Must answer:
- What is the single primary metric?
- What is the strongest current baseline?
- Which vectors are still alive, which are killed, which are deferred?
- What novel vector is introduced this loop?

## 2. Parallel Research Wave
One research agent per live coarse slice.
Each agent writes a focused report under `.scratch/research/`.
Research is read-only and may run fully in parallel.

## 3. Grill-with-docs
Per-slice deep analysis that consumes the research report and the relevant source/docs.
Produces concrete design decisions or disqualifies the vector early.

## 4. to-PRD → Tickets
Convert surviving vectors into tickets that are:
- Independently measurable
- Scoped to one primary outcome
- Explicit about success / kill criteria

## 5. Isolated Execution
One branch + one worktree per ticket.
No shared mutable source without the source lock.

## 6. TDD → Prototype → Verification
- Correctness first
- Then performance / scaling measurement
- Must pass the project verification gate before review

## 7. Code Review + Re-verify
On green path only. Re-run the verification gate after review feedback is applied.

## 8. Failure Path
Document in `.scratch/adrs/`, commit on the feature branch, notify parent.
Do not silently abandon.

## 9. Parent Re-evaluation
- Incorporate measurements
- Kill / promote / defer
- Regenerate Wayfinder (new loop) or declare campaign complete
