# Elsevier / Scopus API usage for PHM Dashboard

## Goal
Use Elsevier’s Scopus APIs to **discover** new papers (cheap, high-volume) and then **enrich** only selected papers with abstracts/keywords (more expensive per-paper calls), so we can classify papers without repeatedly re-fetching the same items.

## Authentication (what we learned)
Elsevier APIs require an **APIKey** with each request.

### Send the API key
Either:
- Header: `X-ELS-APIKey: <your_api_key>` (recommended)
- Query param: `apiKey=<your_api_key>`

### Optional tokens (institution / user entitlements)
Depending on your institution setup and what “views” you want:
- `X-ELS-Insttoken: <insttoken>` (institution token, issued by Elsevier support)
- `X-ELS-Authtoken: <authtoken>` (2-hour token from Authentication API, used when IP maps to multiple accounts)
- OAuth `Authorization: Bearer <token>` (primarily for user-level entitlements, client-side flows; overrides authtoken)

Source: https://dev.elsevier.com/tecdoc_api_authentication.html

## Core workflow (recommended)

### 1) Discovery search (Scopus Search API) — **STANDARD view**
Use the Scopus Search API to find candidate works.

- Endpoint: `GET https://api.elsevier.com/content/search/scopus`
- Required query param: `query=<boolean_search>`
- Recommended headers: `Accept: application/json`, `X-ELS-APIKey: ...`

**Why STANDARD view:**
- Returns strong metadata for dedup + ranking (title, DOI, publication name, coverDate, citedby-count, openaccess flag, affiliations, etc.).
- Supports higher result counts than COMPLETE.
- In our live test, `view=COMPLETE` returned `AUTHORIZATION_ERROR` (not entitled), while `view=STANDARD` worked.

**Important parameters (from ScopusSearchAPI WADL):**
- `view`: `STANDARD` or `COMPLETE` (and others depending on product); default `STANDARD`
- `count`: max results per call (system max depends on view; docs indicate higher max for STANDARD than COMPLETE)
- `start`: offset pagination (works, but subject to total result limits)
- `cursor`: preferred for large result sets (avoids the 5000 item limit mentioned in key settings)
- `sort`: e.g. `-coverDate`, `-citedby-count`, `relevancy`
- `date`: date range like `2002-2007` (year granularity)

Sources:
- Scopus Search API parameters: https://dev.elsevier.com/documentation/ScopusSearchAPI.wadl
- Default key limits/quotas: https://dev.elsevier.com/api_key_settings.html

### 2) Enrichment per record (Abstract Retrieval API)
After search, call Abstract Retrieval for each selected paper (by Scopus ID / EID) to obtain abstract and richer metadata.

- Endpoint pattern: `GET https://api.elsevier.com/content/abstract/scopus_id/<SCOPUS_ID>`
- The search response includes links like:
  - `prism:url`: `https://api.elsevier.com/content/abstract/scopus_id/<id>`

**VIEW concept:** Elsevier APIs use a `view` parameter to control payload fields; views can be subscription/entitlement dependent.

Source: https://dev.elsevier.com/documentation/retrieval/AbstractRetrievalViews.htm

## Query syntax tips (Scopus search language)
Scopus supports Boolean searches and fielded queries; the `query` value must be URL-encoded.

Examples:
- Fielded: `TITLE-ABS-KEY(remaining useful life)`
- DOI: `DOI("10.1016/j.ress.2024.110352")`
- Authors: use `AUTHLASTNAME(...)`, `AUTH(...)`, or more precise author fields.

Docs highlight:
- Operator precedence rules; use parentheses heavily.
- Phrase search in quotes; exact phrases in braces `{...}`.

Source: https://dev.elsevier.com/sc_search_tips.html

## Rate limits / quotas (operational constraints)
Elsevier quotas reset every 7 days; check these response headers:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset` (epoch)

429 errors:
- Can be quota exceeded (`X-ELS-Status: QUOTA_EXCEEDED`) or throttling rate exceeded.

Default quotas (as published on Elsevier key settings page; may vary by account):
- Scopus Search: ~20,000/week, ~9 req/sec
- Abstract Retrieval: ~10,000/week, ~9 req/sec

Source: https://dev.elsevier.com/api_key_settings.html

## Dedup strategy for PHM dashboard
To avoid reprocessing the same papers:
- Use Scopus Search for discovery with a moving time window (e.g., last 7 days) or an incremental field.
- Prefer stable identifiers for dedup:
  - Primary: DOI (`prism:doi`)
  - Secondary: Scopus EID (`eid`) or `SCOPUS_ID`
- Store the last successful run marker in our system.

### Incremental update fields
Elsevier’s IR/CRIS guidance suggests:
- `ORIG-LOAD-DATE` (YYYYMMDD): when record first loaded into Scopus
- `LOAD-DATE`: when record last loaded/reloaded

This is an alternative (often better) to publication date for incremental sync.

Source: https://dev.elsevier.com/tecdoc_ir_cris_vivo.html

## Practical note from our live test
- `view=COMPLETE` for Scopus Search produced:
  - `AUTHORIZATION_ERROR: not authorized to access the requested view or fields`
- `view=STANDARD` succeeded and returned 13 results for `AUTHLASTNAME(Bajarunas)`.
- Abstract Retrieval call for one of those IDs returned no `dc:description` (abstract) in the JSON we saw — meaning abstract availability may depend on:
  - the record itself,
  - the chosen `view`/fields,
  - or account entitlements.

Action item: when implementing, support:
1) requesting a richer Abstract Retrieval `view` if available,
2) graceful fallback when abstract is missing,
3) optional ScienceDirect full-text/metadata enrichment when permitted.

## Proposed implementation in PHM dashboard
1. Add `elsevier_client.py`:
   - `scopus_search(query, count, start|cursor, view='STANDARD')`
   - `abstract_retrieve(scopus_id, view=...)`
   - robust retry/backoff for 429/5xx
2. Extend `sync.py` to support `source='scopus'` alongside OpenAlex:
   - discovery → upsert minimal record
   - optional enrichment step for abstracts/keywords
3. Keep classification unchanged (title+abstract); run only after enrichment when abstract exists.

---

If you want, next step is to implement this client + wiring and then add a “Scopus” toggle in the dashboard sidebar.
