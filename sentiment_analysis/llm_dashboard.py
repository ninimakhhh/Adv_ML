"""
sentiment_analysis/llm_dashboard.py
────────────────────────────────────────────────────────────────────────────────
Streamlit rendering for the "LLM Dashboard" tab in admin_app.py.

Usage — replace the TODO block in admin_app.py with:

    elif selected_tab == "LLM Dashboard":
        from sentiment_analysis.llm_dashboard import render_llm_dashboard
        render_llm_dashboard()

Requires sentiment_events.json to exist (run pipeline.py first).
If the file is missing, a setup guide is shown instead.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from sentiment_analysis.aggregator import (
    category_sentiment,
    cross_reference_alerts,
    load_events,
    problem_frequency,
    sentiment_trend,
    top_problem_products,
    ASPECTS,
)
from shared.logger import get_logger

logger = get_logger(__name__)


# ── Helper: convert hex to rgba with transparency ────────────────────────────
def _hex_to_rgba(hex_color: str, alpha: float = 0.2) -> str:
    """Convert hex color to rgba with transparency."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"
    return f"rgba(100, 100, 100, {alpha})"  # fallback

# ── Colour palette (consistent with admin_app.py) ────────────────────────────
C_POS   = "#10B981"   # emerald
C_NEU   = "#6B7280"   # gray
C_NEG   = "#EF4444"   # red
C_BRAND = "#4F46E5"   # indigo
C_WARN  = "#F59E0B"   # amber

SENTIMENT_COLORS = {"Positive": C_POS, "Neutral": C_NEU, "Negative": C_NEG}

CATEGORY_LABELS = {
    "cat_beauty":  "Beauty",
    "cat_books":   "Books",
    "cat_fashion": "Fashion",
}

ASPECT_LABELS = {
    "delivery":         "Delivery",
    "quality":          "Quality",
    "accuracy":         "Accuracy",
    "packaging":        "Packaging",
    "customer_service": "Support",
    "value":            "Value",
}

_EVENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "mock" / "sentiment_events.json"


# ── Main entry point ─────────────────────────────────────────────────────────

def render_llm_dashboard() -> None:
    st.markdown("### LLM Sentiment Analysis Dashboard")
    logger.info("Rendering LLM Dashboard")

    # Guard: events file must exist
    if not _EVENTS_PATH.exists():
        logger.warning(f"Events file not found at {_EVENTS_PATH}")
        _render_setup_guide()
        return

    events = load_events()
    if not events:
        logger.warning("sentiment_events.json is empty")
        st.warning("sentiment_events.json is empty. Run the pipeline to populate it.")
        _render_setup_guide()
        return

    logger.info(f"Rendering dashboard with {len(events)} events")

    # ── Top KPI strip ────────────────────────────────────────────────────────
    _render_kpi_strip(events)

    st.markdown("---")

    # ── Section 1: Alerts ────────────────────────────────────────────────────
    _render_alerts(events)

    st.markdown("---")

    # ── Section 2: Sentiment trend ───────────────────────────────────────────
    _render_trend(events)

    st.markdown("---")

    # ── Section 4: Problem frequency ─────────────────────────────────────────
    _render_problem_frequency(events)

    st.markdown("---")

    # ── Section 5: Top problem products ──────────────────────────────────────
    _render_top_products(events)

    st.markdown("---")

    # ── Section 6: Category sentiment ranking ─────────────────────────────────
    _render_category_ranking(events)


# ── Section renderers ─────────────────────────────────────────────────────────

def _render_kpi_strip(events: list[dict]) -> None:
    total  = len(events)
    pos    = sum(1 for e in events if e.get("overall_sentiment") == "Positive")
    neg    = sum(1 for e in events if e.get("overall_sentiment") == "Negative")
    high   = sum(1 for e in events if e.get("severity") == "high")
    alerts = len(cross_reference_alerts(events))

    col1, col2, col3, col4, col5 = st.columns(5)
    _kpi(col1, "Events Analysed",  str(total),               C_BRAND)
    _kpi(col2, "Positive",         f"{pos}",                 C_POS)
    _kpi(col3, "Negative",         f"{neg}",                 C_NEG)
    _kpi(col4, "High Severity",    f"{high}",                C_WARN)
    _kpi(col5, "Cross-Ref Alerts", f"{alerts}",              C_NEG)


def _render_alerts(events: list[dict]) -> None:
    st.markdown("### 🚨 Cross-Reference Alerts")
    st.caption("Products with confirmed problems in **both** negative reviews and support tickets (last 14 days).")

    alerts = cross_reference_alerts(events)

    if not alerts:
        st.success("✅ No cross-referenced problem products in the last 14 days.")
        return

    for alert in alerts:
        problems_str = ", ".join(
            f"{p['label']} ({p['count']})" for p in alert["dominant_problems"]
        ) or "—"
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 1, 1, 3])
            with col1:
                st.markdown(f"**{alert['product_name']}**")
                st.caption(f"`{alert['product_id']}`")
            with col2:
                st.metric("Neg. Reviews", alert["negative_review_count"])
            with col3:
                st.metric("Tickets", alert["ticket_count"])
            with col4:
                st.markdown(f"**Problems:** {problems_str}")
                st.caption(f"💡 {alert['suggested_action']}")


def _render_trend(events: list[dict]) -> None:
    st.markdown("### 📈 Sentiment Trend (Last 30 Days)")

    col_src, _ = st.columns([1, 3])
    with col_src:
        source_filter = st.selectbox(
            "Source", ["All", "Reviews only", "Tickets only"],
            key="trend_source"
        )
    src_map = {"All": None, "Reviews only": "review", "Tickets only": "ticket"}
    trend = sentiment_trend(events, days=30, source=src_map[source_filter])

    if not trend:
        st.info("Not enough time-stamped events to draw a trend.")
        return

    df = pd.DataFrame(trend)
    df["date"] = pd.to_datetime(df["date"])

    fig = go.Figure()
    for sentiment, color in SENTIMENT_COLORS.items():
        if sentiment in df.columns:
            fig.add_trace(go.Scatter(
                x=df["date"], y=df[sentiment],
                name=sentiment, mode="lines",
                line=dict(color=color, width=2),
                stackgroup="one",
                fillcolor=_hex_to_rgba(color, alpha=0.2),
            ))
    fig.update_layout(
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)



def _render_problem_frequency(events: list[dict]) -> None:
    st.markdown("### 📊 Most Common Problems")

    col1, col2 = st.columns(2)

    with col1:
        st.caption("**Reviews**")
        freq_r = problem_frequency(events, source="review")
        if freq_r:
            df_r = pd.DataFrame(freq_r)
            fig = px.bar(
                df_r, x="count", y="problem", orientation="h",
                text="pct", color="count",
                color_continuous_scale=["#FEE2E2", "#EF4444"],
                labels={"count": "Occurrences", "problem": "Problem Type"},
            )
            fig.update_traces(texttemplate="%{text}%", textposition="outside")
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False,
                height=300, margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No review problems found.")



def _render_top_products(events: list[dict]) -> None:
    window = st.slider("Window (days)", 7, 90, 30, key="top_products_window_days")
    st.markdown(f"### ⚠️ Top Problem Products (Last {window} Days)")

    rows = top_problem_products(events, n=10, window_days=window)

    if not rows:
        st.success("✅ No products with negative reviews in this window.")
        return

    for row in rows:
        problems_str = ", ".join(
            f"{p['label'].replace('_', ' ')} ×{p['count']}"
            for p in row["dominant_problems"]
        ) or "—"

        with st.expander(
            f"**{row['product_name']}** — {row['negative_count']} negative reviews  "
            f"· severity {row['avg_severity_score']:.1f}/3"
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Category:** {CATEGORY_LABELS.get(row['category_id'], row['category_id'])}")
                st.markdown(f"**Top Problems:** {problems_str}")

            with col2:
                asp = row["avg_aspect_scores"]
                asp_data = {
                    ASPECT_LABELS[k]: v
                    for k, v in asp.items()
                    if v is not None
                }
                if asp_data:
                    fig = go.Figure(go.Bar(
                        x=list(asp_data.values()),
                        y=list(asp_data.keys()),
                        orientation="h",
                        marker_color=[
                            C_NEG if v < -0.2 else C_POS if v > 0.2 else C_NEU
                            for v in asp_data.values()
                        ],
                    ))
                    fig.update_layout(
                        height=180,
                        xaxis=dict(range=[-1, 1]),
                        margin=dict(l=0, r=0, t=0, b=0),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig, use_container_width=True)


def _render_category_ranking(events: list[dict]) -> None:
    st.markdown("### 📉 Category Sentiment Ranking")
    st.caption("Worst categories first. Mean score: Positive=+1, Neutral=0, Negative=-1.")

    rows = category_sentiment(events)
    if not rows:
        st.info("No categorised events found.")
        return

    for row in rows:
        cat_label = CATEGORY_LABELS.get(row["category_id"], row["category_id"])
        score     = row["mean_score"]
        color     = C_NEG if score < -0.1 else C_POS if score > 0.1 else C_NEU
        worst     = ASPECT_LABELS.get(row["worst_aspect"], row["worst_aspect"] or "—")

        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 2])
            with col1:
                st.markdown(f"**{cat_label}**")
            with col2:
                st.markdown(
                    f"<span style='color:{color};font-weight:700;font-size:18px'>{score:+.2f}</span>",
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(f"✅ {row['positive']}")
            with col4:
                st.markdown(f"❌ {row['negative']}")
            with col5:
                st.markdown(f"Worst aspect: **{worst}**")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _kpi(col, label: str, value: str, color: str) -> None:
    with col:
        st.markdown(
            f"""
            <div style="background:#FFF;border:1px solid #E5E7EB;border-radius:8px;
                        padding:16px;text-align:center;">
                <p style="color:#6B7280;font-size:12px;margin:0">{label}</p>
                <p style="color:{color};font-size:26px;font-weight:700;margin:6px 0 0">{value}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_setup_guide() -> None:
    st.markdown("""
    #### ⚙️ Setup Required

    The sentiment event store has not been populated yet. Run the pipeline once:

    ```bash
    # From project root — process a sample first (cheap & fast)
    python -m sentiment_analysis.pipeline --max-reviews 20 --max-tickets 10

    # Full run (all reviews + tickets)
    python -m sentiment_analysis.pipeline
    ```

    The pipeline is **incremental** — safe to stop and resume at any time.
    Each new review or ticket posted is processed once and cached.
    """)