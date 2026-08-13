#!/bin/bash
# pre-push.sh — pre-push hook for the skunkworks-toolbox repo.
# Installed as .git/hooks/pre-push (copy or symlink). Refuses ANY push to the public
# GitHub mirror while gitea-only paths (scripts/gitea-only.txt) are present in the
# pushed tree. The only sanctioned GitHub push is scripts/push-github.sh, which
# builds a filtered tree and pushes that.
#
# Contract: AGENTS.md §"Gitea-only files". Gitea (LAN) pushes are never blocked.
set -u

# NOTE: $0-based dirname resolution is wrong when git invokes the hook by absolute
# path (.git/hooks/pre-push → .. = .git). Use git discovery — the hook always runs
# inside the repo.
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "pre-push: not in a git repo — refusing" >&2; exit 1; }
[ -f "$REPO/scripts/gitea-only.txt" ] || exit 0   # no registry → nothing to enforce

GITEA_ONLY=()
while IFS= read -r line; do
  case "$line" in
    ''|\#*) continue ;;            # skip blanks and comments
    *) GITEA_ONLY+=("$line") ;;
  esac
done < "$REPO/scripts/gitea-only.txt"
[ "${#GITEA_ONLY[@]}" -eq 0 ] && exit 0

# $1 = remote name, $2 = remote URL. Only the GitHub mirror is gated.
REMOTE_NAME="${1:-}"
REMOTE_URL="${2:-}"
is_github=""
if [ "$REMOTE_NAME" = "github" ]; then is_github=1
elif [[ "$REMOTE_URL" == *github.com/NighmareGit/skunkworks-toolbox* ]]; then is_github=1
fi
[ -z "$is_github" ] && exit 0

# stdin: lines of "<local-ref> <local-sha> <remote-ref> <remote-sha>"
while read -r local_ref local_sha remote_ref remote_sha; do
  [ "$local_sha" = "0000000000000000000000000000000000000000" ] && continue  # deletion
  for path in "${GITEA_ONLY[@]}"; do
    if git ls-tree -r --name-only "$local_sha" -- "$path" 2>/dev/null | grep -q .; then
      echo ""
      echo "⛔ BLOCKED: push to the GitHub mirror would publish a gitea-only path: $path"
      echo "   (registry: scripts/gitea-only.txt; rationale: AGENTS.md §Gitea-only files)"
      echo "   Use scripts/push-github.sh — it filters gitea-only paths, runs the"
      echo "   sanitize scan on the filtered tree, then pushes. Direct pushes are refused."
      echo ""
      exit 1
    fi
  done
done

exit 0
