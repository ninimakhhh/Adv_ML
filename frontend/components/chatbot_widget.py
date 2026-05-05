"""
chatbot_widget.py — Floating chat widget backed by ChatbotOrchestrator.

Architecture
------------
* A round FAB button (💬) is rendered via st.button and then repositioned to
  the viewport's bottom-right corner by a tiny JS snippet injected through
  st.components.v1.html (same-origin iframe → window.parent.document access).

* Clicking the FAB opens an @st.dialog — a first-class Streamlit modal that
  runs as its own fragment.  Widget interactions inside the dialog (button
  clicks, chat_input submissions) rerun ONLY the dialog, so it stays open and
  updates in-place without touching the rest of the page.

* All quick-action buttons, the message history, CSAT thumbs, and the text
  input are rendered INSIDE the dialog with native Streamlit widgets.  No
  widgets live outside the popup.
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
import streamlit.components.v1 as components

from chatbot.ui_adapter import (
    _messages,
    get_button_intents,
    get_or_create_session,
    reset_chat,
    send_button_action,
    send_user_message,
    submit_feedback,
)

# ---------------------------------------------------------------------------
# FAB positioning — runs once per page render
# ---------------------------------------------------------------------------

_FAB_JS = """
<script>
(function () {
  function style(el, css) {
    Object.assign(el.style, css);
  }

  function positionFAB() {
    var parentDoc = window.parent.document;

    // Find the Streamlit button whose text is exactly the chat emoji
    var allBtns = parentDoc.querySelectorAll('[data-testid="stButton"] button');
    for (var i = 0; i < allBtns.length; i++) {
      var btn = allBtns[i];
      if (btn.textContent.trim() === '💬') {   // 💬
        var wrapper = btn.closest('[data-testid="stButton"]');
        if (!wrapper) continue;

        // Position the wrapper div at the corner
        style(wrapper, {
          position:   'fixed',
          bottom:     '28px',
          right:      '28px',
          zIndex:     '99999',
          width:      'auto',
          height:     'auto',
          marginTop:  '0',
          marginBottom: '0',
        });

        // Style the button itself as a round FAB
        style(btn, {
          borderRadius:    '50%',
          width:           '62px',
          height:          '62px',
          fontSize:        '26px',
          lineHeight:      '1',
          padding:         '0',
          minHeight:       'unset',
          border:          'none',
          background:      'linear-gradient(135deg, #FF6B35, #c84b1e)',
          color:           'white',
          boxShadow:       '0 4px 18px rgba(255,107,53,0.50)',
          transition:      'transform 0.18s, box-shadow 0.18s',
          cursor:          'pointer',
        });

        btn.onmouseenter = function () {
          style(this, { transform: 'scale(1.08)', boxShadow: '0 6px 22px rgba(255,107,53,0.65)' });
        };
        btn.onmouseleave = function () {
          style(this, { transform: 'scale(1.0)',  boxShadow: '0 4px 18px rgba(255,107,53,0.50)' });
        };
      }
    }
  }

  // Run immediately and re-run whenever Streamlit mutates the DOM
  positionFAB();
  var observer = new MutationObserver(positionFAB);
  observer.observe(window.parent.document.body, { childList: true, subtree: true });
})();
</script>
"""

_DIALOG_CSS = """
<style>
/* Tighten spacing inside the chat dialog */
div[data-testid="stDialog"] div[data-testid="stVerticalBlock"] {
    gap: 0.4rem;
}
/* Quick-action buttons */
div[data-testid="stDialog"] [data-testid="stButton"] button {
    border-radius: 20px;
    font-size: 13px;
    padding: 6px 14px;
    border: 1.5px solid #FF6B35 !important;
    color: #FF6B35 !important;
    background: #fff !important;
    transition: background 0.15s, color 0.15s;
}
div[data-testid="stDialog"] [data-testid="stButton"] button:hover {
    background: #FF6B35 !important;
    color: #fff !important;
}
/* Escalation / info banners inside dialog */
div[data-testid="stDialog"] [data-testid="stAlert"] {
    font-size: 13px;
    padding: 8px 12px;
}
</style>
"""

# ---------------------------------------------------------------------------
# Dialog — the actual chat UI
# ---------------------------------------------------------------------------

@st.dialog("🤖 Oli — Store Assistant", width="small")
def _chat_dialog() -> None:
    """Full chat rendered inside Streamlit's native modal (fragment-scoped)."""
    st.markdown(_DIALOG_CSS, unsafe_allow_html=True)
    get_or_create_session()
    msgs = _messages()
    escalated = any(m.get("escalated") for m in msgs if m["role"] == "bot")

    # ── Status line ────────────────────────────────────────────────────────
    st.markdown(
        '<p style="margin:0 0 8px;color:#10B981;font-size:12px;">● Online — typically replies instantly</p>',
        unsafe_allow_html=True,
    )

    # ── Empty state: welcome + quick-action buttons ─────────────────────────
    if not msgs:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(
                "Hi! I'm **Oli**, your Olá Market assistant. "
                "How can I help you today?"
            )

        st.markdown(
            '<p style="margin:8px 0 4px;font-size:13px;color:#555;font-weight:600;">'
            "Quick actions:</p>",
            unsafe_allow_html=True,
        )

        button_intents = get_button_intents()
        # Two-column grid for quick-action buttons
        col_pairs = [button_intents[i : i + 2] for i in range(0, len(button_intents), 2)]
        for pair in col_pairs:
            cols = st.columns(len(pair))
            for col, intent in zip(cols, pair):
                with col:
                    if st.button(
                        intent["display_name"],
                        key=f"qa_{intent['intent_id']}",
                        use_container_width=True,
                    ):
                        send_button_action(intent["intent_id"])
                        # No st.rerun() — dialog fragment reruns automatically

    # ── Conversation history ────────────────────────────────────────────────
    else:
        for msg in msgs:
            role = "user" if msg["role"] == "user" else "assistant"
            avatar = None if role == "user" else "🤖"
            with st.chat_message(role, avatar=avatar):
                st.markdown(msg["content"])

            # Escalation banner
            if msg.get("escalated"):
                st.warning(
                    "⚡ A human agent has been notified and will be in touch via email.",
                    icon="⚡",
                )

            # CSAT thumbs after a resolved turn
            if msg.get("resolved") and not msg.get("csat_done"):
                mid = msg["message_id"]
                c1, c2, c3 = st.columns([1, 1, 6])
                with c1:
                    if st.button("👍", key=f"up_{mid}"):
                        submit_feedback(mid, "up")
                with c2:
                    if st.button("👎", key=f"dn_{mid}"):
                        submit_feedback(mid, "down")
                with c3:
                    st.caption("Was this helpful?")

    st.divider()

    # ── Input / post-escalation footer ─────────────────────────────────────
    if escalated:
        st.info("Conversation handed off to a human agent. We'll email you shortly.")
        if st.button("Start new conversation", use_container_width=True, key="reset_chat"):
            reset_chat()
            # Closing the dialog after reset: don't call st.rerun() — let the
            # next user-triggered open start fresh.
    else:
        user_input = st.chat_input("Type a message…", key="chat_dialog_input")
        if user_input:
            send_user_message(user_input.strip())
            # No st.rerun() — dialog fragment reruns after chat_input submit


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_chatbot_widget() -> None:
    """
    Render FAB + dialog on any storefront page.

    Call this at the end of every page render.  The FAB button is placed in
    the page flow and then teleported to the viewport corner by the JS snippet.
    """
    get_or_create_session()

    # ── Inject FAB positioning JS (zero-height iframe) ──────────────────────
    components.html(_FAB_JS, height=0, scrolling=False)

    # ── Actual Streamlit button (label must be exactly 💬 for JS to find it) ─
    if st.button("💬", key="chat_fab", help="Chat with Oli"):
        _chat_dialog()


def render_admin_chatbot_widget() -> None:
    """Render floating chatbot widget for the admin dashboard (decorative)."""
    st.markdown(
        """
        <style>
            .admin-chat-fab {
                position: fixed; bottom: 24px; right: 24px; z-index: 999;
                width: 58px; height: 58px; border-radius: 50%;
                background: #4F46E5; display: flex; align-items: center;
                justify-content: center; font-size: 26px; cursor: pointer;
                box-shadow: 0 4px 12px rgba(79,70,229,0.4);
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .admin-chat-fab:hover {
                transform: scale(1.1);
                box-shadow: 0 6px 18px rgba(79,70,229,0.55);
            }
        </style>
        <div class="admin-chat-fab"
             onclick="alert('Sandbox mode — chatbot available on the storefront.')">
          💬
        </div>
        """,
        unsafe_allow_html=True,
    )


# Keep legacy alias so existing page imports still work
def render_chatbot_placeholder() -> None:
    render_chatbot_widget()
