# AGENTS.md — Skunkworks Toolbox (hygiene contract)

> **This repo is PUBLIC on GitHub.** Everything here must be readable by a stranger
> with zero context — and must leak nothing about the internal network, machines,
> usernames, or personal paths. Two rules govern every change:
> **SANITIZE** (nothing internal escapes) and **GENERALIZE** (nothing project-only
> sits in a general toolbox). This file is the enforcement contract.

---

## 1. The dual-mirror model

| Remote | Visibility | Policy |
|--------|-----------|--------|
| **Gitea (LAN)** | private | Canonical, full fidelity. Project-specific context allowed in the project's own repos — but NOT in the toolbox. |
| **GitHub** | public | Sanitized mirror. Anything here is world-readable. |

**Sync rule (mandatory order):**
1. Commit locally.
2. Push Gitea (LAN).
3. Run the pre-push scan (`scripts/sanitize-check.sh`) — **must pass clean**.
4. Push GitHub only after the scan passes.

If a change fails the scan, fix it (or consciously redact) before pushing GitHub.
Never push GitHub with a failing scan.

---

## 2. SANITIZE — what must never appear in this repo

The toolbox must contain **no internal environment references**. The scan
(`scripts/sanitize-check.sh`) greps for these; the list is the contract:

### 2.1 Forbidden patterns (hard fail)

- **LAN IPs / hostnames** — `192.168.*`, `10.*`, `172.16–31.*`, `*.lan`, internal DNS names.
- **Usernames in access contexts** — `user@host` SSH/SCP lines, `hunter@`, `root@<internal>`.
- **Absolute personal paths** — `/home/<user>/...`, `/Users/<user>/...`, `/mnt/<label>/...`.
- **Credentials of any kind** — passwords, tokens, API keys, `Authorization:` headers,
  private keys (PEM blocks), Gitea/GitHub tokens, `.env` values.
- **Internal service URLs** — `http://<lan-ip>:<port>/...` (Gitea, dashboards, registries).
- **Passwords even in comments/examples** — a redacted-looking `12345` in an example is still a leak vector.

### 2.2 Allowlist (fine to keep)

- Public URLs: `https://github.com/NighmareGit/*` (the public mirrors).
- Placeholders: `<REPO_ROOT>`, `<USER>`, `<HOST>`, `<LAN_IP>`, `<MODEL_PATH>` — prefer these over real values.
- `127.0.0.1` / `localhost` — loopback is not internal topology.

### 2.3 Redaction, not deletion

When a skill legitimately needs a path/host (e.g. a test harness), replace the real
value with a placeholder and document the substitution in the skill's own text:
"replace `<MODEL_PATH>` with your model location". The skill stays usable as a
template; nothing internal leaks.

---

## 3. GENERALIZE — what belongs here and in what form

The toolbox is the **general, reusable** layer. Project-specific content stays in
the project's repo. Use the skill-architect **reusability gate** before adding
anything: *"Would another part of a different project benefit from this?"*

| Category | Belongs in toolbox? | Where it goes instead |
|----------|--------------------|------------------------|
| General capability (research pipeline, bisect procedure) | ✅ as a skill/procedure | — |
| Project-specific automation (one project's fetch scripts, backtest sizing) | ❌ | The project repo (e.g. `uprunner/`), promoted only when a **2nd consumer** appears |
| Project-specific data (model paths, RPC endpoints, machine names) | ❌ even in examples | Project repo, or redact to `<PLACEHOLDER>` |
| System/bundled skills copied verbatim (e.g. Grok's `help`) | ⚠️ only if sanitized | Sanitize paths or drop |

### 3.1 Public-facing prose must stand alone

READMEs, comparisons, and skill descriptions are read by strangers:
- **No project jargon without explanation.** "V2 +56%", "ADR-005", "A7", "BUG-011",
  "T-B1" mean nothing outside the project. State the lesson in universal terms;
  put the war story in the project's own `.scratch/` (the fork repo), not here.
- **Generalize examples.** Use toy names (`X`, `Y`, `acme`), not internal models,
  GPUs, or endpoints.
- **If a project context is essential**, say "see the originating project" —
  never reproduce the internal specifics.

### 3.2 Skills added here must be self-contained

A skill in the toolbox should not depend on files that exist only in one project
(`/home/...`, a project's `.scratch/scripts/`, a specific repo layout). If it does,
either parameterize it (inputs section) or keep it project-side.

---

## 4. Pre-push checklist (before ANY commit)

1. `scripts/sanitize-check.sh` — run it; must exit 0.
2. Read your diff as a stranger would: does any example/path/URL assume internal
   knowledge? (The scan catches patterns, not intent — read the prose too.)
3. Generalization check: is this a 2+ consumer capability, or project-specific?
   If project-specific, it doesn't go in the toolbox.
4. If you touched a `.md` doc, re-read the "public prose" rule — no bare project
   acronyms without explanation.
5. Push Gitea, then push GitHub only when clean.

**Escalation:** if you're unsure whether something leaks or generalizes, DON'T push
GitHub. Leave it on Gitea, flag it in the commit message, and ask the human.

---

## 5. Incident history (why this contract exists)

| When | What leaked / was wrong | Fix |
|------|------------------------|------|
| 2026-08-01 | README backup topology had LAN IP + local path (public) | Sanitized to placeholders + generic wording |
| 2026-08-01 | README rules referenced "V2 +56%", "ADR-005", "A7" — project jargon | Generalized to universal lessons |
| 2026-08-01 | `skills/multi-gpu-verify/` carries 20+ internal refs (paths, LAN IP, SSH user@host) | Under review — candidate for redaction or project-side move |
| 2026-08-01 | `skills/help/` (Grok system skill) leaks local `.grok` paths | Under review — sanitize or drop |
| 2026-08-01 | `scripts/bisect-test-template.sh` has local model/build paths | Under review — parameterize |

Every future incident gets a row here. This file is living — update it when the
contract changes or a new leak class is found.

---

## 6. Quick reference (copy into prompts)

```
Toolbox hygiene (AGENTS.md):
- Repo is PUBLIC on GitHub → sanitize + generalize everything.
- Never: LAN IPs/hostnames, user@host, /home/<user> paths, credentials, internal URLs.
- Prefer: <PLACEHOLDER> tokens, loopback only, public GitHub URLs.
- Generalize: 2+ consumer capabilities only; no project jargon in prose;
  project-specific content stays in the project repo.
- Gate: run scripts/sanitize-check.sh; push Gitea first; GitHub only when clean.
- Unsure? Don't push GitHub. Ask the human.
```
