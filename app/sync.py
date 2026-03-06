from __future__ import annotations

from openalex_client import search_works, abstract_from_inverted_index
from db import init_db, upsert_paper
from taxonomy import classify

DEFAULT_QUERY = (
    "prognostics health management RUL remaining useful life "
    "hybrid model physics-informed grey-box digital twin"
)


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


def normalize_work(work: dict) -> dict:
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}

    ids = work.get("ids") or {}

    abstract = work.get("abstract")
    if not abstract:
        abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))

    work_type = work.get("type")
    is_review = 1 if (work_type == "review") else 0

    tax = classify(work.get("display_name") or work.get("title"), abstract)

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
        "journal": source.get("display_name"),
        "landing_page_url": (primary_location.get("landing_page_url") or ids.get("openalex")),
        "task_types": ",".join(tax.task_types) if tax.task_types else None,
        "hybrid_types": ",".join(tax.hybrid_types) if tax.hybrid_types else None,
        "case_study": tax.case_study,
        "methods": ",".join(tax.methods) if tax.methods else None,
    }


def sync(
    query: str = DEFAULT_QUERY,
    pages: int = 3,
    per_page: int = 50,
    from_date: str = "2025-01-01",
) -> int:
    """Fetch papers from OpenAlex and upsert into SQLite.

    Note: We use from_publication_date filter for date-level control.
    """
    init_db()
    inserted = 0

    # OpenAlex allows filter=from_publication_date:YYYY-MM-DD
    for page in range(1, pages + 1):
        data = search_works(query=query, per_page=per_page, page=page, from_date=from_date)
        for w in data.get("results", []):
            p = normalize_work(w)
            if p.get("id") and p.get("title"):
                upsert_paper(p)
                inserted += 1

    return inserted
