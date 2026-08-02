# AGENTS.bug-fix.md — Operating Manual for Bug-Hunt Agents (universal)

You are the debugging agent for a BUG ticket: reproduce, bisect, root-cause with evidence,
then fix minimally. The hardest-earned lesson across projects: **fluent wrong output = stale
pointer / wrong binding, not data corruption** — diagnose the binding before blaming data.

## Sequence (in order)

1. **Repro-first** — reproduce the bug exactly as recorded (bug ledger entry + ticket repro).
   Record the failure precisely (actual vs expected output, the crash, the log lines).
   Do NOT start fixing until the repro is captured — the repro is the falsify-first input.
2. **Read-first** — the bug ledger entry (all required fields), the prior diagnosis trail
   (bisect reports, prior fix attempts — bugs are often multi-component), the suspect code (file:line).
3. **State-first** — heartbeat the state file; NEVER replace it.
4. **Diagnose with evidence** — the diagnosis loop is YOUR judgment; the rail is:
   - Hypothesize the root cause (with file:line).
   - Falsify/verify it with a measurement (bisect, A/B, instrumented run).
   - State the root cause with evidence BEFORE any edit.
   - No attributable root cause within one cycle → report + HOLD, never a blind patch.
5. **Fix minimally** — the smallest correct change (the discipline: fixes are +1/-N lines,
   never rewrites). Blast radius = the bug. No re-architecting.
6. **Verify the fix** — the repro now passes; the gate (correctness, no regression) holds;
   artifact-verify the build (nm/strings/disassembly; object mtime > source).
7. **Close** — report FIRST, ledger entry (project convention), state → complete / verified-fixed,
   bug ledger status update, lessons field.

## Diagnostic signatures (universal, from hard-won war stories)

- **Deterministic garbage + valid logits** → corruption between compute and readback (stale
  buffer/offset after eviction or restore) — check the readback/binding path, not the kernel.
- **Fluent wrong-language output** → wrong-epoch/right-state read (stale plane binding), not training data.
- **Garbage on ALL backends** ≠ upstream bug — check shared backend code (a thread_local race
  example: a shared staging buffer across async paths).
- **Non-deterministic garbage** → two independent causes can share a symptom; fix one, re-test.
- **Works small, fails large** → scratch/thread-count/size-dependent handling (per-thread padding).

## Skills to load

orchestration-dispatch · diagnosing-bugs · bug-hunt · bisect-regression (if bisecting) · worktree-guard · this class file.
