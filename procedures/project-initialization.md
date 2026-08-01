# Project Initialization — Runbook

> **When to use:** starting a new project in the collection, or rebuilding one from scratch.
> **Proven:** executed 2026-08-01 across 5 sibling projects (signal engine, liquidity stress
> aggregator, overnight information-cost quantifier, self-improving agent meta-loop, cross-asset
> toxicity scanner). Generalized — substitute your own `<PLACEHOLDER>`s.
>
> **Scope note:** this runbook mints a **common** project. `META_SCAFFOLD.md` (the
> academic-hardened meta-pipeline) is NOT part of a common mint — it is a layer used by the
> 5-project signal-engine collection. Collection projects add it via **Appendix C** (optional).

## 0. Preconditions

- [ ] Toolbox available: local clone `<TOOLBOX_DIR>` (or remote `NighmareGit/skunkworks-toolbox`)
- [ ] Central secrets store exists: `<SECRETS_DIR>` (see §4; create it if absent)
- [ ] Grok global config has the MCP servers the project will use (e.g. `searxng`, `academic-mcp`)

## 1. Name it

- Folder = **kebab-case slug** (`<project-slug>`); the human name (`<Human Name>`) lives in the docs, not the path.
- Spaces in folder names break shell/git ergonomics. Renaming is trivial before the first commit.

## 2. Scaffold the base structure

```
<project-slug>/
├── AGENTS.md            # operating contract (template — see Appendix A)
├── MISSION.md           # mission brief (Big Picture / Why / Success Criteria) — template: App D
├── NOTES.md             # dated working notes — template: App D
├── RESOURCES.md         # resource index — template: App D
├── README.md            # one-liner + layout — template: App D
├── docs/
│   ├── agents/          # issue-tracker, triage-labels, domain (setup-matt-pocock-skills output)
│   ├── GOAL.md          # success criteria + anchor/threshold        (created by ask-matt init — App B)
│   ├── SESSION_LOG.md   # append-only session log                   (created by ask-matt init — App B)
│   ├── scaffold-changelog.md                                        (created by ask-matt init — App B)
│   └── research/        # citation-anchored briefs
├── .scratch/            # durable memory (14 dirs): adrs benchmarks code-review investigations
│                        #   leases locks patches plans procedures research scripts task-state tickets
├── worktrees/           # scaffolded empty; filled as tickets land (pipeline §8)
├── scripts/             # bisect-test-template.sh, hitl-loop.template.sh, sanitize-check.sh,
│                        #   sync-secrets.sh (App D), lock.sh → .scratch/scripts/ (App D)
├── mcp/                 # searxng server, academic-mcp server, registration README
└── .grok/
    ├── agents/          # (optional, local-only) home-lab agent defs — omit on public projects
    ├── skills/          # agent-monitor, worktree-guard, gpu-lease, perf-verification,
    │                    #   research-pipeline, task-state, academic-research
    └── workflows/       # academic-research.rhai (+ a mission workflow once the goal sharpens)
```

*Optional teaching layer* (if the project also records what it teaches, like the living
example): `lessons/`, `learning-records/`, `reference/`, `assets/`.

## 3. Copy the portable layer (from the toolbox / global grok)

1. Skills → `.grok/skills/` (curated general-infra set, see tree; the full inventory lives in the toolbox)
2. Scripts → `scripts/` (`bisect-test-template.sh`, `hitl-loop.template.sh`, `sanitize-check.sh`)
3. Procedure → `.scratch/procedures/git-bisect-regression-fix.md`
4. Workflow → `.grok/workflows/academic-research.rhai` (+ a mission workflow once the goal sharpens — reference example: the living project's `gdn-fix-pipeline.rhai`)
5. *(local-only, optional)* Home-lab agent defs (e.g. jupiter-analyzer) — add locally; NOT part of a public mint
6. Lock helper → `.scratch/scripts/lock.sh` — **shipped by the toolbox** (`scripts/lock.sh`)
7. MCP assets → `mcp/` (searxng node script from the global config; `academic_mcp.py` + README + requirements from the academic-research skill)
8. **Sanitize sweep:** grep the copied tree for internal refs (LAN IPs, `user@host`, personal paths) and redact to `<PLACEHOLDER>`s.

## 4. Wire secrets (values stay OUT of the repo)

- `.env.example` — variable names + placeholders (the shareable contract) — **template: Appendix D**
- `.gitignore` — block `.env*`, `secrets/`, `*.key`/`*.pem`, `id_rsa*`, `.netrc` — **template: Appendix D**
- `.grok/secrets.md` — pointer doc: where `<SECRETS_DIR>` is, what is in each file, how to source — **template: Appendix D**
- `scripts/sync-secrets.sh` — re-copies from the canonical sources after rotation — **template: Appendix D**
- AGENTS.md "Credentials" section — same pointer, one more place an agent will find it
- **Public runbook ships placeholders only** — the real variable names and values are local (§0); never put values in a public repo.

## 5. Git init

```
git init -b main                       # GitHub standard branch
git config --global --add safe.directory <abs-project-path>   # fixes "dubious ownership" on env-owned dirs
git status                             # must show scaffold files, ZERO secrets
git check-ignore .env secrets/x        # verify ignore patterns hold
```

## 6. Install the operating docs (common seeds)

- The operating docs (`docs/GOAL.md`, `docs/SESSION_LOG.md`, `docs/scaffold-changelog.md`) are
  **created by the ask-matt initialization** at first session (Appendix B) — not by the mint.
  Their shape: GOAL.md carries success criteria + anchor/threshold; SESSION_LOG is append-only;
  every scaffold evolution gets a changelog row.
- `docs/research/` — scaffold the (empty) dir now; citation-anchored briefs land here later.
- AGENTS.md pointer line: "META_SCAFFOLD.md — read first" **only if you install the collection
  layer (Appendix C)** — a common project omits it

> **Not part of a common mint:** `META_SCAFFOLD.md`, `docs/skill-registry.md`,
> `docs/pipeline-audit.md`, `docs/pipeline-construction.md` — these are the academic-hardened
> **collection** layer (the 5 signal-engine projects). Add them only via Appendix C.

## 7. Inject the mission

- `MISSION.md`: Big Picture / Why It Matters / Success Criteria (+ collection context if part of one) — **template: Appendix D (D.6)**
- `NOTES.md` / `RESOURCES.md` / `README.md` — mint-time root docs — **templates: Appendix D (D.7–D.9)**
- AGENTS.md: "Primary Goal (immutable)" + "Core Insight" + status line
- **Fill the `## Environment / Topology` placeholder BEFORE the first run** — the living example
  includes nodes, credentials, and service-start commands; the pipeline depends on it.

## 8. Harden the contract (from the living example)

Add to AGENTS.md (Appendix A already carries these — verify, don't re-add):

- **Mandatory Pipeline (do not deviate)** — the numbered loop: research wave → wayfinding →
  red-team → to-prd → tickets → one worktree per ticket → tdd/prototype → verify →
  code-review → implement; failure → ADR + notify parent; parent re-evaluates; pivot via
  wayfinding, max 3 times.
- **"Success is measured, never claimed"** — numeric metrics right under the goal.
- **Concurrency protocol** — /tmp scratchfile per agent (update after each step, reparse after
  compaction); sub-agents only when non-interdependent + race-free; build/source/gpu-N locks
  (`lock.sh`); exclusive GPU leases.
- **Verification gate** — every ticket "done" requires measured results against the GOAL.md anchor.

## 9. Verification checklist (run before declaring initialized)

- [ ] `git branch --show-current` = `main`; git operates (no "dubious ownership")
- [ ] Leak scan clean: no secret values, no personal paths in the tree
- [ ] `.scratch/` has all 14 dirs; `worktrees/` scaffolded (empty is normal)
- [ ] `.env` / `secrets/` ignored (`git check-ignore`)
- [ ] `scripts/sync-secrets.sh` (App D) + `.scratch/scripts/lock.sh` (toolbox `scripts/lock.sh`) present
- [ ] *(local-only)* `.grok/agents/` populated only when the project uses home-lab agents
- [ ] Topology section filled (§7) — not a placeholder
- [ ] *(collection only, App C)* `META_SCAFFOLD.md` present, AGENTS.md points to it,
      `docs/skill-registry.md` resolves every name

## 10. Lessons learned (scars from 5 initializations + the mint test)

1. **Tool reach:** file tools (read/write/edit) reach only the current workspace dir — use the shell for sibling directories.
2. **Dubious ownership:** env-created directories belong to a different user; fix with `safe.directory`, do NOT chown.
3. **Heredocs:** quote the delimiter when content has backticks/`$`; prefer heredocs over single-quoted multi-line variables (syntax-error-prone). Keep command chunks small — oversized commands fail at the harness level.
4. **Copying a repo with zero commits** (`cp -r` including `.git`) yields independent repos — each copy's first commit diverges cleanly; no re-init needed.
5. **Scaffold verbatim first, audit second:** copy the upstream scaffold unmodified, then map every name against the real inventory (registry) — never assume.
6. **Secrets in ONE store:** central directory outside any repo, chmod 600/700, re-sync script, gitignore; never inline values in projects.
7. **Generalize shared docs:** anything living in the public toolbox uses `<PLACEHOLDER>`s — no LAN IPs, `user@host`, personal paths, or credentials.
8. **The contract is the product:** the AGENTS.md Mandatory Pipeline + verification gate is what makes unattended runs converge — copy it, don't reinvent.
9. **Layers, not one size:** a generic project mints without META_SCAFFOLD; the academic-hardened layer is collection-specific. Keep the runbook's common path dependency-free.
10. **Terminal env is visible to the harness:** command errors can dump the full shell environment (incl. API keys) into the transcript — be aware when running secret-bearing commands.

---

## Appendix A — AGENTS.md template (generalized)

Copy this file into the new project, fill the `<placeholders>`, inject the mission
(§7), then adapt. The hardened contract (§8) is already baked in. The META_SCAFFOLD
pointer line applies only to collection projects (Appendix C).

```markdown
# AGENTS.md — <Human Name>

> **Status:** mission defined <YYYY-MM-DD> — <mission one-liner>. See `MISSION.md`.
> *(collection projects only)* **Operating procedure:** `META_SCAFFOLD.md` — read first; highest-priority operating procedure.

## Primary Goal (immutable)

<The one sentence that never changes. Until defined, `MISSION.md` is authoritative.>

## Core Insight

<The single insight that shapes all strategy, e.g. "the bottleneck is X, not Y.">

## Success is measured, never claimed

Every ticket's "done" requires **measured results** against the GOAL.md anchor
(`docs/GOAL.md`): the metric, the control, and the threshold that counts as a win —
recorded before the work starts. Claims without measurement are not done; a failed
vector with its falsifying number is worth more than an unmeasured pass.

## Environment / Topology

<Hardware, credentials, and external resources this project runs on. Fill BEFORE first run (§7).>

## Strategy & Doctrine

- The feedback loop: **profile → identify bottleneck → hypothesize → prototype → verify → compare**.
- Every approach is informed by measurement, not vibes. Failed vectors are valuable: record the falsifying number and an ADR (`.scratch/adrs/` or `docs/adr/`).
- Research sub-agents produce new attack vectors continuously; the orchestrator integrates them.

## Mandatory Pipeline (do not deviate)

1. Research wave — academic-research first, then the practitioner layer
2. Wayfinding on the highest-leverage unknown → decision map (research-pipeline / beta-wayfinder)
3. Red-team the chosen path (incl. the literature base) → mitigations folded in
4. `/to-prd` → tickets — one git branch + one worktree per ticket
5. `/tdd` → prototype → verification (correctness + signal, against the GOAL.md anchor)
6. Debug loop on failure (`diagnosing-bugs`)
7. `/code-review` on green → re-verify → `/implement`
8. Failure → ADR in `.scratch/adrs/` + commit + notify parent; success → update docs
9. Parent re-evaluates overall goal progress; pivot via wayfinding — max 3 times

## Active Work

<Attack vectors, tickets, experiments. Tickets live in the local issue tracker:
`.scratch/<feature>/` with `Status:` lines (see `docs/agents/issue-tracker.md`).>

## Delegation Rule (non-negotiable)

The parent/orchestrator **must not** perform research, implementation, benchmarking,
or debugging itself. All concrete work is delegated:

- Research → `/research` sub-agents (parallel)
- Implementation → worktree-isolated sub-agents
- Benchmarking → GPU-leased sub-agents
- Debugging → `diagnosing-bugs` skill
- Review → `code-review` skill

## Subagent Dispatch Rules (deterministic mapping)

<Per-project model routing table.> Default posture:

| Task Category | Agent/Role | Model | Why |
|---------------|-----------|-------|-----|
| Quick search / codebase exploration | explore role | fast model | Fast, read-only |
| Deep research (multi-source, synthesis) | general-purpose | frontier model | Complex reasoning |
| Full code review | reviewer role | frontier model | Standards + spec axes |
| Implementation | implementer role | frontier model | Heavy lifting |
| Planning | plan | frontier model | Structured planning |

## Resource Rules

- No heavy GPU work without a lease from the `gpu-lease` skill (`.scratch/leases/`). Leases are exclusive. Violating this causes OOM and invalidates results.
- Parallel sub-agents that share physical resources **must** coordinate via file-based locks (`.scratch/locks/`, atomic `mkdir`, helper `lock.sh`): `build` (1 agent), `source` (1 agent), `gpu-N` (1 agent).
- Dispatch rule: research tickets run in parallel (no lock); modify+build+test tickets run sequentially with locks; GPU-using tickets are sequential with a lease.
- **Concurrency protocol:** each agent keeps a disposable scratchfile in `/tmp` — status reflecting the current state, updated after each non-minor step or sub-agent call, **reparsed after each compaction**. Instruct every sub-agent to create its own, same discipline.
- **Sub-agent gating:** use sub-agents only when the task is non-interdependent on other tasks' results AND creates no race conditions on results or hardware.

## Verification Gate

A ticket is "done" only when measured results against the GOAL.md anchor are recorded:
- Correctness clean (no garbage output, no crashes, tests pass)
- Primary metric recorded vs the control/anchor, in the same units
- Resource utilization recorded (where relevant)
- Scaling / side-effects documented (or explicitly marked "not yet measurable")
- `perf-verification` (or the project's own gate) reports PASS — never merge a ticket that fails the gate

## Key Reference Files

| File | Content |
|------|---------|
| `MISSION.md` | The mission / goal |
| `docs/GOAL.md` | Success criteria + anchor/threshold |
| `.scratch/BUGS.md` | 🐛 Bug tracking ledger |
| `docs/agents/issue-tracker.md` | Issue tracker conventions (local markdown) |
| `docs/agents/triage-labels.md` | Triage label vocabulary |
| `docs/agents/domain.md` | Domain doc consumer rules |
| `.scratch/` | Working area: adrs benchmarks code-review investigations leases locks patches plans procedures research scripts task-state tickets |
| `worktrees/` | One worktree per ticket (pipeline §8) |
| `<SECRETS_DIR>` | 🔑 Central credential store (outside git, chmod 600) — pointer: `.grok/secrets.md` |

## Credentials

All keys live centrally at **`<SECRETS_DIR>`** — outside this repo, `chmod 600`.
See `.grok/secrets.md` for the layout and `scripts/sync-secrets.sh` for re-syncing
after rotation. Never commit or push secret values; the `.gitignore` blocks
`.env*` and `secrets/`.

## Skunkworks Toolbox

Custom Grok skills, scripts, and procedures are versioned in the
**skunkworks-toolbox** git repo — the canonical, sanitized, portable backup:
`<TOOLBOX_DIR>` (local) / public mirror (GitHub). Skills graduate into the toolbox
when a capability appears in **2+ projects** (reusability gate). Project-specific
content stays in this repo — never in the toolbox. The toolbox is PUBLIC: sanitize
(no LAN IPs/hosts, `user@host`, personal paths, credentials) and generalize before
pushing there.

## Scratch Policy

- Durable state → `.scratch/`
- Ephemeral per-agent notes → `/tmp/agent-<id>-<timestamp>.scratch.md`

## Conventions

- Prefer independently measurable vertical slices
- Use conventional commits on feature branches
- Never merge a ticket that fails the verification gate
- Failed vectors are valuable — document in `.scratch/adrs/` (or `docs/adr/`)
- Always measure and record the primary metric + resource utilization

## Agent skills

### Issue tracker

Issues and PRDs live as markdown files under `.scratch/<feature>/` in this repo
(local-markdown tracker; no external PR surface). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root.
See `docs/agents/domain.md`.
```

---

## Appendix B — Optional next step: the ask-matt skills layer

The scaffold ships with the standard engineering-skills config baked in
(Appendix A's `## Agent skills` block + `docs/agents/`). That config is produced
by a prompt-driven skills layer — re-run it only when the defaults don't fit.

### B.1 — `/setup-matt-pocock-skills` (per-repo config)

Prompt-driven; walks three decisions, one at a time:

1. **Issue tracker** — where issues live. Default for this collection:
   **local markdown** (`.scratch/<feature>/`, `Status:` lines). Choose GitHub /
   GitLab only if the project actually lives on one (needs a remote + `gh`/`glab`).
2. **Triage label vocabulary** — the five canonical roles (`needs-triage`,
   `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). Defaults unless
   the tracker already uses different names.
3. **Domain docs layout** — single-context (one `CONTEXT.md` + `docs/adr/` at
   root) vs multi-context (monorepo with `CONTEXT-MAP.md`).

Writes: the `## Agent skills` block in `AGENTS.md` (or `CLAUDE.md` — edit the one
that exists; ask if neither) + `docs/agents/{issue-tracker,triage-labels,domain}.md`.

Run it **before §7 (inject the mission)** — the config block lives in the same
AGENTS.md the mission edits. Skipped by default: Appendix A's Agent-skills block
IS the local-markdown default output. Re-run only to switch issue trackers,
customize labels, or restart the config.

### B.2 — `/ask-matt` (the flow router)

Read once at project start to confirm which skill path fits the project's state:

- **Main flow (idea → ship):** grill-with-docs → (prototype detour) →
  to-spec / to-tickets → implement (drives tdd) → code-review
- **On-ramps:** /triage (incoming issues you didn't create), /diagnosing-bugs
  (something broken), /wayfinder (foggy greenfield)
- **Vocabulary layer:** /domain-modeling, /codebase-design
- **Crossing sessions:** /handoff (fork), /compact (continue in place)

**Precedence:** for collection projects, META_SCAFFOLD.md (Appendix C) is the
highest-priority operating procedure; its mandatory pipeline refines ask-matt's
main flow (Phase A academic-research before general research). ask-matt is the
map; META_SCAFFOLD is the route — for collection projects only. Common projects
follow ask-matt's flow directly.

### B.3 — Operating docs (created at first session)

The ask-matt initialization flow also creates the operating docs at first session:
`docs/GOAL.md` (success criteria + anchor/threshold), `docs/SESSION_LOG.md`
(append-only), and `docs/scaffold-changelog.md` (every scaffold evolution gets a
row). The mint scaffolds the dirs (§2/§6) but leaves the files to the initialization.

---

## Appendix C — Optional: the academic-hardened collection layer (META_SCAFFOLD)

**For the 5-project signal-engine collection only.** A common project skips this
entire appendix. Install after §6:

1. `META_SCAFFOLD.md` → repo root (content below)
2. AGENTS.md pointer line (Appendix A, status block)
3. `docs/skill-registry.md` — map every META_SCAFFOLD skill/MCP name to the real
   inventory (academic-research, ask-matt, wayfinder family, red-team, research,
   fireplace, prototype, tdd, implement, code-review, diagnosing-bugs,
   grill-with-docs, metacognitive-friction, to-prd, to-issues, domain-modeling,
   check-work + MCP servers academic-mcp / searxng)
4. `docs/pipeline-audit.md` — the per-phase audit (academic-hardened rev-2 flow)
5. `docs/pipeline-construction.md` — the living-example construction pattern
6. GOAL.md gains the "Academic grounding requirement" block

```markdown
# META_SCAFFOLD.md — Self-Constructing Meta-Cognitive Pipeline (Academic-Hardened)

> **Authority**: This file is the highest-priority operating procedure for this repository.
> The agent must treat it as binding. All other instructions are subordinate.
> The agent is authorized (and required) to evolve this file itself when it discovers better structure.
> Record every evolution in `docs/scaffold-changelog.md`.

## 0. Immutable Context

- **Shared toolbox**: `../skunkworks-toolbox` (or remote `NighmareGit/skunkworks-toolbox`). Prefer toolbox skills over invention.
- **Skills available**: ask-matt, wayfinder / alpha-wayfinder / beta-wayfinder, red-team, research, **academic-research**, fireplace, prototype, tdd, implement, code-review, diagnosing-bugs, grill-with-docs, metacognitive-friction, to-prd / to-issues, domain-modeling, and all others present.
- **Goal**: Already injected as project description / CONTEXT.md / initial tickets. Refine understanding of the given goal. Do not invent new goals.

## 1. Bootstrap Sequence (run once at session start)

1. Read this entire file.
2. Read `CONTEXT.md`, any existing ADRs, `docs/`, and current git status.
3. Invoke **ask-matt** to confirm optimal skill flow for the current state.
4. If the goal is still fuzzy → run **grill-with-docs** or **wayfinder** until a clear, testable success criterion exists.
5. Create or update `docs/GOAL.md` with:
   - Precise success criteria (what "satisfactory" means)
   - Non-goals
   - Measurable exit conditions
   - Explicit requirement that core algorithms and insights must be grounded in academic literature

## 2. Core Meta-Loop (repeat until success criteria are met)

### Phase A — Academic Edge Research (mandatory first move)

- **Primary skill**: `academic-research`
- Run literature searches, citation chains, and paper retrieval on the exact problem domain of this project.
- Build or update a local research base (`docs/research-base.md` or equivalent) using the skill's convention (arXiv/DOI required).
- Extract: proven algorithms, empirical results, known failure modes, open questions / gaps.
- Produce a short, citation-anchored research brief in `docs/research/`.
- Only after this phase may the agent move to general research or fireplace.

### Phase B — Wayfinding & Decision
- Run **wayfinder** (or alpha/beta) on the highest-leverage unknown remaining after the academic base is established.
- Produce decision tickets or a small map of next moves.
- Document chosen path + rejected alternatives with explicit reference to which papers support or contradict each option.

### Phase C — Adversarial Pressure
- Immediately run **red-team** on the chosen path / design / prototype plan.
- Force surface of failure modes, hidden assumptions, and edge cases — especially those already documented in the academic literature.
- Update the plan with mitigations. Do not proceed without this step.

### Phase D — Goal-Driven Prototype
- Use **prototype** to produce the smallest possible runnable artifact that answers the current design/logic question, preferably implementing or testing an algorithm drawn from the academic base.
- Keep it throwaway if necessary. Signal is the only requirement.

### Phase E — Build / Debug / Review Cycle (tight loop)
1. Move from prototype to production-grade module using **tdd** (red-green) at the agreed seams.
2. Prefer implementations that can be traced to a specific paper or established method.
3. When something breaks → **diagnosing-bugs**.
4. After any non-trivial change → **code-review** (standards axis + spec axis).
5. Commit only after code-review is clean or residual risk is explicitly documented.
6. Update tests, documentation, ADRs, and the research base continuously.

### Phase F — Refine & Measure
- Run the new module against the success criteria in `docs/GOAL.md`.
- If not yet satisfactory → return to Phase A or B with the new information (re-run academic-research if new questions emerged).
- If satisfactory → document the result with full academic provenance, update the higher-level agent's knowledge, and mark the goal complete (or open the next sub-goal).

## 3. Mandatory Feedback & Documentation Rules

- Every significant action must leave a durable artifact (research brief with citations, decision record, prototype report, test results, ADR, or changelog).
- Maintain `docs/SESSION_LOG.md` (append-only).
- Prefer closed-loop, deployable, actionable results.
- When given 8-hour unattended free control, the agent must still follow this scaffold and leave the repository clean, documented, and buildable.
- Core algorithmic choices must be defensible by reference to academic sources. Pure invention is allowed only after the literature has been exhausted and the gap is explicitly documented.

## 4. Self-Construction Directive

The agent is explicitly authorized and expected to improve this META_SCAFFOLD.md itself.
When a better sequencing, additional mandatory academic check, or tighter feedback loop is discovered, update this file and record the change in `docs/scaffold-changelog.md`.
The scaffold must evolve toward higher reliability, stronger academic grounding, and lower wasted tokens.

## 5. Exit Condition

The loop terminates only when:
1. The success criteria in `docs/GOAL.md` are met, **and**
2. The core methods are backed by real academic literature (or an explicit, documented gap analysis), **and**
3. A final **code-review** + **check-work** (or equivalent) confirms the repository is coherent, tested, and documented.

---

**Operational note**: Every project is now an academic-edge extraction unit. The cheap tokens exist to convert peer-reviewed insight into running kinetic code. Burn them accordingly.
```
*(Canonical copy also lives in any existing collection project — e.g. `<collection-project>/META_SCAFFOLD.md`.)*

---
## Appendix D — Common templates

### D.1 `.env.example`

```bash
# Copy to .env and fill in real values. NEVER commit .env.
# List every variable the project's code reads (models, data, market, infra).
export KEY_NAME=
export ANOTHER_KEY=
```
*Placeholders only — the real variable names and values are local, never in a public repo.*

### D.2 `.gitignore`

```gitignore
# ── Secrets — never commit ──
.env
.env.*
!.env.example
secrets/
*.key
*.pem
*.p12
*.pfx
id_rsa*
id_ed25519*
.netrc

# ── Runtime / scratch locks ──
.scratch/locks/

# ── OS / editor cruft ──
.DS_Store
*.swp
*~
```

### D.3 `.grok/secrets.md` (pointer doc)

```markdown
# Secrets (pointer — values live outside this repo)

This repo contains **no secret values**. Credentials are stored centrally at:

> **`<SECRETS_DIR>`** — outside any git repo, `chmod 600` files / `700` dir

## Layout

| File | Source | Contents |
|------|--------|----------|
| `.env` | consolidated | All keys as `export VAR=...` — source this for app use |
| `grok-secrets.env` | `~/.grok/secrets.env` | Model BYOK keys |
| `<source-project>.env` | `<source-project>/.env` | App / market-data keys |
| `git-credentials` | `~/.git-credentials` | Git credentials |
| `huggingface-token` | `~/.cache/huggingface/token` | HF download token |
| `gitea-token` | Gitea git remote URL | Gitea API token |

## How to use

- **Sourcing:** `source <SECRETS_DIR>/.env`
- **Re-sync after rotation:** `bash scripts/sync-secrets.sh`
- **Never:** commit, push, or print these values. `.gitignore` blocks `.env*` and `secrets/`.
```

### D.4 `scripts/sync-secrets.sh`

```bash
#!/usr/bin/env bash
# Re-sync <SECRETS_DIR> from the canonical sources. Values are copied file-to-file,
# never echoed. Run after rotating keys. Output is paths only.
set -euo pipefail

SECRETS_DIR="${SECRETS_DIR:-<SECRETS_DIR>}"
TOOLBOX_DIR="${TOOLBOX_DIR:-<TOOLBOX_DIR>}"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

cp ~/.grok/secrets.env            "$SECRETS_DIR/grok-secrets.env"
cp <SOURCE_PROJECT>/.env          "$SECRETS_DIR/<source-project>.env"
cp ~/.git-credentials             "$SECRETS_DIR/git-credentials"
cp ~/.cache/huggingface/token     "$SECRETS_DIR/huggingface-token"

GITEA_TOKEN="$(git -C "$TOOLBOX_DIR" remote get-url gitea | sed -E 's#http://[^:]+:([^@]+)@.*#\1#')"
printf '%s' "$GITEA_TOKEN" > "$SECRETS_DIR/gitea-token"

{
  echo "# Consolidated environment (DO NOT COMMIT / PUSH)"
  echo "# Re-sync: bash scripts/sync-secrets.sh"
  echo
  echo "# --- Model BYOK keys ---"
  cat "$SECRETS_DIR/grok-secrets.env"
  echo
  echo "# --- App / market-data keys ---"
  cat "$SECRETS_DIR/<source-project>.env"
  echo
  echo "# --- Infra tokens ---"
  echo "export GITEA_TOKEN=$GITEA_TOKEN"
  echo "export HUGGINGFACE_TOKEN=$(cat "$SECRETS_DIR/huggingface-token")"
} > "$SECRETS_DIR/.env"

chmod 600 "$SECRETS_DIR"/.env "$SECRETS_DIR"/grok-secrets.env "$SECRETS_DIR"/<source-project>.env \
        "$SECRETS_DIR"/git-credentials "$SECRETS_DIR"/huggingface-token "$SECRETS_DIR"/gitea-token

echo "secrets synced to $SECRETS_DIR (chmod 600)"
```

### D.5 `.scratch/scripts/lock.sh`

Shipped by the toolbox as `scripts/lock.sh` (generalized atomic-mkdir locks for
build / source / gpu-N). Copy it to `.scratch/scripts/` and point `LOCK_DIR` at the
project's `.scratch/locks/`. Usage:
`source lock.sh && acquire_lock <name> <timeout_secs>` … `release_lock <name>`.

---

*Docs seeds (`GOAL.md` / `SESSION_LOG.md` / `scaffold-changelog.md`) and agent
definitions (e.g. jupiter-analyzer) are deliberately NOT in the common templates:
docs seeds are created by the ask-matt initialization (Appendix B.3); agent defs
are home-lab local — omit on public projects. Root docs (`MISSION.md`, `NOTES.md`,
`RESOURCES.md`, `README.md`) ARE mint-time files — templates D.6–D.9 below.

### D.6 `MISSION.md`

```markdown
# Mission: <Human Name>

## The Big Picture

<What this project is, in one or two sentences.>

## Why It Matters

<Why this exists — the problem it solves, the asymmetry it exploits.>

## Success Criteria

- <measurable outcomes, one per line>

*(Optional, for collection projects:)*

## Collection context

<How this project feeds the larger system / other projects.>
```

### D.7 `NOTES.md`

```markdown
# Working Notes

Informal, date-stamped memory of decisions, discoveries, and context — the
durable record of "why". Append new entries at the top.

## <YYYY-MM-DD> — <topic>

- <notes>
```

### D.8 `RESOURCES.md`

```markdown
# Resources

## This repo

| Resource | What it is |
|----------|------------|
| `AGENTS.md` | Agent instructions + operating contract |
| `MISSION.md` | The mission / goal |
| `docs/` | Goal, session log, scaffold changelog, research |
| `.scratch/` | Working area (benchmarks, research, plans, ...) |
| `.grok/` | Project-local skills, agents, workflows |
| `scripts/` | Reusable shell helpers |

## External

- <toolbox / docs / services this project depends on>
```

### D.9 `README.md`

```markdown
# <Human Name>

<One-liner describing the project.>

## Status

Initialized <YYYY-MM-DD> — mission defined / pending (see `MISSION.md`).

## Layout

| Path | Contents |
|------|----------|
| `AGENTS.md` | Agent instructions & operating contract |
| `MISSION.md` | Mission / goal |
| `docs/` | Operating docs |
| `.scratch/` | Working area |
| `.grok/` | Project-local skills, agents, workflows |
```
