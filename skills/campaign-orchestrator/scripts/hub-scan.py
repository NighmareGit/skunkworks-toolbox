#!/usr/bin/env python3
"""hub-scan.py — from the grok HUB, list every project with campaign/dispatch
state and its next action. Turns the hub workspace into the control room:
   python3 hub-scan.py                          # scan projects registered in config/projects.yaml
   python3 hub-scan.py --root ~/projects        # or scan a projects root directly
   python3 hub-scan.py --workspace <dir>        # explicit hub workspace (default: os.getcwd())

Port of hub-scan.sh to stdlib-only Python. Resolves its own toolchain location,
no hardcoded paths / no shell=True. For each project prints: dispatch-task
count, state summary, and the ONE-LINE next action a fresh session would take.
Exit 0 always (except --project not found -> 1, unknown arg -> 2).
"""

import os
import subprocess
import sys
from pathlib import Path

STATE_PY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "toolchain", "dispatch-state.py"
)


def usage(prog: str) -> str:
    return (
        f"Usage: {prog} [--workspace <dir>] [--root <projects-root>] [--projects-yaml <path>]\n"
        f"                      [--project <name>]\n"
        "\n"
        "  --workspace <dir>      hub workspace to read config/projects.yaml from (default: os.getcwd())\n"
        "  --root <dir>           scan a projects root directly instead of the yaml registry\n"
        "  --projects-yaml <path> explicit project registry (default: <workspace>/config/projects.yaml)\n"
        "  --project <name>       resolve ONE project by name (registry first, then\n"
        "                         <projects-root>/<name> convention) and print its path,\n"
        "                         agents.md location, and next action — for \"read agents.md\n"
        "                         from project xyz\"\n"
    )


def run_state(subcmd: str, cwd: str) -> str:
    """Run STATE_PY <subcmd> --cwd <cwd>; return stdout (empty on error)."""
    try:
        r = subprocess.run(
            [sys.executable, STATE_PY, subcmd, "--cwd", cwd],
            capture_output=True,
            text=True,
            check=False,
        )
        return r.stdout
    except OSError:
        return ""


def run_state_first_line(subcmd: str, cwd: str) -> str:
    out = run_state(subcmd, cwd)
    for line in out.splitlines():
        return line
    return ""


def parse_yaml_paths(yaml_path: str) -> list[str]:
    """Parse `path:` lines from the yaml registry (simple line parser, no yaml dep)."""
    paths: list[str] = []
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n").rstrip("\r")
                if "path:" in line:
                    p = line.split("path:", 1)[1]
                    p = p.strip()
                    p = p.replace("~", str(Path.home()))
                    if os.path.isdir(p):
                        paths.append(p)
    except OSError:
        pass
    return paths


def resolve_project(want: str, yaml_path: str, root: str) -> tuple[str, str] | None:
    """Resolve ONE project by name. Returns (proj_dir, agents_md) or None."""
    proj = ""
    agents_md = "agents.md"

    # registry first: find the block whose `name:` matches
    if yaml_path and os.path.isfile(yaml_path):
        block = ""
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.rstrip("\n").rstrip("\r")
                    # block header: "  <name>:" (two spaces, anything, colon at end)
                    if line.startswith("  ") and line.rstrip().endswith(":"):
                        # a new project entry — check the previous block
                        if block and block == want:
                            break
                        header = line
                        if header.endswith(":"):
                            header = header[:-1]  # strip trailing colon
                        block = header.replace(" ", "")
                    elif "path:" in line and block == want:
                        p = line.split("path:", 1)[1]
                        p = p.lstrip()
                        p = p.replace("~", str(Path.home()))
                        if p.endswith("/"):
                            p = p[:-1]  # strip one trailing slash (bash: ${p%/})
                        proj = p
                    elif "agents_md:" in line and block == want:
                        agents_md = line.split("agents_md:", 1)[1].lstrip()
        except OSError:
            pass

    # convention against the given root
    if not proj and root and os.path.isdir(os.path.join(root, want)):
        proj = os.path.join(root, want)
    # default convention <HOME>/projects/<name>
    elif not proj and os.path.isdir(os.path.join(str(Path.home()), "projects", want)):
        proj = os.path.join(str(Path.home()), "projects", want)

    if not proj or not os.path.isdir(proj):
        return None
    return proj, agents_md


def count_briefs(proj: str) -> int:
    briefs_dir = os.path.join(proj, ".scratch", "dispatch-briefs")
    if not os.path.isdir(briefs_dir):
        return 0
    n = 0
    for dirpath, dirnames, filenames in os.walk(briefs_dir):
        for fn in filenames:
            if fn == "brief.json":
                n += 1
    return n


def cmd_project(want: str, yaml_path: str, root: str) -> int:
    result = resolve_project(want, yaml_path, root)
    if result is None:
        y = yaml_path or "none"
        print(
            f"ERROR: project '{want}' not found (registry {y}, nor <root>/{want})",
            file=sys.stderr,
        )
        return 1
    proj, agents_md = result
    print(f"=== PROJECT: {want} ===")
    print(f"  path      : {proj}")
    print(f"  agents.md : {proj}/{agents_md}")
    print()
    next_line = run_state_first_line("next-action", proj)
    print(f"  next      : {next_line or 'no campaign state'}")
    print()
    print(
        f"  → tell the agent: read {proj}/{agents_md}, then operate with --cwd {proj}"
    )
    return 0


def cmd_scan(candidates: list[str], yaml_path: str) -> int:
    print("=== GROK HUB — project scan ===")
    print()

    if not candidates:
        print(f"No projects found (no registry at {yaml_path} and no --root given).")
        return 0

    found = 0
    for proj in candidates:
        proj = proj.rstrip("/")
        name = os.path.basename(proj)
        nbriefs = count_briefs(proj)
        ledger = os.path.join(proj, ".scratch", "task-state", "TASKS.json")
        found += 1

        if nbriefs == 0 and not os.path.isfile(ledger):
            print(f"── {name} ({proj})  — no campaign state (managed, not active)")
            print()
            continue

        print(f"── {name} ({proj})")
        print(f"   dispatches: {nbriefs}")
        if nbriefs > 0:
            status_out = run_state("status", proj)
            lines = status_out.splitlines()
            # skip first 2 header lines, indent each remaining line 3 spaces
            for line in lines[2:]:
                print(f"   {line}")
        next_line = run_state_first_line("next-action", proj)
        print(f"   next: {next_line or 'no campaign state'}")
        print()

    if found == 0:
        print("No projects with campaign state found under the scanned locations.")

    print("=== how to work from the hub ===")
    print("  - target one project:  every toolchain command takes --cwd <project> (e.g.")
    print("    toolchain.py dispatch --mode handoff --cwd ~/projects/atomic-grinder)")
    print("  - or cd into the project and use its own .scratch/scripts/ (identical copies)")
    print("  - session handoff: 'we need a new session' -> run --mode handoff --cwd <project>")
    return 0


def main(argv=None) -> int:
    prog = "hub-scan.py"
    args = argv if argv is not None else sys.argv[1:]

    workspace = os.getcwd()
    root = ""
    yaml_path = ""
    want = ""

    # manual arg parse to match the bash exactly (unknown -> usage + exit 2)
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            print(usage(prog))
            return 0
        if a == "--workspace":
            workspace = args[i + 1]
            i += 2
        elif a == "--root":
            root = args[i + 1]
            i += 2
        elif a == "--projects-yaml":
            yaml_path = args[i + 1]
            i += 2
        elif a == "--project":
            want = args[i + 1]
            i += 2
        else:
            print(f"ERROR: unknown arg {a}")
            print(usage(prog))
            return 2

    # default yaml / fallback root
    if not root:
        if not yaml_path:
            yaml_path = os.path.join(workspace, "config", "projects.yaml")
        if not os.path.isfile(yaml_path):
            root = os.path.join(str(Path.home()), "projects")

    if want:
        return cmd_project(want, yaml_path, root)

    # scan mode: collect candidate project dirs
    candidates: list[str] = []
    if root:
        for entry in sorted(os.listdir(root)):
            full = os.path.join(root, entry)
            if os.path.isdir(full):
                candidates.append(full)
    elif yaml_path and os.path.isfile(yaml_path):
        candidates = parse_yaml_paths(yaml_path)

    return cmd_scan(candidates, yaml_path)


if __name__ == "__main__":
    sys.exit(main())
