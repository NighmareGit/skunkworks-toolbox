#!/usr/bin/env python3
"""tool_fixworkdir.py — Move files from wrong project directory to correct one.

Usage:
  tool_fixworkdir.py <search_dir> <target_dir> [pattern]

Examples:
  tool_fixworkdir.py /path/to/wrong-project/docs /path/to/correct-project/docs "*.md"

R1 (portable): NO hardcoded default project pair. Guessing the pair could
move files between the WRONG directories (data corruption). Explicit args or
the WRONG_PROJECT_SOURCE / WRONG_PROJECT_TARGET env pair are required.

Exit codes:
  0 = ok
  2 = arg error / search dir missing
  otherwise = error count
"""

import argparse
import fnmatch
import os
import sys

from tool_common import move_noclobber


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("search_dir", nargs="?", default=os.environ.get("WRONG_PROJECT_SOURCE"))
    ap.add_argument("target_dir", nargs="?", default=os.environ.get("WRONG_PROJECT_TARGET"))
    ap.add_argument("pattern", nargs="?", default="*.md")
    args = ap.parse_args(argv)

    search_dir = args.search_dir
    target_dir = args.target_dir
    pattern = args.pattern

    if not search_dir or not target_dir:
        print("ERROR: toolchain.py fix-workdir requires explicit <search_dir> <target_dir> args", file=sys.stderr)
        print("  (or WRONG_PROJECT_SOURCE / WRONG_PROJECT_TARGET env). Refusing to guess.", file=sys.stderr)
        return 2
    if not os.path.isdir(search_dir):
        print(f"ERROR: search dir does not exist: {search_dir}", file=sys.stderr)
        return 2

    print("=== Fix Working Directory ===")
    print(f"Search: {search_dir}/{pattern}")
    print(f"Target: {target_dir}")
    print("")

    moved = 0
    errors = 0

    # Normalize search dir (strip trailing separator) so relpath matches the
    # bash ${file#$SEARCH_DIR/} prefix strip.
    search_dir_norm = os.path.normpath(search_dir)

    for root, dirs, files in os.walk(search_dir_norm):
        for name in files:
            if not fnmatch.fnmatch(name, pattern):
                continue
            file = os.path.join(root, name)
            rel_path = os.path.relpath(file, search_dir_norm)
            target_file = os.path.join(target_dir, rel_path)
            target_subdir = os.path.dirname(target_file)

            # Skip if source and target are the same
            if os.path.normpath(file) == os.path.normpath(target_file):
                continue

            print(f"Found: {file}")
            print(f"  → {target_file}")

            # Create target directory if needed
            if not os.path.isdir(target_subdir):
                os.makedirs(target_subdir, exist_ok=True)
                print(f"  Created dir: {target_subdir}")

            # Move the file (never clobber existing targets).
            # M4 fix: success = source is GONE (mv -n returns 0 even when it skips a
            # pre-existing target, so testing target-exists reports false "MOVED").
            # move_noclobber = mv -n semantics + EXDEV-safe copy fallback.
            if move_noclobber(file, target_file):
                print("  MOVED")
                moved += 1
            else:
                print("  SKIPPED/FAILED (target exists or move error)")
                errors += 1
            print("")

    print("=== Summary ===")
    print(f"Moved: {moved}")
    print(f"Errors: {errors}")

    if moved > 0:
        print("")
        print("Files moved successfully. Verify with:")
        print(f"  find '{target_dir}' -name '{pattern}' -type f | wc -l")

    return errors


if __name__ == "__main__":
    sys.exit(main())
