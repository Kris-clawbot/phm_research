from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from db import connect

PLOTS_DIR = Path(__file__).resolve().parent.parent / "data" / "plots"


def _write(name: str, obj):
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PLOTS_DIR / f"{name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def refresh_plots() -> dict:
    """Compute and persist plot-ready datasets.
    - task distribution
    - publications per year
    - task×hybrid heatmap
    - citations vs year bubble
    """
    with connect() as con:
        rows = con.execute("SELECT publication_year, is_review, task_types, hybrid_types, cited_by_count FROM papers").fetchall()

    # publications per year by type
    pubs = defaultdict(lambda: {"article": 0, "review": 0})
    for r in rows:
        y = r["publication_year"]
        if not y:
            continue
        t = "review" if int(r["is_review"] or 0) == 1 else "article"
        pubs[int(y)][t] += 1
    pubs_list = [
        {"year": y, "article": vals["article"], "review": vals["review"], "total": vals["article"] + vals["review"]}
        for y, vals in sorted(pubs.items())
    ]
    _write("publications_per_year", pubs_list)

    # task distribution
    task_counter = Counter()
    for r in rows:
        if r["task_types"]:
            for t in str(r["task_types"]).split(","):
                tt = t.strip()
                if tt:
                    task_counter[tt] += 1
    tasks_list = sorted(({"task": k, "count": v} for k, v in task_counter.items()), key=lambda x: -x["count"])[:50]
    _write("task_distribution", tasks_list)

    # task × hybrid heatmap
    heat = defaultdict(lambda: defaultdict(int))
    for r in rows:
        tasks = str(r["task_types"]).split(",") if r["task_types"] else ["(none)"]
        hybrids = str(r["hybrid_types"]).split(",") if r["hybrid_types"] else ["(none)"]
        for t in tasks:
            t = t.strip() or "(none)"
            for h in hybrids:
                h = h.strip() or "(none)"
                heat[t][h] += 1
    heat_list = []
    for t, cols in heat.items():
        for h, c in cols.items():
            heat_list.append({"task": t, "hybrid": h, "count": c})
    _write("task_hybrid_heatmap", heat_list)

    # citations vs year bubble
    bubbles = []
    for r in rows:
        y = r["publication_year"]
        c = r["cited_by_count"] or 0
        if y:
            bubbles.append({"year": int(y), "citations": int(c)})
    _write("citations_vs_year", bubbles)

    return {
        "publications_per_year": len(pubs_list),
        "task_distribution": len(tasks_list),
        "task_hybrid_heatmap": len(heat_list),
        "citations_vs_year": len(bubbles),
    }
