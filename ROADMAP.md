# PHM Research Dashboard Roadmap

## Task Tracking and Project Directions

All directions from Kris and future tasks found via evaluation go here. Tasks get labeled:
- [IN PROGRESS] — Actively being worked on now
- [COMPLETE] — Fully finished

---

## Outstanding Tasks

- [IN PROGRESS] Maintain this Roadmap file: aggregate every direction from Kris and all new tasks from the evaluation model/logic.
- [IN PROGRESS] Implement caching with default settings (TTL 24h for search + metadata; prune stale >7d; local fs store) and document clearly in README.
- [IN PROGRESS] Extend paper search to include not only OpenAlex but also other free APIs (e.g., Semantic Scholar, CORE, arXiv, etc). Implement deduplication logic to merge papers found across sources.

- [IN PROGRESS] Redesign UI to minimal, modern layout; add Overview/Sources/Papers tabs.
- [IN PROGRESS] Add Sources tab with counts per API (OpenAlex now; S2/arXiv/CORE next).
- [IN PROGRESS] Improve plots: add task×hybrid heatmap and time trends; export JSONs.
- [IN PROGRESS] Multi-source ready DB: add 'source' column and indices; tag openalex in sync.

---

## Task Log

2026-03-06: Initial roadmap and tracker created (by Clyde as per Kris's request).
- Added future task: multi-source paper search (not only OpenAlex)

(Tasks and status will be updated as the project progresses.)
