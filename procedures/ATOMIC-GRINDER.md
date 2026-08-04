# ATOMIC-GRINDER — the dissolve→chew→package pipeline protocol

> **Reusable operating procedure.** The atoms-grinder machine (user proposal 2026-08-04,
> LEDGER #189-195 + CONCEPT-atoms-grinder.md REVISIONS 1-5): the end-to-end pipeline that
> dissolves complex tasks into atomic subtasks (jupiter), chews them with a local GPU worker
> pool at zero marginal cost, assembles mechanically, and packages the result for review.
> This is the OPERATING manual — how the machine runs, its gates, its doctrine, and its
> current state. Run it by this file, not from memory.

---

## 1. What it is (one paragraph)

The campaign's **free-fleet throughput machine**: the dispatcher emits a ticketed task →
jupiter (the 7.5B reasoning-distill, LAN lane) dissolves it into atomic subtasks → a
co-resident GPU worker pool (2B/4B/9B-MTP on the 7900) chews the atoms at KV-sweet-spot
speed → a mechanical compositor assembles + scores → one finished package per task
(worktree + LEDGER + closed ticket + deliverable-gate PASS) lands in a pickup queue for
review. **$0 marginal API cost** (the 10.5M-token paid-frontier burn is the baseline it
re-routes), **airgap-ready** (no vendor dependency once Hydra lands), and the **measured
bounded gap** is the price (jupiter 10/10, 4B 9/10 with the corrected harness).

## 2. The pipeline map

```
dispatcher ──ticket/workflow──▶ atomizer ──atoms──▶ grinder ──finished packages──▶ pickup queue
  (engine)        (jupiter T3)      (jupiter helm     (LEDGER + worktree +       (review rail /
   rhai-builder,   seam-finder,      + 2B/4B/9B-MTP     closed ticket + gate       MPR gate,
   MPR gate,       dissolve)         worker pool,       verdict)                   orchestrator)
   4 rails)                          chew)
                                        ▲
                                        └── compositor (mechanical assembly + echo-rejected scoring)
```

## 3. The seats

| Stage | Seat | Notes |
|-------|------|-------|
| Decomposer (T3 seam-finder) | jupiter (gemma-4-E4B, LAN) | **Corrected harness mandatory**: max_tokens ≥2000 (it reasons ~240+ tokens/task; truncation empties content — #183/#185); ≤180-char atoms (the 2B CPU limit, now the speed dial); never-force-a-bad-atom (escalators refuse atomization — P3: 3/3 held) |
| Grinder helm | jupiter fresh-session sibling | File-based dispatch (claim → emit → signal → runner fires — B6 correction, no agent-spawn) |
| Workers | 2B / 4B / 9B-MTP co-resident on the 7900 (~12.3 GiB) | Pool composition = G2 data (the fastest worker(s) meeting the correctness bar); 9B-MTP is the star candidate (+45.9% E-1 MTP boost); multi-slot (per-slot −19-20% at 4 slots, measured) |
| Compositor | mechanical (pilot compositor + grader) | Scoring MUST reject echo-pass (regurgitation = FAIL — the P3 confound); pre-sealed per-task criteria |
| Packaging | worktree-guard + ledger.py + claim protocol + **deliverable-gate.sh** (penholder v2) | One task → one package; gate PASS required (persist + ≥3 file:line citations) |
| Pickup | results queue → R1/MPR review rail | **Review stays a gate, never an auto-merge** (signal-not-decide + MPR lesson) |

## 4. The operating loop (6 stages)

1. **Intake** — the dispatcher emits a machine-ready ticket (4 rails: seam/discriminator/kill/commands).
2. **Dissolve** — jupiter (corrected harness) produces the atom set: `{task_id, atoms[{id, instruction ≤180 chars, expected_outcome_check}]}`; escalators → REFUSE, never force.
3. **Chew** — the grinder claims the atom run, emits per-atom worker tickets (claim protocol), the runner fires the pool (co-resident llama-servers), atoms fed at KV sweet spot; results collected.
4. **Compose** — the compositor assembles atom outputs per task, scores vs the pre-sealed expected-outcome checks, with echo-rejection.
5. **Package** — one finished package: worktree commit + LEDGER entry + closed ticket + **deliverable-gate PASS** (the penholder).
6. **Pickup** — the package lands in the results queue; an orchestrator/another machine reviews (gate-on-exception) or final-processes.

## 5. The gates (the build chain)

| Gate | What it decides | State (2026-08-05) |
|------|-----------------|---------------------|
| **G1** — atomizer P3 | atoms atomic-enough? doctrine held? | ✅ **PASS** (#195): 34/34 chewable by 2B+4B, escalators refused 3/3; end-to-end lift confounded (echo-pass) → scoring fix |
| **G2** — worker battery | pool composition (speed × correctness, MTP on/off, multi-slot) | 🏃 **IN FLIGHT** (019fcc4d, on the 7900) |
| **G3** — grinder v0 skeleton | one task live loop end-to-end | ⏳ pending |
| **G4** — end-to-end KPI | atoms/sec beats **direct-jupiter** (~100 t/s serial) — the parallelism must earn its complexity | ⏳ pending |

**Kill criteria:** (a) G1 no lift → grinder is theater (NOT the case — G1 passed); (b) G2 shows the 9B adds nothing over a reliable 4B AND 4B is unreliable → direct-jupiter is cheaper; (c) G4 fails to beat direct-jupiter → the machinery is shelved (components stay reusable); (d) packaging contract not mechanically passable → untrustworthy queue.

## 6. The KPI and the economics

- **KPI = atoms/sec end-to-end** = min(dissolve rate, chew rate, compose rate, package rate). The pipeline must OVERLAP (dissolve N+1 while chewing N, compose N-1) — never serialize (jupiter's ~10-30s/task dissolve would become the choke).
- **Cost**: $0 marginal (jupiter + local workers + mechanical tools). The measured burn baseline: **10,499,600 tokens, ~100% paid frontier** (agent-time-ledger) — the volume the grinder re-routes.
- **Endgame**: grinder (bulk) + Hydra (frontier-class compute, local) + machinery (local) = the airgap future; the paid API becomes the optional exception rail.

## 7. Doctrine (the rails that keep it honest)

1. **Review stays a gate** — the machine automates dissolve→chew→compose→package; the pickup queue's review is never an auto-merge.
2. **Never force a bad atom** — escalators refuse atomization (measured: jupiter 3/3).
3. **Echo-pass = FAIL** — scoring rejects prompt regurgitation (the P3 confound fix).
4. **Evidence rails** — every package passes the deliverable gate (persist + ≥3 file:line citations); the spawn path must own the record (the #187 finding — wiring carded).
5. **Measured, not assumed** — worker floors are non-monotonic in model size (#135); the pool comes from G2 data, not preference.
6. **Atom length is the speed dial** — short atoms keep every worker pinned in its fast-decode zone.

## 8. How a fresh session fires it

1. Verify jupiter (192.168.8.21:8080) + the 7900 are up; verify the sealed corpus (`.scratch/archives/tmp-2026-08-04/atomizer-pilot/calibration/labels.sha256` — 8ffdbd4a…; symlinked to /tmp after a reboot).
2. Check the gate state: G2 report → G3 → G4 (the chain is sequential — each gate's verdict feeds the next).
3. Dispatch per the dispatcher-engine (4-rail tickets) + the gpu-lease + worktree-guard protocols.
4. Close each ticket with the perf-verification contract + the deliverable gate; bank the verdict in the LEDGER.

## 9. Lessons encoded

1. **The harness is the model's other half** — jupiter: 8/10 at a 900-token cap → 10/10 at 2000 (#183/#185). Never measure a reasoning-distill with a truncating budget.
2. **Echo-pass is a real scoring confound** — keyword scoring rewarded the 2B regurgitating prompts in P3; G2+ scoring rejects it.
3. **The 2B CPU can't hold a real atom prompt** (>180 chars degrades) — GPU co-residency + short atoms is the design, not an accident.
4. **Cost-free is the enabling property; throughput is the edge; the bounded gap is the price** — the honest framing that keeps the machine from becoming theater.
5. **Everything lives in the archives** — the sealed corpus + harnesses survive reboots via the sundown protocol; never rely on /tmp.
