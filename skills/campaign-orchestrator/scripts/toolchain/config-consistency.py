#!/usr/bin/env python3
"""config-consistency.py — cross-check ~/.grok config.toml against ROLE-ARCHITECTURE.md.

Detects the red-team F13 failure class: doc and config silently diverging
(e.g. ROLE-ARCHITECTURE.md said explore -> ds-4-flash while config.toml routed
explore -> local-gemma-4-e4b). Nothing previously detected the drift until a
human read both files side by side.

Checks (config side):
  C1  config.toml parses as valid TOML
  C2  every [subagents.roles.*] has a model that resolves to a [model.*] section
  C3  every role prompt_file exists on disk
  C4  default_capability_mode is one of read-only | read-write | execute | all
  C5  every model referenced by [models] default, ui.fork_secondary_model and
      [subagents.models] resolves to a [model.*] section

Checks (doc side — ROLE-ARCHITECTURE.md):
  D1  role -> model mapping in the "Model-Role Matrix" table matches config,
      including the special rows "(session fork)" and "(built-in explore)"

Usage:
  config-consistency.py [--config ~/.grok/config.toml] [--doc ~/.grok/ROLE-ARCHITECTURE.md]
                        [--quiet]

Exit codes:
  0 = consistent
  1 = drift found (fix doc or config)
  2 = usage / IO error
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib  # Python >= 3.11
except ImportError:  # pragma: no cover
    tomllib = None

try:
    import yaml as _yaml  # pyyaml — strict front-matter parse (D2b)
    YAML = _yaml
except ImportError:  # pragma: no cover
    YAML = None

ALLOWED_CAPABILITIES = {"read-only", "read-write", "execute", "all"}
# Doc rows that map to config keys rather than [subagents.roles.*] entries.
SPECIAL_DOC_ROLES = {
    "(session fork)": ("ui", "fork_secondary_model"),
    "(built-in explore)": ("subagents", "models", "explore"),
}


def parse_config(path: Path) -> dict:
    """Load and parse a TOML config file."""
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    if tomllib is None:
        raise RuntimeError("tomllib unavailable — Python >= 3.11 required")
    with open(path, "rb") as f:
        return tomllib.load(f)


def parse_role_matrix(doc_text: str) -> list[tuple[str, str]]:
    """Extract (role, model) rows from the Model-Role Matrix markdown table."""
    rows = []
    in_matrix = False
    for line in doc_text.splitlines():
        if re.match(r"^#+\s*The Model-Role Matrix", line):
            in_matrix = True
            continue
        if in_matrix and re.match(r"^#+", line):
            break  # next section ends the matrix
        if not in_matrix or not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        role = cells[1].strip("`* ")
        model = cells[2].strip("`* ")
        if not role or not model or model in ("—", "-"):
            continue
        rows.append((role, model))
    return rows


def parse_registry_table(doc_text: str) -> list[tuple[str, str, str, str]]:
    """Extract (role, model, capability, prompt_file) rows from the ROLE-REGISTRY table.

    Table columns: Role | Model | Capability | Prompt file | Rails | When to dispatch.
    Returns rows with the first four columns; skips header/separator lines.
    """
    rows = []
    in_table = False
    for line in doc_text.splitlines():
        if re.match(r"^#+\s*The Registry", line):
            in_table = True
            continue
        if in_table and re.match(r"^#+", line):
            break
        if not in_table or not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        role = cells[0].strip("`* ")
        model = cells[1].strip("`* ")
        capability = cells[2].strip("`* ")
        prompt = cells[3].strip("`* ")
        if not role or not model or model in ("—", "-"):
            continue
        if role in ("Role",) or re.fullmatch(r"-+", role):
            continue  # header row / separator row
        rows.append((role, model, capability, prompt))
    return rows


def parse_agent_definition(path: Path, role: str, models: dict,
                           expect_model: str = "", expect_cap: str = "") -> list[str]:
    """Validate one spawnable agent definition (D2b).

    Mirrors production discovery: the harness (serde_yaml 0.9) parses the YAML
    front-matter in ~/.grok/agents/<role>.md and silently DROPS the definition
    on parse failure — which surfaces later as "Unknown subagent type: <role>"
    (a real incident: unquoted `: ` in a description scalar broke verifier.md
    and orchestrator.md). pyyaml catches the same plain-scalar failure class.
    Also cross-checks the definition's model/capability_mode against the
    registry row (RT-10): a silently-swapped verifier model would break the
    correlated-error invariant while the checker stays green.
    Returns a list of problems (empty = healthy).
    """
    probs: list[str] = []
    if not path.is_file():
        return probs  # existence handled by the caller
    if YAML is None:
        probs.append("pyyaml unavailable — front-matter parse skipped")
        return probs
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.lstrip().startswith("---"):
        probs.append(f"definition {path.name} missing YAML front-matter (must start with ---)")
        return probs
    parts = text.split("---", 2)
    if len(parts) < 3:
        probs.append(f"definition {path.name} front-matter not closed (missing second ---)")
        return probs
    try:
        data = YAML.safe_load(parts[1])
    except Exception as e:
        probs.append(f"definition {path.name} front-matter does not parse: {e}")
        return probs
    if not isinstance(data, dict):
        probs.append(f"definition {path.name} front-matter is not a mapping")
        return probs
    if data.get("name") != role:
        probs.append(f"definition name '{data.get('name')}' != registry role '{role}' (discovery keys by filename)")
    for field in ("model", "capability_mode"):
        if not data.get(field):
            probs.append(f"definition missing '{field}'")
    cap = data.get("capability_mode")
    if cap and cap not in ALLOWED_CAPABILITIES:
        probs.append(f"invalid capability_mode '{cap}' (allowed: {', '.join(sorted(ALLOWED_CAPABILITIES))})")
    model = data.get("model")
    if model and models and model not in models:
        probs.append(f"definition model '{model}' not defined in [model.*]")
    if expect_model and model and model != expect_model:
        probs.append(f"definition model '{model}' != registry model '{expect_model}'")
    if expect_cap and cap and cap != expect_cap:
        probs.append(f"definition capability '{cap}' != registry capability '{expect_cap}'")
    return probs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="~/.grok/config.toml", help="path to config.toml")
    ap.add_argument("--doc", default="~/.grok/ROLE-ARCHITECTURE.md", help="path to ROLE-ARCHITECTURE.md")
    ap.add_argument("--registry", default="~/.grok/ROLE-REGISTRY.md", help="path to ROLE-REGISTRY.md (dispatch front-door)")
    ap.add_argument("--agents-dir", default="~/.grok/agents", help="dir with spawnable agent definitions <role>.md (D2b)")
    ap.add_argument("--workflow", default="~/.grok/workflows/dispatch-wave.rhai", help="path to the dispatch workflow (D2c)")
    ap.add_argument("--quiet", action="store_true", help="suppress informational notes")
    args = ap.parse_args()

    problems: list[str] = []
    notes: list[str] = []

    config_path = Path(args.config).expanduser()
    doc_path = Path(args.doc).expanduser()
    registry_path = Path(args.registry).expanduser()
    agents_dir = Path(args.agents_dir).expanduser()
    workflow_path = Path(args.workflow).expanduser()

    # C1 — config must parse
    try:
        cfg = parse_config(config_path)
    except FileNotFoundError:
        problems.append(f"C1 config not found: {config_path}")
        cfg = None
    except Exception as e:  # TOMLDecodeError etc.
        problems.append(f"C1 config parse failed: {e}")
        cfg = None

    if cfg is not None:
        # RT-A1 fix: table values may be malformed (a list instead of a table).
        # isinstance guards turn a would-be AttributeError crash into a clean
        # drift report — a checker that tracebacks is not a control system.
        # A section that exists but is the wrong TYPE is itself drift worth
        # reporting, not something to silently ignore.
        models = cfg.get("model", {}) or {}
        subagents_cfg = cfg.get("subagents")
        if subagents_cfg is not None and not isinstance(subagents_cfg, dict):
            problems.append("C1 [subagents] is not a table (malformed config)")
            subagents_cfg = {}
        subagents_cfg = subagents_cfg if isinstance(subagents_cfg, dict) else {}
        roles = subagents_cfg.get("roles", {}) or {}
        sub_models = subagents_cfg.get("models", {}) or {}
        ui_cfg = cfg.get("ui")
        if ui_cfg is not None and not isinstance(ui_cfg, dict):
            problems.append("C1 [ui] is not a table (malformed config)")
            ui_cfg = {}
        ui_cfg = ui_cfg if isinstance(ui_cfg, dict) else {}

        # C2/C3/C4 — per-role integrity
        for role, rcfg in sorted(roles.items()):
            if not isinstance(rcfg, dict):
                notes.append(f"role '{role}' is not a table — skipped")
                continue
            model = rcfg.get("model")
            if not model:
                problems.append(f"C2 role '{role}' has no 'model'")
            elif model not in models:
                problems.append(
                    f"C2 role '{role}' references undefined model '{model}' — no [model.{model}] section"
                )
            pfile = rcfg.get("prompt_file")
            if pfile:
                if not Path(str(pfile)).expanduser().is_file():
                    problems.append(f"C3 role '{role}' prompt_file missing: {pfile}")
            else:
                notes.append(f"role '{role}' has no prompt_file (falls back to default system prompt)")
            cap = rcfg.get("default_capability_mode")
            if cap and cap not in ALLOWED_CAPABILITIES:
                problems.append(
                    f"C4 role '{role}' invalid default_capability_mode '{cap}' "
                    f"(allowed: {', '.join(sorted(ALLOWED_CAPABILITIES))})"
                )

        # C5 — every referenced model must resolve
        refs: list[tuple[str, str]] = []
        default_model = cfg.get("models", {}).get("default") if isinstance(cfg.get("models"), dict) else None
        if default_model:
            refs.append(("models.default", default_model))
        fork_model = ui_cfg.get("fork_secondary_model")
        if fork_model:
            refs.append(("ui.fork_secondary_model", fork_model))
        for k, v in sub_models.items():
            if isinstance(v, str):
                refs.append((f"subagents.models.{k}", v))
        for where, m in sorted(refs):
            if m not in models:
                problems.append(f"C5 {where} references undefined model '{m}' — no [model.{m}] section")

        # D1 — doc vs config cross-check
        if doc_path.is_file():
            matrix = parse_role_matrix(doc_path.read_text(encoding="utf-8", errors="replace"))
            if not matrix:
                notes.append("D1 no Model-Role Matrix table found in doc — cross-check skipped")
            for role, doc_model in matrix:
                if role in roles:
                    cfg_model = roles[role].get("model")
                    if cfg_model and doc_model != cfg_model:
                        problems.append(
                            f"D1 role '{role}': doc says '{doc_model}', config says '{cfg_model}'"
                        )
                elif role in SPECIAL_DOC_ROLES:
                    keys = SPECIAL_DOC_ROLES[role]
                    node: object = cfg
                    for k in keys:
                        if isinstance(node, dict):
                            node = node.get(k)
                        else:
                            node = None
                    cfg_val = node if isinstance(node, str) else None
                    if cfg_val and doc_model != cfg_val:
                        problems.append(
                            f"D1 {role}: doc says '{doc_model}', config says '{cfg_val}'"
                        )
                elif re.match(r"^[a-z][a-z0-9-]*$", role):
                    # Reverse drift (RT-A2): doc documents a role config lacks.
                    # Note-level: the doc may legitimately describe future roles.
                    notes.append(f"D1 doc documents role '{role}' — not defined in [subagents.roles]")
                # unknown rows (documentation-only roles) are ignored
        else:
            notes.append(f"D1 doc not found: {doc_path} — cross-check skipped")

        # D2 — ROLE-REGISTRY (the dispatch front-door) vs config. Every registry
        # role must exist in config with a matching model + valid capability.
        registry_roles: set[str] = set()
        if registry_path.is_file():
            registry_rows = parse_registry_table(registry_path.read_text(encoding="utf-8", errors="replace"))
            if not registry_rows:
                notes.append("D2 no Registry table found in ROLE-REGISTRY.md — cross-check skipped")
            for role, rmodel, rcap, rprompt in registry_rows:
                if role == "(fork)":
                    fork_val = ui_cfg.get("fork_secondary_model")
                    if fork_val and rmodel != fork_val:
                        problems.append(f"D2 fork: registry says '{rmodel}', config says '{fork_val}'")
                    continue
                if role in ("explore", "(built-in explore)"):
                    cfg_model = sub_models.get("explore")
                    if cfg_model and rmodel != cfg_model:
                        problems.append(f"D2 explore: registry says '{rmodel}', config says '{cfg_model}'")
                    registry_roles.add("explore")
                    continue
                if role not in roles:
                    problems.append(f"D2 registry role '{role}' not defined in [subagents.roles]")
                    continue
                registry_roles.add(role)
                cfg_model = roles[role].get("model")
                if cfg_model and rmodel != cfg_model:
                    problems.append(f"D2 role '{role}': registry says '{rmodel}', config says '{cfg_model}'")
                if rcap and rcap not in ALLOWED_CAPABILITIES:
                    problems.append(f"D2 role '{role}' invalid registry capability '{rcap}'")
                if rprompt and rprompt.startswith("prompts/"):
                    pf = Path.home() / ".grok" / rprompt
                    if not pf.is_file():
                        problems.append(f"D2 role '{role}' registry prompt file missing: {pf}")
                # D2b — the routing layer: every registry role (except explore/fork,
                # which are builtin) must have a spawnable agent definition in
                # ~/.grok/agents/<role>.md (user-defined subagent types, verified
                # against the grok-build source: discovery scans ~/.grok/agents/).
                # Existence is NOT enough: an unparseable front-matter silently
                # drops the definition from discovery ("Unknown subagent type"),
                # so the front-matter is parsed and validated here too.
                ad = agents_dir / f"{role}.md"
                if not ad.is_file():
                    problems.append(
                        f"D2b role '{role}' has no agent definition {ad} — "
                        f"create it to make '{role}' a spawnable subagent type"
                    )
                else:
                    for p in parse_agent_definition(ad, role, models, rmodel, rcap):
                        problems.append(f"D2b role '{role}': {p}")
        else:
            notes.append(f"D2 registry not found: {registry_path} — cross-check skipped")

        # D2c — the dispatch workflow routes via `agent_type` (the same type
        # registry). A typo'd or renamed type silently fails its parallel slot
        # (or the whole panel); cross-check every literal agent_type the
        # workflow references — including its KNOWN_TYPES allowlist — against
        # the registry roles + builtin subagent types.
        if workflow_path.is_file():
            wf = workflow_path.read_text(encoding="utf-8", errors="replace")
            known = set(registry_roles) | {"general-purpose"}
            refs: list[str] = re.findall(r'agent_type:\s*"([^"]+)"', wf)
            allow_match = re.search(r"KNOWN_TYPES\s*=\s*\[([^\]]*)\]", wf)
            allow_set: set[str] = set()
            if allow_match:
                allow_set = {t.strip().strip('"') for t in allow_match.group(1).split(",") if t.strip().strip('"')}
                refs += sorted(allow_set)
            for t in sorted(set(refs)):
                if t not in known:
                    problems.append(
                        f"D2c workflow agent_type '{t}' is not a registry role or builtin "
                        f"(known: {', '.join(sorted(known)) or 'none'})"
                    )
            if allow_match:
                missing = sorted(registry_roles - allow_set - {"explore"})
                if missing:
                    notes.append(
                        f"D2c workflow KNOWN_TYPES omits registry roles: {', '.join(missing)} — "
                        f"those types must be dispatched via spawn_subagent, not this workflow"
                    )
        else:
            notes.append(f"D2c workflow not found: {workflow_path} — workflow type references not checked")

    # ── output ──
    for p in problems:
        print(f"  ❌ {p}")
    if not args.quiet:
        for n in notes:
            print(f"  ℹ️  {n}")

    if problems:
        print()
        print(f"CONFIG-DRIFT: {len(problems)} problem(s) — fix the doc or the config, then re-run.")
        return 1
    print()
    print("CONFIG-CONSISTENT: config.toml and ROLE-ARCHITECTURE.md agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
