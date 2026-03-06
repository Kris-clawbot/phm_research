# PHM Research Dashboard

This repository powers the PHM (Prognostics & Health Management) research dashboard focused on hybrid models.

## Default Cache Settings

- Layered cache with local filesystem store at `phm_research/cache/`
- Search results TTL: 24 hours
- Metadata/enrichment TTL: 24 hours
- Stale cache pruning: files older than 7 days are deleted automatically by the 3-hour update job
- Rate-limits: client-side backoff + jitter (planned); multi-source rotation (planned)

## Scheduled Jobs

- Update job (every 3 hours): `phm_research/scripts/update_job.sh`
  - Refreshes cached metadata, re-scores summaries, updates taxonomy tags, regenerates plots
  - Produces a short summary (<=10 lines) starting with "Update:" at `phm_research/logs/last_update_summary.txt`

- Search job (every 24 hours): `phm_research/scripts/search_job.sh`
  - Queries sources for new papers (currently OpenAlex; more to come)
  - Produces a short summary (<=10 lines) starting with "Update:" at `phm_research/logs/last_search_summary.txt`

## Roadmap

See `phm_research/ROADMAP.md` for tasks, statuses, and future improvements (multi-source search, deduplication, etc.).
