#!/usr/bin/env bash
set -euo pipefail

ROOT="/data/.openclaw/workspace/phm_research"
LOG_DIR="$ROOT/logs"
CACHE_DIR="$ROOT/cache"
SUMMARY_FILE="$LOG_DIR/last_update_summary.txt"
mkdir -p "$LOG_DIR" "$CACHE_DIR"

# Placeholder for the 3-hour update routine.
# Intent: refresh cached metadata, re-score summaries, update taxonomy tags, regenerate plots.
# Model policy: do not use Claude Opus. Use local/Ollama or other approved non-Opus models only.

start_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
changes=()

# Example maintenance: prune stale cache entries older than 7 days
if find "$CACHE_DIR" -type f -mtime +7 | grep -q .; then
  pruned=$(find "$CACHE_DIR" -type f -mtime +7 -print -delete | wc -l | tr -d ' ')
  changes+=("Pruned $pruned stale cache files")
fi

# TODO: invoke real pipeline here when available, e.g.:
# python3 -m phm.pipeline.update --no-opus --cache "$CACHE_DIR" 2>&1 | tee -a "$LOG_DIR/update_job.log"

# Compute a lightweight summary (max 10 lines, must start with "Update:")
{
  echo "Update: PHM 3-hour update run at $start_ts (UTC)"
  echo "Status: OK"
  if [ ${#changes[@]} -gt 0 ]; then
    printf 'Changes: %s\n' "${changes[*]}"
  else
    echo "Changes: none"
  fi
  echo "Cache: default TTL 24h; prune >7d; store=$CACHE_DIR"
  echo "Logs: $LOG_DIR/update_job.log"
} | head -n 10 | tee "$SUMMARY_FILE"
