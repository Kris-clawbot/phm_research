
import textwrap
from collections import Counter

import pandas as pd
import streamlit as st

from db import init_db, list_papers, get_paper, update_taxonomy, iter_papers
from sync import sync, DEFAULT_QUERY, last_week_date
from taxonomy import classify

import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="PHM Hybrid Research Dashboard", page_icon="📊", layout="wide")

init_db()

# Sidebar: compact controls
with st.sidebar:
    st.header("Sync")
    query = st.text_area("Search query", value=DEFAULT_QUERY, height=100)
    from_date = st.text_input("From date (YYYY-MM-DD)", value=last_week_date())
    pages = st.slider("Pages", min_value=1, max_value=20, value=5)
    per_page = st.slider("Per page", min_value=10, max_value=200, value=50, step=10)
    include_scopus = st.checkbox("Also sync from Scopus (Elsevier)", value=False)
    enrich_scopus_abstracts = st.checkbox("Scopus: fetch abstracts (uses quota)", value=False)

    if st.button("Sync now", type="primary"):
        total = 0
        with st.spinner("Fetching from OpenAlex..."):
            n = sync(query=query, pages=pages, per_page=per_page, from_date=from_date)
            total += n

        if include_scopus:
            # Scopus query language differs from OpenAlex.
            # PUBDATETXT(AFT ...) looks tempting, but in practice often yields 0 results
            # (format/field semantics differ). Use a coarse-but-reliable year filter instead.
            try:
                y = int((from_date or "").split("-", 1)[0])
            except Exception:
                y = None

            # Build a Scopus-safe query.
            # Scopus expects explicit boolean operators; raw free-text with hyphens can trigger 400.
            def _scopus_terms_or(text: str, max_terms: int = 12) -> str:
                """Turn a free-text query into a Scopus-safe OR query.

                Scopus is picky: long AND-chains + hyphenated tokens often yield 0 results or 400.
                For discovery, OR is the right default; we rely on the DB de-dup + filters later.
                """
                raw = " ".join((text or "").replace("\n", " ").split())
                low = raw.lower()

                # Prefer a few meaningful phrases if present
                phrases = [
                    "prognostics health management",
                    "remaining useful life",
                    "digital twin",
                    "hybrid model",
                    "physics-informed",
                    "grey-box",
                ]

                picked: list[str] = []
                for ph in phrases:
                    if ph in low:
                        picked.append(f'"{ph}"')
                        low = low.replace(ph, " ")

                # Remaining tokens
                toks = [t.strip() for t in low.split() if t.strip()]
                for t in toks:
                    # skip very short noise
                    if len(t) < 3:
                        continue
                    t = t.replace('"', "")
                    if any((not ch.isalnum()) for ch in t):
                        picked.append(f'"{t}"')
                    else:
                        picked.append(t)

                # de-dup while preserving order
                seen = set()
                uniq = []
                for t in picked:
                    if t not in seen:
                        seen.add(t)
                        uniq.append(t)
                    if len(uniq) >= max_terms:
                        break

                return " OR ".join(uniq)

            scopus_terms = _scopus_terms_or(query)
            scopus_q = f"TITLE-ABS-KEY({scopus_terms})" if scopus_terms else "TITLE-ABS-KEY(\"prognostics\")"
            if y:
                # Scopus doesn't accept ">=" here; use a strict greater-than on previous year.
                scopus_q += f" AND PUBYEAR > {y-1}"

            with st.spinner("Fetching from Scopus (Elsevier)..."):
                from sync import sync_scopus
                n2 = sync_scopus(
                    scopus_q,
                    count=25,
                    start=0,
                    enrich_abstracts=enrich_scopus_abstracts,
                )
                total += n2

        st.success(f"Synced {total} records (upserted).")

    st.divider()
    st.header("Taxonomy (rules v0)")
    if st.button("Re-run taxonomy for all"):
        with st.spinner("Classifying from title+abstract..."):
            n = 0
            for row in iter_papers():
                tax = classify(row["title"], row["abstract"])  # type: ignore
                update_taxonomy(
                    row["id"],
                    ",".join(tax.task_types) if tax.task_types else None,
                    ",".join(tax.hybrid_types) if tax.hybrid_types else None,
                    tax.case_study,
                    ",".join(tax.methods) if tax.methods else None,
                )
                n += 1
        st.success(f"Reclassified {n} papers.")

st.title("PHM Hybrid Research Dashboard")
st.caption("Multi-source research explorer for PHM, hybrid models, and taxonomy-driven insights.")

# Data
rows = list_papers(limit=2000)
if not rows:
    st.info("No papers yet. Use 'Sync now' in the sidebar.")
    st.stop()

df = pd.DataFrame([dict(r) for r in rows])

# Derive provider/platform for display (provider=ingest source, platform=publisher site)
_df = df.copy()
_df["provider"] = _df.get("source").fillna("unknown") if "source" in _df.columns else "unknown"

import re

def _infer_platform(url: str | None, doi: str | None) -> str | None:
    u = (url or "").lower()
    d = (doi or "").lower()
    if "arxiv.org" in u or d.startswith("10.48550/"): return "arxiv"
    if "ieeexplore.ieee.org" in u or d.startswith("10.1109/"): return "ieee"
    if "sciencedirect.com" in u or d.startswith("10.1016/"): return "sciencedirect"
    if "link.springer.com" in u or d.startswith("10.1007/"): return "springer"
    if "dl.acm.org" in u or d.startswith("10.1145/"): return "acm"
    if "onlinelibrary.wiley.com" in u: return "wiley"
    if "mdpi.com" in u or d.startswith("10.3390/"): return "mdpi"
    if "nature.com" in u or d.startswith("10.1038/"): return "nature"
    if "tandfonline.com" in u: return "tandf"
    if "frontiersin.org" in u: return "frontiers"
    if "hindawi.com" in u: return "hindawi"
    if "journals.sagepub.com" in u or "sagepub.com" in u: return "sage"
    return None

_df["platform_inferred"] = _df.apply(lambda r: _infer_platform(r.get("landing_page_url"), r.get("doi")), axis=1)
_df["platform_display"] = _df["platform_inferred"].fillna("unknown")

def _split_to_rows(df: pd.DataFrame, col: str) -> pd.DataFrame:
    # split comma lists into rows
    out = []
    for _, r in df.iterrows():
        vals = [v.strip() for v in (r.get(col) or '').split(',') if v.strip()]
        if not vals:
            out.append({**r.to_dict(), col: None})
        else:
            for v in vals:
                out.append({**r.to_dict(), col: v})
    return pd.DataFrame(out)

# Tabs: Overview | Sources | Papers
ov, src_tab, papers_tab = st.tabs(["Overview", "Sources", "Papers"])

with ov:
    # KPIs
    total = len(df)
    n_reviews = int((df["is_review"].fillna(0) == 1).sum())
    n_articles = total - n_reviews
    n_journals = df["journal"].dropna().nunique()
    n_sources = df.get("source", pd.Series([None]*len(df))).nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total papers", total)
    c2.metric("Reviews", n_reviews)
    c3.metric("Journals", n_journals)
    c4.metric("Sources", n_sources)

    sns.set_theme(style="whitegrid")

    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Papers per year (by type)**")
        tmp = df.copy()
        tmp["type"] = pd.to_numeric(tmp["is_review"], errors="coerce").fillna(0).astype(int).map(lambda v: "review" if v == 1 else "article")
        tmp = tmp[tmp["publication_year"].notna()].groupby(["publication_year", "type"]).size().reset_index(name="count")
        if not tmp.empty:
            fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
            sns.lineplot(data=tmp, x="publication_year", y="count", hue="type", marker="o", ax=ax)
            ax.set_xlabel("Year"); ax.set_ylabel("# papers"); ax.legend(title="")
            st.pyplot(fig, clear_figure=True)
        else:
            st.write("Not enough data.")

    with cB:
        st.markdown("**Task × Hybrid heatmap**")
        base = df[(df["task_types"].notna()) | (df["hybrid_types"].notna())].copy()
        if not base.empty:
            tdf = _split_to_rows(base, "task_types")
            hdf = _split_to_rows(tdf, "hybrid_types")
            hh = hdf.groupby(["task_types", "hybrid_types"]).size().reset_index(name="count")
            hh = hh[(hh["task_types"].notna()) & (hh["hybrid_types"].notna())]
            if not hh.empty:
                pivot = hh.pivot_table(index="task_types", columns="hybrid_types", values="count", fill_value=0, aggfunc="sum").astype(int)
                fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
                sns.heatmap(pivot, cmap="Blues", linewidths=.5, annot=True, fmt="d", ax=ax)
                ax.set_xlabel("Hybrid"); ax.set_ylabel("Task")
                st.pyplot(fig, clear_figure=True)
            else:
                st.write("No task/hybrid overlap yet.")
        else:
            st.write("No taxonomy labels yet.")

with src_tab:
    st.subheader("Sources overview")
    if "source" in df.columns:
        by_provider = (
            _df.assign(provider=_df["provider"].fillna("unknown"))
              .groupby("provider")
              .size()
              .reset_index(name="count")
              .sort_values("count", ascending=False)
        )
        by_platform = (
            _df.assign(platform=_df.get("platform").fillna(_df["platform_display"]) if "platform" in _df.columns else _df["platform_display"])\
              .groupby("platform")
              .size()
              .reset_index(name="count")
              .sort_values("count", ascending=False)
        )
    else:
        by_provider = pd.DataFrame({"provider": ["unknown"], "count": [len(df)]})
        by_platform = pd.DataFrame({"platform": ["unknown"], "count": [len(df)]})

    csp1, csp2 = st.columns(2)
    with csp1:
        st.write("Provider (ingest source)")
        st.dataframe(by_provider, use_container_width=True, hide_index=True)
    with csp2:
        st.write("Platform (publisher/site)")
        st.dataframe(by_platform, use_container_width=True, hide_index=True)

with papers_tab:
    st.subheader("Papers")
    # Filters
    col1, col2, col3, col4, col5 = st.columns([2,1,1,1,1])
    with col1:
        q = st.text_input("Search (title/abstract/journal/authors/DOI/id)")
    with col2:
        year_min = st.number_input("Min year", min_value=1990, max_value=2100, value=2025, step=1)
    with col3:
        reviews_filter = st.selectbox("Type", ["All", "Reviews only", "Non-reviews"], index=0)
    with col4:
        limit = st.selectbox("Max rows", [50, 100, 200, 500, 1000], index=2)
    with col5:
        sort_by = st.selectbox("Sort", ["Date", "Citations", "Rubric score"], index=0)

    reviews_only = None
    if reviews_filter == "Reviews only":
        reviews_only = True
    elif reviews_filter == "Non-reviews":
        reviews_only = False

    rows2 = list_papers(limit=int(limit), year_min=int(year_min), q=q.strip() or None, reviews_only=reviews_only)
    if not rows2:
        st.info("No papers match.")
        st.stop()

    df2 = pd.DataFrame([dict(r) for r in rows2])
    if sort_by == "Citations":
        df2 = df2.sort_values(by=["cited_by_count"], ascending=False, na_position="last")
    elif sort_by == "Rubric score":
        df2 = df2.sort_values(by=["rubric_total"], ascending=False, na_position="last")
    else:
        df2 = df2.sort_values(by=["publication_date"], ascending=False, na_position="last")

    df_show = df2[[
        "publication_date", "publication_year", "is_review", "rubric_total",
        "task_types", "hybrid_types", "case_study", "methods",
        "cited_by_count", "journal", "source",
        "authors", "title", "doi", "openalex_id"
    ]].copy()
    df_show.rename(columns={
        "publication_date": "Date", "publication_year": "Year", "is_review": "Review?",
        "rubric_total": "Score", "task_types": "Task", "hybrid_types": "Hybrid",
        "case_study": "Case", "methods": "Methods", "cited_by_count": "Citations",
        "journal": "Journal", "source": "Source", "authors": "Authors",
        "title": "Title", "doi": "DOI", "openalex_id": "OpenAlex ID",
    }, inplace=True)
    df_show["Review?"] = pd.to_numeric(df_show["Review?"], errors="coerce").fillna(0).astype(int).map(lambda v: "review" if v == 1 else "article")

    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "DOI": st.column_config.LinkColumn("DOI", display_text="doi"),
            "OpenAlex ID": st.column_config.LinkColumn("OpenAlex ID", display_text="openalex"),
        },
    )

    with st.expander("Paper detail"):
        options = df2["id"].tolist()
        if options:
            selected = st.selectbox("Select paper (by title)", options=options, format_func=lambda pid: df2.loc[df2["id"] == pid, "title"].iloc[0])
            paper_row = get_paper(selected)
            if paper_row:
                paper = dict(paper_row)
                st.markdown(f"### {paper.get('title', '')}")
                meta_cols = st.columns(4)
                meta_cols[0].metric("Date", paper.get("publication_date") or "")
                meta_cols[1].metric("Citations", paper.get("cited_by_count") if paper.get("cited_by_count") is not None else "")
                meta_cols[2].write("**Type**"); meta_cols[2].write("review" if pd.to_numeric(paper.get("is_review"), errors="coerce") == 1 else (paper.get("work_type") or "article"))
                meta_cols[3].write("**Source**"); meta_cols[3].write(paper.get("source") or "—")
                if paper.get("doi"): st.write(paper["doi"]) 
                if paper.get("openalex_id"): st.write(paper["openalex_id"]) 
                st.write("**Taxonomy**"); st.write({
                    "task_types": paper.get("task_types"),
                    "hybrid_types": paper.get("hybrid_types"),
                    "case_study": paper.get("case_study"),
                    "methods": paper.get("methods"),
                })
                st.write("**Summary**")
                if paper.get("summary_text"):
                    st.write(paper["summary_text"])  # compact, rubric-aligned summary
                    if paper.get("rubric_total") is not None:
                        st.caption(f"Rubric score: {paper['rubric_total']}")
                elif paper.get("abstract"):
                    summary = " ".join(textwrap.wrap(paper["abstract"], width=120)[:6])
                    st.write(summary)
                else:
                    st.write("—")
