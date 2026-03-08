#!/bin/bash
# Versioned backup for PHM dashboard
# Usage: ./scripts/backup.sh "Summary of changes"
set -euo pipefail
REPO_DIR="$(dirname "$0")/.."
cd "$REPO_DIR"
SUMMARY=${1:-"PHM dashboard backup"}

TOKEN_FILE="/data/.openclaw/workspace/.secrets/github-token"
if [ ! -f "$TOKEN_FILE" ]; then
  echo "Error: Token file not found at $TOKEN_FILE" >&2
  exit 1
fi
GITHUB_TOKEN=$(cat "$TOKEN_FILE")

# Stage relevant changes in PHM repo only
if ! git diff-index --quiet HEAD --; then
  git add -A
  git commit -m "$SUMMARY"
else
  echo "No file changes detected; tagging." >&2
fi
# Tag (date-based): phm-YYYYMMDD.N
BASE="phm-$(date +%Y%m%d)"
LAST_TAG=$(git tag -l "$BASE.*" | sort -V | tail -n1 || true)
if [ -z "$LAST_TAG" ]; then N=1; else N=$(( $(echo "$LAST_TAG" | awk -F'.' '{print $NF}') + 1 )); fi
TAG="$BASE.$N"
echo "Creating tag: $TAG"
git tag -a "$TAG" -m "$SUMMARY"

# Push commit/tag
REMOTE_URL="https://$GITHUB_TOKEN@github.com/Kris-clawbot/phm_research.git"
git push "$REMOTE_URL" master:master
git push "$REMOTE_URL" --tags

echo "Backup complete: $TAG"
