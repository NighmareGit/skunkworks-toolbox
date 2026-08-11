# Research Campaign House Style

> The conventions that govern research campaigns run from this hub — structure, docs, workflows,
> model routing, measurement, and ops. Works for ANY project that runs the campaign-orchestrator
> pipeline (`scaffold-campaign.py`, workflows, dispatch-trace). New campaigns follow this;
> deviations need a reason.
>
> Pairs with [orchestration-playbook.md](orchestration-playbook.md) (the parent-agent operating
> manual) — this file is the *artifact* conventions (what a campaign's docs/workflows look like);
> the playbook is the *process* conventions (how dispatch/orchestration flows).
>
> *Generalized 2026-08-11 from the atomic-grinder campaigns
> (task-atomization / complex-task-decomposition / recursive-llm-pipeline / lower-stage-vectors).
> Project-local instances may add project-specific paths/lessons on top.*

---

## 1. Campaign structure

Every campaign lives in **two places**:

```
<project>/docs/research/<topic-slug>/     # knowledge artifacts (MISSION, tasks, reports, ledgers)
<project>/.scratch/campaigns/<id>/        # coordination layer (CAMPAIGN.json, DECISIONS.md, tasks/)
<project>/.scratch/task-state/<id>.json   # compaction-safe pipeline state
```

- `MISSION.md` — Goal · Why now · Nugget lineage (table) · Research Questions · Scope (in/out) ·
  Success Criteria (checkbox) · Pipeline (code block) · **Task Table** (`| Task | File | Depends |
  Output |` — scaffold-campaign.py auto-wire parses this) · Hardware/Pools.
- `task-0X-<slug>.md` — per pipeline stage: `## Objective` · `## Deliverables` (table: Output /
  Min bytes / Contract) · `## Success` · `## Dispatch` · `## State Persistence`.
- `reports/` — deliverables with the header block (below).
- `steal-ledger.md` (actionable, `SL-###`) + `collect-list.md` (leads, `CL-###`) — appended, never pruned.
- `map.md` — collection index, updated at campaign end.

Scaffold with the skill:

```bash
python3 ~/.grok/skills/campaign-orchestrator/scripts/scaffold-campaign.py \
    --id <slug> --mission <project>/docs/research/<slug>/MISSION.md \
    --target <project>/.scratch/campaigns --auto-wire
```

The auto-wire does **not** set `depends_on` — fix it in CAMPAIGN.json after scaffolding.

## 2. Document conventions

- **Report header block:** `> Task`, `> DISPATCH_TAG`, `> Date`, `> Searcher/Model`, `> Inputs
  consumed`.
- **Evidence grades** (repos): `benchmarked / demonstrated / implemented`; (papers) numeric
  avg-score, must-collect threshold (≥4.5).
- **Steal entries:** `### SL-### — Stage | Title` → mechanism, source, evidence grade, effort×leverage.
- **Collect entries:** `### CL-### — Title` → lead, link, why.
- **Verdict sections answer explicitly** (GO / ADOPT / REJECT + rationale), never "it depends" without a decision.
- **Citation coverage gate:** every claim traces to a source actually read; coverage % stated;
  **AMBIGUOUS flagged honestly** instead of guessing.
- Footer: `*End of <file>. Companion: <siblings>.*`

## 3. Workflow conventions (Rhai)

- `let meta = #{ name, description, when_to_use, phases }`; phases `Build/Scout/Map → Check → Report`.
- `args` required: `dispatch_tag` + `campaign_root` (+ campaign-specific roots); `pause` if missing.
- **RAILS string** (R1-R9) in every agent prompt; R6 no-derivation, R8 report-ambiguous, R9 heartbeat.
- `result_schema` / `verdict_schema` maps; parallel panels for independent work; **explicit arrays
  and loop-built jobs — never `.map()` closures** (unsupported).
- Verifier maps use **`prompt: vprompt`** (the `prompt: prompt` self-reference crashes). Explicit
  `out_name` / artifact paths per task.
- `complete()` with `dispatch_tag` + `verified_count`. **Smoke-check with `validate_only` before
  launch** — but it does NOT exercise every branch.

## 4. Agent / model routing

| Role | Model | Lane |
|------|-------|------|
| research / implement / screen / generalize | **longcat** | deep work, 256K ctx, R1-R9 rails |
| verifier / math-enforcer / orchestrator | **ds-4-flash** | cheap mechanical checks, **must be a different model** (correlated-error protection) |
| scribe / raw completion only | **laguna-xs** | NO tool-use loops, NO repo walking (measured: context-exceeded at 900K-1.8M; scribe-grade only) |

- Verifier is always a different model than the implementer — never self-verify.
- math-enforcer recomputes every aggregate with Python from raw JSON; no trust in self-report.

## 5. Measurement discipline

- **No fabricated metrics.** Every number traces to a logged run; raw JSON paths referenced. A
  failed run is a documented failure, not a number.
- Seeded + reproducible; **per-model labels on heterogeneous pools** (free-tier pools especially).
- **Server ctx guards:** silent truncation past n_ctx is real (32K server accepted 87K prompts
  with garbage) — fail-fast guards, verify n_ctx before long runs.
- **Slot / KV-cache awareness (local pools):** local llama-servers are slot-bounded and
  KV-cache-sensitive — parallel clients beyond the slot count queue, evict contexts, and corrupt
  latency metrics (measured: 6 clients on a 2-slot server). Check `/slots` + `/metrics` before
  fan-out; keep the overflow queue in the dispatcher; group same-prefix requests to reuse KV;
  default to serial for latency-critical/metric work. (2026-08-11 lesson, folded into the
  `route` tool spec.)
- **Stale-task guards:** idempotent generators reuse stale files (row-count mismatch) — delete/
  regenerate on mismatch.
- Small-N honesty: state the N and the caveat.

## 6. Ops playbook

- **Mint a dispatch tag before every workflow:** `python3 <project>/.scratch/scripts/dispatch-trace.py mint`.
- **Log to DECISIONS.md** (append-only, timestamped `## YYYY-MM-DD T+HH:MM — <event>`); **save
  state** to `.scratch/task-state/<id>.json` before compaction / phase changes; update the
  **RESEARCH.md tracker** on completion.
- **Run `wf-guard.py` before every workflow launch/relaunch**
  (`scripts/wf-guard.py --name <workflow> --pattern <workload-regex> [--exclude <regex>]`).
  Run state is NOT a liveness oracle in either direction — "active" can be a dead stale record,
  "cancelled" can still be executing. Ground truth = agent metas (`completed_at`) + live
  processes. Exit 1 (LIVE) = investigate, do not launch. After cancelling, `scripts/wf-sweep.sh
  --pattern <regex>` lists orphaned workload processes (add `--kill` to TERM them).
- **Kill + relaunch** for stuck/mis-framed workflows: find the subagent session under
  `~/.grok/sessions/.../<uuid>/summary.json` (agent_name + title confirm identity), kill by
  task_id, fix framing, relaunch. A killed run completes `0/N verified` — expected aborted outcome.
- **Parallelize everything:** don't lock on a single wait — dispatch the next phase and do
  cross-campaign work in the meantime.
- **Stale heartbeat ≠ dead:** check the agent session mtime before concluding stuck; long API
  calls legitimately silence the heartbeat for 30+ min.

## 7. Hard-won lessons (the scar list)

1. String slicing bugs silently collide outputs (e.g. `sub_string(3,1)` on "T1A-1" → "-") —
   use explicit per-task output names.
2. Small scribe-grade models cannot do tool-use loops — context-exceeded; keep them to
   summarize-only lanes.
3. Data-array field conventions: if the loop reads `r.repo` but entries carry `name:`, everything
   silently resolves to empty strings. Check the loop against the array.
4. `validate_only` skips the verify branch — variable bugs in verify maps crash at runtime.
5. Stale idempotent tasks silently corrupt runs — guard on regenerate (row-count / content check).
6. Silent prompt truncation past n_ctx returns HTTP 200 with garbage — verify n_ctx + prompt size.
7. A small-model "can't do X" verdict can be harness-guidance, not a model ceiling — steer the
   root (direct strategy preference + deterministic helper + explicit fallback) before blaming
   the model. (A coder-14B went 1/3 → 3/3 at 119K with steering.)
8. Fixed pipelines underperform adaptive orchestration: decompose on demand (router-gated), not
   as a mandatory hop (U-shaped granularity, escalation-cliff evidence).
9. Local model servers are slot-bounded: parallel fan-out beyond the slot count thrashes the KV
   cache and corrupts latency metrics — serialize local legs (one request at a time, seeds batched
   in one process) and probe `/slots` before heavy runs.
10. Run state is not a liveness oracle in either direction. A dead host freezes runs at "active"
    (stale) while its agents keep running as orphans; cancelling a workflow does not kill its
    agents' subprocesses (they run on for minutes, duplicating spend and colliding outputs).
    Before ANY launch/relaunch, read agent metas (`completed_at`) and `pgrep` the workload —
    `scripts/wf-guard.py --name <wf> --pattern <regex>`, exit 1 = hard block.
    (2026-08-11: T2 v1 stayed alive 40+ min after its host died; v2's agents ran ~8 min after
    cancellation — double FMD spend + filename collisions; wf-guard.py born from this.)

---
*Portable: pair with the campaign-orchestrator skill bundle (`scripts/scaffold-campaign.py`,
`scripts/toolchain/dispatch-trace.py`). Project-local instances may extend sections 1/6 with
project paths. Sanitized per `scripts/sanitize-check.sh`.*
