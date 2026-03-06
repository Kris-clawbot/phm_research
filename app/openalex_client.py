import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.openalex.org"


def _session():
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
    s.headers.update({
        "User-Agent": "PHM-Dashboard/0.1 (+https://example.local)",
        "Accept": "application/json",
    })
    return s


def search_works(
    query: str,
    per_page: int = 25,
    page: int = 1,
    from_year: int | None = None,
    from_date: str | None = None,
):
    params = {
        "search": query,
        "per-page": per_page,
        "page": page,
    }

    # OpenAlex supports filter=from_publication_date:YYYY-MM-DD
    if from_date:
        params["filter"] = f"from_publication_date:{from_date}"
    elif from_year is not None:
        params["filter"] = f"from_publication_date:{from_year}-01-01"

    r = _session().get(f"{BASE_URL}/works", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def abstract_from_inverted_index(inv_idx: dict | None) -> str | None:
    """OpenAlex stores abstracts as an inverted index.

    https://docs.openalex.org/api-entities/works/work-object#abstract_inverted_index
    """
    if not inv_idx:
        return None
    positions: list[tuple[int, str]] = []
    for token, idxs in inv_idx.items():
        for i in idxs:
            positions.append((i, token))
    if not positions:
        return None
    positions.sort(key=lambda x: x[0])
    text = " ".join(tok for _, tok in positions)
    # tiny cleanup
    return text.replace("  ", " ").strip()
