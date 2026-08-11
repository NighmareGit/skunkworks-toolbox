#!/usr/bin/env python3
"""bootstrap.py — cross-platform MACHINE mint.

Fresh OS + grok install -> full orchestration hub, in one command. Mints, in order:

  1. the HUB        (grok-home: agent types, role registry/architecture, prompts,
                     workflows, config.toml from a sanitized example)
  2. the HUB WORKSPACE (projects-root: <root>/grok with agents.md + a GENERATED
                     config/projects.yaml registry of managed projects)
  3. optionally ONE PROJECT (toolchain copies + tests + agents.md + task-ledger seed)

Pure stdlib (argparse, pathlib, shutil, json, subprocess) — runs identically on
Linux/macOS/Windows. NO bash dependency. Every file it ships is a static payload or
a placeholder template ({{TOKENS}} substituted at mint time); it never clobbers
existing files unless --force.

Usage:
  python3 bootstrap.py --mint hub                                # hub + hub workspace
  python3 bootstrap.py --mint project --target <dir>             # one project (old bootstrap-project)
  python3 bootstrap.py --mint all --target <dir>                 # hub + workspace + one project
  python3 bootstrap.py --ensure-python                           # report Python; --install-python to install via uv

Options:
  --grok-home <dir>    grok home to mint the hub into (default ~/.grok)
  --root <dir>         projects root (default ~/projects)
  --hub-dir <dir>      hub workspace dir (default <root>/grok)
  --force              overwrite existing files (default: never clobber)
  --no-verify          skip the suite + sabotage verification
  --install-python     auto-install a Python >= 3.11 interpreter via uv if missing
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PY = (3, 11)


def script_dir() -> Path:
    src = Path(os.path.abspath(__file__))
    return src.parent


def skill_root() -> Path:
    return script_dir().parent


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    """Run a subprocess without a shell (Windows-safe)."""
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ensure_python(install: bool) -> int:
    ok = sys.version_info >= MIN_PY
    print(f"python: {sys.version.split()[0]} ({sys.executable})")
    if ok:
        print("OK — Python >= 3.11 present, the whole toolchain runs on this interpreter.")
        return 0
    print(f"NEED Python >= 3.{MIN_PY[1]} (found {sys.version.split()[0]})")
    if not install:
        print("Run with --install-python to install one via uv, or install Python 3.11+ yourself.")
        return 1
    # uv: one static cross-platform binary that installs standalone interpreters.
    if shutil.which("uv"):
        r = run(["uv", "python", "install", "3.12"])
        print(r.stdout or r.stderr)
        return 0 if r.returncode == 0 else 1
    print("uv not found — install it first:")
    print("  unix:   curl -LsSf https://astral.sh/uv/install.sh | sh")
    print("  powershell: irm https://astral.sh/uv/install.ps1 | iex")
    print("then re-run with --install-python.")
    return 1


def substitute(text: str, subs: dict) -> str:
    for k, v in subs.items():
        text = text.replace(k, v)
    return text


def copy_payload(src_dir: Path, dst_dir: Path, force: bool, label: str) -> int:
    """Copy a payload dir's contents into dst_dir; never clobber unless force."""
    copied = skipped = 0
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in sorted(src_dir.iterdir()):
        target = dst_dir / item.name
        if target.exists() and not force:
            skipped += 1
            continue
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
        copied += 1
    print(f"  {label}: {copied} written, {skipped} skipped (exist)")
    return copied


def mint_hub(grok_home: Path, root: Path, force: bool) -> int:
    ht = skill_root() / "hub-templates"
    print(f"── mint hub into {grok_home}")
    total = 0
    total += copy_payload(ht / "agents", grok_home / "agents", force, "agent types")
    total += copy_payload(ht / "prompts", grok_home / "prompts", force, "role prompts")
    total += copy_payload(ht / "workflows", grok_home / "workflows", force, "workflows")
    for f in ("ROLE-REGISTRY.md", "ROLE-ARCHITECTURE.md"):
        dst = grok_home / f
        if dst.exists() and not force:
            print(f"  {f}: skipped (exists)")
            continue
        shutil.copy2(ht / f, dst)
        total += 1
    # config.toml — machine-specific; from the sanitized example, placeholders filled.
    cfg = grok_home / "config.toml"
    if cfg.exists() and not force:
        print("  config.toml: skipped (exists)")
    else:
        ex = (ht / "config.toml.example").read_text(encoding="utf-8")
        cfg.write_text(substitute(ex, {"{{GROK_HOME}}": str(grok_home),
                                       "{{PROJECTS_ROOT}}": str(root)}), encoding="utf-8")
        print(f"  config.toml: written from sanitized example (api keys empty — fill them in)")
        total += 1
    # the skill itself (self-replication) so the minted hub has the full payload.
    sk = grok_home / "skills" / skill_root().name
    if sk.exists() and not force:
        print(f"  skills/{skill_root().name}: skipped (exists)")
    else:
        shutil.copytree(skill_root(), sk, dirs_exist_ok=True)
        total += 1
        print(f"  skills/{skill_root().name}: installed")
    print(f"  hub minted: {total} items")
    return 0


def mint_hub_workspace(root: Path, hub_dir: Path, force: bool) -> int:
    hw = skill_root() / "hub-templates" / "hub-workspace"
    print(f"── mint hub workspace at {hub_dir}")
    hub_dir.mkdir(parents=True, exist_ok=True)
    subs = {"{{GROK_HOME}}": str(Path.home() / ".grok"),
            "{{PROJECTS_ROOT}}": str(root)}
    ag = hub_dir / "agents.md"
    if ag.exists() and not force:
        print("  agents.md: skipped (exists)")
    else:
        ag.write_text(substitute((hw / "agents.md").read_text(encoding="utf-8"), subs),
                      encoding="utf-8")
        print("  agents.md: written")
    # projects.yaml — GENERATED by scanning the projects root (auto-discovery).
    reg = hub_dir / "config" / "projects.yaml"
    reg.parent.mkdir(parents=True, exist_ok=True)
    if reg.exists() and not force:
        print("  config/projects.yaml: skipped (exists)")
    else:
        lines = ["# Project Registry — generated by bootstrap.py (edit freely).",
                 "# Maps project names to paths + entry docs. Discovery is registry-first,",
                 "# then the <projects-root>/<name>/agents.md convention.",
                 "", "projects:"]
        for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            entry = (d / "agents.md") if (d / "agents.md").is_file() else "README.md"
            lines.append(f"  {d.name}:")
            lines.append(f"    path: {d}")
            lines.append(f"    agents_md: {entry.name}")
            lines.append(f"    description: (fill in)")
        reg.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  config/projects.yaml: generated ({len([l for l in lines if l.startswith('  ') and l.endswith(':')])} projects)")
    (hub_dir / "README.md").write_text(
        f"# {hub_dir.name} — orchestration hub\n\nSee `agents.md` (hub orientation).\n",
        encoding="utf-8") if not (hub_dir / "README.md").exists() or force else None
    return 0


def mint_project(target: Path, root: Path, force: bool) -> int:
    print(f"── mint project at {target}")
    sk = skill_root()
    target.mkdir(parents=True, exist_ok=True)
    total = copy_payload(sk / "scripts" / "toolchain", target / ".scratch" / "scripts",
                         force, "toolchain scripts")
    # tests + suite (Python — cross-platform; PROJECT resolved from env at run time)
    tests = target / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    suite_dst = tests / "run_toolchain_tests.py"
    if suite_dst.exists() and not force:
        print("  tests/run_toolchain_tests.py: skipped (exists)")
    else:
        shutil.copy2(sk / "scripts" / "run_toolchain_tests.py", suite_dst)
        os.chmod(suite_dst, 0o755)
        print("  tests/run_toolchain_tests.py: copied")
    # the dress-rehearsal scenario is invoked by the suite — copy it too
    scen_dst = tests / "scenario_dress_rehearsal.py"
    scen_src = sk / "scripts" / "scenario_dress_rehearsal.py"
    if scen_src.is_file():
        if scen_dst.exists() and not force:
            print("  tests/scenario_dress_rehearsal.py: skipped (exists)")
        else:
            shutil.copy2(scen_src, scen_dst)
            os.chmod(scen_dst, 0o755)
            print("  tests/scenario_dress_rehearsal.py: copied")
    # project agents.md from the placeholder template
    tmpl = sk / "templates" / "agents.md"
    proj_ag = target / "agents.md"
    if proj_ag.exists() and not force:
        print("  agents.md: skipped (exists)")
    else:
        subs = {"{{PROJECT_NAME}}": target.name,
                "{{MISSION}}": "(fill in the mission)",
                "{{REPO_LAYOUT}}": "(fill in)",
                "{{SECRETS_PATH}}": ".scratch/secrets",
                "{{MODEL_SERVER_URL}}": "http://127.0.0.1:8080"}
        proj_ag.write_text(substitute(tmpl.read_text(encoding="utf-8"), subs), encoding="utf-8")
        print("  agents.md: written from template (fill the {{...}} placeholders)")
    # empty task ledger seed
    ts = target / ".scratch" / "task-state"
    ts.mkdir(parents=True, exist_ok=True)
    ledger = ts / "TASKS.json"
    if not ledger.exists() or force:
        ledger.write_text(json.dumps({"tasks": {}}, indent=2) + "\n", encoding="utf-8")
    return total


def verify(target: Path) -> int:
    print("── verify")
    suite = target / "tests" / "run_toolchain_tests.py"
    if not suite.is_file():
        print("  suite not found — skipping verification.")
        return 1
    # Python suite — cross-platform (no bash needed); PROJECT pinned to the mint.
    env = dict(os.environ)
    env["PROJECT"] = str(target)
    r = run([sys.executable, str(suite)], cwd=str(target), env=env)
    print((r.stdout or "")[-600:])
    if r.returncode != 0:
        print("  ❌ suite FAILED")
        return 1
    print("  ✅ suite passed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mint", choices=["hub", "project", "all"], help="what to mint")
    ap.add_argument("--target", help="project dir (mint project/all)")
    ap.add_argument("--grok-home", default=str(Path.home() / ".grok"))
    ap.add_argument("--root", default=str(Path.home() / "projects"))
    ap.add_argument("--hub-dir")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--ensure-python", action="store_true")
    ap.add_argument("--install-python", action="store_true")
    args = ap.parse_args()

    if args.ensure_python:
        return ensure_python(args.install_python)

    rc = ensure_python(False)
    if rc != 0:
        print("(pass --install-python to install one via uv)")
        return 1

    root = Path(args.root)
    grok_home = Path(args.grok_home)
    hub_dir = Path(args.hub_dir) if args.hub_dir else root / "grok"

    if args.mint in ("hub", "all"):
        mint_hub(grok_home, root, args.force)
        mint_hub_workspace(root, hub_dir, args.force)
    if args.mint in ("project", "all"):
        if not args.target:
            print("ERROR: --target <dir> required for --mint project/all", file=sys.stderr)
            return 2
        mint_project(Path(args.target), root, args.force)

    print("")
    print("=== BOOTSTRAP: DONE ===")
    print(f"  hub          : {grok_home} (agents, registry, prompts, workflows, config.toml)")
    print(f"  hub workspace: {hub_dir} (agents.md + config/projects.yaml)")
    if args.mint in ("project", "all"):
        print(f"  project      : {args.target} (.scratch/scripts + tests + agents.md)")
    print("  next: fill config.toml api keys, fill agents.md placeholders, then:",
          "hub-scan.py --project <name> to open a project, or run a session handoff drill.")

    if args.mint in ("project", "all") and not args.no_verify:
        return verify(Path(args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
