# Workflows

Project automation that has **graduated** to the toolbox (promoted via the
skill-architect reusability gate: "appears in 2+ places").

Rules:
- A workflow stays in its originating project until a **second consumer** exists.
  One-off project automation does NOT belong here (e.g. uprunner's
  fix-missed-targets / fix-backtest-sizing / donkey-docker live in the uprunner
  repo, not here).
- When a pattern repeats across 2+ projects, promote it: copy here, generalize
  the params, validate (`workflow <name> validate_only=true`), and note the
  consuming projects in a header comment.
- Format: Rhai with `let meta = #{ name, description };` header, one file per
  workflow.

Empty as of 2026-08-01 — no reusable candidate yet. Fill as candidates emerge.
