#!/bin/bash
# push-github.sh — the ONLY sanctioned way to push the public GitHub mirror.
#
# Why: the repo carries gitea-only paths (scripts/gitea-only.txt) that must never
# reach the public mirror. A direct `git push github master` is refused by the
# pre-push hook. This script:
#   1. builds a temp worktree at HEAD,
#   2. removes the gitea-only paths there,
#   3. runs the sanitize scan on the filtered tree (must pass),
#   4. pushes the filtered branch to github/master,
#   5. cleans up the temp worktree + branch.
#
# Contract: AGENTS.md §"Gitea-only files". Run from the repo root.
set -eu

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "push-github: not in a git repo — abort" >&2; exit 1; }
cd "$REPO"

# --- sanity: gitea-only registry must exist ---
[ -f scripts/gitea-only.txt ] || { echo "missing scripts/gitea-only.txt — abort"; exit 1; }

# --- collect gitea-only paths ---
GITEA_ONLY=()
while IFS= read -r line; do
  case "$line" in
    ''|\#*) continue ;;
    *) GITEA_ONLY+=("$line") ;;
  esac
done < scripts/gitea-only.txt

BRANCH="gh-push-filter"
WORKTREE="$(mktemp -d /tmp/toolbox-gh-XXXXXX)"

cleanup() {
  git worktree remove --force "$WORKTREE" 2>/dev/null || true
  git branch -D "$BRANCH" 2>/dev/null || true
  rm -rf "$WORKTREE"
}
trap cleanup EXIT

# --- filtered worktree at HEAD ---
git branch -D "$BRANCH" 2>/dev/null || true   # stale branch from a crashed run
git worktree add --detach "$WORKTREE" HEAD >/dev/null
git -C "$WORKTREE" checkout -qb "$BRANCH"

# --- remove gitea-only paths ---
for path in "${GITEA_ONLY[@]}"; do
  [ -e "$WORKTREE/$path" ] || { echo "⚠️  gitea-only path not present in tree (already excluded?): $path"; continue; }
  git -C "$WORKTREE" rm -rq --ignore-unmatch "$path"
done

# --- the gate: sanitize scan on the FILTERED tree (must be clean) ---
echo "== sanitize scan on the filtered tree =="
if ! (cd "$WORKTREE" && bash scripts/sanitize-check.sh); then
  echo "⛔ push-github aborted: sanitize scan failed on the filtered tree. Fix leaks, then re-run."
  exit 1
fi

# --- commit the exclusion ---
if git -C "$WORKTREE" diff --cached --quiet; then
  echo "== no gitea-only paths to filter — pushing the tree as-is =="
else
  git -C "$WORKTREE" commit -q -m "chore(gitea-only): exclude $(echo "${GITEA_ONLY[*]}" | tr ' ' ',') from the public mirror"
fi

# --- push to github (hook passes: filtered tree has no gitea-only paths) ---
echo "== pushing to github =="
git push github "$BRANCH:master"

echo ""
echo "✅ pushed filtered tree to github/master (gitea-only paths excluded)."
echo "   gitea continues to carry the full tree — never push github directly."
