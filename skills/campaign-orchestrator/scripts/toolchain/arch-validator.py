#!/usr/bin/env python3
"""arch-validator.py — validate an architecture/scaffolding doc BEFORE implementation starts.

The architect produces scaffolding docs, but nothing previously checked they were
complete before an implementer started: a doc missing its I/O contract or test
cases flows downstream as garbage. This is the pre-implementation gate.

Checks:
  V1  every required markdown section is present (header match, case-insensitive)
  V2  doc meets a minimum size
  V3  no placeholder tokens ([TODO], [TBD], lorem ipsum, "coming soon", ...)

Usage:
  arch-validator.py <doc.md>
      [--required Goal,Approach,I/O Contract,Test Cases,Risks]
      [--min-bytes 500]
      [--no-placeholders]     # skip the placeholder-token check

Exit codes:
  0 = valid (ready for implementation)
  1 = violations found (list printed; fix before implementing)
  2 = usage / IO error
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_REQUIRED = ["Goal", "Approach", "I/O Contract", "Test Cases", "Risks"]
DEFAULT_MIN_BYTES = 200  # header-only stubs run ~50-80B; genuine content clears this easily

# Bracket forms are unambiguous placeholders; bare words are suspicious.
# RT-B1 fix: bare `\btodo\b` is NOT a violation — `## Todo` is a legitimate
# section header. Likewise bare "placeholder" / "coming soon" appear in normal
# prose ("no placeholder markers") — only bracket forms and unambiguous filler
# phrases flag.
PLACEHOLDER_RE = re.compile(
    r"\[(?:TODO|TBD|FIXME|XXX|INSERT|PLACEHOLDER|COMING\s+SOON)\]"
    r"|\blorem ipsum\b"
    r"|\bfill me in\b"
    r"|\bunder construction\b"
    r"|\b(?:tbd|fixme)\b",
    re.IGNORECASE,
)


def find_section(text: str, name: str) -> re.Match | None:
    """Match a markdown header whose text starts with the section name."""
    pat = re.compile(
        rf"^#{{1,6}}\s+{re.escape(name)}\b.*$",
        re.IGNORECASE | re.MULTILINE,
    )
    return pat.search(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("doc", help="path to the architecture doc (.md)")
    ap.add_argument("--required", default=",".join(DEFAULT_REQUIRED),
                    help="comma-separated required section names (default: %(default)s)")
    ap.add_argument("--min-bytes", type=int, default=DEFAULT_MIN_BYTES)
    ap.add_argument("--no-placeholders", action="store_true",
                    help="skip the placeholder-token check")
    args = ap.parse_args()

    doc = Path(args.doc)
    if not doc.is_file():
        print(f"  ❌ V0 doc not found: {doc}")
        return 2

    try:
        text = doc.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"  ❌ V0 cannot read {doc}: {e}")
        return 2

    required = [s.strip() for s in args.required.split(",") if s.strip()]
    violations: list[str] = []

    # V1 — required sections
    for name in required:
        if not find_section(text, name):
            violations.append(f"missing required section: '{name}' (use a markdown header like '## {name}')")

    # V2 — min size
    size = len(text.encode("utf-8"))
    if size < args.min_bytes:
        violations.append(f"too small: {size} bytes < {args.min_bytes} min — a scaffolding doc at this size "
                          f"has no real content")

    # V3 — placeholders
    if not args.no_placeholders:
        for lineno, line in enumerate(text.splitlines(), 1):
            m = PLACEHOLDER_RE.search(line)
            if m:
                snippet = line.strip()[:100]
                violations.append(f"line {lineno}: placeholder token '{m.group(0)}' → {snippet!r}")

    for v in violations:
        print(f"  ❌ {v}")

    if violations:
        print()
        print(f"ARCH-INVALID: {len(violations)} violation(s) — resolve before implementation "
              f"(re-run with --no-placeholders to ignore TODO markers, or --required to adjust sections).")
        return 1

    print(f"ARCH-VALID: {doc} — {len(required)} required section(s) present, {size} bytes, "
          "no placeholder tokens.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
