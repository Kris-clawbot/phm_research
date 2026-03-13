import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "papers.sqlite"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    con.row_factory = sqlite3.Row
    return con


def _column_names(con) -> set[str]:
    rows = con.execute("PRAGMA table_info(papers)").fetchall()
    return {r[1] for r in rows}


def init_db():
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
              id TEXT PRIMARY KEY,
              openalex_id TEXT,
              doi TEXT,
              title TEXT NOT NULL,
              authors TEXT,
              abstract TEXT,
              work_type TEXT,
              is_review INTEGER,
              publication_year INTEGER,
              publication_date TEXT,
              cited_by_count INTEGER,
              journal TEXT,
              landing_page_url TEXT,
              source TEXT,         -- data provider (openalex, scopus, arxiv-api, crossref, scraper, ...)
              platform TEXT,       -- publisher/platform (ieee, springer, arxiv, ...)

              scopus_id TEXT,      -- numeric scopus id (e.g. 85199264454)
              scopus_eid TEXT,     -- scopus EID (e.g. 2-s2.0-85199264454)

              task_types TEXT,
              hybrid_types TEXT,
              case_study TEXT,
              methods TEXT,

              -- summarizer outputs
              summary_text TEXT,
              rubric_coverage INTEGER,
              rubric_clarity INTEGER,
              rubric_relevance INTEGER,
              rubric_informativeness INTEGER,
              rubric_taxonomy_linkage INTEGER,
              rubric_total INTEGER,

              inserted_at TEXT DEFAULT (datetime('now'))
            );
            """
        )

        # lightweight migrations for older DBs
        cols = _column_names(con)
        alters: list[str] = []
        if "openalex_id" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN openalex_id TEXT")
        if "authors" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN authors TEXT")
        if "work_type" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN work_type TEXT")
        if "is_review" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN is_review INTEGER")
        if "task_types" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN task_types TEXT")
        if "hybrid_types" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN hybrid_types TEXT")
        if "case_study" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN case_study TEXT")
        if "methods" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN methods TEXT")
        if "summary_text" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN summary_text TEXT")
        if "rubric_coverage" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN rubric_coverage INTEGER")
        if "rubric_clarity" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN rubric_clarity INTEGER")
        if "rubric_relevance" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN rubric_relevance INTEGER")
        if "rubric_informativeness" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN rubric_informativeness INTEGER")
        if "rubric_taxonomy_linkage" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN rubric_taxonomy_linkage INTEGER")
        if "rubric_total" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN rubric_total INTEGER")
        if "source" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN source TEXT")
        if "platform" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN platform TEXT")
        if "scopus_id" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN scopus_id TEXT")
        if "scopus_eid" not in cols:
            alters.append("ALTER TABLE papers ADD COLUMN scopus_eid TEXT")

        for sql in alters:
            con.execute(sql)

        con.execute("CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(publication_year);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_papers_openalex_id ON papers(openalex_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_papers_scopus_id ON papers(scopus_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_papers_scopus_eid ON papers(scopus_eid);")
        con.commit()


def backfill_sources():
    """Heuristically backfill missing source values for older rows."""
    with connect() as con:
        rules = [
            ("openalex", "openalex_id IS NOT NULL OR landing_page_url LIKE '%openalex%'"),
            ("arxiv", "landing_page_url LIKE '%arxiv.org%' OR doi LIKE '10.48550/%'"),
            ("ieee", "landing_page_url LIKE '%ieeexplore.ieee.org%' OR doi LIKE '10.1109/%'"),
            ("sciencedirect", "landing_page_url LIKE '%sciencedirect.com%' OR doi LIKE '10.1016/%'"),
            ("springer", "landing_page_url LIKE '%link.springer.com%' OR doi LIKE '10.1007/%'"),
            ("acm", "landing_page_url LIKE '%dl.acm.org%' OR doi LIKE '10.1145/%'"),
            ("wiley", "landing_page_url LIKE '%onlinelibrary.wiley.com%'"),
            ("mdpi", "landing_page_url LIKE '%mdpi.com%' OR doi LIKE '10.3390/%'"),
            ("nature", "landing_page_url LIKE '%nature.com%' OR doi LIKE '10.1038/%'"),
            ("tandf", "landing_page_url LIKE '%tandfonline.com%'"),
        ]
        for src, cond in rules:
            con.execute(
                f"UPDATE papers SET source=? WHERE (source IS NULL OR source='') AND ({cond})",
                (src,),
            )
        con.commit()


def upsert_paper(p: dict):
    with connect() as con:
        con.execute(
            """
            INSERT INTO papers (
              id, openalex_id, doi, title, authors, abstract, work_type, is_review,
              publication_year, publication_date, cited_by_count, journal, landing_page_url, source, platform,
              scopus_id, scopus_eid,
              task_types, hybrid_types, case_study, methods
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              openalex_id=excluded.openalex_id,
              doi=excluded.doi,
              title=excluded.title,
              authors=excluded.authors,
              abstract=excluded.abstract,
              work_type=excluded.work_type,
              is_review=excluded.is_review,
              publication_year=excluded.publication_year,
              publication_date=excluded.publication_date,
              cited_by_count=excluded.cited_by_count,
              journal=excluded.journal,
              landing_page_url=excluded.landing_page_url,
              source=excluded.source,
              platform=excluded.platform,
              scopus_id=excluded.scopus_id,
              scopus_eid=excluded.scopus_eid,
              task_types=excluded.task_types,
              hybrid_types=excluded.hybrid_types,
              case_study=excluded.case_study,
              methods=excluded.methods;
            """,
            (
                p.get("id"),
                p.get("openalex_id"),
                p.get("doi"),
                p.get("title"),
                p.get("authors"),
                p.get("abstract"),
                p.get("work_type"),
                p.get("is_review"),
                p.get("publication_year"),
                p.get("publication_date"),
                p.get("cited_by_count"),
                p.get("journal"),
                p.get("landing_page_url"),
                p.get("source"),
                p.get("platform"),
                p.get("scopus_id"),
                p.get("scopus_eid"),
                p.get("task_types"),
                p.get("hybrid_types"),
                p.get("case_study"),
                p.get("methods"),
            ),
        )
        con.commit()


def list_papers(limit: int = 300, year_min: int | None = None, q: str | None = None, reviews_only: bool | None = None):
    sql = "SELECT * FROM papers"
    params = []
    where = []
    if year_min is not None:
        where.append("publication_date >= ?")
        params.append(f"{year_min:04d}-01-01")
    if q:
        where.append("(title LIKE ? OR abstract LIKE ? OR journal LIKE ? OR authors LIKE ? OR doi LIKE ? OR openalex_id LIKE ? OR scopus_eid LIKE ? OR scopus_id LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like, like, like, like, like])
    if reviews_only is True:
        where.append("is_review = 1")
    elif reviews_only is False:
        where.append("(is_review IS NULL OR is_review = 0)")

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY publication_date DESC, cited_by_count DESC NULLS LAST LIMIT ?"
    params.append(limit)

    with connect() as con:
        rows = con.execute(sql, params).fetchall()
    return rows


def get_paper(pid: str):
    with connect() as con:
        row = con.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone()
    return row


def update_taxonomy(pid: str, task_types: str | None, hybrid_types: str | None, case_study: str | None, methods: str | None):
    with connect() as con:
        con.execute(
            "UPDATE papers SET task_types = ?, hybrid_types = ?, case_study = ?, methods = ? WHERE id = ?",
            (task_types, hybrid_types, case_study, methods, pid),
        )
        con.commit()


def update_summary_scores(pid: str, summary: str | None, scores: dict | None):
    with connect() as con:
        if scores is None:
            scores = {}
        con.execute(
            """
            UPDATE papers SET
                summary_text = ?,
                rubric_coverage = ?,
                rubric_clarity = ?,
                rubric_relevance = ?,
                rubric_informativeness = ?,
                rubric_taxonomy_linkage = ?,
                rubric_total = ?
            WHERE id = ?
            """,
            (
                summary,
                scores.get("coverage"),
                scores.get("clarity"),
                scores.get("relevance"),
                scores.get("informativeness"),
                scores.get("taxonomy_linkage"),
                scores.get("total"),
                pid,
            ),
        )
        con.commit()


def iter_papers():
    with connect() as con:
        for row in con.execute("SELECT id, title, abstract FROM papers"):
            yield row
