"""
chatbot_widget.py — Real chat panel backed by ChatbotOrchestrator.

Renders as a Streamlit sidebar-style expander anchored to the bottom-right
of the page.  Call render_chatbot_widget() at the end of every page.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRONTEND = Path(__file__).parent.parent
_ROOT = _FRONTEND.parent
for _p in (str(_ROOT), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

from chatbot.ui_adapter import (
    get_button_intents,
    get_or_create_session,
    reset_chat,
    send_button_action,
    send_user_message,
    submit_feedback,
    _messages,
)

# ---------------------------------------------------------------------------
# Floating button + panel CSS (injected once)
# ---------------------------------------------------------------------------

_CHAT_CSS = """
<style>
/* ── Floating action button ─────────────────────────────────── */
#chat-fab-anchor {
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 9999;
}
.chat-fab-btn {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: linear-gradient(135deg, #FF6B35, #e85d25);
    border: none;
    cursor: pointer;
    font-size: 26px;
    box-shadow: 0 4px 16px rgba(255,107,53,0.45);
    transition: transform 0.2s, box-shadow 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
}
.chat-fab-btn:hover {
    transform: scale(1.08);
    box-shadow: 0 6px 20px rgba(255,107,53,0.55);
}

/* ── Chat panel container ───────────────────────────────────── */
.chat-panel {
    position: fixed;
    bottom: 100px;
    right: 28px;
    width: 380px;
    max-height: 600px;
    background: #fff;
    border-radius: 18px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.18);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 9998;
    animation: slideUp 0.25s ease;
}
@keyframes slideUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ── Panel header ───────────────────────────────────────────── */
.chat-header {
    background: linear-gradient(135deg, #1A1A2E, #0F3460);
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}
.chat-avatar { font-size: 28px; }
.chat-header-info { flex: 1; }
.chat-header-name { color: #fff; font-weight: 700; font-size: 15px; }
.chat-header-status { color: #4ade80; font-size: 12px; margin-top: 2px; }
.chat-header-close {
    color: rgba(255,255,255,0.7);
    background: none;
    border: none;
    font-size: 20px;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 6px;
    transition: background 0.15s;
}
.chat-header-close:hover { background: rgba(255,255,255,0.15); color: #fff; }

/* ── Message list ───────────────────────────────────────────── */
.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-height: 380px;
}

/* ── Individual messages ────────────────────────────────────── */
.chat-msg-bot {
    display: flex;
    align-items: flex-start;
    gap: 8px;
}
.chat-msg-bot-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: linear-gradient(135deg, #FF6B35, #e85d25);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    flex-shrink: 0;
}
.chat-bubble-bot {
    background: #F5F5F5;
    color: #1a1a1a;
    padding: 10px 14px;
    border-radius: 0 14px 14px 14px;
    font-size: 13.5px;
    line-height: 1.5;
    max-width: 280px;
    word-wrap: break-word;
}
.chat-bubble-user {
    background: linear-gradient(135deg, #FF6B35, #e85d25);
    color: #fff;
    padding: 10px 14px;
    border-radius: 14px 14px 0 14px;
    font-size: 13.5px;
    line-height: 1.5;
    max-width: 280px;
    word-wrap: break-word;
    margin-left: auto;
}

/* ── Escalation banner ──────────────────────────────────────── */
.escalation-banner {
    background: #FFF3CD;
    border: 1px solid #FFD166;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 12.5px;
    color: #856404;
    margin: 4px 0;
    text-align: center;
}

/* ── CSAT thumbs ────────────────────────────────────────────── */
.csat-prompt {
    font-size: 12px;
    color: #666;
    margin-top: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* ── Quick action buttons ───────────────────────────────────── */
.quick-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 12px 16px 0;
}
.quick-btn {
    background: #fff;
    border: 1.5px solid #FF6B35;
    color: #FF6B35;
    border-radius: 20px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
    white-space: nowrap;
}
.quick-btn:hover { background: #FF6B35; color: #fff; }

/* ── Input area ─────────────────────────────────────────────── */
.chat-input-area {
    padding: 12px 16px;
    border-top: 1px solid #f0f0f0;
    flex-shrink: 0;
    background: #fff;
}
</style>
"""

# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_chatbot_widget() -> None:
    """Render the full chatbot widget (FAB + panel) on any page."""
    st.markdown(_CHAT_CSS, unsafe_allow_html=True)

    # Initialise open/close state
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    get_or_create_session()

    # ── Floating action button ──────────────────────────────────────────────
    st.markdown('<div id="chat-fab-anchor">', unsafe_allow_html=True)

    fab_label = "✕" if st.session_state.chat_open else "💬"
    if st.button(fab_label, key="chat_fab", help="Open / close chat", type="primary"):
        st.session_state.chat_open = not st.session_state.chat_open
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    if not st.session_state.chat_open:
        return

    # ── Chat panel ──────────────────────────────────────────────────────────
    with st.container():
        st.markdown("""
        <div class="chat-panel">
          <div class="chat-header">
            <div class="chat-avatar">🤖</div>
            <div class="chat-header-info">
              <div class="chat-header-name">Store Assistant</div>
              <div class="chat-header-status">● Online</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _render_panel_body()


def _render_panel_body() -> None:
    msgs = _messages()
    escalated = any(m.get("escalated") for m in msgs if m["role"] == "bot")

    # ── Message history ─────────────────────────────────────────────────────
    if msgs:
        for i, msg in enumerate(msgs):
            if msg["role"] == "user":
                st.markdown(
                    f'<div style="display:flex;justify-content:flex-end;margin:4px 0">'
                    f'<div class="chat-bubble-user">{msg["content"]}</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="chat-msg-bot">'
                    f'<div class="chat-msg-bot-avatar">🤖</div>'
                    f'<div class="chat-bubble-bot">{msg["content"]}</div></div>',
                    unsafe_allow_html=True,
                )
                # Escalation banner
                if msg.get("escalated"):
                    st.markdown(
                        '<div class="escalation-banner">'
                        '⚡ Connecting you with a human agent…</div>',
                        unsafe_allow_html=True,
                    )

                # CSAT after resolved turns
                if msg.get("resolved") and not msg.get("csat_done"):
                    mid = msg["message_id"]
                    st.markdown(
                        '<div class="csat-prompt">Was this helpful?</div>',
                        unsafe_allow_html=True,
                    )
                    c1, c2, _ = st.columns([1, 1, 6])
                    with c1:
                        if st.button("👍", key=f"up_{mid}"):
                            submit_feedback(mid, "up")
                            st.rerun()
                    with c2:
                        if st.button("👎", key=f"dn_{mid}"):
                            submit_feedback(mid, "down")
                            st.rerun()
    else:
        # Welcome message on first open
        st.markdown(
            '<div class="chat-msg-bot">'
            '<div class="chat-msg-bot-avatar">🤖</div>'
            '<div class="chat-bubble-bot">Hi! I\'m Oli, your Ola Market assistant. '
            'How can I help you today?</div></div>',
            unsafe_allow_html=True,
        )

    # ── Quick-action buttons (only when no conversation yet) ────────────────
    if not msgs:
        button_intents = get_button_intents()
        st.markdown('<div class="quick-actions">', unsafe_allow_html=True)
        cols = st.columns(len(button_intents))
        for col, intent in zip(cols, button_intents):
            with col:
                if st.button(
                    intent["display_name"],
                    key=f"qb_{intent['intent_id']}",
                    use_container_width=True,
                ):
                    send_button_action(intent["intent_id"])
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Input area ──────────────────────────────────────────────────────────
    if escalated:
        st.info("A human agent has been notified. Please wait for a response via email.", icon="ℹ️")
        if st.button("Start new conversation", key="chat_reset"):
            reset_chat()
            st.rerun()
    else:
        with st.form(key="chat_form", clear_on_submit=True):
            col_input, col_send = st.columns([5, 1])
            with col_input:
                user_input = st.text_input(
                    "Message",
                    placeholder="Type a message…",
                    label_visibility="collapsed",
                    key="chat_input_text",
                )
            with col_send:
                submitted = st.form_submit_button("➤")

        if submitted and user_input.strip():
            send_user_message(user_input.strip())
            st.rerun()


def render_admin_chatbot_widget() -> None:
    """Render floating chatbot widget for admin dashboard (unchanged)."""
    widget_html = """
    <style>
        .admin-chatbot-widget { position:fixed;bottom:24px;right:24px;z-index:999; }
        .admin-chatbot-button {
            width:60px;height:60px;border-radius:50%;background-color:#4F46E5;
            border:none;cursor:pointer;display:flex;align-items:center;
            justify-content:center;font-size:28px;
            box-shadow:0 4px 12px rgba(79,70,229,0.4);transition:all 0.3s ease;
        }
        .admin-chatbot-button:hover {
            background-color:#4338CA;box-shadow:0 6px 16px rgba(79,70,229,0.5);
            transform:scale(1.1);
        }
    </style>
    <div class="admin-chatbot-widget">
        <button class="admin-chatbot-button"
            onclick="alert('Test Mode - Coming Soon');" title="Chat with AI">💬</button>
    </div>
    """
    st.markdown(widget_html, unsafe_allow_html=True)


# Keep old name as alias so existing imports don't break
def render_chatbot_placeholder() -> None:
    render_chatbot_widget()
