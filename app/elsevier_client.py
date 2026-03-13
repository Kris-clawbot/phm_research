from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.elsevier.com"


def _read_api_key() -> str:
    # 1) env var
    k = os.getenv("ELSEVIER_API_KEY")
    if k:
        return k.strip()

    # 2) workspace secret file (used in this deployment)
    p = Path("/data/.openclaw/workspace/.secrets/elsevier-api-key")
    if p.exists():
        return p.read_text(encoding="utf-8").strip()

    raise RuntimeError(
        "Missing Elsevier API key. Set ELSEVIER_API_KEY or create /data/.openclaw/workspace/.secrets/elsevier-api-key"
    )


def _session() -> requests.Session:
    s = requests.Session()

    retry = Retry(
        total=4,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504, 520, 522, 524],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)

    s.headers.update(
        {
            "User-Agent": "PHM-Dashboard/0.1 (+https://example.local)",
            "Accept": "application/json",
            "X-ELS-APIKey": _read_api_key(),
        }
    )
    return s


@dataclass
class RateLimit:
    limit: int | None = None
    remaining: int | None = None
    reset_epoch: int | None = None


def _parse_rate_limit_headers(headers: dict[str, str]) -> RateLimit:
    def _int(v: str | None) -> int | None:
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    return RateLimit(
        limit=_int(headers.get("X-RateLimit-Limit")),
        remaining=_int(headers.get("X-RateLimit-Remaining")),
        reset_epoch=_int(headers.get("X-RateLimit-Reset")),
    )


def scopus_search(
    query: str,
    *,
    count: int = 25,
    start: int = 0,
    view: str = "STANDARD",
    sort: str | None = None,
) -> dict[str, Any]:
    """Scopus Search API.

    Endpoint: /content/search/scopus

    Note: For high-volume paging, prefer cursor pagination, but `start` is fine for our
    low-volume weekly sync.
    """
    params: dict[str, Any] = {
        "query": query,
        "count": count,
        "start": start,
        "view": view,
    }
    if sort:
        params["sort"] = sort

    r = _session().get(f"{BASE_URL}/content/search/scopus", params=params, timeout=30)

    # If throttled, Retry() above will retry; if still 429, surface a helpful error.
    if r.status_code == 429:
        rl = _parse_rate_limit_headers(dict(r.headers))
        raise RuntimeError(f"Elsevier 429 throttled/quota. remaining={rl.remaining} reset={rl.reset_epoch}")

    r.raise_for_status()
    return r.json()


def abstract_retrieve_scopus_id(scopus_id: str, *, view: str | None = None) -> dict[str, Any]:
    """Abstract Retrieval API by scopus_id.

    Endpoint: /content/abstract/scopus_id/{id}

    Elsevier uses VIEWs; availability can depend on entitlements.
    If view is None, we use the API default.
    """
    params = {}
    if view:
        params["view"] = view

    r = _session().get(f"{BASE_URL}/content/abstract/scopus_id/{scopus_id}", params=params, timeout=30)
    if r.status_code == 429:
        rl = _parse_rate_limit_headers(dict(r.headers))
        raise RuntimeError(f"Elsevier 429 throttled/quota. remaining={rl.remaining} reset={rl.reset_epoch}")

    r.raise_for_status()
    return r.json()


def extract_abstract(payload: dict[str, Any]) -> str | None:
    """Best-effort extraction of abstract text from Abstract Retrieval payload."""
    resp = payload.get("abstracts-retrieval-response") or {}
    core = resp.get("coredata") or {}

    # Most common field
    abstract = core.get("dc:description")
    if isinstance(abstract, str) and abstract.strip():
        return abstract.strip()

    # Some variants exist; keep best-effort fallbacks
    item = resp.get("item") or {}
    bib = item.get("bibrecord") or {}
    head = bib.get("head") or {}

    # Sometimes it's nested (rare in JSON, but keep this as fallback)
    for k in ["abstract", "ce:abstract"]:
        v = head.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    return None


def first_n_sentences(text: str, n: int = 2) -> str:
    # very small heuristic sentence splitter (good enough for a test output)
    t = " ".join(text.split())
    if not t:
        return ""

    out: list[str] = []
    start = 0
    for i, ch in enumerate(t):
        if ch in ".!?" and i + 1 < len(t) and t[i + 1] == " ":
            sent = t[start : i + 1].strip()
            if sent:
                out.append(sent)
            start = i + 2
            if len(out) >= n:
                break

    if len(out) < n:
        tail = t[start:].strip()
        if tail:
            out.append(tail)

    return " ".join(out[:n]).strip()
