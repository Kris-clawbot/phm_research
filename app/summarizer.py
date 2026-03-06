from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from db import connect, update_summary_scores, update_taxonomy
from taxonomy import classify


@dataclass
class RubricScore:
    coverage: int
    clarity: int
    relevance: int
    informativeness: int
    taxonomy_linkage: int

    @property
    def total(self) -> int:
        return self.coverage + self.clarity + self.relevance + self.informativeness + self.taxonomy_linkage


def _format_summary(row) -> str:
    title = row["title"] or ""
    year = row["publication_year"] or ""
    ven = row["journal"] or ""
    work_type = "review" if int(row["is_review"] or 0) == 1 else (row["work_type"] or "article")
    authors = (row["authors"] or "").split(", ") if row["authors"] else []
    auth_str = ", ".join(authors[:3]) + (f" (+{len(authors)-3})" if len(authors) > 3 else "") if authors else "—"

    tasks = (row["task_types"] or "").split(",") if row["task_types"] else []
    hybrids = (row["hybrid_types"] or "").split(",") if row["hybrid_types"] else []
    methods = (row["methods"] or "").split(",") if row["methods"] else []
    case = row["case_study"] or None

    parts = []
    parts.append(f"{title} ({year}, {ven or 'venue n/a'}) — {work_type}.")
    if tasks or hybrids:
        parts.append("Focus: " + ", ".join(filter(None, [
            ("tasks: " + "/".join(tasks)) if tasks else None,
            ("hybrid: " + "/".join(hybrids)) if hybrids else None,
        ])))
    if case:
        parts.append(f"Case: {case}.")
    if methods:
        parts.append("Methods: " + ", ".join(methods) + ".")
    parts.append(f"Authors: {auth_str}.")

    # Keep it compact, 2–4 short sentences.
    return " ".join(parts)


def _score_summary(row, summary: str) -> RubricScore:
    # 0/1/2 heuristics per criterion
    # Coverage: title, year/venue, type, plus at least two of tasks/hybrid/methods/case
    coverage_bits = 0
    if row["title"]:
        coverage_bits += 1
    if row["publication_year"] or row["journal"]:
        coverage_bits += 1
    if row["is_review"] is not None or row["work_type"]:
        coverage_bits += 1
    extras = sum(1 for f in [row["task_types"], row["hybrid_types"], row["methods"], row["case_study"]] if f)
    coverage = 2 if coverage_bits >= 3 and extras >= 2 else (1 if coverage_bits >= 2 and extras >= 1 else 0)

    # Clarity: short length and readable punctuation
    length = len(summary)
    clarity = 2 if length <= 420 else (1 if length <= 700 else 0)

    # Relevance: mentions at least one PHM keyword or hybrid cue
    text = summary.lower()
    rel_hits = any(k in text for k in ["prognostic", "rul", "remaining useful life", "fault", "anomaly"]) or \
               any(k in text for k in ["physics", "pinn", "grey", "digital twin", "bayesian", "state-space"])
    relevance = 2 if rel_hits else 1 if (row["title"] and ("health" in text or "maintenance" in text)) else 0

    # Informativeness: include at least two of tasks/hybrid/methods/case
    info = 2 if extras >= 2 else (1 if extras == 1 else 0)

    # Taxonomy linkage: summary reflects taxonomy labels if present
    link = 0
    if row["task_types"]:
        if any(t in text for t in row["task_types"].split(",")):
            link += 1
    if row["hybrid_types"]:
        if any(h in text for h in row["hybrid_types"].split(",")):
            link += 1
    if row["methods"]:
        if any(m in text for m in row["methods"].split(",")):
            link += 1
    taxonomy_linkage = 2 if link >= 2 else (1 if link == 1 else 0)

    return RubricScore(coverage, clarity, relevance, info, taxonomy_linkage)


def run_summarizer() -> dict:
    """Summarize and score papers that lack a summary or scores. Also patch missing taxonomy.
    Returns counts.
    """
    n_total = 0
    n_scored = 0
    n_tax_updated = 0
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM papers WHERE summary_text IS NULL OR rubric_total IS NULL"
        ).fetchall()
        for row in rows:
            n_total += 1
            # backfill taxonomy if missing
            if not row["task_types"] and not row["hybrid_types"] and not row["methods"] and (row["title"] or row["abstract"]):
                tax = classify(row["title"], row["abstract"])  # type: ignore
                update_taxonomy(
                    row["id"],
                    ",".join(tax.task_types) if tax.task_types else None,
                    ",".join(tax.hybrid_types) if tax.hybrid_types else None,
                    tax.case_study,
                    ",".join(tax.methods) if tax.methods else None,
                )
                # refresh row fields used for summary/score
                row = con.execute("SELECT * FROM papers WHERE id = ?", (row["id"],)).fetchone()
                n_tax_updated += 1

            summary = _format_summary(row)
            score = _score_summary(row, summary)
            update_summary_scores(
                row["id"],
                summary,
                {
                    "coverage": score.coverage,
                    "clarity": score.clarity,
                    "relevance": score.relevance,
                    "informativeness": score.informativeness,
                    "taxonomy_linkage": score.taxonomy_linkage,
                    "total": score.total,
                },
            )
            n_scored += 1
    return {"found": n_total, "scored": n_scored, "taxonomy_backfilled": n_tax_updated}
