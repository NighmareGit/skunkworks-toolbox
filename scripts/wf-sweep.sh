#!/bin/bash
# wf-sweep.sh — sweep orphaned workload processes left behind by cancelled/dead workflow runs.
#
# WHY: cancelling a workflow (or a host restart) marks runs cancelled/leaves state stale,
# but does NOT kill the agents' subprocesses — they keep running (FMD legs, benchmark
# scripts, agent shell loops) and duplicate spend or corrupt outputs. This sweep finds
# them so you can decide.
#
# Usage:
#   bash wf-sweep.sh --pattern "benchmarks.py"                # dry-run: list only
#   bash wf-sweep.sh --pattern "benchmarks.py" --kill         # TERM matching processes
#   bash wf-sweep.sh --pattern "benchmarks.py" --exclude "run_lsv2_local" --kill
#
# NEVER matches this script itself. Kill is per-PID (TERM, no -9, no process groups) —
# the harness and your own runner are safe as long as they don't match --pattern.
set -u

PATTERN=""
EXCLUDE=""
KILL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --pattern) PATTERN="$2"; shift 2 ;;
    --exclude) EXCLUDE="$2"; shift 2 ;;
    --kill)    KILL=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$PATTERN" ]; then
  echo "usage: bash wf-sweep.sh --pattern <regex> [--exclude <regex>] [--kill]" >&2
  exit 2
fi

SELF=$$
MATCHES=$(ps -eo pid,ppid,args \
  | awk -v pat="$PATTERN" -v excl="$EXCLUDE" -v self="$SELF" '
      NR == 1 { next }
      $1 == self { next }
      $0 ~ pat && (excl == "" || $0 !~ excl) { print }
    ')

if [ -z "$MATCHES" ]; then
  echo "wf-sweep: no processes match '$PATTERN'"${EXCLUDE:+ (excluding '$EXCLUDE')}
  exit 0
fi

echo "wf-sweep: $([ "$KILL" = 1 ] && echo "killing" || echo "found (dry-run)") processes matching '$PATTERN'"${EXCLUDE:+ (excluding '$EXCLUDE')}
echo "$MATCHES"
COUNT=$(echo "$MATCHES" | wc -l)

if [ "$KILL" = 1 ]; then
  # TERM only the PIDs we listed (column 1); never -9, never process groups.
  echo "$MATCHES" | awk '{print $1}' | xargs -r kill
  echo "wf-sweep: sent TERM to $COUNT process(es) — verify with --pattern '$PATTERN' (no --kill)"
fi
