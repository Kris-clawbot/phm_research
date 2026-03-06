# PHM Dashboard - Project Memory

## Purpose
Scientific research dashboard for PHM (prognostics, diagnostics, fault detection) with emphasis on **hybrid models** (prior knowledge + data-driven).

## Key requirements (v0)
- Fetch papers (OpenAlex) from >= 2025-01-01
- Store: title, authors, DOI, OpenAlex ID, year/date, citations, journal, review-vs-article
- Dashboard: table + detail view
- Sync: weekly job + manual trigger
- Next: taxonomy classification (task type, hybrid model type, case-study) with confidence + evidence snippets

## Ops
- Streamlit server on port :3001
- Heartbeat auto-starts dashboard if down

