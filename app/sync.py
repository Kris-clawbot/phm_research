from __future__ import annotations

from datetime import date, timedelta

from openalex_client import search_works, abstract_from_inverted_index
from elsevier_client import scopus_search, abstract_retrieve_scopus_id, extract_abstract
from db import init_db, upsert_paper
from taxonomy import classify

DEFAULT_QUERY = (
    "prognostics health management RUL remaining useful life "
    "hybrid model physics-informed grey-box digital twin"
)


def last_week_date() -> str:
    """Return ISO date string for today minus 7 days (local time)."""
    return (date.today() - timedelta(days=7)).isoformat()


def _authors_str(work: dict) -> str | None:
    authorships = work.get("authorships") or []
    names = []
    for a in authorships:
        author = a.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    if not names:
        return None
    # keep it compact
    if len(names) <= 6:
        return ", ".join(names)
    return ", ".join(names[:6]) + f" (+{len(names)-6})"


def _detect_source(landing_page_url: str | None, doi: str | None, fallback: str = "openalex") -> str:
    url = (landing_page_url or "").lower()
    doi = (doi or "").lower()
    # publisher/platform heuristics by domain/DOI prefix
    if "arxiv.org" in url or doi.startswith("10.48550/"):
        return "arxiv"
    if "ieeexplore.ieee.org" in url or doi.startswith("10.1109/"):
        return "ieee"
    if "sciencedirect.com" in url or doi.startswith("10.1016/"):
        return "sciencedirect"
    if "link.springer.com" in url or doi.startswith("10.1007/"):
        return "springer"
    if "dl.acm.org" in url or doi.startswith("10.1145/"):
        return "acm"
    if "onlinelibrary.wiley.com" in url:
        return "wiley"
    if "mdpi.com" in url or doi.startswith("10.3390/"):
        return "mdpi"
    if "nature.com" in url or doi.startswith("10.1038/"):
        return "nature"
    if "tandfonline.com" in url:
        return "tandf"
    if "frontiersin.org" in url:
        return "frontiers"
    if "hindawi.com" in url:
        return "hindawi"
    if "journals.sagepub.com" in url or "sagepub.com" in url:
        return "sage"
    if "openalex.org" in url or "openalex" in url:
        return "openalex"
    return fallback


def normalize_work(work: dict, source: str = "openalex") -> dict:
    primary_location = work.get("primary_location") or {}
    src = primary_location.get("source") or {}

    ids = work.get("ids") or {}

    abstract = work.get("abstract")
    if not abstract:
        abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))

    work_type = work.get("type")
    is_review = 1 if (work_type == "review") else 0

    tax = classify(work.get("display_name") or work.get("title"), abstract)

    landing = primary_location.get("landing_page_url") or ids.get("openalex")
    platform = _detect_source(landing, ids.get("doi"), fallback=None)

    return {
        "id": work.get("id"),
        "openalex_id": ids.get("openalex"),
        "doi": ids.get("doi"),
        "title": work.get("display_name") or work.get("title"),
        "authors": _authors_str(work),
        "abstract": abstract,
        "work_type": work_type,
        "is_review": is_review,
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "cited_by_count": work.get("cited_by_count"),
        "journal": (src.get("display_name") if isinstance(src, dict) else None),
        "landing_page_url": landing,
        "source": source,
        "platform": platform,
        "task_types": ",".join(tax.task_types) if tax.task_types else None,
        "hybrid_types": ",".join(tax.hybrid_types) if tax.hybrid_types else None,
        "case_study": tax.case_study,
        "methods": ",".join(tax.methods) if tax.methods else None,
    }


def sync(
    query: str = DEFAULT_QUERY,
    pages: int = 3,
    per_page: int = 50,
    from_date: str | None = None,
) -> int:
    """Fetch papers from OpenAlex and upsert into SQLite.

    Defaults to the last 7 days if from_date is not provided.
    Uses the OpenAlex filter: from_publication_date=YYYY-MM-DD.
    """
    init_db()
    inserted = 0

    # Default to last 7 days to avoid re-fetching older papers repeatedly
    if not from_date:
        from_date = last_week_date()

    # OpenAlex allows filter=from_publication_date:YYYY-MM-DD
    for page in range(1, pages + 1):
        data = search_works(query=query, per_page=per_page, page=page, from_date=from_date)
        for w in data.get("results", []):
            p = normalize_work(w, source="openalex")
            if p.get("id") and p.get("title"):
                upsert_paper(p)
                inserted += 1

    return inserted


def _scopus_pick_link(entry: dict, ref: str) -> str | None:
    for l in entry.get("link", []) or []:
        if isinstance(l, dict) and l.get("@ref") == ref:
            return l.get("@href")
    return None


def normalize_scopus_entry(entry: dict) -> dict:
    """Normalize one Scopus search entry into our DB row shape.

    We store:
    - id: a stable, namespaced id (scopus:<eid>) to avoid collisions with OpenAlex ids
    - scopus_id: numeric scopus id (from dc:identifier)
    - scopus_eid: EID
    """
    scopus_identifier = entry.get("dc:identifier") or ""
    scopus_id = None
    if isinstance(scopus_identifier, str) and scopus_identifier.startswith("SCOPUS_ID:"):
        scopus_id = scopus_identifier.split(":", 1)[1]

    eid = entry.get("eid")
    pid = f"scopus:{eid or scopus_id or scopus_identifier}"

    title = entry.get("dc:title")
    doi = entry.get("prism:doi")
    journal = entry.get("prism:publicationName")
    cover_date = entry.get("prism:coverDate")
    cited_by = entry.get("citedby-count")
    creator = entry.get("dc:creator")

    landing = _scopus_pick_link(entry, "scopus") or entry.get("prism:url")

    platform = _detect_source(landing, doi, fallback=None)

    # year best-effort
    pub_year = None
    if isinstance(cover_date, str) and len(cover_date) >= 4:
        try:
            pub_year = int(cover_date[:4])
        except Exception:
            pub_year = None

    # Note: Scopus search STANDARD view doesn't reliably include the full author list.
    authors = creator

    return {
        "id": pid,
        "openalex_id": None,
        "doi": doi,
        "title": title,
        "authors": authors,
        "abstract": None,
        "work_type": None,
        "is_review": None,
        "publication_year": pub_year,
        "publication_date": cover_date,
        "cited_by_count": int(cited_by) if isinstance(cited_by, str) and cited_by.isdigit() else cited_by,
        "journal": journal,
        "landing_page_url": landing,
        "source": "scopus",
        "platform": platform,
        "scopus_id": scopus_id,
        "scopus_eid": eid,
        "task_types": None,
        "hybrid_types": None,
        "case_study": None,
        "methods": None,
    }


def sync_scopus(
    query: str,
    *,
    count: int = 25,
    start: int = 0,
    enrich_abstracts: bool = False,
    abstract_view: str | None = None,
) -> int:
    """Search Scopus and upsert results.

    Default behavior is discovery-only (metadata), to minimize API calls.

    If enrich_abstracts=True, we call Abstract Retrieval per paper (quota-sensitive).
    """
    init_db()
    inserted = 0

    data = scopus_search(query=query, count=count, start=start, view="STANDARD")
    results = (data.get("search-results") or {}).get("entry") or []
    for e in results:
        if not isinstance(e, dict):
            continue
        p = normalize_scopus_entry(e)
        if p.get("id") and p.get("title"):
            upsert_paper(p)
            inserted += 1

        if enrich_abstracts and p.get("scopus_id"):
            payload = abstract_retrieve_scopus_id(str(p["scopus_id"]), view=abstract_view)
            abstract = extract_abstract(payload)
            if abstract:
                p2 = dict(p)
                p2["abstract"] = abstract
                # We can now run taxonomy classification because we have title+abstract
                tax = classify(p2.get("title"), p2.get("abstract"))
                p2["task_types"] = ",".join(tax.task_types) if tax.task_types else None
                p2["hybrid_types"] = ",".join(tax.hybrid_types) if tax.hybrid_types else None
                p2["case_study"] = tax.case_study
                p2["methods"] = ",".join(tax.methods) if tax.methods else None
                upsert_paper(p2)

    return inserted
