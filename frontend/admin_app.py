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

     # ── Filter bar ───────────────────────────────────────────────────────────
    STATUS_OPTIONS = {
        "All": None,
        "Open": "open",
        "In Progress": "in_progress",
        "Resolved": "resolved",
        "Closed": "closed",
    }

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filter_status_label = st.selectbox(
            "Status", list(STATUS_OPTIONS.keys()), key="f_status"
        )
        filter_status = STATUS_OPTIONS[filter_status_label]      

    with col2:
        intent_options = {"All": "All"} | INTENT_OPTIONS
        filter_intent_label = st.selectbox("Intent / Category", list(intent_options.values()), key="f_intent")
        filter_intent = next((k for k, v in intent_options.items() if v == filter_intent_label), "All")
    with col3:
        filter_date = st.selectbox("Time Range", ["All time", "Last 7 days", "Last 30 days"], key="f_date")
    with col4:
        filter_date = st.selectbox("Time Range", ["Last 7 days", "Last 30 days", "All time"])
    
    st.markdown("---")
    
    # SECTION 1: MANUAL CLASSIFICATION
    st.markdown("### 🔍 Manual Classification (To Review)")
    
    if len(st.session_state.pending_reviews) > 0:
        st.markdown(f"**{len(st.session_state.pending_reviews)} tickets pending review**")
        
        for idx, ticket in enumerate(st.session_state.pending_reviews):
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([1, 2, 2, 2])
                
                with col1:
                    st.caption(f"**{ticket['id']}**")
                
                with col2:
                    st.caption(f"👤 {ticket['customer']}")
                
                with col3:
                    st.caption(f"**{ticket['subject']}**")
                
                with col4:
                    confidence_color = "#10B981" if ticket['confidence'] > 85 else "#F59E0B"
                    st.caption(f"🤖 {ticket['confidence']}%")
                
                # Expand to show details
                with st.expander("View Details"):
                    st.markdown(f"**Raw Text:**\n\n{ticket['raw_text']}")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(f"**Suggested Category:** {ticket['suggested_category']} ({ticket['confidence']}%)")
                        selected_category = st.selectbox(
                            "Confirm or change category:",
                            ["Bug", "Shipping", "Returns", "Payments", "Other"],
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
                                "category": selected_category,
                                "sentiment": "Neutral",
                                "confidence": ticket["confidence"],
                                "assigned_queue": f"{selected_category} Support",
                                "status": "In Progress",
                                "created_at": datetime.now().isoformat() + "Z",
                                "resolved_at": None
                            }
                            st.session_state.auto_classified.append(classified_ticket)
                            st.session_state.pending_reviews.pop(idx)
                            st.rerun()
    else:
        st.info("✨ No pending reviews! All tickets have been classified.")
    
    st.markdown("---")
    
    # SECTION 2: AUTOMATICALLY CLASSIFIED
    st.markdown("### ✅ Automatically Classified Tickets")
    
    if len(st.session_state.auto_classified) > 0:
        st.markdown(f"**{len(st.session_state.auto_classified)} automatically classified tickets**")
        
        # Create dataframe for display
        classified_df = pd.DataFrame(st.session_state.auto_classified)
        
        # Format for display
        display_df = classified_df[[
            "id", "customer", "subject", "category", "sentiment", "confidence", "assigned_queue", "status"
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
                "category": st.column_config.TextColumn("Category", width=100),
                "sentiment": st.column_config.TextColumn("Sentiment", width=100),
                "confidence": st.column_config.TextColumn("Confidence", width=80),
                "assigned_queue": st.column_config.TextColumn("Queue", width=120),
                "status": st.column_config.TextColumn("Status", width=100),
            }
        )
    else:
        st.info("No automatically classified tickets yet.")
    
    st.markdown("---")

    # ── Tickets-tab KPI mini cards ───────────────────────────────────────────
    st.markdown("### Performance Metrics")
    
    total_tickets = len(st.session_state.pending_reviews) + len(st.session_state.auto_classified)
    auto_classified_pct = (len(st.session_state.auto_classified) / total_tickets * 100) if total_tickets > 0 else 0
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Auto-Classified</p>
            <p style="color: #4F46E5; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{int(auto_classified_pct)}%</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Pending Review</p>
            <p style="color: #F59E0B; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{len(st.session_state.pending_reviews)}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        avg_confidence = (
            sum(t["confidence"] for t in st.session_state.pending_reviews) / len(st.session_state.pending_reviews)
            if len(st.session_state.pending_reviews) > 0
            else 0
        )
        st.markdown(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Avg Confidence</p>
            <p style="color: #10B981; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{int(avg_confidence)}%</p>
        </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: LLM Dashboard
# ═══════════════════════════════════════════════════════════════════════════

elif selected_tab == "LLM Dashboard":
    render_llm_dashboard()

# Render chatbot widget
