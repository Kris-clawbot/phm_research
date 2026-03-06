import textwrap

import pandas as pd
import streamlit as st

from db import init_db, list_papers, get_paper, update_taxonomy, iter_papers
from sync import sync, DEFAULT_QUERY
from taxonomy import classify

# dataviz (matplotlib/seaborn) per python-dataviz skill
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="PHM Hybrid Research Dashboard", layout="wide")

init_db()

st.title("PHM Hybrid Research Dashboard")
st.caption(
    "Single-user MVP: fetches papers from OpenAlex, shows a searchable table + basic plots. "
    "Taxonomy classification comes next."
)

with st.sidebar:
    st.header("Sync")
    query = st.text_area("OpenAlex search query", value=DEFAULT_QUERY, height=120)
    from_date = st.text_input("From date (YYYY-MM-DD)", value="2025-01-01")
    pages = st.slider("Pages", min_value=1, max_value=20, value=5)
    per_page = st.slider("Per page", min_value=10, max_value=200, value=50, step=10)
    if st.button("Sync now", type="primary"):
        with st.spinner("Fetching from OpenAlex..."):
            n = sync(query=query, pages=pages, per_page=per_page, from_date=from_date)
        st.success(f"Synced {n} records (upserted).")

    st.divider()
    st.header("Taxonomy (rules v0)")
    if st.button("Re-run taxonomy for all stored papers"):
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

st.subheader("Papers")

col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    q = st.text_input("Search (title/abstract/journal/authors/DOI/id)")
with col2:
    year_min = st.number_input("Min year", min_value=1990, max_value=2100, value=2025, step=1)
with col3:
    reviews_filter = st.selectbox("Type", ["All", "Reviews only", "Non-reviews"], index=0)
with col4:
    limit = st.selectbox("Max rows", [50, 100, 200, 500, 1000], index=2)

reviews_only = None
if reviews_filter == "Reviews only":
    reviews_only = True
elif reviews_filter == "Non-reviews":
    reviews_only = False

rows = list_papers(limit=int(limit), year_min=int(year_min), q=q.strip() or None, reviews_only=reviews_only)

if not rows:
    st.info("No papers yet. Click 'Sync now' in the sidebar.")
    st.stop()

df = pd.DataFrame([dict(r) for r in rows])

# ------- Table -------
df_show = df[["publication_date", "publication_year", "is_review", "task_types", "hybrid_types", "case_study", "methods", "cited_by_count", "journal", "authors", "title", "doi", "openalex_id"]].copy()
df_show.rename(
    columns={
        "publication_date": "Date",
        "publication_year": "Year",
        "is_review": "Review?",
        "task_types": "Task",
        "hybrid_types": "Hybrid",
        "case_study": "Case",
        "methods": "Methods",
        "cited_by_count": "Citations",
        "journal": "Journal",
        "authors": "Authors",
        "title": "Title",
        "doi": "DOI",
        "openalex_id": "OpenAlex ID",
    },
    inplace=True,
)
df_show["Review?"] = df_show["Review?"].map(lambda x: "review" if int(x or 0) == 1 else "article")

st.dataframe(
    df_show,
    use_container_width=True,
    hide_index=True,
    column_config={
        "DOI": st.column_config.LinkColumn("DOI", display_text="doi"),
        "OpenAlex ID": st.column_config.LinkColumn("OpenAlex ID", display_text="openalex"),
    },
)

# ------- Plots -------
st.subheader("Plots (quick insights)")

plot_df = df.copy()
plot_df["type"] = plot_df["is_review"].map(lambda x: "review" if int(x or 0) == 1 else "article")
plot_df["year"] = plot_df["publication_year"].fillna(0).astype(int)

c1, c2 = st.columns(2)

with c1:
    st.markdown("**Papers per year (by type)**")
    tmp = plot_df[plot_df["year"] > 0].groupby(["year", "type"]).size().reset_index(name="count")
    if not tmp.empty:
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
        sns.lineplot(data=tmp, x="year", y="count", hue="type", marker="o", ax=ax)
        ax.set_xlabel("Year")
        ax.set_ylabel("# papers")
        ax.legend(title="")
        st.pyplot(fig, clear_figure=True)
    else:
        st.write("Not enough data.")

with c2:
    st.markdown("**Top case studies (rules v0)**")
    top_n = 12
    tmp = plot_df[plot_df["case_study"].notna()].groupby("case_study").size().sort_values(ascending=False).head(top_n)
    if not tmp.empty:
        fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
        sns.barplot(x=tmp.values, y=tmp.index, ax=ax)
        ax.set_xlabel("# papers")
        ax.set_ylabel("")
        st.pyplot(fig, clear_figure=True)
    else:
        st.write("No case-study labels yet (run taxonomy or sync again).")

st.markdown("**Top journals/venues (current view)**")
_tmpj = plot_df[plot_df["journal"].notna()].groupby("journal").size().sort_values(ascending=False).head(15)
if not _tmpj.empty:
    fig, ax = plt.subplots(figsize=(10, 4), dpi=150)
    sns.barplot(x=_tmpj.values, y=_tmpj.index, ax=ax)
    ax.set_xlabel("# papers")
    ax.set_ylabel("")
    st.pyplot(fig, clear_figure=True)

# ------- Detail -------
st.subheader("Paper detail")
selected = st.selectbox(
    "Select paper (by title)",
    options=df["id"].tolist(),
    format_func=lambda pid: df.loc[df["id"] == pid, "title"].iloc[0],
)

paper = get_paper(selected)
if paper:
    st.markdown(f"### {paper['title']}")

    meta_cols = st.columns(4)
    meta_cols[0].metric("Date", paper["publication_date"] or "")
    meta_cols[1].metric("Citations", paper["cited_by_count"] if paper["cited_by_count"] is not None else "")
    meta_cols[2].write("**Type**")
    meta_cols[2].write("review" if int(paper["is_review"] or 0) == 1 else (paper["work_type"] or "article"))
    meta_cols[3].write("**Identifiers**")
    if paper["doi"]:
        meta_cols[3].write(paper["doi"])
    if paper["openalex_id"]:
        meta_cols[3].write(paper["openalex_id"])

    st.write("**Authors**")
    st.write(paper["authors"] or "—")

    st.write("**Taxonomy (rules v0)**")
    st.write(
        {
            "task_types": paper["task_types"],
            "hybrid_types": paper["hybrid_types"],
            "case_study": paper["case_study"],
            "methods": paper["methods"],
        }
    )

    st.write("**Journal / venue**")
    st.write(paper["journal"] or "—")

    if paper["landing_page_url"]:
        st.write("**Landing page**")
        st.write(paper["landing_page_url"])

    st.write("**Abstract**")
    st.write(paper["abstract"] or "(No abstract available from OpenAlex for this record)")

    st.write("**Quick summary (MVP placeholder)**")
    if paper["abstract"]:
        summary = " ".join(textwrap.wrap(paper["abstract"], width=120)[:6])
        st.write(summary)
    else:
        st.write("—")
