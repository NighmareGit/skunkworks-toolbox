#!/usr/bin/env python3
"""tool_common.py — shared helpers for the ported tool_*.py modules (stdlib only).

Verifier-driven hardening (stage-1 port review): the bash `mv -n` semantics
cross a filesystem boundary by copy+unlink; a bare `os.rename` raises EXDEV and
silently fails. `move_noclobber` restores that behavior while keeping the
"never clobber a pre-existing target" guarantee on every path.
"""

import os
import shutil


def move_noclobber(src: str, dst: str) -> bool:
    """`mv -n` semantics with cross-filesystem support.

    NEVER overwrites an existing dst.

    - Fast path: `os.rename` (atomic within one filesystem; same TOCTOU window
      as GNU `mv -n`, which is also a check-then-rename).
    - On OSError (e.g. EXDEV across devices/network mounts): fall back to an
      exclusive-create (`O_EXCL`) copy + unlink, so a dst that appears between
      the exists-check and the copy is never clobbered.

    Success = dst exists AND src is gone (M4: the source-GONE test, matching
    `mv -n`'s skip behavior — a pre-existing target reports as failure here).
    """
    if os.path.islink(dst) or os.path.exists(dst):
        return False
    try:
        os.rename(src, dst)
    except OSError:
        # Cross-filesystem or transient error — copy, never overwriting.
        try:
            fd = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return False  # dst appeared concurrently — do not clobber
        try:
            with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
                shutil.copyfileobj(inp, out)
        except OSError:
            try:
                os.unlink(dst)
            except OSError:
                pass
            return False
        try:
            os.unlink(src)
        except OSError:
            pass
    return os.path.exists(dst) and not os.path.exists(src)
