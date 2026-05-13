import sys
from pathlib import Path

_FRONTEND = Path(__file__).parent
_ROOT = _FRONTEND.parent
for _p in (str(_ROOT), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json

from components.admin_sidebar import render_admin_sidebar
from components.metric_card import metric_card, small_metric
from components.chatbot_widget import render_admin_chatbot_widget
from components.metric_card import metric_card
from shared.db.repository import TicketRepository
from shared.db.migrate import _DB_PATH, migrate
from chatbot.registry.loader import load_intents
from chatbot.feedback.analyzer import weekly_review, export_labeled_jsonl

from sentiment_analysis.llm_dashboard import render_llm_dashboard

# Page config
st.set_page_config(layout="wide", page_title="Olá Market - Admin Dashboard")

st.markdown("""
<style>
    /* Hide Streamlit default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="stSidebarNavItems"] { display: none !important; }

    /* Overall styling */
    body {
        background-color: #F7F8FA;
        font-family: 'Inter', system-ui, -apple-system;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background:#F7F8FA; border-radius:8px; border:1px solid #E5E7EB; padding:12px 24px;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background:#FFFFFF; border-color:#4F46E5;
    }
    .card { background:#FFF; border:1px solid #E5E7EB; border-radius:8px; padding:20px; margin-bottom:16px; }
    .transcript-user {
        background:#FF6B35; color:#fff; padding:8px 12px; border-radius:12px 12px 2px 12px;
        display:inline-block; max-width:75%; font-size:13px; margin:3px 0;
    }
    .transcript-bot {
        background:#F0F0F0; color:#111; padding:8px 12px; border-radius:12px 12px 12px 2px;
        display:inline-block; max-width:75%; font-size:13px; margin:3px 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "classified_tickets" not in st.session_state:
    st.session_state.classified_tickets = []

if "pending_reviews" not in st.session_state:
    with open("data/mock/recent_tickets.json") as f:
        tickets_data = json.load(f)
        st.session_state.pending_reviews = tickets_data["to_review"].copy()
        st.session_state.auto_classified = tickets_data["classified"].copy()

# Load data
with open("data/mock/admin_metrics.json") as f:
    metrics_data = json.load(f)

with open("data/mock/recent_chats.json") as f:
    chats_data = json.load(f)

with open("data/mock/products.json") as f:
    products_by_id = {p["id"]: p["name"] for p in json.load(f)}

# ── Comments tab: load reviews + sentiment events, derive classification ─────
_ASPECT_KEYS = ("delivery", "quality", "accuracy", "packaging", "customer_service", "value")
_ASPECT_LABEL = {
    "delivery": "Delivery",
    "quality": "Quality",
    "accuracy": "Accuracy",
    "packaging": "Packaging",
    "customer_service": "Customer Service",
    "value": "Value",
}
_SEVERITY_LABEL = {"high": "High", "medium": "Medium", "low": "Low"}
_ASPECT_TO_TEAM = {
    "Delivery": "Logistics",
    "Quality": "Product Quality",
    "Accuracy": "Catalog",
    "Packaging": "Logistics",
    "Customer Service": "Support",
    "Value": "Marketing",
    "None": "General",
}


def _dominant_aspect(event: dict) -> str:
    best_label = "None"
    best_abs = 0.0
    for key in _ASPECT_KEYS:
        score = event.get(key)
        if score is None:
            continue
        if abs(score) > best_abs and abs(score) > 0.1:
            best_abs = abs(score)
            best_label = _ASPECT_LABEL[key]
    return best_label


def _build_classified_comment(review: dict, event: dict) -> dict:
    aspect = _dominant_aspect(event)
    return {
        "id": review["id"],
        "author": review.get("author_name", "—"),
        "product_id": review.get("product_id"),
        "title": review.get("title", ""),
        "body": review.get("body", ""),
        "rating": review.get("rating"),
        "date": review.get("date"),
        "aspect": aspect,
        "severity": _SEVERITY_LABEL.get(event.get("severity", "low"), "Low"),
        "sentiment": event.get("overall_sentiment", "Neutral"),
        "confidence": event.get("confidence", 0),
        "dominant_problem": event.get("dominant_problem", "none"),
        "assigned_team": _ASPECT_TO_TEAM.get(aspect, "General"),
    }


if "pending_comments" not in st.session_state:
    with open("data/mock/reviews.json", encoding="utf-8") as f:
        _all_reviews = json.load(f)
    with open("data/mock/sentiment_events.json", encoding="utf-8") as f:
        _all_events = json.load(f)

    _reviews_by_id = {r["id"]: r for r in _all_reviews}
    _review_events = [e for e in _all_events if e.get("source") == "review"]

    _classified: list[dict] = []
    _classified_ids: set[str] = set()
    for _ev in _review_events:
        _sid = _ev.get("source_id")
        _rev = _reviews_by_id.get(_sid)
        if _rev is None:
            continue
        _classified.append(_build_classified_comment(_rev, _ev))
        _classified_ids.add(_sid)

    # Pick the same 5 pending reviews the realign script chose (seed-deterministic).
    import random as _random
    _candidates = [r for r in _all_reviews if r["id"] not in _classified_ids]
    _rng = _random.Random(31)  # same seed as scripts/realign_comment_dates.py
    _rng.shuffle(_candidates)
    _pending_raw = _candidates[:5]
    _pending: list[dict] = []
    for _rev in _pending_raw:
        _pending.append({
            "id": _rev["id"],
            "author": _rev.get("author_name", "—"),
            "product_id": _rev.get("product_id"),
            "title": _rev.get("title", ""),
            "body": _rev.get("body", ""),
            "rating": _rev.get("rating"),
            "date": _rev.get("date"),
        })

    st.session_state.classified_comments = _classified
    st.session_state.pending_comments = _pending

# Render sidebar
render_admin_sidebar()

st.markdown("""
<div style="padding:0 0 20px 0;">
  <h1 style="color:#111827;margin:0;font-weight:800;">Olá Market — Admin</h1>
  <p style="color:#6B7280;margin:8px 0 0 0;">
    Monitor operations, manage support, and evaluate AI performance
  </p>
</div>
""", unsafe_allow_html=True)

selected_tab = st.radio(
    "Navigation",
    ["Main", "Tickets", "Comments", "Sentiment Analysis"],
    horizontal=True,
    key="main_tabs",
    label_visibility="collapsed",
)
st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _intent_label(intent_id: str | None) -> str:
    if not intent_id:
        return "—"
    return INTENT_OPTIONS.get(intent_id, intent_id.replace("_", " ").title())


def _status_badge(status: str) -> str:
    colours = {"open": "#F59E0B", "in_progress": "#3B82F6", "resolved": "#10B981", "closed": "#6B7280"}
    c = colours.get(status, "#9CA3AF")
    return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">{status}</span>'


def _path_badge(path: str) -> str:
    if path.startswith("escalated"):
        return f'<span style="background:#EF4444;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">escalated</span>'
    if path == "bot_resolved":
        return f'<span style="background:#10B981;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">bot resolved</span>'
    return f'<span style="background:#9CA3AF;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">{path}</span>'


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

if selected_tab == "Main":
    kpi = metrics_data["kpi_summary"]
    
    # TOP KPI STRIP
    st.markdown("### Key Performance Indicators · Last 30 days")
    st.caption("Historical aggregates from the last 30 days of support activity. These numbers reflect the full ticket volume, not the smaller live queue shown in the Tickets tab.")

    # Row 1: Tickets
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card(
            "Created", f"{kpi['tickets']['created']}", icon="📥",
            description="Total support tickets submitted in the last 30 days (historical aggregate).",
        )
    with col2:
        metric_card(
            "Solved", f"{kpi['tickets']['solved']}", icon="✅",
            description="Tickets marked resolved over the last 30 days — by the bot or a human agent.",
        )
    with col3:
        metric_card(
            "Open", f"{kpi['tickets']['open']}", icon="🔓",
            description="Tickets from the last 30 days still awaiting a first or final response.",
        )
    with col4:
        metric_card(
            "Reopened", f"{kpi['tickets']['reopened']}", icon="🔄",
            description="Previously resolved tickets re-opened by the customer in the last 30 days.",
        )

    # Row 2: AI Performance
    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card(
            "Auto-Resolution", f"{kpi['ai_performance']['auto_resolution_rate']}%", icon="🤖",
            description="Share of tickets fully resolved by the bot with no human intervention (last 30 days).",
        )
    with col2:
        metric_card(
            "Auto-Routed", f"{kpi['ai_performance']['tickets_auto_routed']}", icon="📊",
            description="Tickets automatically classified and assigned to the correct queue (last 30 days).",
        )
    with col3:
        metric_card(
            "AI Accuracy", f"{kpi['ai_performance']['accuracy']}%", icon="🎯",
            description="Intent classification accuracy verified against human-reviewed labels (last 30 days).",
        )

    # Row 3: Response Times
    col1, col2 = st.columns(2)
    with col1:
        metric_card(
            "Avg First Reply",
            f"{kpi['response_times']['avg_first_reply_minutes']}m",
            icon="⏱️",
            description="Median time from ticket creation to the first bot or agent response (last 30 days).",
        )
    with col2:
        metric_card(
            "Avg Resolution Time",
            f"{kpi['response_times']['avg_full_resolution_hours']:.1f}h",
            icon="⏲️",
            description="Median time from ticket creation to final resolution or closure (last 30 days).",
        )
    
    st.markdown("---")
    
    # ROW 1: MAIN CHARTS
    st.markdown("### Trends")
    
    col1, col2 = st.columns([0.6, 0.4])
    
    # LEFT: Tickets Created vs Solved
    with col1:
        daily_data = pd.DataFrame(metrics_data["daily_metrics"])
        daily_data["date"] = pd.to_datetime(daily_data["date"])
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=daily_data["date"],
            y=daily_data["created"],
            name="Created",
            marker_color="#4F46E5",
            opacity=0.8
        ))
        fig.add_trace(go.Scatter(
            x=daily_data["date"],
            y=daily_data["solved"],
            name="Solved",
            mode="lines",
            line=dict(color="#10B981", width=3)
        ))
        fig.update_layout(
            title="Tickets Created vs Solved (30 Days)",
            xaxis_title="Date",
            yaxis_title="Count",
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=400,
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # RIGHT: Response Time Trends
    with col2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=daily_data["date"],
            y=daily_data["first_reply_time"],
            name="First Reply",
            fill="tozeroy",
            line=dict(color="#F59E0B"),
        ))
        fig.add_trace(go.Scatter(
            x=daily_data["date"],
            y=daily_data["resolution_time"],
            name="Full Resolution",
            fill="tozeroy",
            line=dict(color="#EF4444"),
        ))
        fig.update_layout(
            title="Response Time Trends",
            xaxis_title="Date",
            yaxis_title="Minutes/Hours",
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=400,
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # ROW 2: DISTRIBUTIONS
    st.markdown("### Distributions")
    
    col1, col2, col3 = st.columns(3)
    
    # Tickets by Channel
    with col1:
        channel_data = metrics_data["channel_distribution"]
        fig = go.Figure(data=[go.Pie(
            labels=list(channel_data.keys()),
            values=list(channel_data.values()),
            hole=0.4,
            marker_colors=["#4F46E5", "#10B981", "#F59E0B", "#EF4444"]
        )])
        fig.update_layout(
            title="Tickets by Channel",
            height=350,
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Tickets by Type
    with col2:
        type_data = metrics_data["ticket_type_distribution"]
        fig = go.Figure(data=[go.Pie(
            labels=list(type_data.keys()),
            values=list(type_data.values()),
            hole=0.4,
            marker_colors=["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#6366F1"]
        )])
        fig.update_layout(
            title="Tickets by Type",
            height=350,
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Satisfaction Score
    with col3:
        satisfaction = metrics_data["satisfaction_score"]
        fig = go.Figure(data=[go.Pie(
            labels=["Satisfied", "Other"],
            values=[satisfaction, 100 - satisfaction],
            hole=0.4,
            marker_colors=["#10B981", "#E5E7EB"]
        )])
        fig.update_layout(
            title=f"Satisfaction Score: {satisfaction}%",
            height=350,
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # ROW 3: SENTIMENT TREND
    st.markdown("### Sentiment Analysis")
    
    sentiment_data = metrics_data["sentiment_distribution"]
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Positive</p>
            <p style="color: #10B981; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{sentiment_data['Positive']}</p>
            <p style="color: #6B7280; font-size: 12px; margin: 4px 0 0 0;">{int(sentiment_data['Positive'] / sum(sentiment_data.values()) * 100)}%</p>
        </div>
        """)

    with col2:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Neutral</p>
            <p style="color: #6B7280; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{sentiment_data['Neutral']}</p>
            <p style="color: #6B7280; font-size: 12px; margin: 4px 0 0 0;">{int(sentiment_data['Neutral'] / sum(sentiment_data.values()) * 100)}%</p>
        </div>
        """)

    with col3:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Negative</p>
            <p style="color: #EF4444; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{sentiment_data['Negative']}</p>
            <p style="color: #6B7280; font-size: 12px; margin: 4px 0 0 0;">{int(sentiment_data['Negative'] / sum(sentiment_data.values()) * 100)}%</p>
        </div>
        """)
    
    st.markdown("---")
    
    # AI INSIGHT BANNER
    st.html("""
    <div style="
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
        border-radius: 8px;
        padding: 24px;
        color: white;
        margin: 20px 0;
    ">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div style="flex: 1;">
                <h3 style="margin: 0 0 8px 0; font-size: 18px;">💡 AI Insight of the Day</h3>
                <p style="margin: 0; line-height: 1.5;">
                    Negative sentiment about shipping increased 23% this week. Consider proactive communication about delivery times or offering expedited shipping options.
                </p>
            </div>
        </div>
    </div>
    """)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: TICKETS (HUMAN-IN-THE-LOOP)
# ═══════════════════════════════════════════════════════════════════════════════


elif selected_tab == "Tickets":
    st.markdown("### Ticket Management")

    # Build the union of product_ids referenced by any ticket (for the Product filter)
    all_tickets_for_products = st.session_state.pending_reviews + st.session_state.auto_classified
    product_ids_in_tickets = sorted({t.get("product_id") for t in all_tickets_for_products if t.get("product_id")})
    product_filter_options = ["All"] + product_ids_in_tickets

    def _format_product_option(pid: str) -> str:
        if pid == "All":
            return "All"
        return f"{pid} — {products_by_id.get(pid, 'Unknown')}"

    # TOP FILTER BAR
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        filter_status = st.selectbox("Status", ["All", "Open", "In Progress", "Resolved"])
    with col2:
        filter_urgency = st.selectbox("Urgency", ["All", "High", "Medium", "Low"])
    with col3:
        filter_category = st.selectbox("Category", ["All", "Bug", "Shipping", "Returns", "Payments", "Other"])
    with col4:
        filter_date = st.selectbox("Time Range", ["Last 7 days", "Last 30 days", "All time"])
    with col5:
        filter_product = st.selectbox("Product", product_filter_options, format_func=_format_product_option)

    st.markdown("---")

    # SECTION 1: MANUAL CLASSIFICATION
    st.markdown("### 🔍 Manual Classification (To Review)")

    # The Product filter also applies to pending review tickets.
    if filter_product != "All":
        pending_visible_indices = [
            i for i, t in enumerate(st.session_state.pending_reviews)
            if t.get("product_id") == filter_product
        ]
    else:
        pending_visible_indices = list(range(len(st.session_state.pending_reviews)))

    if len(st.session_state.pending_reviews) == 0:
        st.info("✨ No pending reviews! All tickets have been classified.")
    elif len(pending_visible_indices) == 0:
        st.info("No pending tickets match the selected product filter.")
    else:
        header_col, btn_col = st.columns([3, 1])
        with header_col:
            st.markdown(f"**{len(pending_visible_indices)} of {len(st.session_state.pending_reviews)} tickets pending review**")
        with btn_col:
            if st.button("🤖 Auto-classify pending", key="auto_classify_all", width="stretch"):
                with st.status("Classifying tickets with Claude...", expanded=True) as status:
                    for t in st.session_state.pending_reviews:
                        st.write(f"→ {t['id']}: {t['subject']}")
                        try:
                            result = classify_ticket(t["subject"], t["raw_text"])
                        except Exception as exc:
                            status.update(label=f"Failed on {t['id']}: {exc}", state="error")
                            st.exception(exc)
                            break
                        t["suggested_category"] = result.category
                        t["confidence"] = result.confidence
                        t["sentiment"] = result.sentiment
                        t["urgency"] = result.urgency
                        t["assigned_queue"] = result.assigned_queue
                        t["reasoning"] = result.reasoning
                    else:
                        status.update(label="All tickets classified ✅", state="complete")
                st.rerun()

        for idx in pending_visible_indices:
            ticket = st.session_state.pending_reviews[idx]
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([1, 2, 2, 2])

                with col1:
                    st.caption(f"**{ticket['id']}**")

                with col2:
                    st.caption(f"👤 {ticket['customer']}")

                with col3:
                    st.caption(f"**{ticket['subject']}**")

                with col4:
                    st.caption(f"🤖 {ticket['confidence']}%")

                if ticket.get("product_id"):
                    st.caption(f"📦 {ticket['product_id']} — {products_by_id.get(ticket['product_id'], 'Unknown')}")

                # Expand to show details
                with st.expander("View Details"):
                    st.markdown(f"**Raw Text:**\n\n{ticket['raw_text']}")

                    if ticket.get("reasoning"):
                        st.markdown(f"**AI reasoning:** _{ticket['reasoning']}_")

                    if ticket.get("sentiment") or ticket.get("urgency"):
                        badges = []
                        if ticket.get("sentiment"):
                            badges.append(f"💬 Sentiment: **{ticket['sentiment']}**")
                        if ticket.get("urgency"):
                            badges.append(f"⏱️ Urgency: **{ticket['urgency']}**")
                        if ticket.get("assigned_queue"):
                            badges.append(f"📥 Queue: **{ticket['assigned_queue']}**")
                        st.markdown(" &nbsp;·&nbsp; ".join(badges))

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Suggested Category:** {ticket['suggested_category']} ({ticket['confidence']}%)")
                        category_options = ["Bug", "Shipping", "Returns", "Payments", "Other"]
                        default_idx = (
                            category_options.index(ticket["suggested_category"])
                            if ticket["suggested_category"] in category_options
                            else 0
                        )
                        selected_category = st.selectbox(
                            "Confirm or change category:",
                            category_options,
                            index=default_idx,
                            key=f"category_{idx}"
                        )

                    with col2:
                        st.markdown("**Actions:**")
                        if st.button("✅ Approve Classification", key=f"approve_{idx}", width="stretch"):
                            # Move to classified
                            classified_ticket = {
                                "id": ticket["id"],
                                "customer": ticket["customer"],
                                "subject": ticket["subject"],
                                "raw_text": ticket.get("raw_text", ""),
                                "category": selected_category,
                                "sentiment": ticket.get("sentiment", "Neutral"),
                                "urgency": ticket.get("urgency", "Medium"),
                                "confidence": ticket["confidence"],
                                "assigned_queue": ticket.get(
                                    "assigned_queue",
                                    CATEGORY_TO_QUEUE.get(selected_category, "General"),
                                ),
                                "status": "In Progress",
                                "created_at": datetime.now().isoformat() + "Z",
                                "resolved_at": None,
                                "product_id": ticket.get("product_id"),
                            }
                            st.session_state.auto_classified.append(classified_ticket)
                            st.session_state.pending_reviews.pop(idx)
                            st.rerun()

    st.markdown("---")

    # SECTION 2: AUTOMATICALLY CLASSIFIED
    st.markdown("### ✅ Automatically Classified Tickets")

    if len(st.session_state.auto_classified) == 0:
        st.info("No automatically classified tickets yet.")
    else:
        # Apply filters
        now = datetime.now()
        if filter_date == "Last 7 days":
            date_threshold = now - timedelta(days=7)
        elif filter_date == "Last 30 days":
            date_threshold = now - timedelta(days=30)
        else:
            date_threshold = None

        def _ticket_matches(t: dict) -> bool:
            if filter_status != "All" and t.get("status") != filter_status:
                return False
            if filter_urgency != "All" and t.get("urgency", "Medium") != filter_urgency:
                return False
            if filter_category != "All" and t.get("category") != filter_category:
                return False
            if filter_product != "All" and t.get("product_id") != filter_product:
                return False
            if date_threshold is not None:
                created_at = t.get("created_at")
                if not created_at:
                    return False
                ts = pd.to_datetime(created_at).tz_localize(None)
                if ts < date_threshold:
                    return False
            return True

        filtered_classified = [t for t in st.session_state.auto_classified if _ticket_matches(t)]

        st.markdown(f"**Showing {len(filtered_classified)} of {len(st.session_state.auto_classified)} classified tickets**")

        if len(filtered_classified) == 0:
            st.info("No classified tickets match the current filters.")
        else:
            # Create dataframe for display
            classified_df = pd.DataFrame(filtered_classified)
            classified_df["product"] = classified_df["product_id"].apply(
                lambda pid: products_by_id.get(pid, "—") if pid else "—"
            )
            if "urgency" not in classified_df.columns:
                classified_df["urgency"] = "Medium"

            display_df = classified_df[[
                "id", "customer", "subject", "product", "category", "sentiment", "urgency", "confidence", "assigned_queue", "status"
            ]].copy()

            display_df["confidence"] = display_df["confidence"].astype(str) + "%"

            st.dataframe(
                display_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "id": st.column_config.TextColumn("ID", width=80),
                    "customer": st.column_config.TextColumn("Customer", width=120),
                    "subject": st.column_config.TextColumn("Subject", width=150),
                    "product": st.column_config.TextColumn("Product", width=160),
                    "category": st.column_config.TextColumn("Category", width=100),
                    "sentiment": st.column_config.TextColumn("Sentiment", width=100),
                    "urgency": st.column_config.TextColumn("Urgency", width=80),
                    "confidence": st.column_config.TextColumn("Confidence", width=80),
                    "assigned_queue": st.column_config.TextColumn("Queue", width=120),
                    "status": st.column_config.TextColumn("Status", width=100),
                }
            )

            # ─── MANAGE TICKET PANEL ──────────────────────────────────────────
            st.markdown("#### Manage ticket")
            manage_options = [None] + [t["id"] for t in filtered_classified]
            selected_id = st.selectbox(
                "Select ticket to manage",
                manage_options,
                format_func=lambda x: "—" if x is None else x,
                key="manage_select",
            )

            if selected_id is not None:
                # Find the live reference in session_state (not the filtered copy)
                target = next(
                    (t for t in st.session_state.auto_classified if t["id"] == selected_id),
                    None,
                )
                if target is not None:
                    with st.container(border=True):
                        info_col, edit_col = st.columns(2)

                        with info_col:
                            st.markdown(f"**Customer:** {target['customer']}")
                            st.markdown(f"**Subject:** {target['subject']}")
                            pid = target.get("product_id")
                            product_label = f"`{pid}` — {products_by_id.get(pid, 'Unknown')}" if pid else "—"
                            st.markdown(f"**Product:** {product_label}")
                            st.markdown(f"**Created at:** {target.get('created_at', '—')}")
                            st.markdown(f"**Resolved at:** {target.get('resolved_at') or '—'}")
                            st.markdown(f"**AI confidence:** {target.get('confidence', 0)}%")
                            st.markdown(f"**Sentiment:** {target.get('sentiment', 'Neutral')}")

                        with edit_col:
                            category_options = ["Bug", "Shipping", "Returns", "Payments", "Other"]
                            queue_options = ["Technical Support", "Logistics", "Returns", "Payments", "General"]
                            urgency_options = ["High", "Medium", "Low"]
                            status_options = ["Open", "In Progress", "Resolved"]

                            cur_category = target.get("category", "Other")
                            cur_queue = target.get("assigned_queue", CATEGORY_TO_QUEUE.get(cur_category, "General"))
                            cur_urgency = target.get("urgency", "Medium")
                            cur_status = target.get("status", "In Progress")

                            new_category = st.selectbox(
                                "Category",
                                category_options,
                                index=category_options.index(cur_category) if cur_category in category_options else 0,
                                key=f"manage_cat_{selected_id}",
                            )
                            new_queue = st.selectbox(
                                "Assigned queue",
                                queue_options,
                                index=queue_options.index(cur_queue) if cur_queue in queue_options else queue_options.index(CATEGORY_TO_QUEUE.get(new_category, "General")),
                                key=f"manage_queue_{selected_id}",
                            )
                            new_urgency = st.selectbox(
                                "Urgency",
                                urgency_options,
                                index=urgency_options.index(cur_urgency) if cur_urgency in urgency_options else 1,
                                key=f"manage_urg_{selected_id}",
                            )
                            new_status = st.selectbox(
                                "Status",
                                status_options,
                                index=status_options.index(cur_status) if cur_status in status_options else 1,
                                key=f"manage_status_{selected_id}",
                            )

                            reclass_col, save_col = st.columns(2)
                            with reclass_col:
                                if st.button("🤖 Re-classify with AI", key=f"manage_reclass_{selected_id}", width="stretch"):
                                    try:
                                        raw = target.get("raw_text") or target.get("subject", "")
                                        result = classify_ticket(target["subject"], raw)
                                        target["category"] = result.category
                                        target["sentiment"] = result.sentiment
                                        target["urgency"] = result.urgency
                                        target["assigned_queue"] = result.assigned_queue
                                        target["confidence"] = result.confidence
                                        st.success(f"Re-classified as **{result.category}** ({result.confidence}% confidence).")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"Re-classification failed: {exc}")

                            with save_col:
                                if st.button("💾 Save changes", key=f"manage_save_{selected_id}", width="stretch"):
                                    target["category"] = new_category
                                    target["assigned_queue"] = new_queue
                                    target["urgency"] = new_urgency
                                    previous_status = target.get("status")
                                    target["status"] = new_status
                                    if new_status == "Resolved" and not target.get("resolved_at"):
                                        target["resolved_at"] = datetime.now().isoformat() + "Z"
                                    elif new_status != "Resolved" and previous_status == "Resolved":
                                        target["resolved_at"] = None
                                    st.success("Changes saved.")
                                    st.rerun()

    st.markdown("---")
    
    # KPI MINI CARDS
    st.markdown("### Performance Metrics")
    
    total_tickets = len(st.session_state.pending_reviews) + len(st.session_state.auto_classified)
    auto_classified_pct = (len(st.session_state.auto_classified) / total_tickets * 100) if total_tickets > 0 else 0
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Auto-Classified</p>
            <p style="color: #4F46E5; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{int(auto_classified_pct)}%</p>
        </div>
        """)

    with col2:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Pending Review</p>
            <p style="color: #F59E0B; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{len(st.session_state.pending_reviews)}</p>
        </div>
        """)

    with col3:
        avg_confidence = (
            sum(t["confidence"] for t in st.session_state.pending_reviews) / len(st.session_state.pending_reviews)
            if len(st.session_state.pending_reviews) > 0
            else 0
        )
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Avg Confidence</p>
            <p style="color: #10B981; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{int(avg_confidence)}%</p>
        </div>
        """)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: COMMENTS (review-based, last 7 days)
# ═══════════════════════════════════════════════════════════════════════════

elif selected_tab == "Comments":
    st.markdown("### Comments Management")
    st.caption("Customer reviews from the last 7 days. The 20 already processed by the sentiment pipeline are shown classified; 5 more are waiting for review.")

    _aspect_options = ["Delivery", "Quality", "Accuracy", "Packaging", "Customer Service", "Value", "None"]
    _severity_options = ["High", "Medium", "Low"]
    _sentiment_options = ["Positive", "Neutral", "Negative"]
    _team_options = ["Logistics", "Product Quality", "Catalog", "Support", "Marketing", "General"]

    def _sentiment_from_rating(rating: int) -> str:
        if rating >= 4:
            return "Positive"
        if rating == 3:
            return "Neutral"
        return "Negative"

    def _severity_from_rating(rating: int) -> str:
        if rating == 1:
            return "High"
        if rating == 2:
            return "Medium"
        return "Low"

    # ─── SECTION 1: TO BE CLASSIFIED ─────────────────────────────────────────
    st.markdown("### 🔍 To Be Classified")

    if len(st.session_state.pending_comments) == 0:
        st.info("✨ No pending comments! All caught up.")
    else:
        header_col, btn_col = st.columns([3, 1])
        with header_col:
            st.markdown(f"**{len(st.session_state.pending_comments)} comments pending review**")
        with btn_col:
            if st.button("🤖 Auto-classify all pending", key="comments_auto_all", width="stretch"):
                from sentiment_analysis.analyzer import analyse_text
                with st.status("Classifying comments with DeepSeek...", expanded=True) as status:
                    for _c in list(st.session_state.pending_comments):
                        st.write(f"→ {_c['id']}: {_c['title']}")
                        try:
                            result = analyse_text(_c["body"])
                        except Exception as exc:
                            status.update(label=f"Failed on {_c['id']}: {exc}", state="error")
                            st.exception(exc)
                            break
                        # Convert AspectSentiment dataclass to dict-like fake event
                        _ev = {
                            "delivery": result.delivery,
                            "quality": result.quality,
                            "accuracy": result.accuracy,
                            "packaging": result.packaging,
                            "customer_service": result.customer_service,
                            "value": result.value,
                            "severity": result.severity,
                            "overall_sentiment": result.overall_sentiment,
                            "confidence": result.confidence,
                            "dominant_problem": result.dominant_problem,
                        }
                        _rev_view = {
                            "id": _c["id"],
                            "author_name": _c["author"],
                            "product_id": _c["product_id"],
                            "title": _c["title"],
                            "body": _c["body"],
                            "rating": _c["rating"],
                            "date": _c["date"],
                        }
                        st.session_state.classified_comments.append(_build_classified_comment(_rev_view, _ev))
                        st.session_state.pending_comments = [
                            x for x in st.session_state.pending_comments if x["id"] != _c["id"]
                        ]
                    else:
                        status.update(label="All comments classified ✅", state="complete")
                st.rerun()

        for idx, comment in enumerate(list(st.session_state.pending_comments)):
            with st.container(border=True):
                col1, col2, col3 = st.columns([1, 2, 3])
                with col1:
                    st.caption(f"**{comment['id']}**")
                with col2:
                    st.caption(f"👤 {comment['author']}")
                with col3:
                    st.caption(f"**{comment['title']}**")

                if comment.get("product_id"):
                    st.caption(f"📦 `{comment['product_id']}` — {products_by_id.get(comment['product_id'], 'Unknown')}")

                with st.expander("View details"):
                    st.markdown(f"**Body:** {comment['body']}")
                    st.markdown(f"**Rating:** {'⭐' * int(comment.get('rating', 0))}  ({comment.get('rating')}/5) &nbsp;·&nbsp; **Date:** {comment.get('date', '—')}")

                    edit_col, action_col = st.columns(2)
                    with edit_col:
                        _aspect_val = st.selectbox(
                            "Aspect",
                            _aspect_options,
                            index=_aspect_options.index("None"),
                            key=f"comments_pending_aspect_{idx}",
                        )
                        _severity_val = st.selectbox(
                            "Severity",
                            _severity_options,
                            index=_severity_options.index(_severity_from_rating(comment.get("rating") or 5)),
                            key=f"comments_pending_severity_{idx}",
                        )
                        _sentiment_val = st.selectbox(
                            "Sentiment",
                            _sentiment_options,
                            index=_sentiment_options.index(_sentiment_from_rating(comment.get("rating") or 5)),
                            key=f"comments_pending_sentiment_{idx}",
                        )

                    with action_col:
                        st.markdown("**Actions:**")
                        if st.button("✅ Approve Classification", key=f"comments_approve_{idx}", width="stretch"):
                            st.session_state.classified_comments.append({
                                "id": comment["id"],
                                "author": comment["author"],
                                "product_id": comment["product_id"],
                                "title": comment["title"],
                                "body": comment["body"],
                                "rating": comment["rating"],
                                "date": comment["date"],
                                "aspect": _aspect_val,
                                "severity": _severity_val,
                                "sentiment": _sentiment_val,
                                "confidence": 100,
                                "dominant_problem": "none",
                                "assigned_team": _ASPECT_TO_TEAM.get(_aspect_val, "General"),
                            })
                            st.session_state.pending_comments = [
                                x for x in st.session_state.pending_comments if x["id"] != comment["id"]
                            ]
                            st.rerun()

    st.markdown("---")

    # ─── SECTION 2: CLASSIFIED COMMENTS ──────────────────────────────────────
    st.markdown("### ✅ Classified Comments")

    if len(st.session_state.classified_comments) == 0:
        st.info("No classified comments yet.")
    else:
        product_ids_in_comments = sorted({c.get("product_id") for c in st.session_state.classified_comments if c.get("product_id")})
        product_filter_options = ["All"] + product_ids_in_comments

        def _format_product_option(pid: str) -> str:
            if pid == "All":
                return "All"
            return f"{pid} — {products_by_id.get(pid, 'Unknown')}"

        fcol1, fcol2, fcol3, fcol4 = st.columns(4)
        with fcol1:
            f_sentiment = st.selectbox("Sentiment", ["All"] + _sentiment_options, key="comments_f_sentiment")
        with fcol2:
            f_severity = st.selectbox("Severity", ["All"] + _severity_options, key="comments_f_severity")
        with fcol3:
            f_aspect = st.selectbox("Aspect", ["All"] + _aspect_options, key="comments_f_aspect")
        with fcol4:
            f_product = st.selectbox(
                "Product",
                product_filter_options,
                format_func=_format_product_option,
                key="comments_f_product",
            )

        def _matches(c: dict) -> bool:
            if f_sentiment != "All" and c.get("sentiment") != f_sentiment:
                return False
            if f_severity != "All" and c.get("severity") != f_severity:
                return False
            if f_aspect != "All" and c.get("aspect") != f_aspect:
                return False
            if f_product != "All" and c.get("product_id") != f_product:
                return False
            return True

        filtered = [c for c in st.session_state.classified_comments if _matches(c)]
        st.markdown(f"**Showing {len(filtered)} of {len(st.session_state.classified_comments)} classified comments**")

        if not filtered:
            st.info("No comments match the current filters.")
        else:
            display_rows = []
            for c in filtered:
                display_rows.append({
                    "id": c["id"],
                    "author": c["author"],
                    "product": products_by_id.get(c["product_id"], "—") if c.get("product_id") else "—",
                    "title": c["title"],
                    "aspect": c["aspect"],
                    "severity": c["severity"],
                    "sentiment": c["sentiment"],
                    "rating": c.get("rating"),
                    "confidence": f"{c.get('confidence', 0)}%",
                    "date": c.get("date"),
                })
            df = pd.DataFrame(display_rows)
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
                column_config={
                    "id": st.column_config.TextColumn("ID", width=80),
                    "author": st.column_config.TextColumn("Author", width=120),
                    "product": st.column_config.TextColumn("Product", width=160),
                    "title": st.column_config.TextColumn("Title", width=150),
                    "aspect": st.column_config.TextColumn("Aspect", width=120),
                    "severity": st.column_config.TextColumn("Severity", width=80),
                    "sentiment": st.column_config.TextColumn("Sentiment", width=90),
                    "rating": st.column_config.NumberColumn("Rating", width=70, format="%d ⭐"),
                    "confidence": st.column_config.TextColumn("Conf.", width=70),
                    "date": st.column_config.TextColumn("Date", width=100),
                },
            )

            # ─── MANAGE COMMENT PANEL ────────────────────────────────────────
            st.markdown("#### Manage comment")
            manage_options = [None] + [c["id"] for c in filtered]
            sel_id = st.selectbox(
                "Select comment to manage",
                manage_options,
                format_func=lambda x: "—" if x is None else x,
                key="comments_manage_select",
            )

            if sel_id is not None:
                target = next((c for c in st.session_state.classified_comments if c["id"] == sel_id), None)
                if target is not None:
                    with st.container(border=True):
                        info_col, edit_col = st.columns(2)
                        with info_col:
                            st.markdown(f"**Author:** {target['author']}")
                            pid = target.get("product_id")
                            product_label = f"`{pid}` — {products_by_id.get(pid, 'Unknown')}" if pid else "—"
                            st.markdown(f"**Product:** {product_label}")
                            st.markdown(f"**Date:** {target.get('date', '—')}")
                            st.markdown(f"**Rating:** {'⭐' * int(target.get('rating') or 0)}  ({target.get('rating')}/5)")
                            st.markdown(f"**Body:** {target.get('body', '')}")
                            st.markdown(f"**AI confidence:** {target.get('confidence', 0)}%")
                            st.markdown(f"**Dominant problem:** `{target.get('dominant_problem', 'none')}`")

                        with edit_col:
                            cur_aspect = target.get("aspect", "None")
                            cur_severity = target.get("severity", "Low")
                            cur_sentiment = target.get("sentiment", "Neutral")
                            cur_team = target.get("assigned_team", "General")

                            new_aspect = st.selectbox(
                                "Aspect",
                                _aspect_options,
                                index=_aspect_options.index(cur_aspect) if cur_aspect in _aspect_options else _aspect_options.index("None"),
                                key=f"comments_manage_aspect_{sel_id}",
                            )
                            new_severity = st.selectbox(
                                "Severity",
                                _severity_options,
                                index=_severity_options.index(cur_severity) if cur_severity in _severity_options else _severity_options.index("Low"),
                                key=f"comments_manage_severity_{sel_id}",
                            )
                            new_sentiment = st.selectbox(
                                "Sentiment",
                                _sentiment_options,
                                index=_sentiment_options.index(cur_sentiment) if cur_sentiment in _sentiment_options else _sentiment_options.index("Neutral"),
                                key=f"comments_manage_sentiment_{sel_id}",
                            )
                            new_team = st.selectbox(
                                "Assigned team",
                                _team_options,
                                index=_team_options.index(cur_team) if cur_team in _team_options else _team_options.index("General"),
                                key=f"comments_manage_team_{sel_id}",
                            )

                            reclass_col, save_col = st.columns(2)
                            with reclass_col:
                                if st.button("🤖 Re-classify with AI", key=f"comments_reclass_{sel_id}", width="stretch"):
                                    try:
                                        from sentiment_analysis.analyzer import analyse_text
                                        res = analyse_text(target.get("body", ""))
                                        _ev = {
                                            "delivery": res.delivery,
                                            "quality": res.quality,
                                            "accuracy": res.accuracy,
                                            "packaging": res.packaging,
                                            "customer_service": res.customer_service,
                                            "value": res.value,
                                            "severity": res.severity,
                                            "overall_sentiment": res.overall_sentiment,
                                            "confidence": res.confidence,
                                            "dominant_problem": res.dominant_problem,
                                        }
                                        target["aspect"] = _dominant_aspect(_ev)
                                        target["severity"] = _SEVERITY_LABEL.get(res.severity, "Low")
                                        target["sentiment"] = res.overall_sentiment
                                        target["confidence"] = res.confidence
                                        target["dominant_problem"] = res.dominant_problem
                                        target["assigned_team"] = _ASPECT_TO_TEAM.get(target["aspect"], "General")
                                        st.success(f"Re-classified — aspect: **{target['aspect']}** ({res.confidence}% confidence).")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"Re-classification failed: {exc}")

                            with save_col:
                                if st.button("💾 Save changes", key=f"comments_save_{sel_id}", width="stretch"):
                                    target["aspect"] = new_aspect
                                    target["severity"] = new_severity
                                    target["sentiment"] = new_sentiment
                                    target["assigned_team"] = new_team
                                    st.success("Changes saved.")
                                    st.rerun()

    st.markdown("---")

    # ─── KPI MINI ────────────────────────────────────────────────────────────
    st.markdown("### Performance Metrics")
    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)

    _n_classified = len(st.session_state.classified_comments)
    _n_pending = len(st.session_state.pending_comments)
    _avg_conf = (
        sum(c.get("confidence", 0) for c in st.session_state.classified_comments) / _n_classified
        if _n_classified > 0
        else 0
    )

    with kpi_col1:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Classified</p>
            <p style="color: #4F46E5; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{_n_classified}</p>
        </div>
        """)
    with kpi_col2:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Pending</p>
            <p style="color: #F59E0B; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{_n_pending}</p>
        </div>
        """)
    with kpi_col3:
        st.html(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Avg Confidence</p>
            <p style="color: #10B981; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{int(_avg_conf)}%</p>
        </div>
        """)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: SENTIMENT ANALYSIS (LLM Dashboard)
# ═══════════════════════════════════════════════════════════════════════════

elif selected_tab == "Sentiment Analysis":
    render_llm_dashboard()

# Render chatbot widget
