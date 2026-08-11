---
name: fmd-dispatcher-operator
description: >
  Operate the free-model-dispatcher (FMD): a dispatcher engine that curates and
  ranks a pool of free LLM endpoints, breaks missions into atoms, dispatches them
  in parallel via Rhai workflows (agent() with per-call model:), and records every
  charge in a SQLite usage ledger that acts as load-balancer, verifier, fallback,
  and telemetry source. Use when: running a mission/wave on the free pool,
  planning/settling atoms, checking pool health, rotating keys, minting a fresh
  machine, adding a provider, gating mechanical-worker edits, or answering "what
  is the state of the dispatcher". Trigger phrases: "free-model-dispatcher",
  "dispatcher", "free pool", "pool_db", "run a wave", "plan atoms", "settle the
  wave", "mint the dispatcher", "fmd".
---

# free-model-dispatcher — Operator Skill

The dispatcher lives at `~/projects/free-model-dispatcher`. **Read
`~/projects/free-model-dispatcher/agents.md` first** — it is the canonical
orientation (quick-reference table, K1–K5 gates, session startup). This skill is
the loadable pointer + the 60-second operating loop.

## The four stable surfaces (call these; nothing else)

| Surface | Command | When |
|---|---|---|
| **Pool health** | `python3 src/pool_db.py status` / `select <task> <n> [--min-tier X] [--min-probe-ttl N] [--json]` | session start, before planning |
| **Plan** | `python3 src/orchestrator.py plan --stage <task> --atoms <file> --wave <id> --gear <gear> [--allow <slugs>] [--min-probe-ttl N] [--wave-ttl S]` | turn atoms into assignments (preflights judge health + tier feasibility BEFORE quota; exit 2 unknown gear, exit 3 gear infeasible) |
| **Settle** | `python3 src/orchestrator.py settle --wave <id> --results <file> [--paid-events <file>]` | charge the ledger + release reservations after a wave |
| **Workflows** | `free-pool-wave` (one stage) / `mission-pipeline` (mission end-to-end) | actual dispatch (deployed to `~/.grok/workflows/`, kept in sync with repo `workflows/`) |

Everything else (keys vault, mint, probes, gears, budget) is a subcommand of
`pool_db.py` or a module in `src/` — see `agents.md` for the full table.

## The 60-second operating loop

1. **`status` + `select` first** — know the pool before touching anything. Only
   models probed OK within `PROBE_TTL_S` (7d) are dispatchable by default.
2. **Check the dispatchable universe**: `agent(model:)` slugs are the
   config.toml `[model.*]` blocks present at session start — a model can rank in
   the ledger but NOT be dispatchable this session (a real failure mode; see
   ledger finding D13). Gate `plan --allow` on slugs you can actually fire.
3. **Plan → wave → settle** in one breath. The ledger charges only on settle.
4. **Honesty rules** (K1–K5): no silent paid (model: is mandatory per
   assignment); the verifier is a different model family than every worker
   (K3); one transaction per event (K4); sensitive missions never ship to the
   free pool (K5 — `src/k5gate.py` scans file contents, not just paths/goals).
5. **Mechanical-worker lane**: free low-B models + local model are PROPOSERS —
   their self-reports are never trusted. `src/fmd_verify.py snapshot|run|restore`
   is the only acceptance (scope/compile/suite/check vs REAL state). Probes live
   in `probes/`, manifests in `.scratch/lane/`.
6. **Gears**: presets live in `pool/gears.json` (eco/balanced/speed/quality/
   overnight) — resolve via `plan --gear`, never re-encode the table. Budgets
   persist in `mission_budgets`; `settle --paid-events` accrues judge/verifier
   cost with fail-closed over-cap refusal.

## Current state (2026-08-10)

- **Poolside wired 2026-08-10**: provider + 2 paid models added (`poolside-laguna-s-21`,
  `poolside-laguna-xs-21`; vault key `vault-poolside-1`; cost_tier mid; code-class;
  selectable for code tasks). Paid API — K2 "no silent paid" applies; they rank below
  the free fleet. Registry anchors + seed.json + HOST_TO_PROVIDER updated; mint WIRE 66/66.
- **Local model**: `local-laguna-xs` (Laguna-XS-2.1-APEX-dynamic 33.4B Q3_K_M,
  llama-server :8080, ~88 t/s, reasoning-class — needs max_tokens headroom).
  Renamed from `local-gemma-4-e4b` 2026-08-10 (config + registry + ledger
  migrated). The new slug joins the dispatch allowlist at the NEXT session.
- **Test matrix**: 466/466 across 13 suites (a0 · pool_db · layers · keyvault ·
  telemetry · fmd_verify · contracts · contracts_rhai_sync · gears · mint ·
  v3b · v7a · v5a).
- **Mint DoD**: SEALED (smoke wave `smoke-dod-2026-08-10`, evidence in
  `docs/dod-smoke-wave-2026-08-10/`). `python3 src/mint.py check --config ~/.grok/config.toml`
  → WIRE MATCH 64/64, vault provisioned.
- **Build status**: V1 contracts (+drift-guard) · V3 gears (+budget) · V4 mint
  (+DoD) · V5 trust (k5gate + vault keys) · V6 ledger honesty · V7-A scale
  (select caching + reservation visibility + wave-ttl guard) · V9 lane probes
  — all built. Deferred items D1–D16 on the ledger.
- **Daily scheduler**: discovery + probe pass runs daily (renew ~7d).

## The four stable surfaces the hub calls

`agents.md` startup · `orchestrator.py plan|settle` · `free-pool-wave` /
`mission-pipeline` workflows · the daily scheduler. A future `fmd` facade would
collapse these to one command (concept/04).

## Where this came from

Extracted from the free-model-dispatcher build (2026-08-09/10) — the wayfinder
integration campaign (V1–V9). The canonical repo docs are `agents.md`,
`README.md`, and `docs/dispatcher-integration-questions-ledger.md`; keep those
and this skill in sync when the pool's shape changes materially.
