# Skunkworks Toolbox

Custom Grok skills, scripts, and procedures — the project's operational memory,
versioned and backed up (Gitea LAN + GitHub public mirror). Every skill here was
**earned from a measured failure**, not written from a template: the +56% mirage,
the falsify test that killed a 10×-latency "fix", the A7 kill overturned on a
false premise — each is baked into a rule below.

## What's in here

| Dir | Contents | Promotion rule |
|-----|----------|----------------|
| `skills/` | Reusable skills (40) — general + project-flavored | A capability graduates here when it appears in **2+ places** (skill-architect reusability gate) |
| `workflows/` | Rhai workflows for project automation | Stays in its originating project until a **second consumer** exists; then promoted + generalized here |
| `scripts/` | Reusable shell/python helpers (bisect template, hitl loop template) | Same 2-consumer rule |
| `procedures/` | Case-study procedures (e.g. git-bisect-regression-fix) | Written after a hard-won debugging campaign |

## How to read this repo (for agents)

If you're an agent arriving here, you don't need to know all 40 skills. You need
to answer **one question: "what am I trying to do?"** Then pick the right tool:

- **"Should we build X / which fix is best / is idea Y viable?"** →
  `research-pipeline` (generic) or `rpc-research-pipeline` (RPC flavor).
  These run the idea→evidence→decision funnel: baseline → fireplace → research
  wave → triage → wayfinder → PRD → red-team → scaffold → decide. **Start here
  before any big build.** The funnel's kill discipline (ADR + flip test) and its
  conflict-adjudication stage are the two rules most worth respecting.
- **"We've decided WHAT; now run the campaign."** → `wayfinder-assembly-chain`,
  `beta-wayfinder` (small/medium campaigns), or `alpha-wayfinder` (large,
  parallel, checkpoint-heavy builds). See
  [docs/wayfinder-comparison.md](docs/wayfinder-comparison.md) for when to use
  which — the short version: assembly-chain for execution teeth (red-team before
  verify, merge discipline), beta for economics (when to stop), alpha for
  orchestration at scale (toolbox dispatch, checkpoints, nesting).
- **"Something is broken."** → `diagnosing-bugs` (hard bugs) or `bug-hunt`
  (ledger-driven sweep).
- **"Build/test/review this ticket."** → `tdd` → `prototype` → `implement` →
  `code-review` (Standards + Spec axes), with `worktree-guard` for isolation and
  `task-state` for resumability. **Red-team before verify** — a code review
  cannot catch spec-level flaws.
- **"We lack a capability."** → `skill-architect` (build a skill for 2+ places)
  or a workflow/script (one-off).
- **"What's the vocabulary / domain?"** → `codebase-design`, `domain-modeling`.
- **"Do I need GPUs?"** → `gpu-lease` first. Never run GPU work without a lease.

## The rules that matter most (learned the hard way)

1. **Never a claim without measurement** — the V2 "+56%" was a silent
   recompute-skip wearing a speedup costume. Benchmark against a real baseline,
   diff output, don't trust grep-only gates.
2. **Before/after isn't proof — the flip test is** — a mechanism must survive
   ON/OFF falsify (ADR-005: a double-buffer "fix" that passed before/after died
   on the flip).
3. **Kill decisions never rest on an unverified premise** — the A7 NO-GO was
   overturned by adjudication (starfish is serial, not parallel). When two
   reports contradict on a load-bearing claim, dispatch an adjudicator.
4. **Red-team BEFORE verify/review** — and if it finds issues, adapt the spec and
   re-run; don't hot-fix a wrong ticket (max 3 iterations, then escalate).
5. **Strong scaffold, weak execution** — agents are expendable; durable state
   (ledger, task-state, specs) is the memory. Verify-already-done on restart.
6. **Kill criteria are honored at the gate, not after** — and every kill gets an
   ADR with a re-open condition.

## Backup topology

- **Gitea (LAN):** `http://192.168.8.108:3005/hunter/skunkworks-toolbox` — canonical
- **GitHub (public):** `https://github.com/NighmareGit/skunkworks-toolbox` — mirror
- **Local:** `/home/hunter/scratch/skunkworks-toolbox` — working copy

Sync rule: commit locally → push Gitea → push GitHub (sanitized). The GitHub copy
is public by design — anyone who finds it useful is welcome to the skills.

## Status

- Skills: 40 (incl. research-pipeline pair, alpha-wayfinder quartet, the
  assembly-chain + wayfinder family)
- Workflows: 0 (scaffolded, waiting for its first 2-consumer candidate)
- Procedures: 1 (git-bisect-regression-fix — the 122B GDN case study)

*Last updated: 2026-08-01*
