#!/usr/bin/env bash
# Atomic mkdir-based locks (build / source / gpu-N) for parallel sub-agents that
# share physical resources. Generalized — point LOCK_DIR at the project's lock dir.
# Usage:
#   source lock.sh
#   acquire_lock <name> <timeout_secs>   # e.g. acquire_lock build 600
#   ... work ...
#   release_lock <name>
LOCK_DIR="${LOCK_DIR:-.scratch/locks}"

acquire_lock() {
  local name="$1" timeout="${2:-120}" waited=0
  local lock="$LOCK_DIR/$name.lock"
  while ! mkdir "$lock" 2>/dev/null; do
    if [ "$waited" -ge "$timeout" ]; then echo "TIMEOUT acquiring lock: $name"; return 1; fi
    sleep 1; waited=$((waited + 1))
  done
  printf '%s' "$$" > "$lock/pid"
  echo "lock acquired: $name"
}

release_lock() { rm -rf "$LOCK_DIR/$1.lock"; echo "lock released: $1"; }
