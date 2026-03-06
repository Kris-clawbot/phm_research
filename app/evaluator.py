from __future__ import annotations

from statistics import mean
from db import connect


def evaluate() -> dict:
    with connect() as con:
        rows = con.execute(
            "SELECT rubric_total, rubric_coverage, rubric_clarity, rubric_relevance, rubric_informativeness, rubric_taxonomy_linkage FROM papers WHERE rubric_total IS NOT NULL"
        ).fetchall()

    counts = {"n_scored": len(rows), "excellent": 0, "good": 0, "needs_improvement": 0, "poor": 0}
    by_crit = {"coverage": [], "clarity": [], "relevance": [], "informativeness": [], "taxonomy_linkage": []}

    for r in rows:
        total = int(r["rubric_total"]) if r["rubric_total"] is not None else 0
        if total >= 9:
            counts["excellent"] += 1
        elif total >= 7:
            counts["good"] += 1
        elif total >= 4:
            counts["needs_improvement"] += 1
        else:
            counts["poor"] += 1
        by_crit["coverage"].append(int(r["rubric_coverage"]) if r["rubric_coverage"] is not None else 0)
        by_crit["clarity"].append(int(r["rubric_clarity"]) if r["rubric_clarity"] is not None else 0)
        by_crit["relevance"].append(int(r["rubric_relevance"]) if r["rubric_relevance"] is not None else 0)
        by_crit["informativeness"].append(int(r["rubric_informativeness"]) if r["rubric_informativeness"] is not None else 0)
        by_crit["taxonomy_linkage"].append(int(r["rubric_taxonomy_linkage"]) if r["rubric_taxonomy_linkage"] is not None else 0)

    recs = []
    if counts["needs_improvement"] + counts["poor"] > 0:
        recs.append("Tighten summarizer formatting to keep <420 chars and explicitly name tasks/hybrid when present.")
    if by_crit["taxonomy_linkage"] and mean(by_crit["taxonomy_linkage"]) < 1.2:
        recs.append("Increase taxonomy phrasing overlap (use exact labels like 'physics_informed', 'digital_twin').")
    if by_crit["coverage"] and mean(by_rit := by_crit["coverage"]) < 1.3:  # type: ignore
        recs.append("Ensure title, year/venue, and type are always included.")

    return {"counts": counts, "recommendations": recs}
