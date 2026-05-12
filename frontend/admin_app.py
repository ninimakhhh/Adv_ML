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
from components.metric_card import metric_card
from shared.db.repository import TicketRepository
from shared.db.migrate import _DB_PATH, migrate
from chatbot.registry.loader import load_intents
from chatbot.feedback.analyzer import weekly_review, export_labeled_jsonl

_ROOT = _FRONTEND.parent

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(layout="wide", page_title="Olá Market — Admin Dashboard")

st.markdown("""
<style>
    #MainMenu {visibility:hidden;} footer {visibility:hidden;} header {visibility:hidden;}
    body { background-color:#F7F8FA; font-family:'Inter',system-ui,-apple-system; }
    .stTabs [data-baseweb="tab-list"] { gap:8px; }
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

# ── Bootstrap DB (idempotent) ────────────────────────────────────────────────
migrate(_DB_PATH)

# ── Repo (one per render — lightweight, no persistent connection) ────────────
repo = TicketRepository(_DB_PATH)
intents_registry = load_intents()
INTENT_OPTIONS = {iid: d["display_name"] for iid, d in intents_registry.items()}

# ── Sidebar + Header ─────────────────────────────────────────────────────────
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
        sent = m["by_sentiment"] or {}
        if sent:
            fig = go.Figure(data=[go.Pie(
                labels=list(sent.keys()), values=list(sent.values()),
                hole=0.4,
                marker_colors=["#10B981" if k=="positive" else "#EF4444" if k=="negative" else "#6B7280"
                               for k in sent],
            )])
            fig.update_layout(title="Sentiment Distribution", height=320, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("""
            <div style="background:#FFF;border:1px solid #E5E7EB;border-radius:8px;
                        padding:40px;text-align:center;height:320px;display:flex;
                        align-items:center;justify-content:center;flex-direction:column">
              <p style="color:#9CA3AF;font-size:14px;">No sentiment data yet.<br>
              Sentiment is populated when tickets have a score.</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── AI Insight Banner ────────────────────────────────────────────────────
    if insight:
        banner_text = insight["insight_text"]
        change_str = (
            f"+{insight['change_pct']}% vs last week"
            if insight["change_pct"] > 0
            else "most-escalated intent this week"
        )
    else:
        banner_text = "Not enough data yet. Start chatbot conversations to generate insights."
        change_str = ""

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#4F46E5,#7C3AED);border-radius:8px;
                padding:24px;color:white;margin:20px 0;">
      <h3 style="margin:0 0 8px 0;font-size:18px;">💡 AI Insight of the Day</h3>
      <p style="margin:0;line-height:1.6;">{banner_text}</p>
      {"<p style='margin:8px 0 0 0;font-size:12px;opacity:0.75;'>"+change_str+"</p>" if change_str else ""}
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: TICKETS
# ═══════════════════════════════════════════════════════════════════════════

elif selected_tab == "Tickets":
    st.markdown("### Ticket Management")

    # ── Filter bar ───────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filter_status = st.selectbox(
            "Status", ["All", "open", "in_progress", "resolved", "closed"], key="f_status"
        )
    with col2:
        intent_options = {"All": "All"} | INTENT_OPTIONS
        filter_intent_label = st.selectbox("Intent / Category", list(intent_options.values()), key="f_intent")
        filter_intent = next((k for k, v in intent_options.items() if v == filter_intent_label), "All")
    with col3:
        filter_date = st.selectbox("Time Range", ["All time", "Last 7 days", "Last 30 days"], key="f_date")
    with col4:
        if st.button("🔄 Refresh", key="btn_refresh"):
            st.rerun()

    days_map = {"Last 7 days": 7, "Last 30 days": 30, "All time": None}
    _days = days_map[filter_date]
    _status = None if filter_status == "All" else filter_status
    _intent = None if filter_intent == "All" else filter_intent

    st.markdown("---")

    # ── Section 1: Pending Escalations (Manual Review) ───────────────────────
    st.markdown("### 🔍 Manual Classification (Escalated — Pending Review)")

    pending = repo.list_pending_escalations()

    if pending:
        st.markdown(f"**{len(pending)} ticket(s) pending human review**")

        for ticket in pending:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([1.2, 2, 2, 1.5, 1.5])
                with c1:
                    st.markdown(f"`{ticket.ticket_id[:8]}…`")
                with c2:
                    st.markdown(f"**{_intent_label(ticket.classified_intent)}**")
                with c3:
                    conf = ticket.classification_confidence
                    conf_str = f"{conf*100:.0f}%" if conf else "—"
                    st.markdown(f"🤖 Confidence: {conf_str}")
                with c4:
                    st.markdown(
                        _status_badge(ticket.final_status) + "&nbsp;&nbsp;" + _path_badge(ticket.resolution_path),
                        unsafe_allow_html=True,
                    )
                with c5:
                    created = ticket.created_at.strftime("%Y-%m-%d %H:%M") if ticket.created_at else "—"
                    st.caption(created)

                with st.expander(f"View transcript & approve — {ticket.ticket_id[:8]}…"):
                    # Transcript
                    msgs = repo.get_messages(ticket.ticket_id)
                    if msgs:
                        st.markdown("**Conversation Transcript:**")
                        for msg in msgs:
                            if msg.role == "user":
                                st.markdown(
                                    f'<div style="text-align:right;margin:4px 0">'
                                    f'<div class="transcript-user">{msg.body}</div></div>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(
                                    f'<div style="text-align:left;margin:4px 0">'
                                    f'<div class="transcript-bot">🤖 {msg.body}</div></div>',
                                    unsafe_allow_html=True,
                                )
                        st.markdown("")
                    else:
                        st.caption("No messages found.")

                    col_left, col_right = st.columns(2)
                    with col_left:
                        suggested = ticket.classified_intent or list(INTENT_OPTIONS.keys())[0]
                        suggested_label = _intent_label(suggested)
                        intent_labels = list(intent_options.values())
                        default_idx = intent_labels.index(suggested_label) if suggested_label in intent_labels else 0
                        chosen_label = st.selectbox(
                            "Confirm or change intent:",
                            intent_labels,
                            index=default_idx,
                            key=f"sel_{ticket.ticket_id}",
                        )
                        chosen_id = next((k for k, v in intent_options.items() if v == chosen_label), None)

                    with col_right:
                        st.markdown("**Actions:**")
                        if st.button(
                            "✅ Approve Classification",
                            key=f"approve_{ticket.ticket_id}",
                            type="primary",
                        ):
                            if chosen_id and chosen_id != "All":
                                repo.update_classification(ticket.ticket_id, chosen_id, confidence=1.0)
                                st.success(f"Classified as **{chosen_label}** with confidence 1.0 (human verified)")
                                st.rerun()
                            else:
                                st.warning("Please select a valid intent before approving.")

                        if st.button("✔ Mark Resolved", key=f"resolve_{ticket.ticket_id}"):
                            repo.update_ticket(
                                ticket.ticket_id,
                                final_status="resolved",
                                resolved_at=datetime.utcnow().isoformat(),
                            )
                            st.rerun()
    else:
        st.success("✨ No pending escalations — all tickets have been reviewed or resolved by the bot.")

    st.markdown("---")

    # ── Section 2: All Tickets (filtered) ───────────────────────────────────
    st.markdown("### 📋 All Tickets")

    all_tickets = repo.list_auto_classified(status=_status, intent=_intent, days=_days)

    if not all_tickets:
        st.info("No tickets match the selected filters. Try adjusting the filter bar above.")
    else:
        # Build display DataFrame
        rows = []
        for t in all_tickets:
            rows.append({
                "ticket_id":   t.ticket_id,
                "intent":      _intent_label(t.classified_intent),
                "status":      t.final_status,
                "path":        t.resolution_path,
                "confidence":  f"{t.classification_confidence*100:.0f}%" if t.classification_confidence else "—",
                "verified":    "✅" if t.human_verified else "🤖",
                "csat":        str(t.csat_score) if t.csat_score else "—",
                "created_at":  t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "—",
            })
        df = pd.DataFrame(rows)

        # Row-selection dataframe
        event = st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "ticket_id":  st.column_config.TextColumn("Ticket ID", width=180),
                "intent":     st.column_config.TextColumn("Intent", width=150),
                "status":     st.column_config.TextColumn("Status", width=100),
                "path":       st.column_config.TextColumn("Resolution", width=140),
                "confidence": st.column_config.TextColumn("Confidence", width=90),
                "verified":   st.column_config.TextColumn("Verified", width=70),
                "csat":       st.column_config.TextColumn("CSAT", width=60),
                "created_at": st.column_config.TextColumn("Created", width=140),
            },
            key="tickets_table",
        )

        selected_rows = event.selection.rows if hasattr(event, "selection") else []

        # ── Ticket Detail Drawer ─────────────────────────────────────────────
        if selected_rows:
            selected_ticket = all_tickets[selected_rows[0]]
            tid = selected_ticket.ticket_id

            st.markdown(f"---\n### 🗂 Ticket Detail — `{tid}`")

            dcol1, dcol2 = st.columns([0.55, 0.45])

            with dcol1:
                st.markdown("**Conversation Transcript**")
                msgs = repo.get_messages(tid)
                if msgs:
                    for msg in msgs:
                        ts = msg.sent_at.strftime("%H:%M") if msg.sent_at else ""
                        if msg.role == "user":
                            st.markdown(
                                f'<div style="text-align:right;margin:4px 0">'
                                f'<div class="transcript-user">{msg.body}</div>'
                                f'<div style="font-size:10px;color:#999;margin-top:2px">{ts}</div></div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f'<div style="text-align:left;margin:4px 0">'
                                f'<div class="transcript-bot">🤖 {msg.body}</div>'
                                f'<div style="font-size:10px;color:#999;margin-top:2px">{ts}</div></div>',
                                unsafe_allow_html=True,
                            )
                else:
                    st.caption("No messages recorded for this ticket.")

            with dcol2:
                st.markdown("**Classification Details**")
                st.markdown(f"- **Intent:** {_intent_label(selected_ticket.classified_intent)}")
                conf = selected_ticket.classification_confidence
                st.markdown(f"- **Confidence:** {conf*100:.0f}%" if conf else "- **Confidence:** —")
                st.markdown(f"- **Human Verified:** {'Yes ✅' if selected_ticket.human_verified else 'No 🤖'}")
                st.markdown(f"- **Resolution:** {selected_ticket.resolution_path}")
                st.markdown(f"- **Status:** {selected_ticket.final_status}")
                st.markdown(f"- **CSAT:** {selected_ticket.csat_score or '—'}")
                st.markdown(f"- **Sentiment:** {selected_ticket.sentiment or '—'}")
                if selected_ticket.tags:
                    st.markdown(f"- **Tags:** {', '.join(selected_ticket.tags)}")

                st.markdown("---")
                st.markdown("**Actions**")

                new_intent_label = st.selectbox(
                    "Reassign Intent:",
                    list(intent_options.values()),
                    index=max(0, list(intent_options.values()).index(
                        _intent_label(selected_ticket.classified_intent)
                    ) if _intent_label(selected_ticket.classified_intent) in list(intent_options.values()) else 0),
                    key=f"reassign_{tid}",
                )
                new_intent_id = next((k for k, v in intent_options.items() if v == new_intent_label), None)

                bcol1, bcol2, bcol3 = st.columns(3)
                with bcol1:
                    if st.button("💾 Save", key=f"save_{tid}"):
                        if new_intent_id and new_intent_id != "All":
                            repo.update_classification(tid, new_intent_id, 1.0)
                            st.success("Saved")
                            st.rerun()
                with bcol2:
                    if st.button("✔ Resolve", key=f"res_{tid}"):
                        repo.update_ticket(
                            tid,
                            final_status="resolved",
                            resolved_at=datetime.utcnow().isoformat(),
                        )
                        st.rerun()
                with bcol3:
                    if st.button("📧 Reply", key=f"reply_{tid}"):
                        st.info("(Demo) Reply flow would open here.")

    st.markdown("---")

    # ── Tickets-tab KPI mini cards ───────────────────────────────────────────
    st.markdown("### Performance Metrics")
    m2 = repo.get_metrics()
    total2 = m2["total_tickets"]
    auto_pct = m2["bot_resolution_rate_pct"]
    pending_count = len(repo.list_pending_escalations())
    ai_acc = m2["ai_accuracy_pct"]

    col1, col2, col3, col4 = st.columns(4)
    for col, label, value, colour in [
        (col1, "Total Tickets",      str(total2),          "#4F46E5"),
        (col2, "Bot-Resolved %",     f"{auto_pct}%",       "#10B981"),
        (col3, "Pending Review",     str(pending_count),   "#F59E0B"),
        (col4, "AI Accuracy",        f"{ai_acc}%",         "#3B82F6"),
    ]:
        with col:
            st.markdown(f"""
            <div style="background:#FFF;border:1px solid #E5E7EB;border-radius:8px;
                        padding:16px;text-align:center;">
              <p style="color:#6B7280;font-size:12px;margin:0">{label}</p>
              <p style="color:{colour};font-size:28px;font-weight:700;margin:8px 0 0 0">{value}</p>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: BOT IMPROVEMENT
# ═══════════════════════════════════════════════════════════════════════════

elif selected_tab == "Bot Improvement":
    st.markdown("### Bot Improvement — Weekly Review")

    # Cache report for this render cycle (ttl=0 means re-run each page load)
    @st.cache_data(ttl=60, show_spinner="Running analysis…")
    def _get_report():
        return weekly_review(_DB_PATH)

    report = _get_report()
    low_conf   = report["low_confidence_messages"]
    escalated  = report["attempted_but_escalated"]
    thumbs_dn  = report["thumbs_down"]
    no_intent  = report["no_intent_messages"]

    # ── Summary cards ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    for col, label, val, colour in [
        (c1, "Low-Conf Messages",     len(low_conf),  "#F59E0B"),
        (c2, "Struggling Intents",    len(escalated), "#EF4444"),
        (c3, "Thumbs-Down Tickets",   len(thumbs_dn), "#EF4444"),
        (c4, "Unmatched Messages",    len(no_intent), "#6B7280"),
    ]:
        with col:
            st.markdown(f"""
            <div style="background:#FFF;border:1px solid #E5E7EB;border-radius:8px;
                        padding:16px;text-align:center;">
              <p style="color:#6B7280;font-size:12px;margin:0">{label}</p>
              <p style="color:{colour};font-size:28px;font-weight:700;margin:8px 0 0 0">{val}</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown(f"*Report generated at {report['generated_at'][:19]} UTC*")
    st.markdown("---")

    # ── Section 1: Low-confidence messages ──────────────────────────────────
    st.markdown("### 🎯 Low-Confidence Messages (< 70%)")
    st.caption("Candidates for new intents or improved few-shot examples.")

    if low_conf:
        df_lc = pd.DataFrame(low_conf)
        df_lc["confidence_%"] = df_lc["classification_confidence"].apply(
            lambda v: f"{v*100:.0f}%" if v else "—"
        )
        df_lc["intent"] = df_lc["classified_intent"].apply(_intent_label)
        st.dataframe(
            df_lc[["user_message", "intent", "confidence_%", "resolution_path", "created_at"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "user_message":   st.column_config.TextColumn("User Message",   width=320),
                "intent":         st.column_config.TextColumn("Matched Intent", width=160),
                "confidence_%":   st.column_config.TextColumn("Confidence",     width=90),
                "resolution_path":st.column_config.TextColumn("Outcome",        width=160),
                "created_at":     st.column_config.TextColumn("Date",           width=140),
            },
        )
    else:
        st.success("No low-confidence messages — the classifier is performing well.")

    st.markdown("---")

    # ── Section 2: Intents with high escalation rate ─────────────────────────
    st.markdown("### 🔥 Intents with Highest Escalation Rate")
    st.caption("Bot attempted resolution but the conversation still escalated.")

    if escalated:
        df_esc = pd.DataFrame(escalated)
        df_esc["Intent"] = df_esc["intent_id"].apply(_intent_label)
        df_esc["Escalation Rate"] = df_esc["escalation_rate_pct"].apply(lambda v: f"{v}%")
        df_esc["Escalated / Total"] = df_esc.apply(
            lambda r: f"{r['esc_count']} / {r['total']}", axis=1
        )
        st.dataframe(
            df_esc[["Intent", "Escalated / Total", "Escalation Rate"]],
            hide_index=True,
            use_container_width=True,
        )

        # Mini bar chart
        fig = go.Figure(go.Bar(
            x=df_esc["escalation_rate_pct"],
            y=df_esc["Intent"],
            orientation="h",
            marker_color="#EF4444",
        ))
        fig.update_layout(
            title="Escalation Rate by Intent (%)",
            xaxis_title="Escalation Rate (%)",
            height=260,
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("No intents with escalation issues found.")

    st.markdown("---")

    # ── Section 3: Thumbs-down feedback + suggest better response ───────────
    st.markdown("### 👎 Thumbs-Down Feedback")
    st.caption("For each thumbs-down ticket, suggest a better bot response.")

    if thumbs_dn:
        for item in thumbs_dn:
            tid_short = item["ticket_id"][:8]
            with st.expander(
                f"Ticket {tid_short}… — Intent: {_intent_label(item['classified_intent'])}"
            ):
                col_msg, col_resp = st.columns(2)
                with col_msg:
                    st.markdown("**User said:**")
                    st.info(item["user_message"])
                with col_resp:
                    st.markdown("**Bot replied:**")
                    st.warning(item["bot_response"] or "*(no bot message recorded)*")

                st.markdown("**Suggest a better response:**")
                suggestion = st.text_area(
                    "Improved response:",
                    placeholder="Type the ideal bot response for this message…",
                    key=f"suggest_{item['ticket_id']}",
                    label_visibility="collapsed",
                )
                col_save, col_skip = st.columns([1, 5])
                with col_save:
                    if st.button("💾 Save suggestion", key=f"save_sug_{item['ticket_id']}"):
                        if suggestion.strip():
                            # Persist as a tag on the ticket for now
                            repo.update_ticket(
                                item["ticket_id"],
                                tags=["has_suggested_response"],
                            )
                            # Write to a side-file for export pipeline
                            sug_dir = _ROOT / "data" / "response_suggestions"
                            sug_dir.mkdir(parents=True, exist_ok=True)
                            sug_file = sug_dir / f"{item['ticket_id']}.json"
                            import json as _json
                            sug_file.write_text(
                                _json.dumps({
                                    "ticket_id":     item["ticket_id"],
                                    "user_message":  item["user_message"],
                                    "bot_response":  item["bot_response"],
                                    "suggested_response": suggestion.strip(),
                                    "intent":        item["classified_intent"],
                                    "saved_at":      datetime.utcnow().isoformat(),
                                }, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                            st.success("Suggestion saved.")
                        else:
                            st.warning("Please type a suggestion first.")
    else:
        st.success("No thumbs-down tickets yet.")

    st.markdown("---")

    # ── Section 4: Unmatched messages → Create new intent ───────────────────
    st.markdown("### ❓ Unmatched Messages — Create New Intent")
    st.caption("Messages that didn't match any intent. Promote recurring ones to new intents.")

    if no_intent:
        df_ni = pd.DataFrame(no_intent)
        df_ni["created_at"] = df_ni["created_at"].astype(str).str[:16]
        st.dataframe(
            df_ni[["user_message", "created_at", "ticket_id"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "user_message": st.column_config.TextColumn("User Message", width=380),
                "created_at":   st.column_config.TextColumn("Date",         width=140),
                "ticket_id":    st.column_config.TextColumn("Ticket ID",    width=200),
            },
        )

        st.markdown("#### ➕ Draft a New Intent from a Message")

        # Let admin pick one message to promote
        ni_options = {f"{r['ticket_id'][:8]}… | {r['user_message'][:60]}": r
                      for r in no_intent}
        chosen_key = st.selectbox(
            "Select a message to use as the first example utterance:",
            list(ni_options.keys()),
            key="ni_select",
        )
        seed_msg = ni_options[chosen_key]["user_message"]

        with st.form("create_intent_form"):
            st.markdown("**New Intent Definition**")

            col_a, col_b = st.columns(2)
            with col_a:
                new_intent_id = st.text_input(
                    "intent_id (snake_case):",
                    placeholder="e.g. check_loyalty_points",
                    key="ni_id",
                )
                new_display   = st.text_input(
                    "display_name:",
                    placeholder="e.g. Check Loyalty Points",
                    key="ni_display",
                )
                new_category  = st.selectbox(
                    "category:",
                    ["orders", "returns", "products", "account", "other"],
                    key="ni_cat",
                )
            with col_b:
                new_res_type = st.selectbox(
                    "resolution_type:",
                    ["faq_answer", "api_call", "guided_flow"],
                    key="ni_res",
                )
                new_answer = st.text_area(
                    "Initial answer / response template:",
                    placeholder="TODO: Write the response the bot should give…",
                    height=100,
                    key="ni_answer",
                )

            st.markdown("**Example utterances** (seed message is pre-filled; add at least 4 more):")
            utt_1 = st.text_input("Utterance 1:", value=seed_msg,  key="u1")
            utt_2 = st.text_input("Utterance 2:", placeholder="…", key="u2")
            utt_3 = st.text_input("Utterance 3:", placeholder="…", key="u3")
            utt_4 = st.text_input("Utterance 4:", placeholder="…", key="u4")
            utt_5 = st.text_input("Utterance 5:", placeholder="…", key="u5")

            submitted = st.form_submit_button("💾 Save Draft Intent", type="primary")

        if submitted:
            import re, json as _json

            errors = []
            if not re.match(r"^[a-z][a-z0-9_]*$", new_intent_id or ""):
                errors.append("intent_id must be snake_case (e.g. check_loyalty_points)")
            if not new_display.strip():
                errors.append("display_name is required")

            utterances = [u for u in [utt_1, utt_2, utt_3, utt_4, utt_5] if u.strip()]
            if len(utterances) < 5:
                errors.append("At least 5 example utterances are required")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                resolution_config: dict = {}
                if new_res_type == "faq_answer":
                    resolution_config = {"answer": new_answer.strip() or "TODO: fill in answer."}
                elif new_res_type == "api_call":
                    resolution_config = {
                        "endpoint": "/api/v1/TODO",
                        "method": "GET",
                        "response_template": new_answer.strip() or "TODO",
                    }
                elif new_res_type == "guided_flow":
                    resolution_config = {
                        "steps": [
                            {"prompt": new_answer.strip() or "TODO", "expected_input_type": "text"}
                        ]
                    }

                draft = {
                    "intent_id": new_intent_id,
                    "display_name": new_display.strip(),
                    "category": new_category,
                    "example_utterances": utterances,
                    "required_slots": [],
                    "resolution_type": new_res_type,
                    "resolution_config": resolution_config,
                    "escalation_triggers": [],
                    "confidence_threshold": 0.70,
                    "is_button_visible": False,
                }

                _DRAFTS_DIR = _ROOT / "chatbot" / "registry" / "intents" / "_drafts"
                _DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
                draft_path = _DRAFTS_DIR / f"{new_intent_id}.json"
                draft_path.write_text(
                    _json.dumps(draft, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                st.success(
                    f"Draft intent saved to `chatbot/registry/intents/_drafts/{new_intent_id}.json`. "
                    f"Run `python -m chatbot.registry.validate` after moving it to `intents/` to promote it."
                )
                st.json(draft)
    else:
        st.success("No unmatched messages — the classifier is covering all inputs.")

    st.markdown("---")

    # ── Export for Fine-Tuning ───────────────────────────────────────────────
    st.markdown("### 📤 Export Labeled Tickets for Fine-Tuning")
    st.markdown(
        "Exports human-verified tickets as a JSONL fine-tuning dataset — "
        "`(user_message, correct_intent, bot_response)` triples where a human has confirmed the label."
    )

    col_export, col_info = st.columns([1, 3])
    with col_export:
        if st.button("🔄 Generate Export", key="gen_export"):
            st.session_state["export_jsonl"] = export_labeled_jsonl(_DB_PATH)

    jsonl_content = st.session_state.get("export_jsonl", "")
    if jsonl_content:
        line_count = jsonl_content.count("\n") + 1 if jsonl_content.strip() else 0
        with col_info:
            st.info(f"{line_count} labeled example(s) ready for download.")
        st.download_button(
            label="⬇️ Download labeled_tickets.jsonl",
            data=jsonl_content.encode("utf-8"),
            file_name="labeled_tickets.jsonl",
            mime="application/jsonlines",
            key="dl_jsonl",
        )
        with st.expander("Preview first 3 lines"):
            for line in jsonl_content.split("\n")[:3]:
                st.code(line, language="json")
    elif jsonl_content == "" and "export_jsonl" in st.session_state:
        st.warning(
            "No human-verified tickets found yet. "
            "Approve ticket classifications in the Tickets tab first."
        )


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: LLM Dashboard
# ═══════════════════════════════════════════════════════════════════════════

elif selected_tab == "LLM Dashboard":
    st.markdown("### LLM Performance Dashboard")
    st.markdown("""
    ✨ **Coming soon** — advanced LLM monitoring and optimisation insights

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
    - Cost optimisation recommendations
    - Prompt effectiveness metrics
    """)

