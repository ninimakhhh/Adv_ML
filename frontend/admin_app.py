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

# Render sidebar
render_admin_sidebar()

st.markdown("""
<div style="padding:0 0 20px 0;">
  <h1 style="color:#111827;margin:0;font-weight:800;">Admin Dashboard</h1>
  <p style="color:#6B7280;margin:8px 0 0 0;">
    Monitor operations, manage support, and evaluate AI performance
  </p>
</div>
""", unsafe_allow_html=True)

selected_tab = st.radio(
    "Navigation",
    ["Dashboard", "Tickets", "LLM Dashboard"],
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

if selected_tab == "Dashboard":
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
# TAB 4: LLM Dashboard
# ═══════════════════════════════════════════════════════════════════════════

elif selected_tab == "LLM Dashboard":
    render_llm_dashboard()

# Render chatbot widget
