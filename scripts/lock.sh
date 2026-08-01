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
  local name="$1" timeout="${2:-120}"
  local lock="$LOCK_DIR/$name.lock"
  local deadline=$(( $(date +%s) + timeout ))
  while (( $(date +%s) < deadline )); do
    if mkdir "$lock" 2>/dev/null; then
      printf '%s' "$$" > "$lock/pid"
      echo "lock acquired: $name"
      return 0
    fi
    # Stale-lock recovery: if the holder pid is dead (agent killed mid-hold,
    # e.g. session kill), reap the lock instead of spinning until timeout.
    local holder_pid=""
    [ -f "$lock/pid" ] && holder_pid=$(cat "$lock/pid" 2>/dev/null)
    if [ -n "$holder_pid" ] && ! kill -0 "$holder_pid" 2>/dev/null; then
      echo "reaping stale $name lock (holder pid $holder_pid dead)" >&2
      rm -rf "$lock"
      continue
    fi
    sleep 1
  done
  echo "TIMEOUT acquiring lock: $name" >&2
  return 1
}

release_lock() { rm -rf "$LOCK_DIR/$1.lock"; echo "lock released: $1"; }
