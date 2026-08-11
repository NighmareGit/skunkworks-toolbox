# Skunkworks Toolbox

Custom Grok skills, scripts, and procedures — the project's operational memory,
versioned and backed up (Gitea LAN + GitHub public mirror). Every skill here was
**earned from a measured failure**, not written from a template: each rule below
comes from a real incident where the naive approach produced a wrong answer.

> *"Scars are the way the beauty of wisdom is earned."* — the operating principle:
> every rule in this repo is a scar — a lesson paid for with a wrong answer,
> a mirage, or a kill that had to be overturned. We keep the scars, and the
> wisdom they bought.

## What's in here

| Dir | Contents | Promotion rule |
|-----|----------|----------------|
| `skills/` | Reusable skills (43) — general + project-flavored | A capability graduates here when it appears in **2+ places** (skill-architect reusability gate) |
| `workflows/` | Rhai workflows for project automation | Stays in its originating project until a **second consumer** exists; then promoted + generalized here |
| `scripts/` | Reusable shell/python helpers (bisect template, hitl loop template, lock helper, task-state) | Same 2-consumer rule |
| `procedures/` | Case-study procedures (e.g. git-bisect-regression-fix, project-initialization) | Written after a hard-won debugging campaign |

## How to read this repo (for agents)

If you're an agent arriving here, you don't need to know all 40 skills. You need
to answer **one question: "what am I trying to do?"** Then pick the right tool:

- **"I'm orchestrating a whole campaign (or part of one)."** → read
  [docs/orchestration-playbook.md](docs/orchestration-playbook.md) first — the
  generalized dispatch + orchestration playbook: the dispatch-brief anatomy,
  agent-assignment map, lock/lease rules, resume-after-kill discipline, and the
  failure lessons. It's the parent-agent's operating manual; the
  `orchestration-dispatch` skill is its loadable pointer + templates. Pair it
  with [docs/pattern-recognition.md](docs/pattern-recognition.md) — the
  judgment layer (agent-health triage, signature diagnostics, brief
  calibration, the three dispatch archetypes with skeleton exemplars). For the
  *artifact* conventions of a research campaign (MISSION/task/report skeletons,
  workflow shape, ledgers, measurement discipline, scar list), see
  [docs/house-style.md](docs/house-style.md).

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

1. **Never a claim without measurement.** A benchmark that skips the very work it
   claims to speed up can look like a huge win while actually producing garbage.
   Always measure against a real baseline, verify output correctness (not just
   timing), and treat log-grep checks as necessary-but-not-sufficient.
2. **Before/after isn't proof — the flip test is.** A mechanism that "fixes"
   something when measured before/after can still be irrelevant: flip it on and
   off under identical conditions. If the symptom doesn't change, the mechanism
   isn't the cause — and the "fix" may be pure overhead.
3. **Kill decisions never rest on an unverified premise.** When two analyses
   contradict on a claim the whole verdict hinges on, test that claim directly
   (code + measured data) before accepting a kill — never pick a winner by
   intuition. A wrong kill buries a good idea; a wrong keep wastes the campaign.
4. **Red-team BEFORE verify/review.** A code review checks implementation against
   spec — it cannot catch a flawed spec. Attack the plan/ticket adversarially
   first; if issues surface, adapt the spec and re-run rather than hot-fixing a
   wrong ticket. Bound the loop (max ~3), then escalate to the human.
5. **Strong scaffold, weak execution.** Agents are expendable; durable state
   (ledger, task-state, specs) is the memory. On restart, verify ground truth on
   disk — never trust state alone, never redo verified work, never skip
   unverified work.
6. **Kill criteria are honored at the gate, not after.** State kill criteria up
   front, check them at the decision gate, and record every kill as an ADR with
   its re-open condition (what would make it viable again).

## Backup topology

- **Gitea (private LAN mirror)** — canonical
- **GitHub (public mirror):** `https://github.com/NighmareGit/skunkworks-toolbox`
- **Local working copy** — the repo this README ships in

Sync rule: commit locally → push the private LAN mirror → push the public GitHub
mirror (sanitized: no internal hostnames/IPs, credentials, or personal paths).
The GitHub copy is public by design — anyone who finds it useful is welcome to
the skills.

## Status

- Skills: 48 (incl. campaign-orchestrator, research-pipeline pair, alpha-wayfinder quartet, the
  assembly-chain + wayfinder family, orchestration-dispatch, academic-research,
  skill-architect tooling)
- Workflows: 1 (academic-research — the first Rhai workflow, dual-mode focus)
- Procedures: 1 (git-bisect-regression-fix — the 122B GDN case study)

*Last updated: 2026-08-02*
