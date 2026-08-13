#!/usr/bin/env python3
"""adr-log.py — Architecture Decision Record (ADR) logger [port of adr-log.sh].

decision-log.sh records OPERATIONAL dispatch outcomes. Architecture decisions
(why Ternary-Bonsai over X, why depth<=3, why a capability is read-only) need
a separate, stable, numbered record that implementation must respect. This is
that record.

Usage:
  adr-log.py --add --title "Title" --context "..." --decision "..." --consequences "..." [--status Proposed|Accepted|Deprecated] [--dir <path>]
  adr-log.py --list [--dir <path>]
  adr-log.py --show NNN [--dir <path>]

Options:
  --dir <path>   ADR directory (default: docs/adr relative to cwd)
  --status       one of Proposed (default) | Accepted | Deprecated

Exit codes:
  0 = ok
  1 = validation / write error
  2 = usage error
"""

import argparse
import datetime
import os
import re
import sys
import time
from pathlib import Path


STATUS_CHOICES = ("Proposed", "Accepted", "Deprecated")
LIST_ID_WIDTH = 12   # printf '%-12s' for the ID column (ADR-<n> left-justified)
STATUS_WIDTH = 11    # printf '%-11s' for the STATUS column


def usage() -> str:
    """Mirror bash usage(): docstring body with leading '#' stripped."""
    out = []
    for line in __doc__.splitlines()[2:40]:
        if line.startswith("# "):
            out.append(line[2:])
        elif line.startswith("#"):
            out.append(line[1:])
        else:
            out.append(line)
    return "\n".join(out)


def next_number(dir_path: Path) -> int:
    """Max existing ADR-<n> + 1. Never reuses numbers even if gaps exist."""
    max_n = 0
    for f in dir_path.glob("ADR-*.md"):
        m = re.match(r"^ADR-0*(\d+)-", f.name)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return max_n + 1


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    s = s[:60]
    return s if s else "decision"


def acquire_lock(dir_path: Path) -> Path | None:
    """mkdir-based lock (same pattern as task-state.py). Retries ~5s."""
    lock = dir_path / ".lock"
    tries = 0
    while True:
        try:
            os.mkdir(lock)
            return lock
        except FileExistsError:
            tries += 1
            if tries >= 10:
                print(f"ERROR: could not acquire lock {lock} (another adr-log running?)",
                      file=sys.stderr)
                return None
        time.sleep(0.5)


def release_lock(lock: Path | None) -> None:
    if lock is None:
        return
    try:
        os.rmdir(lock)
    except OSError:
        pass


def extract_title(path: Path) -> str:
    """grep -m1 '^# ADR-[0-9]+: ' | sed 's/^# ADR-[0-9]+: //'."""
    text = path.read_text(errors="replace")
    m = re.search(r"^# ADR-\d+: (.*)$", text, re.MULTILINE)
    return m.group(1) if m else "?"


def extract_status(path: Path) -> str:
    """grep -m1 '^[-*] Status: ' | sed 's/^[-*] Status: //'."""
    text = path.read_text(errors="replace")
    m = re.search(r"^[-*] Status: (.*)$", text, re.MULTILINE)
    return m.group(1) if m else "?"


def cmd_list(dir_path: Path) -> int:
    if not dir_path.is_dir():
        print(f"No ADRs yet (dir {dir_path} does not exist).")
        return 0
    print(f"ADR directory: {dir_path}")
    print(f"{'ID':<{LIST_ID_WIDTH}} {'STATUS':<{STATUS_WIDTH}} TITLE")
    print(f"{'--':<{LIST_ID_WIDTH}} {'------':<{STATUS_WIDTH}} -----")
    for f in sorted(dir_path.glob("ADR-*.md")):
        m = re.match(r"^ADR-0*(\d+)-", f.name)
        # sed strips leading zeros, so ADR-003 -> "3"
        num = str(int(m.group(1))) if m else "?"
        title = extract_title(f)
        st = extract_status(f)
        # printf 'ADR-%-8s %-11s %s\n' -> "ADR-" + num left-justified in 8
        print(f"ADR-{num:<8} {st:<{STATUS_WIDTH}} {title}")
    return 0


def cmd_show(dir_path: Path, nnn: str) -> int:
    if not nnn:
        print("ERROR: --show requires a number, e.g. --show 3", file=sys.stderr)
        return 2
    if not re.fullmatch(r"\d+", nnn):
        print(f"ERROR: --show requires a numeric ADR number, got '{nnn}'", file=sys.stderr)
        return 2
    pad = f"{int(nnn):03d}"
    match = None
    # R5: match both ADR-<PAD>-<slug>.md (canonical) and ADR-<PAD>.md (slug-less)
    for f in sorted(dir_path.glob(f"ADR-{pad}*.md")):
        match = f
        break
    if match is None:
        print(f"ERROR: no ADR-{pad} found in {dir_path}", file=sys.stderr)
        return 1
    sys.stdout.write(match.read_text(errors="replace"))
    return 0


def cmd_add(dir_path: Path, args) -> int:
    if not args.title or not args.decision:
        print("ERROR: --add requires --title and --decision", file=sys.stderr)
        return 2

    # RT-C2 fix: collapse newlines so a crafted value cannot inject front-matter
    # lines (e.g. $'Bogus\n- Status: Accepted') into the ADR record.
    title = args.title.replace("\n", " ")
    context = (args.context or "").replace("\n", " ")
    decision = args.decision.replace("\n", " ")
    consequences = (args.consequences or "").replace("\n", " ")

    dir_path.mkdir(parents=True, exist_ok=True)

    lock = acquire_lock(dir_path)
    if lock is None:
        return 1

    try:
        num = next_number(dir_path)
        pad = f"{num:03d}"
        slug = slugify(title)
        file_path = dir_path / f"ADR-{pad}-{slug}.md"
        tmp_path = dir_path / f".ADR-{pad}-{slug}.tmp"
        date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        content = (
            f"# ADR-{pad}: {title}\n"
            "\n"
            f"- Status: {args.status}\n"
            f"- Date: {date}\n"
            "\n"
            "## Context\n"
            "\n"
            f"{context if context else '_no context recorded_'}\n"
            "\n"
            "## Decision\n"
            "\n"
            f"{decision}\n"
            "\n"
            "## Consequences\n"
            "\n"
            f"{consequences if consequences else '_none recorded_'}\n"
        )
        tmp_path.write_text(content)
        os.replace(tmp_path, file_path)

        # Best-effort derived index (--list re-derives from files, so a stale
        # index self-heals; a failed index write never fails the add).
        try:
            readme = dir_path / "README.md"
            if not readme.exists():
                readme.write_text(
                    "# Architecture Decision Records\n"
                    "\n"
                    "Numbered, stable decisions. See `adr-log.sh --list` for the live index.\n"
                    "\n"
                    f"{'ID':<{LIST_ID_WIDTH}} {'STATUS':<{STATUS_WIDTH}} {'DATE':<12} TITLE\n"
                    f"{'--':<{LIST_ID_WIDTH}} {'------':<{STATUS_WIDTH}} {'----':<12} -----\n"
                )
            with readme.open("a", newline="") as fh:
                fh.write(f"ADR-{pad:<8} {args.status:<{STATUS_WIDTH}} {date:<12} {title}\n")
        except OSError:
            pass
    finally:
        release_lock(lock)

    print(f"ADR written: {file_path}")
    print(f"  Status: {args.status} | Date: {date}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], add_help=False)
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", nargs="?", const="", default=None)
    ap.add_argument("--dir", default="docs/adr")
    ap.add_argument("--status", default="Proposed")
    ap.add_argument("--title")
    ap.add_argument("--context")
    ap.add_argument("--decision")
    ap.add_argument("--consequences")
    ap.add_argument("--help", "-h", action="store_true")

    args, unknown = ap.parse_known_args(argv)

    if args.help:
        print(usage())
        return 0

    if unknown:
        print(f"ERROR: Unknown arg: {unknown[0]}")
        print(usage())
        return 2

    if args.status not in STATUS_CHOICES:
        print(f"ERROR: invalid --status '{args.status}' (use {'|'.join(STATUS_CHOICES)})")
        return 2

    dir_path = Path(args.dir)

    if args.add:
        return cmd_add(dir_path, args)
    if args.list:
        return cmd_list(dir_path)
    if args.show is not None:
        return cmd_show(dir_path, args.show)

    print("ERROR: no action given (--add | --list | --show)", file=sys.stderr)
    print(usage(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
