import os
import tempfile

import pytest

# Ensure local imports work
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "app"))

from db import init_db, list_papers
from sync import sync


def test_sync_and_list(monkeypatch):
    # isolate DB per test by redirecting DB_PATH via env var pattern
    # (quick hack: monkeypatch module-level DB_PATH)
    import db as dbmod

    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path
        dbmod.DB_PATH = Path(td) / "papers.sqlite"  # type: ignore
        init_db()
        n = sync(query="prognostics remaining useful life RUL hybrid", pages=1, per_page=5, from_date="2025-01-01")
        assert n > 0
        rows = list_papers(limit=10, year_min=2025)
        assert len(rows) > 0
        assert rows[0]["title"]
