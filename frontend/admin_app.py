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

from components.admin_sidebar import render_admin_sidebar
from components.metric_card import metric_card, small_metric
from components.chatbot_widget import render_admin_chatbot_widget
from components.metric_card import metric_card
from shared.db.repository import TicketRepository
from shared.db.migrate import _DB_PATH, migrate
from chatbot.registry.loader import load_intents
from chatbot.feedback.analyzer import weekly_review, export_labeled_jsonl

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
    ["Dashboard", "Tickets", "Bot Improvement", "LLM Dashboard"],
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
    m = repo.get_metrics()
    daily = repo.get_daily_counts(days=30)
    insight = repo.get_escalation_insight()

    open_count      = m["by_status"].get("open", 0)
    resolved_count  = m["by_status"].get("resolved", 0) + m["by_status"].get("closed", 0)

    # ── KPI strip ───────────────────────────────────────────────────────────
    st.markdown("### Key Performance Indicators")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("Total Tickets", str(m["total_tickets"]), icon="📥")
    with col2:
        metric_card("Resolved", str(resolved_count), icon="✅")
    with col3:
        metric_card("Open", str(open_count), icon="🔓")
    with col4:
        metric_card("Escalated", str(m["escalated"]), icon="🔄")

    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card("Auto-Resolution Rate", f"{m['bot_resolution_rate_pct']}%", icon="🤖")
    with col2:
        metric_card("AI Accuracy", f"{m['ai_accuracy_pct']}%", icon="🎯")
    with col3:
        csat = m["avg_csat"]
        metric_card("Avg CSAT", f"{csat:.1f} / 5" if csat else "—", icon="⭐")

    col1, col2 = st.columns(2)
    with col1:
        metric_card("Avg First Reply", f"{m['avg_first_reply_min']}m", icon="⏱️")
    with col2:
        metric_card("Avg Resolution Time", f"{m['avg_resolution_hours']}h", icon="⏲️")

    st.markdown("---")

    # ── Tickets Created vs Solved (30 days) ─────────────────────────────────
    st.markdown("### Trends")

    if daily:
        df_daily = pd.DataFrame(daily)
        df_daily["date"] = pd.to_datetime(df_daily["date"])

        col1, col2 = st.columns([0.6, 0.4])
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_daily["date"], y=df_daily["created"],
                name="Created", marker_color="#4F46E5", opacity=0.85,
            ))
            fig.add_trace(go.Scatter(
                x=df_daily["date"], y=df_daily["resolved"],
                name="Resolved", mode="lines+markers",
                line=dict(color="#10B981", width=3),
            ))
            fig.update_layout(
                title="Tickets Created vs Resolved (30 Days)",
                xaxis_title="Date", yaxis_title="Count",
                hovermode="x unified",
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                height=380, margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Resolution path breakdown
            path_labels = list(m["top_intents"].keys()) or ["(none)"]
            path_values = list(m["top_intents"].values()) or [1]
            fig2 = go.Figure(data=[go.Bar(
                x=path_values, y=[_intent_label(l) for l in path_labels],
                orientation="h",
                marker_color="#4F46E5",
            )])
            fig2.update_layout(
                title="Tickets by Intent (Top 10)",
                height=380, margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No ticket data in the last 30 days yet. Send some chatbot messages to populate the charts.")

    st.markdown("---")

    # ── Distribution charts ──────────────────────────────────────────────────
    st.markdown("### Distributions")
    col1, col2, col3 = st.columns(3)

    with col1:
        ch = m["by_channel"] or {"chat": 1}
        fig = go.Figure(data=[go.Pie(
            labels=list(ch.keys()), values=list(ch.values()),
            hole=0.4, marker_colors=["#4F46E5","#10B981","#F59E0B","#EF4444"],
        )])
        fig.update_layout(title="Tickets by Channel", height=320, margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st_ = m["by_status"] or {"open": 1}
        fig = go.Figure(data=[go.Pie(
            labels=list(st_.keys()), values=list(st_.values()),
            hole=0.4, marker_colors=["#F59E0B","#3B82F6","#10B981","#6B7280"],
        )])
        fig.update_layout(title="Tickets by Status", height=320, margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)

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
        st.markdown(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Positive</p>
            <p style="color: #10B981; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{sentiment_data['Positive']}</p>
            <p style="color: #6B7280; font-size: 12px; margin: 4px 0 0 0;">{int(sentiment_data['Positive'] / sum(sentiment_data.values()) * 100)}%</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Neutral</p>
            <p style="color: #6B7280; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{sentiment_data['Neutral']}</p>
            <p style="color: #6B7280; font-size: 12px; margin: 4px 0 0 0;">{int(sentiment_data['Neutral'] / sum(sentiment_data.values()) * 100)}%</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; text-align: center;">
            <p style="color: #6B7280; font-size: 12px; margin: 0;">Negative</p>
            <p style="color: #EF4444; font-size: 28px; font-weight: 700; margin: 8px 0 0 0;">{sentiment_data['Negative']}</p>
            <p style="color: #6B7280; font-size: 12px; margin: 4px 0 0 0;">{int(sentiment_data['Negative'] / sum(sentiment_data.values()) * 100)}%</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # AI INSIGHT BANNER
    st.markdown("""
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
                <button style="
                    background-color: rgba(255,255,255,0.2);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.4);
                    padding: 8px 16px;
                    border-radius: 6px;
                    cursor: pointer;
                    margin-top: 12px;
                    font-weight: 500;
                ">
                    View Details →
                </button>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: TICKETS
# ═══════════════════════════════════════════════════════════════════════════

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
    st.markdown("### LLM Performance Dashboard")
    
    st.markdown("""
    ✨ **Coming soon** — advanced LLM monitoring and optimization insights
    
    # TODO: Add features
    - Token usage analytics
    - Latency monitoring
    - Cost tracking
    - Prompt performance analysis
    - Model A/B testing results
    - Cache hit rates
    """)
    
    st.info("""
    This dashboard will provide detailed insights into LLM performance, including:
    - Real-time token consumption tracking
    - API latency and response time analysis
    - Cost optimization recommendations
    - Prompt effectiveness metrics
    - Model comparison data
    """)

# Render chatbot widget
