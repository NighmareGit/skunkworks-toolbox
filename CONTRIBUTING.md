# Contributing

This repo is a **public toolbox**. Outside contributions are welcome as
**pull requests**. Maintainers review every change before it lands. Nobody
outside the maintainers has push access to `master`.

## What belongs here

Same bar as [AGENTS.md](AGENTS.md):

- **Reusable.** A second, independent consumer would benefit. One-project
  scripts and war stories stay in that project's repo.
- **Sanitized.** No LAN IPs, `user@host`, `/home/<user>` paths, tokens,
  internal URLs. Use placeholders (`<REPO_ROOT>`, `<USER>`, `<HOST>`,
  `<LAN_IP>`, `<MODEL_PATH>`).
- **Standalone.** A stranger with no lab context must be able to read the
  skill. No project jargon without a one-line explanation.

If you are unsure whether something generalizes, open an **issue** first
and describe the capability. That is cheaper than a large PR we would
reject as project-specific.

## How to send a change

1. Fork the repo. Work on a branch in your fork.
2. Add or change only what the PR is about. Match the surrounding
   skill/doc shape (`SKILL.md`, short factual comments).
3. Run the hygiene scan from the repo root:

   ```bash
   bash scripts/sanitize-check.sh
   ```

   It must exit 0. CI runs the same script on every PR.
4. Open a pull request against `master`. Use the PR template.
5. Wait for review. Maintainers may ask for redaction, generalization,
   or a split. Nothing merges without a human look.

Do **not** expect a direct push, collaborator invite, or merge of an
unreviewed dump of local files.

## Review bar

A maintainer will check:

| Check | Fail if |
|-------|---------|
| Hygiene scan | CI red, or leaks the scan does not catch (intent, jargon) |
| Reusability | Only one project's layout or data |
| Secrets | Tokens, keys, `.env` values, private URLs |
| Scope | Unrelated refactors bundled with the new skill |

Passing CI is necessary, not sufficient.

## Issues

Use issues to propose a skill, report a broken instruction, or ask whether
a capability belongs here. Feature chat without a concrete artifact can
live in an issue; the artifact still arrives as a PR.
