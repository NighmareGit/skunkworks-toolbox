# Bootstrap a New Machine / Project

> **Primary path (cross-platform):** `bootstrap.py` — a fresh OS + grok install gets the
> whole orchestration hub in one command, no bash required (works on Windows too):
> ```bash
> python3 ~/.grok/skills/campaign-orchestrator/scripts/bootstrap.py --mint all --target ~/projects/<your-project>
> ```
> It mints the hub (`~/.grok`: agent types, role registry/architecture, prompts,
> workflows, a SANITIZED `config.toml` with empty api keys), the hub workspace
> (`~/projects/grok` + a generated `config/projects.yaml`), and the project. Add
> `--install-python` to auto-install Python 3.11+ via uv. Legacy Linux-only path:
> `bootstrap-project.sh` (deleted in the bash→Python migration — bootstrap.py is the only path).

A freshly minted project can be wired to the campaign-orchestration layer in
**one command** with the bootstrap kit. The kit seeds the dispatch toolchain,
the regression test suite, and a generic orientation doc (`agents.md`), then
runs the suite to prove the wiring holds.

## One-command usage

```bash
# From anywhere — cross-platform (Windows/Linux/macOS), stdlib Python, no bash:
python3 ~/.grok/skills/campaign-orchestrator/scripts/bootstrap.py --mint project --target ~/projects/<your-project>

# Options:
#   --target DIR   project dir to bootstrap (created if absent) — required
#   --force        overwrite agents.md if it already exists (default: refuse)
#   --install-python   install Python 3.11+ via uv if missing (--ensure-python to just report)

# (the old bash entry `bootstrap-project.sh` was deleted in the bash→Python migration)
```

The script is **model-free** (no AI calls, no secrets, no network) and
**idempotent** (re-running re-copies scripts/tests but never clobbers an existing
`agents.md` or task ledger).

## What the kit contains

| Path in skill | What it is |
|---------------|------------|
| `scripts/bootstrap.py` | The one-command, cross-platform bootstrap entry point (supersedes `bootstrap-project.sh`) |
| `scripts/toolchain/*` | Bundled copy of the full dispatch toolchain — entirely Python (`toolchain.py` + `tool_*.py`), no bash |
| `scripts/run_toolchain_tests.py` | The model-free regression suite (93 tests) |
| `templates/agents.md` | Generic orientation-doc template (placeholder-based) — includes Session Startup, the state-machine boot (`next-action`), and the one-command **session handoff** (`--mode handoff` + `RESUME.md`), so "we need a new session" works in a freshly minted project with no extra wiring |

## Prerequisites

Before bootstrapping, confirm:

- [ ] **The toolchain's companion roles exist** in `~/.grok/config.toml`
  (`[subagents.roles.*]`) — at minimum a longcat role for deep work and a
  `deepseek-v4-flash` role for coordination/verification.
- [ ] **A local AI endpoint** is reachable for the `explore` role
  (e.g. llama-server on loopback). Not required to *run* the kit, but required
  to exercise recon tasks afterward.
- [ ] **Python 3.11+ is available** (the whole toolchain is Python; `--ensure-python`
  reports it, `--install-python` installs it via uv if missing).

> The kit itself has **zero secret or path dependencies** — it ships no API
> keys, no hardcoded hostnames, and refuses to touch `~/.grok/config.toml`.

## Step-by-step wiring

1. **Run the kit** (see one-command usage above). It:
   - creates `.scratch/scripts/` and copies the full toolchain (Python leaf tools via
     `toolchain.py` + `tool_*.py` (all Python, incl. the dispatch wrapper);
     t2_* campaign utilities excluded),
   - creates `tests/` and copies `run_toolchain_tests.py` + `scenario_dress_rehearsal.py`,
   - seeds an empty task ledger at `.scratch/task-state/TASKS.json`,
   - writes `templates/agents.md` → your project root as `agents.md`
     (**only if it doesn't exist** — pass `--force` to overwrite),
   - runs the suite to verify (expect **93 passed, 0 failed**).

2. **Fill the placeholders** in your new `agents.md`:
   `{{PROJECT_NAME}}`, `{{MISSION}}`, `{{REPO_LAYOUT}}`, `{{SECRETS_PATH}}`,
   `{{MODEL_SERVER_URL}}`.

3. **Define roles** in `~/.grok/config.toml` if not already present
   (see Model Routing Rules below).

4. **Scaffold your first campaign:**
   ```bash
   cd ~/projects/<your-project>
   python3 ~/.grok/skills/campaign-orchestrator/scripts/scaffold-campaign.py \
       --id <slug> --mission <path-to-MISSION.md> --target .scratch/campaigns
   ```

## Verification

After bootstrapping, run these in your project root:

```bash
# 1. The full regression net (93 model-free tests). Must be all-green.
PROJECT="$PWD" python3 tests/run_toolchain_tests.py

# 2. Failure injection — proves the dispatch gates actually gate.
python3 .scratch/scripts/toolchain.py dispatch --mode sabotage --task-id S0

# 3. Gate your finished agents.md before relying on it (catches missing
#    sections + leftover placeholder tokens).
python3 .scratch/scripts/arch-validator.py agents.md \
    --required "Context Budget Note,Session Startup,North-Star Mission,Environment Setup,State Verification"

# 4. Confirm your config and role docs agree (no drift).
python3 .scratch/scripts/config-consistency.py
```

### Smoke test (identical in spirit to the reference project's)

A mandatory toolchain smoke-test after any change to `.scratch/scripts/`, and
recommended at every session start:

```bash
PROJECT="$PWD" python3 tests/run_toolchain_tests.py                # 93 model-free tests
python3 .scratch/scripts/toolchain.py dispatch --mode sabotage --task-id S0  # failure injection
```

If either fails, **STOP and report** — the dispatch gates you are about to rely
on do not hold. Do not dispatch real sub-agents through a red toolchain.

## Model-routing rules

Sub-agent work is routed to **roles** defined in `~/.grok/config.toml`
(`[subagents.roles.*]`). The full architecture lives in
`~/.grok/ROLE-ARCHITECTURE.md`. Quick map:

| Work type | `subagent_type` | Model | Why |
|-----------|----------------|-------|-----|
| Coordination, forks, verification | `orchestrator` / `verifier` | `deepseek-v4-flash` | Cheap, mechanical, high-frequency |
| Research, implementation, planning | `researcher` / `implementer` / `general` / `planner` | `longcat` | Deep work, 256K context — **needs R1-R9 rails** |
| Codebase recon | `explore` | `local-gemma-4-e4b` | Free local AI, fast. **No math** (re-verify its output) |

**Rules:**

- **Longcat executes.** Every longcat brief MUST include the rail core
  (`~/.grok/prompts/longcat-rails.md`): single goal, tool budget, numbered
  steps, stop-and-report, definition of done. Use
  `.scratch/scripts/sanitize-prompt.py --brief` to build the brief.
- **ds-4-flash reviews/verifies.** The verifier MUST be a different model than
  the implementer (longcat implements, ds-4-flash verifies) — this prevents
  correlated blind spots.
- **Local AI explores.** Route read-only recon to the free local model. Never
  default a deep task to the orchestrator's own model.
- Always pass `subagent_type=<role>` matching the work type.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `bootstrap-project.sh` no longer exists | Kit reference to the deleted bash entry point | Use `bootstrap.py --mint project` (see One-command usage) |
| Suite fails `ledger report` / `ledger phases` | No task ledger at `.scratch/task-state/TASKS.json` | Re-run the kit (it seeds one); don't delete that file |
| `arch-validator.py agents.md` flags placeholders | `{{TOKEN}}` left unfilled | Fill every placeholder, or they are by design in the template |
| `config-consistency.py` exits 1 | Role/model drift between config and `ROLE-ARCHITECTURE.md` | Reconcile the two; the script tells you what disagrees |

## What the kit deliberately does NOT do

- It does **not** modify `~/.grok/config.toml` (roles are yours to define).
- It does **not** copy real secrets or API keys (the template has none).
- It does **not** overwrite an existing `agents.md` unless you pass `--force`.
- It does **not** touch the reference project in any way.
