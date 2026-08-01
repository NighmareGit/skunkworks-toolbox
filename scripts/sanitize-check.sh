#!/bin/bash
# sanitize-check.sh — pre-push hygiene gate for the public GitHub mirror.
# Scans tracked files for internal references (LAN IPs, usernames in access
# contexts, personal paths, credentials, internal URLs). Exit 0 = clean.
# Contract: AGENTS.md §2. Run before pushing GitHub; never push on a failing scan.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

# Patterns that must never appear in tracked content.
# NOTE: .git/ is never scanned; only git-tracked files are.
PATTERNS=(
  '192\.168\.[0-9]+\.[0-9]+'          # private LAN IPs
  '10\.[0-9]+\.[0-9]+\.[0-9]+'        # private 10/8
  '172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+'  # private 172.16-31/12
  '[a-zA-Z0-9._-]+@192\.168\.[0-9]+\.[0-9]+'    # user@LAN-ip
  '/home/[a-zA-Z0-9_]+/'              # /home/<user> absolute paths
  '/Users/[a-zA-Z0-9_]+/'             # macOS user paths
  '/mnt/[a-zA-Z0-9_]+/'               # mount-label paths
  'BEGIN (RSA |OPENSSH |EC |PRIVATE )'          # private keys
  'password[[:space:]]*=[[:space:]]*[^< ]'      # password=value
  'passwd[[:space:]]*=[[:space:]]*[^< ]'
  'api[_-]?key[[:space:]]*[:=][[:space:]]*[^< ]'  # api_key=value
  'token[[:space:]]*[:=][[:space:]]*[A-Za-z0-9]{20,}'  # long token values
  'Bearer[[:space:]]+[A-Za-z0-9._-]+' # Bearer tokens
  'http://(?!127\.0\.0\.1)[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'  # http://<ip> internal URLs (loopback exempt)
)

FILES=$(git ls-files | grep -vE "^(AGENTS\.md|scripts/sanitize-check\.sh)$")
[ -z "$FILES" ] && { echo "no tracked files"; exit 0; }

FAIL=0
for pat in "${PATTERNS[@]}"; do
  HITS=$(grep -nE "$pat" $FILES 2>/dev/null | grep -v '^Binary')
  if [ -n "$HITS" ]; then
    echo "❌ pattern: $pat"
    echo "$HITS" | head -20
    FAIL=1
  fi
done

if [ "$FAIL" -eq 0 ]; then
  echo "✅ sanitize-check: CLEAN ($(echo "$FILES" | wc -l) files scanned)"
  exit 0
else
  echo ""
  echo "⚠️  sanitize-check: LEAKS FOUND — do NOT push GitHub."
  echo "   Fix (redact to <PLACEHOLDER>) or escalate per AGENTS.md §4."
  exit 1
fi
